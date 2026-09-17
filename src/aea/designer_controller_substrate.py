"""Private production accounting adapter for the explicit v3 selector.

Construction installs accounting only; it neither runs the method nor starts paid work.
The caller must use a local gitignored run directory and separately authorize execution.
Historical runners, models, retries, ledger accounting and the R5 judge are unchanged.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace

from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.core.config import LLMConfig
from aea.designer_controller_confirmation import candidate_hash, validate_traces
from aea.errors import ConfigError
from aea.llm.attribution import attributed
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.physical_audit import AuditedTransport, physical_summary
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.privilege_judge import JudgeConfig
from aea.privilege_witness import WitnessCheckingPrivilegeJudge
from aea.settings import load_settings
from aea.substrate import AeaSubstrate


def physical_closed(summary: Mapping[str, Any]) -> None:
    """Uncertain charges remain estimates; unresolved/corrupt accounting stops execution."""
    if any(summary[key] for key in ("inflight", "invalid_usage", "incomplete_journal_lines")):
        raise ConfigError("Physical accounting has unresolved or corrupt attempts")


def _append_private(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream, fcntl.LOCK_UN)


class DesignerControllerSubstrate(AeaSubstrate):
    """Retain logical call/rollout ledgers and independently audit physical attempts.

    One adapter owns one run directory and its fresh episode-ID set. Operations on that
    adapter are serialized; the released runner still parallelizes episodes within a batch.
    There are no experiment globals, task lists, retry loops or automatic execution here.
    """

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
        judge_pricing_path: Path = Path("configs/privilege_judge_pricing.yaml"),
    ) -> None:
        if aea_config.method_version != "llm_v3_designer_controller":
            raise ConfigError("The audited designer/controller adapter requires the v3 selector")
        self._audit_lock = threading.RLock()
        self._seen_episodes: set[str] = set()
        self._judge_pricing_path = judge_pricing_path
        super().__init__(
            corpus_yaml=corpus_yaml,
            run_dir=run_dir,
            run_id=run_id,
            policy_llm=policy_llm,
            designer_llm=designer_llm,
            aea_config=aea_config,
            stage_config_path=stage_config_path,
            pricing_path=pricing_path,
            skills_block=skills_block,
            rollout_concurrency=rollout_concurrency,
            subprocess_timeout_s=subprocess_timeout_s,
        )
        self.policy_spec_kwargs["client_factory"] = "aea.llm.physical_audit:AuditedPolicyClient"
        self.policy_spec_kwargs["client_kwargs"].update(
            audit_dir=str(run_dir / "physical"), run_id=run_id
        )
        if self._designer is not None:
            assert designer_llm is not None
            self._audit_client(self._designer, designer_llm, pricing_path)

    def _audit_client(
        self, client: OpenAICompatibleClient, config: LLMConfig, pricing_path: Path
    ) -> None:
        transport = client._transport
        if isinstance(transport, AuditedTransport):
            if (
                transport.audit_dir.resolve() != (self.run_dir / "physical").resolve()
                or transport.config != config
                or transport.run_id != self.run_id
                or transport.pricing_sha256 != hashlib.sha256(pricing_path.read_bytes()).hexdigest()
            ):
                raise ConfigError(
                    "Existing physical audit wrapper has different experiment binding"
                )
            return
        client._transport = AuditedTransport(
            transport,
            self.run_dir / "physical",
            config=config,
            pricing_path=pricing_path,
            run_id=self.run_id,
        )

    def _logged_complete(
        self, client: OpenAICompatibleClient, label: str
    ) -> Callable[[ChatRequest], ChatResponse]:
        def complete(request: ChatRequest) -> ChatResponse:
            with self._audit_lock:
                directory = self.run_dir / "raw" / label
                _append_private(directory / "requests.jsonl", request.model_dump(mode="json"))
                with attributed(request.attribution, request.seed):
                    response = client.complete(request)
                _append_private(directory / "responses.jsonl", response.model_dump(mode="json"))
                self.physical_accounting()
                return response

        return complete

    def designer(self) -> Callable[[ChatRequest], ChatResponse] | None:
        if self._designer is None:
            return None
        return self._logged_complete(self._designer, "designer")

    def privilege_judge(self, attribution: Attribution) -> WitnessCheckingPrivilegeJudge:
        with self._audit_lock:
            config = JudgeConfig()
            if self._judge_client is None:
                llm = config.llm_config()
                self._judge_client = OpenAICompatibleClient(
                    config=llm,
                    transport=make_openai_transport(
                        api_key=load_settings().require(llm.api_key_env.lower()),
                        base_url=llm.base_url,
                        timeout_s=llm.timeout_s,
                    ),
                    ledger=self.ledger,
                    pricing=load_pricing(self._judge_pricing_path),
                )
            self._audit_client(self._judge_client, config.llm_config(), self._judge_pricing_path)
            return WitnessCheckingPrivilegeJudge(
                self._logged_complete(self._judge_client, "judge"),
                config=config,
                attribution=attribution,
            )

    def physical_accounting(self, *, require_closed: bool = True) -> dict[str, Any]:
        summary = physical_summary(self.run_dir / "physical")
        if require_closed:
            physical_closed(summary)
        return summary

    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        with self._audit_lock:
            if attribution.task_id != task.task_id or n < 1:
                raise ConfigError("Policy batch requires explicit matching task identity and size")
            expected_candidate = candidate.model_copy(deep=True)
            expected_sha256 = candidate_hash(expected_candidate)
            batch = {
                "batch_id": uuid.uuid4().hex,
                "task_id": task.task_id,
                "seed": task.seed,
                "phase": attribution.phase,
                "budget": attribution.budget,
                "arm": attribution.arm,
                "n": n,
                "candidate_sha256": expected_sha256,
            }
            journal = self.run_dir / "physical_batches.jsonl"
            _append_private(journal, {**batch, "status": "started", "ts": time.time()})
            try:
                traces = super().rollouts(
                    task, candidate, n, attribution=attribution, reset_options=reset_options
                )
                for trace in traces:
                    _append_private(
                        self.run_dir / "all_physical_traces.jsonl",
                        {**batch, "trace": trace.model_dump(mode="json")},
                    )
                if any(
                    marker in (trace.error or "")
                    for trace in traces
                    for marker in ("provider_mismatch", "pricing_mismatch")
                ):
                    raise ConfigError("Learner provenance or pricing guard failed")
                if candidate_hash(candidate) != expected_sha256:
                    raise ConfigError("Dispatched candidate mutated during policy batch")
                validate_traces(traces, n, task, expected_candidate, self._seen_episodes)
                self.physical_accounting()
            except BaseException as exc:
                _append_private(
                    journal,
                    {
                        **batch,
                        "status": "failed",
                        "ts": time.time(),
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            _append_private(
                journal,
                {
                    **batch,
                    "status": "returned",
                    "ts": time.time(),
                    "returned": len(traces),
                    "successes": sum(bool(trace.success) for trace in traces),
                    "errors": sum(bool(trace.error) for trace in traces),
                },
            )
            return traces
