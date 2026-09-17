"""Full AEA integration boundaries, with synthetic worlds and scripted model replies."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

import aea.controller as module
import aea.low_optimizer as optimizer_module
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.designer import serialize_low
from aea.errors import ConfigError
from aea.families import LeverageTable, ProposedFamily
from aea.io import read_corpus
from aea.llm.types import Attribution
from aea.llm_privilege_low import LLMLowPrivilegeScreen
from aea.low_optimizer import LowEnvironmentOptimizer
from aea.privilege_judge import LLMPrivilegeJudge
from aea.privilege_witness import WitnessCheckingPrivilegeJudge
from aea.substrate import AeaSubstrate, reference_provider
from aea.witness import Solvable
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.unit.test_assistive_rules import HINT, DoseSubstrate, _reply
from tests.unit.test_iterative_low import REF, _body, _replies
from tests.unit.test_llm_v1 import CASE_FLIP, HIGH_OK, _trace
from tests.unit.test_privilege_judge import decision_args, judge_response

CONFIG = AEAConfig(method_version="llm_v2_integrated")
TASK = TaskRef("9", 9)


class IntegrationSubstrate(DoseSubstrate):
    def __init__(
        self, baseline: list[bool], table: dict[tuple[str, float], list[bool]], reply: Any
    ):
        super().__init__(table, reply)
        self.baseline = baseline
        self.baseline_index = 0
        self.ids = count()

    def rollouts(self, task: TaskRef, candidate: Candidate, n: int, **kw: Any) -> list[Trace]:
        if kw["attribution"].phase == "estimate":
            assert candidate.rules_code in (None, "") and not candidate.in_env_actions
            self.calls.append((task.task_id, "estimate", n))
            traces = [
                _trace(
                    self.baseline[(self.baseline_index + i) % len(self.baseline)],
                    candidate=candidate,
                )
                for i in range(n)
            ]
            self.baseline_index += n
        else:
            traces = super().rollouts(task, candidate, n, **kw)
        return [
            trace.model_copy(update={"episode_id": f"synthetic-{next(self.ids)}"})
            for trace in traces
        ]


def judge(verdict: str = "PASS") -> LLMPrivilegeJudge:
    return LLMPrivilegeJudge(lambda request: judge_response(request, decision_args(verdict)))


def controller(tmp_path: Path, sub: IntegrationSubstrate, **kwargs: Any) -> Controller:
    return Controller(CONFIG, sub, tmp_path / "run", "integration", **kwargs)


def events(tmp_path: Path) -> list[Any]:
    return read_trace(tmp_path / "run/events.jsonl")


def high_reply() -> Any:
    name, args = copy.deepcopy(HIGH_OK)
    args["families"].append(
        {**args["families"][0], "name": "second", "rules_code": CASE_FLIP + "\n# second family\n"}
    )
    return name, args


def forbidden(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("MID must not call designer, judge or reference")


@pytest.mark.parametrize("successes", [3, 13])
def test_mid_uses_posterior_not_raw_fraction(tmp_path: Path, successes: int) -> None:
    pattern = [i in (0, 6, 12) for i in range(16)]
    if successes == 13:
        pattern = [not value for value in pattern]
    sub = IntegrationSubstrate(pattern, {}, forbidden)
    ctrl = controller(tmp_path, sub, reference=forbidden)
    result = ctrl.run([TASK])[0]
    assert result.outcome == "kept" and result.regime == "band"
    assert result.p_hat == successes / 16
    assert result.n_search == result.detail["baseline_rollouts"] == 16
    assert result.detail["adaptation_rollouts"] == ctrl.budget.account("9").spent == 0
    evidence = next(e.payload for e in events(tmp_path) if e.kind == "measurement_evidence")
    assert evidence["successes"] == successes and evidence["stop_reason"] == "k_max"
    assert len(set(evidence["episode_ids"])) == 16
    entry = read_corpus(tmp_path / "run/corpus.jsonl")[0]
    assert not entry.rules_code and not entry.in_env_actions and entry.aea.n_search == 16
    assert not (tmp_path / "run/designer_calls.jsonl").exists()
    assert not (tmp_path / "run/privileged_references.jsonl").exists()


def test_low_three_candidates_keep_full_adaptation_envelope(tmp_path: Path) -> None:
    sub = IntegrationSubstrate(
        [False],
        {
            ("hint_a", 1.0): [False],
            ("hint_b", 1.0): [False],
            ("hint_c", 1.0): [True, False],
        },
        _replies(
            _reply(HINT),
            _reply(HINT + "\n", names=("hint_b",)),
            _reply(HINT + "\n\n", names=("hint_c",)),
        ),
    )
    ctrl = controller(tmp_path, sub, reference=lambda task: REF, privilege_judge=judge())
    outcome = ctrl.run([TASK])[0]
    assert outcome.outcome == "accepted", outcome.detail
    designer = sub._designer
    assert isinstance(designer, ScriptedDesigner) and designer.calls == 3
    assert outcome.detail["baseline_rollouts"] == 10
    assert outcome.detail["adaptation_rollouts"] == ctrl.budget.account("9").spent == 16
    assert outcome.n_search == 26 and optimizer_module.MAX_OPTIMIZER_CALLS == 2
    assert '"remaining_calls": 2' in _body(designer, 1)
    assert '"remaining_calls": 1' in _body(designer, 2)
    assert "REPLACE_MECHANISM" in _body(designer, 2)
    records = [
        json.loads(line)
        for line in (tmp_path / "run/low_candidates.jsonl").read_text().splitlines()
    ]
    assert [record["remaining_calls"] for record in records] == [2, 1, 0]
    assert records[2]["parent_candidate_id"] == records[1]["candidate_id"]
    selected = next(e.payload for e in events(tmp_path) if e.kind == "selected_admission")
    entry = read_corpus(tmp_path / "run/corpus.jsonl")[0]
    assert selected["verdict"] == "PASS" and selected["d"] in selected["doses"]
    assert selected["source_sha256"] == records[2]["source_sha256"]
    assert selected["candidate_sha256"] == hashlib.sha256(entry.rules_code.encode()).hexdigest()
    assert entry.aea.n_search == 26
    with (tmp_path / "run/accounting.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert sum(int(row["n"]) for row in rows) == 26


@pytest.mark.parametrize("verdict", ["FAIL", "UNCERTAIN"])
def test_low_rejected_candidates_never_certify_or_probe(tmp_path: Path, verdict: str) -> None:
    sub = IntegrationSubstrate(
        [False], {}, _replies(_reply(HINT), _reply(HINT + "\n"), _reply(HINT + "\n\n"))
    )
    ctrl = controller(tmp_path, sub, reference=lambda task: REF, privilege_judge=judge(verdict))
    outcome = ctrl.run([TASK])[0]
    assert outcome.outcome == "dropped" and outcome.detail["adaptation_rollouts"] == 0
    assert not sub.probes and isinstance(sub._designer, ScriptedDesigner)
    assert sub._designer.calls == 3
    assert not any(
        e.kind in ("solvable", "family_frozen", "selected_admission") for e in events(tmp_path)
    )


def test_high_freezes_first_viable_family_even_when_control_exhausts(tmp_path: Path) -> None:
    doses = (1.0, 0.5, 0.25, 0.125, 0.0625)
    sub = IntegrationSubstrate([True], {("case_flip", d): [False] for d in doses}, high_reply())
    table = LeverageTable()
    for _ in range(5):
        table.record_frontier("case_flip", 0.9)
    ctrl = controller(tmp_path, sub, reference=forbidden, leverage=table)
    outcome = ctrl.run([TASK])[0]
    assert outcome.outcome == "dropped" and outcome.reason == "exhausted"
    assert [dose for _, dose, _ in sub.probes] == list(doses)
    assert all(name == "case_flip" for name, _, _ in sub.probes)
    assert outcome.n_search == 30 and outcome.detail["adaptation_rollouts"] == 20
    assert isinstance(sub._designer, ScriptedDesigner) and sub._designer.calls == 1
    frozen = [e for e in events(tmp_path) if e.kind == "family_frozen"]
    assert len(frozen) == 1 and frozen[0].payload["direction"] == "harder_with_d"
    assert not any(e.kind == "leverage_restored" for e in events(tmp_path))


def test_high_second_family_only_before_viability(tmp_path: Path) -> None:
    sub = IntegrationSubstrate(
        [True],
        {
            ("case_flip", 1.0): [True],
            ("second", 1.0): [True, False],
        },
        high_reply(),
    )
    outcome = controller(tmp_path, sub, reference=forbidden).run([TASK])[0]
    assert outcome.outcome == "accepted" and outcome.detail["family"] == "second"
    assert sub.probes == [("case_flip", 1.0, 4), ("second", 1.0, 4), ("second", 1.0, 4)]
    endpoint = [e.payload for e in events(tmp_path) if e.kind == "endpoint"]
    assert [(p["s"], p["n"], p["verdict"]) for p in endpoint] == [
        (4, 4, "too_easy"),
        (4, 8, "in_band"),
    ]
    assert sum(e.kind == "family_frozen" for e in events(tmp_path)) == 1


def test_high_infeasible_control_cannot_switch_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ProposedFamily.make

    def make(self: ProposedFamily, dose: float, ctx: Any) -> Candidate | None:
        return None if self.name == "case_flip" and dose == 0.5 else original(self, dose, ctx)

    monkeypatch.setattr(ProposedFamily, "make", make)
    sub = IntegrationSubstrate([True], {("case_flip", 1.0): [False]}, high_reply())
    outcome = controller(tmp_path, sub).run([TASK])[0]
    assert outcome.outcome == "dropped" and outcome.reason == "infeasible"
    assert sub.probes == [("case_flip", 1.0, 4)]


def test_control_family_hash_guard_rejects_mutation(tmp_path: Path) -> None:
    sub = IntegrationSubstrate([True], {}, high_reply())
    ctrl = controller(tmp_path, sub)
    family = ProposedFamily("case_flip", "O", CASE_FLIP)
    ctrl._freeze_family(TASK, family, "harder_with_d")
    object.__setattr__(family, "template", CASE_FLIP + "\n# changed")
    with pytest.raises(ConfigError, match="frozen semantic family"):
        ctrl._assert_frozen_family(TASK, family)


def test_integrated_baseline_error_retry_does_not_prefetch_extra_evidence(tmp_path: Path) -> None:
    sub = IntegrationSubstrate([True, False], {}, forbidden)
    original = sub.rollouts
    calls = count()

    def flaky(*args: Any, **kwargs: Any) -> list[Trace]:
        result = original(*args, **kwargs)
        if next(calls) == 0:
            result[0].error = "synthetic infrastructure failure"
        return result

    sub.rollouts = flaky  # type: ignore[method-assign]
    ctrl = controller(tmp_path, sub, reference=forbidden)
    outcome = ctrl.run([TASK])[0]
    evidence = next(e.payload for e in events(tmp_path) if e.kind == "measurement_evidence")
    assert outcome.outcome == "kept" and evidence["errors_retried"] == 1
    assert evidence["n"] == outcome.detail["baseline_rollouts"]
    assert sub.calls[1] == ("9", "estimate", 1)
    assert sum(n for _, _, n in sub.calls) == evidence["n"] + 1


def test_optimizer_instance_limit_does_not_change_legacy_default() -> None:
    kwargs: dict[str, Any] = dict(
        task_id="9",
        propose=lambda feedback, index: {},
        certify=lambda candidate: Solvable(True, "oracle", {}),
        measure=lambda family, dose: forbidden(),
        remaining=lambda: 30,
    )
    evidence = serialize_low([], 0, 10, REF, rich=True)
    modern = LowEnvironmentOptimizer(evidence, [], REF, "goal", max_calls=3, **kwargs)
    legacy = LowEnvironmentOptimizer(evidence, [], REF, "goal", **kwargs)
    assert modern.max_calls == modern.remaining_calls == 3
    assert legacy.max_calls == legacy.remaining_calls == optimizer_module.MAX_OPTIMIZER_CALLS == 2
    for bad in (0, -1, True):
        with pytest.raises(ConfigError):
            LowEnvironmentOptimizer(evidence, [], REF, "goal", max_calls=bad, **kwargs)


@pytest.mark.parametrize(
    "method,expected",
    [
        ("llm_v2_integrated", WitnessCheckingPrivilegeJudge),
        ("llm_v2_iterative_low_llm_judge", LLMPrivilegeJudge),
    ],
)
def test_production_factory_selects_frozen_witness_judge_only_for_integrated(
    method: str, expected: type[Any]
) -> None:
    substrate = object.__new__(AeaSubstrate)
    substrate._method_version = method  # type: ignore[assignment]
    substrate._judge_client = SimpleNamespace(complete=forbidden)  # type: ignore[assignment]
    built = substrate.privilege_judge(Attribution(phase="privilege_judge", budget="none"))
    assert type(built) is expected
    assert reference_provider(CONFIG, forbidden) is not None
    assert reference_provider(AEAConfig(), forbidden) is None


def test_screen_capture_lock_is_released_before_model_work(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Lock:
        def __enter__(self) -> None:
            calls.append("lock")

        def __exit__(self, *args: Any) -> None:
            calls.append("unlock")

    monkeypatch.setattr(module, "SESSION_LOCK", Lock())

    def capture(self: LLMLowPrivilegeScreen) -> tuple[Any, ...]:
        calls.append("capture")
        return ()

    monkeypatch.setattr(LLMLowPrivilegeScreen, "_capture", capture)
    screen = object.__new__(module._IntegratedPrivilegeScreen)
    assert screen._capture() == ()
    assert calls == ["lock", "capture", "unlock"]


def test_low_adaptation_cap_remains_thirty_after_baseline(tmp_path: Path) -> None:
    mostly_easy = [True, True, True, False] * 2
    sub = IntegrationSubstrate(
        [False],
        {
            ("hint_a", 1.0): [False],
            ("hint_b", 1.0): [False],
            ("hint_c", 1.0): [True],
            ("hint_c", 0.5): mostly_easy,
            ("hint_c", 0.25): mostly_easy,
        },
        _replies(
            _reply(HINT),
            _reply(HINT + "\n", names=("hint_b",)),
            _reply(HINT + "\n\n", names=("hint_c",)),
        ),
    )
    ctrl = controller(tmp_path, sub, reference=lambda task: REF, privilege_judge=judge())
    result = ctrl.run([TASK])[0]
    assert result.outcome == "dropped" and result.reason == "budget"
    assert result.detail["baseline_rollouts"] == 10
    assert result.detail["adaptation_rollouts"] == 28 and result.n_search == 38
    assert ctrl.budget.account("9").remaining() == 2
    assert isinstance(sub._designer, ScriptedDesigner) and sub._designer.calls == 3
    assert not any(dose == 0.125 for _, dose, _ in sub.probes)
    assert sum(e.kind == "family_frozen" for e in events(tmp_path)) == 1


def test_legacy_scoped_call_limit_still_binds_at_run_time(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = serialize_low([], 0, 10, REF, rich=True)
    kwargs: dict[str, Any] = dict(
        task_id="9",
        propose=lambda feedback, index: {},
        certify=forbidden,
        measure=forbidden,
        remaining=lambda: 30,
    )
    legacy = LowEnvironmentOptimizer(evidence, [], REF, "goal", **kwargs)
    modern = LowEnvironmentOptimizer(evidence, [], REF, "goal", max_calls=3, **kwargs)
    with monkeypatch.context() as context:
        context.setattr(optimizer_module, "MAX_OPTIMIZER_CALLS", 3)
        legacy.run()
        assert len(legacy.history) == 3
    assert modern.max_calls == 3 and legacy.max_calls == 2


def test_high_error_is_not_a_control_verdict(tmp_path: Path) -> None:
    sub = IntegrationSubstrate([True], {("case_flip", 1.0): [False]}, high_reply())
    original = sub.rollouts

    def flaky(task: TaskRef, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        traces = original(task, candidate, n, **kwargs)
        if kwargs["attribution"].phase != "estimate":
            traces[0].error = "synthetic failed physical episode"
        return traces

    sub.rollouts = flaky  # type: ignore[method-assign]
    outcome = controller(tmp_path, sub).run([TASK])[0]
    assert outcome.outcome == "infra_error"
    assert not any(e.kind in ("endpoint", "family_frozen") for e in events(tmp_path))


def test_low_inconclusive_keeps_pilot_infrastructure_classification(tmp_path: Path) -> None:
    sub = IntegrationSubstrate([False], {("hint_a", 1.0): [False]}, _reply(HINT))
    original = sub.rollouts

    def flaky(task: TaskRef, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        traces = original(task, candidate, n, **kwargs)
        if kwargs["attribution"].phase != "estimate":
            traces[0].error = "synthetic failed physical episode"
        return traces

    sub.rollouts = flaky  # type: ignore[method-assign]
    result = controller(tmp_path, sub, reference=lambda task: REF, privilege_judge=judge()).run(
        [TASK]
    )[0]
    assert result.outcome == "infra_error" and result.detail["kind"] == "task_infrastructure"
    assert isinstance(sub._designer, ScriptedDesigner) and sub._designer.calls == 1
    assert not any(e.kind in ("family_frozen", "selected_admission") for e in events(tmp_path))
