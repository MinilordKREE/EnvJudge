"""Phase C: LLM-free integration on the real ALFWorld bridge (docs/spec/AEA_v2.md section 12)."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Action, Candidate, Observation, Step, Trace
from envharness.orchestration.runner import EnvSpec, EpisodeSpec, InProcessRunner, PolicySpec
from envharness.orchestration.storage import TraceStore

from aea.certs import (
    DEFAULT_RESET_OPTIONS,
    Session,
    open_session,
    replay_actions,
    run_expert,
)
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.io import read_corpus
from aea.knobs import FooterMask, HorizonSqueeze, KnobContext, footer_masked
from aea.llm.types import Attribution
from aea.stage import compile_prefix, fidelity_check, stage_candidate, stage_reset_options

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
CFG100 = ROOT / "configs" / "alfworld_config_100.yaml"
FIXTURES = ROOT / "tests" / "fixtures"
RO100 = stage_reset_options(DEFAULT_RESET_OPTIONS, CFG100)


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- C.1 fidelity
def test_config100_route_gives_12_vs_62_policy_steps() -> None:
    fx = _load("stage8.json")
    cand = stage_candidate(
        fx["compiled_actions"]
    )  # 38 actions incl. the trailing look (pilot check)
    counts = {}
    for label, opts in (("default", DEFAULT_RESET_OPTIONS), ("config_100", RO100)):
        sess = open_session(cand, fx["task_id"], opts)
        n = 0
        try:
            while not sess.done and n < 120:
                sess.step_text("look")
                n += 1
        finally:
            sess.close()
        counts[label] = n
    assert counts == fx["expected_policy_steps"]


def test_compiled_prefix_replay_reproduces_archived_observation() -> None:
    fx = _load("failed_prefixes.json")
    checked = 0
    for traj in fx["trajectories"]:
        steps = traj["steps"]
        t = min(12, len(steps))
        task_id = int(traj["task_id"])

        def opener(c: Candidate | None, ro: dict[str, Any] | None, t_id: int = task_id) -> Session:
            return open_session(c, t_id, ro)

        prefix = [s["action"] for s in steps[:t]]
        compiled = compile_prefix(opener, prefix, RO100)
        trace = Trace(
            episode_id=traj["episode_id"],
            iteration_id="fx",
            task_id="lbl",
            candidate=Candidate(),
            steps=[
                Step(
                    raw_action=Action(name="do", kwargs={"text": s["action"]}),
                    filtered_observation=Observation(text=s["obs"]),
                )
                for s in steps[:t]
            ],
        )
        assert fidelity_check(opener, trace, t, compiled, RO100), task_id
        checked += 1
    assert checked == 3


# ----------------------------------------------------------------------------- C.2 FooterMask
def _run_capture(
    candidate: Candidate, task_seed: int, capture: Path, steps: int = 6
) -> list[list[dict[str, str]]]:
    os.environ["AEA_CAPTURE_PATH"] = str(capture)
    spec = EpisodeSpec(
        env=EnvSpec(
            import_path="envharness.bridges.alfworld:AlfworldEnv",
            reset_options=dict(DEFAULT_RESET_OPTIONS),
            reset_seed=task_seed,
        ),
        candidate=candidate,
        policy=PolicySpec(
            client_factory="tests.integration.capture_client:CaptureClient",
            client_kwargs={"capture_path": str(capture)},
            action_format="think_action",
            task_prompt="You are an agent.",
            max_history=200,
            temperature=0.0,
        ),
        iteration_id="capture",
        task_id="alfworld-corpus-ours-release",
        max_steps=steps,
    )
    trace = InProcessRunner().run(spec)
    assert not trace.error, trace.error
    return [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]


def test_footer_mask_final_prompt_snapshot(tmp_path: Path) -> None:
    cand = FooterMask().make(1.0, KnobContext(task_id="0"))
    assert cand is not None
    calls = _run_capture(cand, 0, tmp_path / "d1.jsonl")
    assert calls
    for messages in calls:
        for m in messages:
            if m["role"] in ("user", "tool"):
                assert (
                    "Admissible commands" not in m["content"]
                    and "Admissible actions" not in m["content"]
                )
    (tmp_path / "prompt_snapshot_d1.json").write_text(
        json.dumps(calls[-1], indent=1), encoding="utf-8"
    )


def test_footer_mask_nesting_across_processes() -> None:
    script = (
        "import json; from aea.knobs import footer_masked; "
        "print(json.dumps([s for s in range(100) if footer_masked('0', s, 0.5)]))"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    other = set(
        json.loads(
            subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, check=True, env=env
            ).stdout
        )
    )
    here_half = {s for s in range(100) if footer_masked("0", s, 0.5)}
    here_full = {s for s in range(100) if footer_masked("0", s, 1.0)}
    assert other == here_half and here_half <= here_full == set(range(100))


# ----------------------------------------------------------------------------- C.3 HorizonSqueeze
def test_horizon_squeeze_boundary_on_alfworld() -> None:
    cfg = AEAConfig()
    plan = None
    for _ in range(cfg.expert_attempts):
        sess = open_session(None, 1, DEFAULT_RESET_OPTIONS)
        try:
            r = run_expert(sess, max_steps=cfg.expert_max_steps)
        finally:
            sess.close()
        if r.ok and (plan is None or len(r.actions) < len(plan)):
            plan = list(r.actions)
    assert plan, "expert must solve task 1"
    m = len(plan)
    cand = HorizonSqueeze().make(1.0, KnobContext(task_id="1", success_lengths=(m,)))
    assert cand is not None and f"M = {m}" in cand.rules_code
    sess = open_session(cand, 1, DEFAULT_RESET_OPTIONS)
    try:
        r = replay_actions(sess, plan)
        assert r.ok and sess.won
    finally:
        sess.close()
    sess = open_session(cand, 1, DEFAULT_RESET_OPTIONS)
    try:
        last: dict[str, Any] = {}
        for a in ["look", *plan]:
            if sess.done:
                break
            last = sess.step_text(a)
        assert last["truncated"] and not last["terminated"] and not sess.won
    finally:
        sess.close()


# ----------------------------------------------------------------------------- C.4 / C.5 substrates
def _trace_from_session(
    sess: Session, actions: list[str], obs: list[str], task: TaskRef, candidate: Candidate
) -> Trace:
    steps = []
    for a, o in zip(actions, obs, strict=True):
        act = Action(name="do", kwargs={"text": a})
        ob = Observation(text=o)
        steps.append(
            Step(
                raw_action=act,
                filtered_action=act,
                raw_observation=ob,
                filtered_observation=ob,
                policy_raw_response=f"<action>{a}</action>",
            )
        )
    return Trace(
        episode_id=uuid.uuid4().hex[:10],
        iteration_id="int",
        task_id=task.label,
        candidate=candidate,
        rollout_seed=task.seed,
        steps=steps,
        success=sess.won,
        duration_steps=len(steps),
        kind="exploration",
        policy_model_id="expert:handcoded",
    )


class ExpertSubstrate:
    """The closed-loop expert as the policy (saturated path); optionally noisy."""

    def __init__(self, skip_every: int = 0) -> None:
        self.skip_every = skip_every
        self.calls: list[tuple[str, str, int]] = []

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
        self.calls.append((task.task_id, attribution.phase, n))
        out = []
        for _ in range(n):
            sess = open_session(
                candidate, task.seed, {**DEFAULT_RESET_OPTIONS, **(reset_options or {})}
            )
            actions: list[str] = []
            obs: list[str] = []
            try:
                for i in range(50):
                    if sess.done or sess.won:
                        break
                    nxt = sess.expert_next() or "look"
                    if self.skip_every and i % self.skip_every == 1:
                        nxt = "look"
                    r = sess.step_text(nxt)
                    actions.append(nxt)
                    obs.append(str(r["obs"]))
                out.append(_trace_from_session(sess, actions, obs, task, candidate))
            finally:
                sess.close()
        return out

    def open_session(
        self, task: TaskRef, candidate: Candidate | None, reset_options: dict[str, Any] | None
    ) -> Session:
        return open_session(
            candidate, task.seed, {**DEFAULT_RESET_OPTIONS, **(reset_options or {})}
        )

    def game_file(self, task: TaskRef) -> str:
        sess = self.open_session(task, None, None)
        try:
            return sess.gamefile
        finally:
            sess.close()

    def stage_reset_options(self, task: TaskRef) -> dict[str, Any]:
        return RO100

    def designer(self) -> Any:
        return None

    def designer_model(self) -> str:
        return ""

    def setup_builder(self, task: TaskRef) -> Any:
        from aea.displacement import setup_builder

        return setup_builder(lambda c: self.open_session(task, c, None))


class PrefixThenRandomSubstrate(ExpertSubstrate):
    """A zero policy: an archived failed prefix, then pseudo-random non-expert actions."""

    def __init__(self, prefix: list[str]) -> None:
        super().__init__()
        self.prefix = prefix

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
        import random

        self.calls.append((task.task_id, attribution.phase, n))
        rng = random.Random(len(self.calls))
        out = []
        for _ in range(n):
            sess = open_session(
                candidate, task.seed, {**DEFAULT_RESET_OPTIONS, **(reset_options or {})}
            )
            actions: list[str] = []
            obs: list[str] = []
            try:
                plan = list(self.prefix) if not candidate.in_env_actions else []
                for _i in range(50):
                    if sess.done or sess.won:
                        break
                    if plan:
                        nxt = plan.pop(0)
                    else:  # navigation only: the task cannot be solved without manipulation
                        choices = [
                            a
                            for a in sess.admissible()
                            if a.startswith("go to ") or a in ("look", "inventory")
                        ]
                        nxt = rng.choice(choices or ["look"])
                    r = sess.step_text(nxt)
                    actions.append(nxt)
                    obs.append(str(r["obs"]))
                out.append(_trace_from_session(sess, actions, obs, task, candidate))
            finally:
                sess.close()
        return out


def _induce_reads(run_dir: Path) -> None:
    """The released induction helpers read our traces and corpus without an LLM."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "induce_pair", ROOT / "third_party" / "envharness" / "scripts" / "induce_pair.py"
    )
    assert spec and spec.loader
    sys.path.insert(0, str(ROOT / "third_party" / "envharness"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    traces = [t.model_dump() for t in TraceStore(run_dir / "traces.jsonl").all()]
    succ, fail = mod._pick_pair(traces)
    assert succ is not None or fail is not None
    from envharness.reasoning_bank.induce import format_trajectory

    text = format_trajectory((succ or fail)["steps"])
    assert "Observation:" in text


def test_saturated_path_with_expert_policy(tmp_path: Path) -> None:
    sub = ExpertSubstrate()
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "int-sat", arm="A", use_designer=False)
    out = ctrl.run([TaskRef("1", 1)])[0]
    assert out.regime == "saturated" and out.status in (
        "frozen_no_leverage",
        "accepted_knob",
        "exhausted",
    )
    events = read_trace(tmp_path / "run" / "events.jsonl")
    kinds = [e.kind for e in events]
    assert "estimate" in kinds and "dose_search" in kinds and kinds[-1] == "task_done"
    assert out.n_search <= 30
    assert (tmp_path / "run" / "traces.jsonl").exists()
    _induce_reads(tmp_path / "run")
    if out.status == "accepted_knob":
        entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
        assert entry.aea.kind == "knob" and entry.game_file.endswith("game.tw-pddl")


def test_zero_path_with_prefix_then_random_policy(tmp_path: Path) -> None:
    fx = _load("failed_prefixes.json")
    traj = fx["trajectories"][0]
    sub = PrefixThenRandomSubstrate([s["action"] for s in traj["steps"][:8]])
    ctrl = Controller(
        AEAConfig(),
        sub,
        tmp_path / "run",
        "int-zero",
        arm="A",
        use_designer=False,
        with_handoff=True,
    )
    out = ctrl.run([TaskRef(str(traj["task_id"]), traj["task_id"])])[0]
    assert out.regime == "zero" and out.status in ("unresolved", "accepted_stage")
    events = read_trace(tmp_path / "run" / "events.jsonl")
    stage_ev = next(e for e in events if e.kind == "stage_candidates")
    assert stage_ev.payload["certified"], "compiled Setups must certify on the 100-config"
    assert next(e for e in events if e.kind == "probe").payload["profile"]
    assert out.n_search <= 30
    if out.status == "accepted_stage":
        entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
        assert entry.aea.kind == "stage" and entry.stage_budget == 100 and entry.in_env_actions
        assert entry.to_candidate().in_env_actions[-1].kwargs["text"] == "look"
    else:
        assert (tmp_path / "run" / "handoff.jsonl").exists()
    _induce_reads(tmp_path / "run")


def test_rl_corpus_loader_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("ray")
    pytest.importorskip("gymnasium")
    sys.path.insert(0, str(ROOT / "third_party" / "envharness" / "rl"))
    envs = importlib.import_module("envharness_rl.alfworld.envs")
    EnvharnessAlfworldWorker = envs.EnvharnessAlfworldWorker  # noqa: N806

    from aea.io import AeaMeta, entry_from_candidate, write_corpus_entry

    path = tmp_path / "corpus.jsonl"
    write_corpus_entry(
        path,
        entry_from_candidate(
            "json_2.1.1/train/x/game.tw-pddl",
            Candidate(in_env_actions=[Action(name="do", kwargs={"text": "look"})]),
            AeaMeta(kind="stage", task_id="1", seed=1, stage_budget=100),
        ),
    )
    worker = EnvharnessAlfworldWorker.__new__(EnvharnessAlfworldWorker)
    worker._corpus = {}
    worker._load_corpus(str(path))
    assert next(iter(worker._corpus.values()))["in_env_actions"] == [
        {"name": "do", "kwargs": {"text": "look"}}
    ]


# --------------------------------------------------------------------------- C.6 budget invariants
def test_budget_invariants_hold(tmp_path: Path) -> None:
    sub = ExpertSubstrate(skip_every=3)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "int-budget", arm="A", use_designer=False)
    outcomes = ctrl.run([TaskRef("1", 1), TaskRef("2", 2)])
    traces = TraceStore(tmp_path / "run" / "traces.jsonl").all()
    assert len(traces) == sum(o.n_search for o in outcomes) == sum(n for _, _, n in sub.calls)
    assert all(o.n_search <= 30 for o in outcomes)
    rows = (tmp_path / "run" / "accounting.csv").read_text(encoding="utf-8").splitlines()[1:]
    by_task: dict[str, int] = {}
    for row in rows:
        task_id, _round, budget, _phase, n = row.split(",")[:5]
        if budget == "search":
            by_task[task_id] = by_task.get(task_id, 0) + int(n)
    assert by_task == {o.task.task_id: o.n_search for o in outcomes}
    events = read_trace(tmp_path / "run" / "events.jsonl")
    assert not [
        e for e in events if e.kind == "rollouts" and e.payload["phase"] == "confirm"
    ]  # confirm never runs here


# --------------------------------------------------------------------------- 0a.1 Displacement
def test_displacement_replays_the_pilot_seeds() -> None:
    """docs/pilots/e1pilot/LOG.md (F_S0 validated on seeds 7, 9, 2, 0): k=1 feasible on all four;
    k=2/3 infeasible on 7 (no closable receptacle) and 2 (only the goal fridge is compatible);
    k=2 and k=3 feasible on 0."""
    from aea.displacement import build, discover

    expected = {
        7: {1: True, 2: False, 3: False},
        9: {1: True},
        2: {1: True, 2: False, 3: False},
        0: {1: True, 2: True, 3: True},
    }
    for seed, want in expected.items():

        def opener(c: Candidate | None, s: int = seed) -> Session:
            return open_session(c, s, DEFAULT_RESET_OPTIONS)

        info = discover(opener)
        assert info is not None, seed
        for k, feasible in want.items():
            actions, status = build(opener, info, k)
            assert (actions is not None) == feasible, (seed, k, status)
            if actions is not None:
                assert actions[-1] == "look" and any(a.startswith("move ") for a in actions)
                sess = opener(
                    Candidate(
                        in_env_actions=[Action(name="do", kwargs={"text": a}) for a in actions]
                    )
                )
                try:
                    assert (
                        not sess.won and not sess.done
                    )  # a displacement never pre-solves the task
                finally:
                    sess.close()


# --------------------------------------------------------------------------- 0a.2 eval hook
def test_eval_hook_on_one_released_eval_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One released eval episode with a scripted litellm beneath the hook (LLM-free): the released
    code path runs unchanged, the hook routes and writes `eval` ledger rows, the guard passes."""
    import importlib
    from types import SimpleNamespace

    import litellm
    import yaml

    from aea.core.config import LLMConfig
    from aea.evalhook import EvalHook, check_guard, install
    from aea.llm.ledger import Ledger, read_ledger
    from aea.llm.pricing import load_pricing

    sys.path.insert(0, str(ROOT / "third_party" / "envharness" / "experiments" / "alfworld"))
    sys.path.insert(0, str(ROOT / "third_party" / "envharness"))
    rbe = importlib.import_module("reasoning_bank_eval")
    cfg = yaml.safe_load(
        (
            ROOT
            / "third_party"
            / "envharness"
            / "experiments"
            / "alfworld"
            / "reasoning_bank_eval.yaml"
        ).read_text()
    )
    cfg["model"]["name"] = "openai/qwen/qwen3-8b"
    cfg["policy"]["max_steps"] = 3
    usd = (300 * 0.117 + 8 * 0.455) / 1e6
    seen: list[dict[str, Any]] = []

    def scripted(**kwargs: Any) -> Any:
        seen.append(kwargs)
        usage = SimpleNamespace(
            prompt_tokens=300,
            completion_tokens=8,
            prompt_tokens_details=None,
            completion_tokens_details=None,
            cost=usd,
        )
        return SimpleNamespace(
            usage=usage,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="<action>look</action>"), finish_reason="stop"
                )
            ],
            model="qwen/qwen3-8b",
            provider="Alibaba",
            id="x",
        )

    monkeypatch.setattr(litellm, "completion", scripted)
    monkeypatch.setenv("OPENAI_API_KEY", "not-used")
    hook = EvalHook(
        config=LLMConfig(),
        ledger=Ledger(tmp_path / "ledger.jsonl", "eval-int"),
        pricing=load_pricing(ROOT / "configs" / "pricing.yaml"),
        run_dir=tmp_path,
        api_key="sk-test",
    )
    original = install(hook)
    try:
        rec = rbe.run_episode(cfg=cfg, bank=None, seed=0, split="train", gemini_api_key=None)
    finally:
        litellm.completion = original
    assert rec["error"] == "" and rec["duration_steps"] == 3
    assert len(seen) == 3 and seen[0]["api_base"] == "https://openrouter.ai/api/v1"
    assert seen[0]["extra_body"]["provider"] == {"order": ["alibaba"], "allow_fallbacks": False}
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert len(rows) == 3 and {r.budget for r in rows} == {"eval"} and check_guard(tmp_path) is None
