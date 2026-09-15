"""Bounded iterative LOW DESIGN, frozen CONTROL, and the old-method boundary.

All policy and designer calls use deterministic offline fixtures. The historical suites and
v0.4 golden remain unchanged; these tests exercise the new feedback edge and its hard stops.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate

import aea.controller as ctl
from aea.config import AEAConfig
from aea.controller import Controller, TaskOutcome, TaskRef
from aea.core.trace import read_trace
from aea.designer import Reference, ReferenceStep, serialize_low
from aea.errors import InfraError
from aea.evaluate import Eval
from aea.io import read_corpus
from aea.llm.types import ChatRequest
from aea.low_optimizer import Feedback, LowEnvironmentOptimizer, iterative_messages
from aea.substrate import reference_provider
from aea.witness import Solvable
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import PLAN, FakeSubstrate
from tests.unit.test_assistive_rules import (
    HINT,
    NOT_IDENTITY,
    DoseSubstrate,
    _reply,
    _stream,
)
from tests.unit.test_llm_v1 import HIGH_OK, TableSubstrate, _trace

V2 = AEAConfig(method_version="llm_v2_iterative_low")
SECRET = "PRIVILEGED_REFERENCE_ONLY_SENTINEL"
REF = Reference(
    True,
    "pass",
    tuple(PLAN),
    tuple(ReferenceStep(i + 1, SECRET, ("look",), action) for i, action in enumerate(PLAN)),
)
type Reply = tuple[str, dict[str, Any]]
type Table = dict[tuple[str, float], list[bool]]


def _replies(*replies: Reply) -> Callable[[ChatRequest], Reply]:
    pending = iter(replies)

    def next_reply(request: ChatRequest) -> Reply:
        try:
            return next(pending)
        except StopIteration as exc:
            raise AssertionError("designer exceeded the supplied bounded opportunities") from exc

    return next_reply


def _run(
    tmp_path: Path,
    table: Table,
    *replies: Reply,
    config: AEAConfig = V2,
    reference: Reference = REF,
    oracle: bool = True,
) -> tuple[TaskOutcome, DoseSubstrate, ScriptedDesigner, Controller]:
    sub = DoseSubstrate(table, _replies(*replies))
    if not oracle:
        sub.has_oracle = lambda: False  # type: ignore[method-assign]
    designer = sub._designer
    assert isinstance(designer, ScriptedDesigner)
    ctrl = Controller(
        config, sub, tmp_path / "run", "r1", arm="D", reference=lambda task: reference
    )
    outcome = ctrl.run([TaskRef("9", 9)])[0]
    return outcome, sub, designer, ctrl


def _body(designer: ScriptedDesigner, index: int) -> str:
    return "\n".join(message.content for message in designer.requests[index].messages)


def _adaptation(sub: DoseSubstrate) -> int:
    return sum(n for _, phase, n in sub.calls if phase != "estimate")


def test_c1_easy_freezes_then_uses_existing_control(tmp_path: Path) -> None:
    table = {
        ("hint_a", 1.0): [True] * 4,
        ("hint_a", 0.5): [False] * 4,
        ("hint_a", 0.75): [True, False] * 4,
    }
    outcome, sub, designer, _ = _run(tmp_path, table, _reply(HINT))
    assert outcome.outcome == "accepted" and outcome.detail["d"] == 0.75
    assert designer.calls == 1
    assert sub.probes == [
        ("hint_a", 1.0, 4),
        ("hint_a", 0.5, 4),
        ("hint_a", 0.75, 4),
        ("hint_a", 0.75, 4),
    ]
    entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
    assert entry.aea.kind == "knob" and entry.aea.regime == "zero"
    assert entry.rules_code == HINT.replace("__DOSE__", "0.75")
    assert not entry.in_env_actions


def test_c1_in_band_accepts_without_a_second_designer_call(tmp_path: Path) -> None:
    outcome, sub, designer, _ = _run(tmp_path, {("hint_a", 1.0): [True, False] * 4}, _reply(HINT))
    assert outcome.outcome == "accepted" and outcome.detail["d"] == 1.0
    assert designer.calls == 1 and _adaptation(sub) == 8
    assert sub.probes == [("hint_a", 1.0, 4), ("hint_a", 1.0, 4)]
    tools = designer.requests[0].tools
    assert tools is not None
    tool: Any = tools[0]
    schema = tool["function"]["parameters"]["properties"]["families"]
    assert schema["minItems"] == schema["maxItems"] == 1


@pytest.mark.parametrize(
    ("broken", "detail"),
    [
        (HINT.replace("self.DOSE", "DOSE"), "NameError"),
        (
            HINT.replace(
                "    DOSE = __DOSE__",
                "    DOSE = __DOSE__\n\n    def __init__(self):\n        pass",
            ),
            "TypeError",
        ),
        (HINT.replace("__DOSE__", "__MISSING_DOSE__"), "DOSE"),
    ],
)
def test_mechanical_failure_requests_code_repair(tmp_path: Path, broken: str, detail: str) -> None:
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [True, False] * 4},
        _reply(broken),
        _reply(HINT),
    )
    assert outcome.outcome == "accepted" and designer.calls == 2
    second = _body(designer, 1)
    assert "REPAIR_CODE" in second and detail in second
    assert "preserve" in second.lower() and "mechanism" in second.lower()
    assert hashlib.sha256(broken.encode()).hexdigest() in second
    assert _adaptation(sub) == 8


@pytest.mark.parametrize(
    ("broken", "detail"),
    [
        (NOT_IDENTITY, "DOSE = 0"),
        (HINT.replace("Hint: ", "Hint: shelf 77 "), "privileged"),
        (HINT + "\n    # won = True\n", "won"),
    ],
)
def test_semantic_or_privilege_failure_requires_replacement(
    tmp_path: Path, broken: str, detail: str
) -> None:
    reference = Reference(
        True,
        "pass",
        tuple(PLAN),
        (ReferenceStep(1, SECRET + " shelf 77", ("look",), PLAN[0]),),
    )
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [True, False] * 4},
        _reply(broken),
        _reply(HINT),
        reference=reference,
    )
    assert outcome.outcome == "accepted" and designer.calls == 2
    assert "REPLACE_MECHANISM" in _body(designer, 1)
    assert detail in _body(designer, 1)
    assert _adaptation(sub) == 8


def test_solvability_failure_is_feedback_not_policy_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = iter(
        [Solvable(False, "uncertified", {"oracle_1": "blocked"}), Solvable(True, "oracle")]
    )
    monkeypatch.setattr(ctl, "solvable", lambda *args, **kwargs: next(results))
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_b", 1.0): [True, False] * 4},
        _reply(HINT),
        _reply(HINT.replace("!", "?"), names=("hint_b",)),
    )
    assert outcome.outcome == "accepted" and designer.calls == 2
    assert "REPLACE_MECHANISM" in _body(designer, 1)
    assert "solvability" in _body(designer, 1) and "blocked" in _body(designer, 1)
    assert all(family == "hint_b" for family, _, _ in sub.probes)


def test_c1_no_leverage_returns_actual_behavior_then_c2_freezes(tmp_path: Path) -> None:
    table = {
        ("hint_a", 1.0): [False] * 4,
        ("hint_b", 1.0): [True] * 4,
        ("hint_b", 0.5): [True, False] * 4,
    }
    outcome, sub, designer, _ = _run(
        tmp_path, table, _reply(HINT), _reply(HINT.replace("!", "?"), names=("hint_b",))
    )
    assert outcome.outcome == "accepted" and outcome.detail["d"] == 0.5
    assert designer.calls == 2 and _adaptation(sub) == 16
    second = _body(designer, 1)
    assert "REPLACE_MECHANISM" in second and "too_hard" in second
    assert "FAILURE" in second and PLAN[0] in second
    assert hashlib.sha256(HINT.encode()).hexdigest() in second
    assert "numeric dose" in second.lower() or "maximum assistance" in second.lower()


def test_c2_no_leverage_exhausts_two_calls_without_fallback(tmp_path: Path) -> None:
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [False] * 4, ("hint_b", 1.0): [False] * 4},
        _reply(HINT),
        _reply(HINT.replace("!", "?"), names=("hint_b",)),
    )
    assert outcome.outcome == "dropped" and designer.calls == 2
    assert _adaptation(sub) == 8
    events = read_trace(tmp_path / "run" / "events.jsonl")
    assert not any(
        event.kind in {"stage_candidates", "stage_family", "families"} for event in events
    )


def test_c2_invalid_exhausts_two_calls_without_a_third_repair(tmp_path: Path) -> None:
    outcome, sub, designer, _ = _run(
        tmp_path, {}, _reply(NOT_IDENTITY), _reply(NOT_IDENTITY + "\n")
    )
    assert outcome.outcome == "dropped" and designer.calls == 2 and not sub.probes


@pytest.mark.parametrize("families", [None, {}, "not an array", [], [3]])
def test_malformed_family_schema_is_bounded_repair_feedback(tmp_path: Path, families: Any) -> None:
    bad = ("diagnose_and_propose_assistance", {"families": families})
    outcome, sub, designer, _ = _run(
        tmp_path, {("hint_a", 1.0): [True, False] * 4}, bad, _reply(HINT)
    )
    assert outcome.outcome == "accepted" and designer.calls == 2
    assert "REPAIR_CODE" in _body(designer, 1) and _adaptation(sub) == 8


def test_multi_family_response_is_rejected_whole_instead_of_truncated(tmp_path: Path) -> None:
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [True, False] * 4},
        _reply(HINT, HINT.replace("!", "?")),
        _reply(HINT.replace("!", ".")),
    )
    assert outcome.outcome == "accepted" and designer.calls == 2
    assert "exactly one family" in _body(designer, 1) and _adaptation(sub) == 8


def test_duplicate_source_does_not_repeat_guard_or_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guarded: list[Candidate] = []

    def certify(candidate: Candidate, *args: Any, **kwargs: Any) -> Solvable:
        guarded.append(candidate)
        return Solvable(True, "oracle")

    monkeypatch.setattr(ctl, "solvable", certify)
    outcome, sub, designer, _ = _run(
        tmp_path, {("hint_a", 1.0): [False] * 4}, _reply(HINT), _reply(HINT, names=("renamed",))
    )
    assert outcome.outcome == "dropped" and designer.calls == 2
    assert len(guarded) == 1 and sub.probes == [("hint_a", 1.0, 4)]


def test_control_failure_never_reopens_design(tmp_path: Path) -> None:
    table = {("hint_a", d): [True] * 4 for d in (1.0, 0.5, 0.25, 0.125, 0.0625)}
    outcome, sub, designer, _ = _run(tmp_path, table, _reply(HINT))
    assert outcome.outcome == "dropped" and designer.calls == 1
    assert _adaptation(sub) == 20 and outcome.n_search == 30


def test_second_candidate_requires_endpoint_plus_control_reserve(tmp_path: Path) -> None:
    # A mixed first batch reaches only 1/8: twelve adaptation episodes remain, below 8+8.
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [True, False, False, False, False, False, False, False]},
        _reply(HINT),
    )
    assert outcome.outcome == "dropped" and designer.calls == 1
    assert _adaptation(sub) == 8 and outcome.n_search == 18
    assert outcome.detail["design_status"] == "budget_unresolved"
    assert outcome.reason == "endpoint_and_calibration_reserve"


def test_policy_budget_hard_stop_during_control(tmp_path: Path) -> None:
    mixed_easy = [True, False, True, True, True, True, True, False]
    table = {("hint_a", d): mixed_easy for d in (1.0, 0.5, 0.25)}
    outcome, sub, designer, _ = _run(tmp_path, table, _reply(HINT))
    assert outcome.outcome == "dropped" and designer.calls == 1
    assert outcome.n_search <= 30 and _adaptation(sub) <= 20


@pytest.mark.parametrize("oracle", [False, True])
def test_uncertain_expert_infrastructure_does_not_reach_designer_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, oracle: bool
) -> None:
    if oracle:
        monkeypatch.setattr(
            ctl,
            "solvable",
            lambda *args, **kwargs: Solvable(False, "uncertified", {"oracle_1": "expert_error"}),
        )
    outcome, sub, designer, _ = _run(tmp_path, {}, _reply(HINT), oracle=oracle)
    assert outcome.outcome in {"dropped", "infra_error"}
    assert designer.calls <= 1 and not sub.probes


def test_reference_unavailable_keeps_task_without_replacement_or_paid_design(
    tmp_path: Path,
) -> None:
    outcome, sub, designer, _ = _run(tmp_path, {}, reference=Reference(False, "expert_stuck"))
    assert outcome.outcome in {"dropped", "infra_error"}
    assert not sub.probes and designer.calls == 0


def test_recovered_expert_attempt_still_certifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ctl,
        "solvable",
        lambda *args, **kwargs: Solvable(
            True, "oracle", {"oracle_1": "expert_stuck", "oracle_attempt": 2}
        ),
    )
    outcome, sub, designer, _ = _run(tmp_path, {("hint_a", 1.0): [True, False] * 4}, _reply(HINT))
    assert outcome.outcome == "accepted" and _adaptation(sub) == 8 and designer.calls == 1


def test_failed_second_provider_call_keeps_completed_c1_audit(tmp_path: Path) -> None:
    calls = 0

    def reply(request: ChatRequest) -> Reply:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InfraError("provider unavailable", kind="provider")
        return _reply(HINT)

    sub = DoseSubstrate({("hint_a", 1.0): [False] * 4}, reply)
    ctrl = Controller(V2, sub, tmp_path / "run", "r1", reference=lambda task: REF)
    outcome = ctrl.run([TaskRef("9", 9)])[0]
    assert outcome.outcome == "infra_error" and calls == 2
    rows = [
        json.loads(line)
        for line in (tmp_path / "run" / "low_candidates.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1 and rows[0]["optimizer_call_index"] == 1
    assert rows[0]["source_sha256"] == hashlib.sha256(HINT.encode()).hexdigest()


def test_reference_is_privileged_and_k16_is_not_an_optimizer_input(tmp_path: Path) -> None:
    outcome, sub, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [False] * 4, ("hint_b", 1.0): [True, False] * 4},
        _reply(HINT),
        _reply(HINT.replace("!", "?"), names=("hint_b",)),
    )
    assert outcome.outcome == "accepted"
    assert all(SECRET in _body(designer, i) for i in range(designer.calls))
    for filename in ("traces.jsonl", "corpus.jsonl", "events.jsonl", "designer_calls.jsonl"):
        assert SECRET not in (tmp_path / "run" / filename).read_text()
    assert SECRET in (tmp_path / "run" / "privileged_references.jsonl").read_text()
    assert all(n <= 4 and "confirm" not in phase for _, phase, n in sub.calls)
    for request in designer.requests:
        assert request.attribution.budget == "designer"
        assert "K16" not in "\n".join(message.content for message in request.messages)
    for entry in read_corpus(tmp_path / "run" / "corpus.jsonl"):
        assert not entry.in_env_actions and not any(action in entry.rules_code for action in PLAN)


def test_independent_second_prompt_is_built_only_from_original_evidence() -> None:
    failures = [_trace(False)]
    evidence = serialize_low(failures, 0.0, 10, REF, rich=True)
    independent = iterative_messages(evidence, previous_source=HINT)
    text = "\n".join(message.content for message in independent)
    assert evidence.text in text and HINT in text
    assert "Produce a different valid assistive Rules family" in text
    assert "too_hard" not in text and "REPLACE_MECHANISM" not in text and "REPAIR_CODE" not in text


def test_feedback_records_are_immutable_and_include_blocked_behavior() -> None:
    failures = [_trace(False)]
    evidence = serialize_low(failures, 0.0, 10, REF, rich=True)
    endpoint_failure = _trace(False)
    endpoint_failure.steps[0].blocked_reason = "blocked_by_candidate"
    endpoint_failure.steps[0].info["effective"] = False
    feedback_received: list[Feedback | None] = []
    remaining = 20

    def propose(feedback: Feedback | None, index: int) -> dict[str, Any]:
        feedback_received.append(feedback)
        return _reply(HINT if index == 1 else HINT.replace("!", "?"))[1]

    def measure(family: Any, dose: float) -> Eval:
        nonlocal remaining
        assert dose == 1.0
        remaining -= 4
        return Eval(0, 4, "too_hard", [endpoint_failure] * 4)

    optimizer = LowEnvironmentOptimizer(
        evidence,
        failures,
        REF,
        "put x in b",
        task_id="9",
        propose=propose,
        certify=lambda candidate: Solvable(True, "oracle"),
        measure=measure,
        remaining=lambda: remaining,
    )
    result = optimizer.run()
    assert result.status == "unresolved" and optimizer.remaining_calls == 0
    assert optimizer.evidence is evidence and optimizer.reference is REF
    assert len(optimizer.history) == len(optimizer.rejections) == 2
    c1, c2 = optimizer.history
    assert c1.parent_candidate_id is None and c2.parent_candidate_id == c1.candidate_id
    assert (c1.optimizer_call_index, c2.optimizer_call_index) == (1, 2)
    assert c1.source_sha256 != c2.source_sha256
    assert c1.requested_operation == "PROPOSE" and c2.requested_operation == "REPLACE_MECHANISM"
    assert c1.remaining_policy == 16 and c2.remaining_policy == 12
    assert c1.endpoint == c2.endpoint == (0, 4, "too_hard")
    second = feedback_received[1]
    assert second is not None and second.endpoint == (0, 4, "too_hard")
    assert second.remaining_calls == 1 and second.remaining_policy == 16
    assert second.failed_rollout is not None
    assert "blocked_by_candidate" in second.failed_rollout and "no effect" in second.failed_rollout
    assert second.source == HINT and second.mechanism == c1.mechanism
    assert second.failed_episode_id == endpoint_failure.episode_id
    with pytest.raises(FrozenInstanceError):
        c1.source = "changed"  # type: ignore[misc]
    with pytest.raises(RuntimeError, match="single-use"):
        optimizer.run()
    with pytest.raises(ValueError, match="mutually exclusive"):
        iterative_messages(evidence, second, previous_source=HINT)


@pytest.mark.parametrize(
    "old_version", ["llm_v1", "llm_v1_refalign", "llm_v1_stage_control", "llm_v1_assistive_rules"]
)
def test_high_and_mid_are_identical_to_every_existing_llm_variant(
    tmp_path: Path, old_version: str
) -> None:
    for config, tag in (
        (AEAConfig.model_validate({"method_version": old_version}), "old"),
        (V2, "v2"),
    ):
        designer = ScriptedDesigner(HIGH_OK)
        sub = FakeSubstrate({"7": "footer"}, seed=3, with_designer=True, designer_fn=designer)
        outcome = Controller(config, sub, tmp_path / f"high-{tag}", "r1", arm="X").run(
            [TaskRef("7", 7)]
        )[0]
        assert outcome.regime == "saturated" and designer.calls == 1
        designer_mid = ScriptedDesigner(HIGH_OK)
        sub_mid = TableSubstrate({None: [True, False] * 8}, designer_mid)
        outcome_mid = Controller(config, sub_mid, tmp_path / f"mid-{tag}", "r1", arm="X").run(
            [TaskRef("5", 5)]
        )[0]
        assert outcome_mid.outcome == "kept" and designer_mid.calls == 0
    assert _stream(tmp_path / "high-old") == _stream(tmp_path / "high-v2")
    assert _stream(tmp_path / "mid-old") == _stream(tmp_path / "mid-v2")


def test_new_reference_wiring_is_lazy_and_old_v04_stays_reference_free() -> None:
    sub = FakeSubstrate({"9": "random"})
    assert reference_provider(V2, sub.open_session) is not None
    assert reference_provider(AEAConfig(), sub.open_session) is None
    assert not sub.calls and sub.max_active_sessions == 0


def test_old_variants_never_enter_the_new_optimizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def trap(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("old method entered iterative LOW")

    monkeypatch.setattr(LowEnvironmentOptimizer, "run", trap)
    from tests.unit.test_assistive_rules import (
        test_stage_control_and_refalign_unchanged_by_the_new_variant,
    )
    from tests.unit.test_method_version_compat import (
        test_v04_high_and_low_paths_match_the_phase1_golden,
    )

    test_stage_control_and_refalign_unchanged_by_the_new_variant(tmp_path / "old-low")
    test_v04_high_and_low_paths_match_the_phase1_golden(tmp_path / "golden")
    outcome, _, designer, _ = _run(
        tmp_path / "assist-v1",
        {("hint_a", 1.0): [True, False] * 4},
        _reply(HINT),
        config=AEAConfig(method_version="llm_v1_assistive_rules"),
    )
    assert outcome.outcome == "accepted" and designer.calls == 1
