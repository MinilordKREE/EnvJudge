"""The production Substrate: the released runner, bridge sessions and the aea designer client.

Wraps (never edits) third_party/envharness: ``EnvSpec`` / ``PolicySpec`` built the way
``scripts/run_harness.py:173-236`` builds them from a corpus-style YAML (``env``, ``policy``
blocks), episodes run through :class:`aea.runner.AeaSubprocessRunner` (the released
``SubprocessRunner`` with attribution in the child's environment), sessions through
:func:`aea.certs.open_session` (bridge reused per ``config_path``). Policy calls are ledgered per
call by :class:`aea.llm.envharness_client.AeaLLMClient` in the worker; one ``rollout`` row per
episode is written here so the search budget can be audited against the ledger (spec section 0).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from envharness.core.types import Candidate, Trace
from envharness.orchestration.runner import PolicySpec

from aea.certs import Session, open_session
from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.core.config import LLMConfig
from aea.io import relative_game_file
from aea.llm.attribution import attributed
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.pricing import CostBreakdown, PricingTable, load_pricing
from aea.llm.types import Attribution, ChatRequest, ChatResponse, Usage
from aea.policy_skills import inject
from aea.runner import AeaSubprocessRunner, dispatch, episode_spec, ledger_path_for_process
from aea.settings import load_settings

HINT_PREAMBLE = "A reference solution for THIS task exists; its action sequence is: {plan}. Use it."


class AeaSubstrate:
    def __init__(
        self,
        *,
        corpus_yaml: Path,
        run_dir: Path,
        run_id: str,
        policy_llm: LLMConfig,
        designer_llm: LLMConfig | None,
        aea_config: AEAConfig,
        stage_config_path: Path,
        pricing_path: Path = Path("configs/pricing.yaml"),
        skills_block: str = "",
        rollout_concurrency: int = 4,
        subprocess_timeout_s: float = 600.0,
    ) -> None:
        cfg = yaml.safe_load(corpus_yaml.read_text(encoding="utf-8"))
        self.env_import = str(cfg["env"]["import_path"])
        self.reset_options: dict[str, Any] = dict(cfg["env"].get("reset_options") or {})
        policy = cfg["policy"]
        self.task_prompt = inject(
            str(policy.get("task_description") or cfg["orchestrator"]["task_description"]),
            skills_block,
        )
        self.policy_spec_kwargs: dict[str, Any] = {
            "client_factory": "aea.llm.envharness_client:AeaLLMClient",
            "client_kwargs": {
                "llm": policy_llm.model_dump(mode="json"),
                "ledger_dir": str(run_dir),
                "pricing_path": str(pricing_path),
            },
            "action_format": policy.get("action_format", "think_action"),
            "max_history": int(policy.get("max_history", 200)),
            "temperature": float(policy.get("temperature", 0.5)),
        }
        self.max_steps = int(
            cfg["orchestrator"].get("max_episode_steps", aea_config.policy_max_steps)
        )
        self.run_dir = run_dir
        self.run_id = run_id
        self.runner = AeaSubprocessRunner(
            run_id, timeout=subprocess_timeout_s, subprocess_log_dir=run_dir / "subprocess_logs"
        )
        self.concurrency = rollout_concurrency
        self.stage_config_path = stage_config_path
        self.pricing: PricingTable = load_pricing(pricing_path)
        self.ledger = Ledger(ledger_path_for_process(run_dir), run_id)
        self._designer: OpenAICompatibleClient | None = None
        self._designer_model = designer_llm.model if designer_llm else ""
        if designer_llm is not None:
            key = load_settings().require(designer_llm.api_key_env.lower())
            self._designer = OpenAICompatibleClient(
                config=designer_llm,
                transport=make_openai_transport(
                    api_key=key, base_url=designer_llm.base_url, timeout_s=designer_llm.timeout_s
                ),
                ledger=self.ledger,
                pricing=self.pricing,
            )
        self._gamefiles: dict[str, str] = {}

    # -- Substrate protocol ---------------------------------------------------------
    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
        hint: Sequence[str] | None = None,
    ) -> list[Trace]:
        prompt = self.task_prompt
        if hint:
            prompt = f"{prompt.rstrip()}\n\n{HINT_PREAMBLE.format(plan=', '.join(hint))}\n"
        policy = PolicySpec(task_prompt=prompt, **self.policy_spec_kwargs)
        opts = {**self.reset_options, **(reset_options or {})}
        specs = [
            episode_spec(
                import_path=self.env_import,
                reset_options=opts,
                task_seed=task.seed,
                candidate=candidate,
                policy=policy,
                iteration_id=f"{attribution.phase}-{task.task_id}-{i}",
                task_label=task.label,
                max_steps=self.max_steps,
            )
            for i in range(n)
        ]
        traces = dispatch(
            self.runner.run,
            specs,
            attribution=attribution,
            seed=task.seed,
            concurrency=self.concurrency,
        )
        for trace in traces:
            self.ledger.record_rollout(
                attribution=attribution,
                seed=task.seed,
                model=self.policy_spec_kwargs["client_kwargs"]["llm"]["model"],
                rollout_uid=trace.episode_id,
                usage=Usage(prompt_tokens=0, completion_tokens=0),
                cost=CostBreakdown(
                    usd=0.0, tier="flat", pricing_version="rollout-row; cost on call rows"
                ),
                steps=trace.duration_steps,
                success=bool(trace.success),
            )
        return traces

    def open_session(
        self, task: TaskRef, candidate: Candidate | None, reset_options: dict[str, Any] | None
    ) -> Session:
        opts = {**self.reset_options, **(reset_options or {})}
        sess = open_session(candidate, task.seed, opts)
        self._gamefiles.setdefault(task.task_id, relative_game_file(sess.gamefile))
        return sess

    def game_file(self, task: TaskRef) -> str:
        if task.task_id not in self._gamefiles:
            sess = self.open_session(task, None, None)
            sess.close()
        return self._gamefiles[task.task_id]

    def stage_reset_options(self, task: TaskRef) -> dict[str, Any]:
        return {**self.reset_options, "config_path": str(self.stage_config_path)}

    def designer(self) -> Callable[[ChatRequest], ChatResponse] | None:
        if self._designer is None:
            return None
        client = self._designer

        def complete(request: ChatRequest) -> ChatResponse:
            with attributed(request.attribution, request.seed):
                return client.complete(request)

        return complete

    def designer_model(self) -> str:
        return self._designer_model

    def setup_builder(self, task: TaskRef) -> Callable[[float], list[str] | None] | None:
        from aea.displacement import setup_builder

        return setup_builder(lambda c: self.open_session(task, c, None))


def now_utc() -> datetime:
    return datetime.now(UTC)
