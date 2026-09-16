"""Offline physical guards, fixture barriers, and actual frozen downstream LOW behavior."""

from __future__ import annotations

import ast
import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aea.errors import ConfigError, InfraError
from aea.llm.attribution import attributed
from aea.llm.types import Attribution
from aea.privilege_judge import JudgeRecord, PrivilegeDecision
from aea.semantic_privilege import Decision
from tests.unit.test_llm_v1 import _trace


@pytest.fixture
def viability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = importlib.import_module("scripts.e6_iterative_low_llm_judge")
    monkeypatch.setattr(module, "BASE", tmp_path)
    monkeypatch.setattr(module, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(module, "RUN", tmp_path / "private/engineering")
    monkeypatch.setattr(module, "VALIDATION", tmp_path / "private/validation")
    monkeypatch.setattr(module, "FROZEN", tmp_path / "frozen")
    return module


def _design_fixture(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    codes: list[str],
    verdicts: list[Decision] | None = None,
    outcomes: Any = None,
) -> tuple[Any, Any, dict[str, Any], list[Any]]:

    from aea.semantic_low import SemanticAdmissionError
    from aea.witness import Solvable
    from tests.fixtures.fake_designer import ScriptedDesigner
    from tests.unit.test_assistive_rules import _reply
    from tests.unit.test_iterative_low import REF

    failures = [_trace(False) for _ in range(3)]
    for i, trace in enumerate(failures):
        trace.rollout_seed = 9
        trace.episode_id = f"original-9-{i}"
    viability.write_json(
        viability.RUN / "task-9/original_failures.json", [t.model_dump() for t in failures]
    )
    viability.write_json(viability.RUN / "task-9/privileged_reference.json", REF.as_record())
    viability.write_json(
        viability.RUN / "prepared.json",
        [{"all_original_episode_ids": [t.episode_id for t in failures]}],
    )
    viability.initialize_cap(viability.RUN / "cap.json", "engineering")
    replies = iter(_reply(code) for code in codes)
    designer = ScriptedDesigner(lambda request: next(replies))
    planned_decisions: list[Decision] = verdicts if verdicts is not None else ["PASS"] * len(codes)
    decisions = iter(planned_decisions)
    events: list[Any] = []
    shared: dict[str, Any] = {"semantic_records": []}
    admitted: set[str] = set()

    class Screen:
        def screen(self, family: Any) -> Any:
            decision = next(decisions)
            events.append(("semantic", family.template, decision))
            # Controlled semantic outcomes only test orchestration; they make no safety claim.
            result = JudgeRecord(
                decision=PrivilegeDecision(
                    verdict=decision,
                    leakage_score=0.0 if decision == "PASS" else 1.0,
                    information="offline controlled verdict",
                    reference_evidence="offline",
                    public_evidence_check="offline",
                    candidate_evidence="offline",
                    activation="offline",
                    leak_type="NONE" if decision == "PASS" else "OTHER",
                    revision_reason="replace support",
                ),
                source_sha256=viability.digest(family.template),
                input_sha256="input",
                prompt_sha256="prompt",
                schema_sha256="schema",
                config_sha256="config",
                request_sha256=None,
                response_sha256=None,
                request=None,
                response=None,
            )
            shared["semantic_records"].append(
                {"optimizer_call_index": shared["active_call"], "result": result.as_record()}
            )
            if decision == "PASS":
                admitted.add(family.template)
            return result

        def require_pass(self, family: Any, dose: float) -> None:
            events.append(("admission", family.template, dose))
            if family.template not in admitted or dose not in viability.reachable_screen_doses(4):
                raise SemanticAdmissionError("source/dose not admitted")

    # Some driver versions import reachable_screen_doses only indirectly.
    from aea.semantic_low import reachable_screen_doses

    monkeypatch.setattr(viability, "reachable_screen_doses", reachable_screen_doses, raising=False)

    def certify(candidate: Any, *args: Any, **kwargs: Any) -> Any:
        events.append(("certify", candidate.rules_code))
        return Solvable(True, "oracle")

    episode_count = 0

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        nonlocal episode_count
        attr = kwargs["attribution"]
        events.append(("policy", attr.phase, n, attr.budget, candidate.rules_code))
        successes = outcomes(attr.phase, n) if outcomes else [False] * n
        assert len(successes) == n
        result = []
        for success in successes:
            episode_count += 1
            trace = _trace(success, candidate=candidate)
            trace.rollout_seed = 9
            trace.episode_id = f"adaptation-9-{episode_count}"
            result.append(trace)
        return result

    sub = SimpleNamespace(
        designer=lambda: designer,
        designer_model=lambda: "fake",
        has_oracle=lambda: True,
        rollouts=rollouts,
    )
    monkeypatch.setattr(viability, "solvable", certify)
    shared["screen"] = Screen()
    return sub, designer, shared, events


def test_three_calls_keep_exact_lineage_feedback_and_restore_default(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    codes = [HINT + f"\n# proposal {i}\n" for i in range(1, 4)]
    sub, designer, shared, events = _design_fixture(
        viability,
        monkeypatch,
        codes,
        outcomes=lambda phase, n: (
            [i % 2 == 0 for i in range(n)] if phase.startswith("C3:") else [False] * n
        ),
    )
    result = viability.run_task(sub, 9, shared)
    assert result["search_accepted"] and result["first_viable_family_index"] == 3
    assert result["designer_calls"] == designer.calls == 3 and result["adaptation_rollouts"] == 16
    records = result["candidates"]
    assert [r["optimizer_call_index"] for r in records] == [1, 2, 3]
    assert [r["remaining_calls"] for r in records] == [2, 1, 0]
    assert [r["remaining_policy"] for r in records] == [26, 22, 14]
    assert [r["source"] for r in records] == codes
    assert records[0]["parent_candidate_id"] is None
    assert records[1]["parent_candidate_id"] == records[0]["candidate_id"]
    assert records[2]["parent_candidate_id"] == records[1]["candidate_id"]
    assert [r["requested_operation"] for r in records] == [
        "PROPOSE",
        "REPLACE_MECHANISM",
        "REPLACE_MECHANISM",
    ]
    assert [r.seed for r in designer.requests] == [9, 10, 11]
    for index in [1, 2]:
        body = "\n".join(m.content for m in designer.requests[index].messages)
        assert "TYPED DESIGN FEEDBACK" in body and "too_hard" in body
        assert (
            records[index - 1]["source_sha256"] in body
            and records[index - 1]["candidate_id"] in body
        )
    assert viability.optimizer_module.MAX_OPTIMIZER_CALLS == 2
    assert len([e for e in events if e[0] == "semantic"]) == 3


def test_frozen_reserve_can_prevent_third_call_without_budget_extension(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    counts: dict[str, int] = {}

    def outcomes(phase: str, n: int) -> list[bool]:
        counts[phase] = counts.get(phase, 0) + 1
        return [True] + [False] * (n - 1) if counts[phase] == 1 else [False] * n

    sub, designer, shared, _ = _design_fixture(
        viability,
        monkeypatch,
        [HINT + f"\n# {i}\n" for i in range(3)],
        outcomes=outcomes,
    )
    result = viability.run_task(sub, 9, shared)
    assert result["status"] == "budget_unresolved" and not result["search_accepted"]
    assert result["reason"] == "endpoint_and_calibration_reserve"
    assert designer.calls == 2 and result["adaptation_rollouts"] == 16
    assert result["candidates"][-1]["remaining_policy"] == 14
    assert viability.optimizer_module.MAX_OPTIMIZER_CALLS == 2


def test_safe_semantic_fail_uses_replacement_then_second_call_can_succeed(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    sub, designer, shared, events = _design_fixture(
        viability,
        monkeypatch,
        [HINT, HINT + "\n# replacement"],
        verdicts=["FAIL", "PASS"],
        outcomes=lambda phase, n: [i % 2 == 0 for i in range(n)],
    )
    result = viability.run_task(sub, 9, shared)
    assert result["search_accepted"] and result["first_viable_family_index"] == 2
    assert designer.calls == 2 and result["adaptation_rollouts"] == 8
    assert result["candidates"][1]["requested_operation"] == "REPLACE_MECHANISM"
    assert len([e for e in events if e[0] == "certify"]) == 1
    assert all(e[1].startswith("C2:") for e in events if e[0] == "policy")


def test_easy_endpoint_freezes_before_control_and_confirmation_has_no_feedback(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    def outcomes(phase: str, n: int) -> list[bool]:
        if phase == "confirm":
            return [True] * 4 + [False] * 12
        if phase.endswith(":1.0"):
            return [True] * n
        if phase.endswith(":0.5"):
            return [False] * n
        return [i % 2 == 0 for i in range(n)]

    sub, designer, shared, events = _design_fixture(
        viability, monkeypatch, [HINT], outcomes=outcomes
    )
    result = viability.run_task(sub, 9, shared)
    assert result["search_accepted"] and result["accepted_dose"] == 0.75
    assert result["first_viable_family_index"] == 1 and result["designer_calls"] == 1
    assert result["adaptation_rollouts"] == 16 and len(result["candidates"]) == 1
    assert [r["d"] for r in result["control"]["history"]] == [1.0, 0.5, 0.75]
    source = result["frozen_family"]["source_sha256"]
    candidates_before = copy.deepcopy(result["candidates"])
    semantic_before = len(shared["semantic_records"])
    viability.confirm(sub, 9, result, shared["screen"])
    assert result["confirmation"]["n"] == 16 and result["confirmation"]["successes"] == 4
    assert result["confirmation"]["in_band_l"] and not result["confirmation"]["in_band_t"]
    assert designer.calls == 1 and result["adaptation_rollouts"] == 16
    assert (
        result["candidates"] == candidates_before
        and len(shared["semantic_records"]) == semantic_before
    )
    assert result["frozen_family"]["source_sha256"] == source
    confirmation_calls = [e for e in events if e[0] == "policy" and e[1] == "confirm"]
    assert len(confirmation_calls) == 1 and confirmation_calls[0][2:4] == (16, "eval")
    with pytest.raises(InfraError, match="already dispatched"):
        viability.confirm(sub, 9, result, shared["screen"])
    assert len([e for e in events if e[0] == "policy" and e[1] == "confirm"]) == 1


def test_real_schema_identity_lexical_gates_precede_semantic_and_policy(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    mechanical = HINT.replace("self.DOSE", "DOSE")
    lexical = HINT + "\n# won = True\n"
    sub, designer, shared, events = _design_fixture(
        viability,
        monkeypatch,
        [mechanical, lexical, HINT],
        verdicts=["PASS"],
        outcomes=lambda phase, n: [i % 2 == 0 for i in range(n)],
    )
    result = viability.run_task(sub, 9, shared)
    assert result["search_accepted"] and designer.calls == 3
    records = result["candidates"]
    assert records[0]["structural"] and not records[0]["privilege"]
    assert records[1]["privilege"] and not records[1]["structural"]
    assert [r["requested_operation"] for r in records] == [
        "PROPOSE",
        "REPAIR_CODE",
        "REPLACE_MECHANISM",
    ]
    assert [e[1] for e in events if e[0] == "semantic"] == [HINT]
    assert all(e[1].startswith("C3:") for e in events if e[0] == "policy")
    assert len([e for e in events if e[0] == "certify"]) == 1


def test_nonidentity_dose_zero_rejects_before_semantic(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT, NOT_IDENTITY

    sub, designer, shared, events = _design_fixture(
        viability,
        monkeypatch,
        [NOT_IDENTITY, HINT],
        verdicts=["PASS"],
        outcomes=lambda phase, n: [i % 2 == 0 for i in range(n)],
    )
    result = viability.run_task(sub, 9, shared)
    assert result["search_accepted"] and designer.calls == 2
    assert any("DOSE = 0" in reason for reason in result["candidates"][0]["privilege"])
    assert [e[1] for e in events if e[0] == "semantic"] == [HINT]


def test_thirty_rollout_cap_stops_control_without_reopening_design(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    seen: dict[str, int] = {}

    def outcomes(phase: str, n: int) -> list[bool]:
        seen[phase] = seen.get(phase, 0) + 1
        if phase.endswith(":1.0"):
            return [True] * n
        if phase.endswith(":0.5"):
            return [True, True, True, False] if seen[phase] == 1 else [True] * n
        return [True] + [False] * (n - 1)

    sub, designer, shared, events = _design_fixture(
        viability, monkeypatch, [HINT], outcomes=outcomes
    )
    result = viability.run_task(sub, 9, shared)
    assert not result["search_accepted"] and result["control"]["status"] == "budget"
    assert result["adaptation_rollouts"] == 28 and designer.calls == 1
    assert len(result["candidates"]) == 1 and result["first_viable_family_index"] == 1
    assert sum(e[2] for e in events if e[0] == "policy") == 28
    assert viability.optimizer_module.MAX_OPTIMIZER_CALLS == 2


def test_scoped_three_call_budget_restores_even_when_designer_errors(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    sub, _designer, shared, _ = _design_fixture(viability, monkeypatch, [HINT])

    def fail(request: Any) -> Any:
        raise InfraError("offline provider outage", kind="server_error")

    sub.designer = lambda: fail
    with pytest.raises(InfraError, match="offline provider outage"):
        viability.run_task(sub, 9, shared)
    assert viability.optimizer_module.MAX_OPTIMIZER_CALLS == 2
    saved = json.loads((viability.RUN / "task-9/adaptation/summary.json").read_text())
    assert saved["designer_calls"] == 1 and saved["candidates"] == []


def test_three_failed_designs_stop_without_c4(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    sub, designer, shared, _ = _design_fixture(
        viability,
        monkeypatch,
        [HINT + f"\n# failed {i}\n" for i in range(3)],
    )
    result = viability.run_task(sub, 9, shared)
    assert result["status"] == "unresolved" and not result["search_accepted"]
    assert designer.calls == 3 and len(result["candidates"]) == 3
    assert result["adaptation_rollouts"] == 12 and result["candidates"][-1]["remaining_calls"] == 0
    assert viability.optimizer_module.MAX_OPTIMIZER_CALLS == 2


def test_tampered_k16_environment_is_rejected_before_any_confirmation_episode(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    sub, _, shared, events = _design_fixture(
        viability,
        monkeypatch,
        [HINT],
        outcomes=lambda phase, n: [i % 2 == 0 for i in range(n)],
    )
    result = viability.run_task(sub, 9, shared)
    assert result["search_accepted"]
    result["final_candidate"]["rules_code"] += "\n# source-corruption\n"
    before = len([e for e in events if e[0] == "policy"])
    with pytest.raises(viability.ConfigError, match="K16 environment differs"):
        viability.confirm(sub, 9, result, shared["screen"])
    assert len([e for e in events if e[0] == "policy"]) == before
    assert not (viability.RUN / "task-9/confirmation_traces.json").exists()


@pytest.mark.parametrize("stage,limit", [("validation", 3.0), ("engineering", 17.0)])
def test_physical_stage_caps_are_independent_and_sticky(
    viability: Any, stage: str, limit: float
) -> None:
    directory = viability.VALIDATION if stage == "validation" else viability.RUN
    path = directory / "cap.json"
    viability.initialize_cap(path, stage)
    calls = []

    def transport(**wire: Any) -> Any:
        calls.append(wire)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, cost=None)
        )

    guard = viability.CappedTransport(transport, path)
    wire = {"model": "deepseek-v4-flash", "messages": [], "max_tokens": 2048}
    attr = Attribution(phase="judge_validation", budget="none", arm=viability.ARM, task_id="110")
    with attributed(attr, 0):
        guard(**wire)
        with viability.cap_lock(path) as state:
            state["actual_usd"] = limit - 0.000001
        with pytest.raises(InfraError, match="stopped"):
            guard(**wire)
        with pytest.raises(InfraError, match="stopped"):
            guard(**wire)
    assert len(calls) == 1
    state = json.loads(path.read_text())
    assert state["limit_usd"] == limit and state["attempts"] == 1 and not state["inflight"]
    assert len(viability.jsonl(path.with_suffix(".denials.jsonl"))) == 2
    with pytest.raises(ConfigError, match="existing cap"):
        viability.initialize_cap(path, stage)


def test_physical_failed_attempts_keep_full_reservations(viability: Any) -> None:
    path = viability.VALIDATION / "cap.json"
    viability.initialize_cap(path, "validation")

    def fail(**wire: Any) -> Any:
        raise TimeoutError("offline timeout")

    guard = viability.CappedTransport(fail, path)
    attr = Attribution(phase="judge_validation", arm=viability.ARM, task_id="110")
    with attributed(attr, 0):
        for _ in range(2):
            with pytest.raises(TimeoutError):
                guard(model="deepseek-v4-flash", messages=[], max_tokens=2048)
    state = json.loads(path.read_text())
    attempts = viability.jsonl(path.with_suffix(".attempts.jsonl"))
    assert state["attempts"] == 2 and state["actual_usd"] == 0 and not state["inflight"]
    assert state["uncertain_usd"] == sum(
        r["reserved_usd"] for r in attempts if r["status"] == "ambiguous_failure"
    )
    assert [r["status"] for r in attempts] == ["reserved", "ambiguous_failure"] * 2
    viability.initialize_cap(viability.RUN / "cap.json", "engineering")
    assert json.loads((viability.RUN / "cap.json").read_text())["uncertain_usd"] == 0


def test_guard_refuses_unattributed_policy_during_validation_and_namespace_tampering(
    viability: Any,
) -> None:
    path = viability.VALIDATION / "cap.json"
    viability.initialize_cap(path, "validation")
    guard = viability.CappedTransport(lambda **kwargs: pytest.fail("no API"), path)
    with pytest.raises(ConfigError, match="attribution"):
        guard(model="deepseek-v4-flash", max_tokens=10)
    with (
        attributed(
            Attribution(phase="C1:dose:1", budget="search", arm=viability.ARM, task_id="154"), 154
        ),
        pytest.raises(ConfigError, match="non-judge"),
    ):
        guard(model="qwen/qwen3-8b", max_tokens=10)
    with viability.cap_lock(path) as state:
        state["cap_path"] = "/wrong-namespace/cap.json"
    with pytest.raises(ConfigError, match="namespace"):
        viability.check_cap(path, "offline")


def test_unknown_inflight_and_operation_crashes_never_dispatch_again(viability: Any) -> None:
    path = viability.RUN / "cap.json"
    viability.initialize_cap(path, "engineering")
    with viability.cap_lock(path) as state:
        state["inflight"]["unknown-worker"] = 0.3
    with pytest.raises(InfraError, match="unresolved"):
        viability.cost_check("offline")
    with (
        pytest.raises(TimeoutError),
        viability.stage_operation(viability.VALIDATION, "judge-1", {}),
    ):
        raise TimeoutError("offline process died")
    with (
        pytest.raises(InfraError, match="already dispatched"),
        viability.stage_operation(viability.VALIDATION, "judge-1", {}),
    ):
        pytest.fail("repeated operation")
    assert json.loads(path.read_text())["inflight"] == {"unknown-worker": 0.3}


def test_child_policy_factory_binds_engineering_cap_without_v3_globals(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = viability.RUN / "cap.json"
    viability.initialize_cap(path, "engineering")
    with viability.cap_lock(path) as state:
        state["actual_usd"] = state["limit_usd"] - 0.000001
    monkeypatch.setattr(
        viability.AeaLLMClient,
        "__init__",
        lambda self, **kwargs: setattr(
            self, "_client", SimpleNamespace(_transport=lambda **wire: pytest.fail("cap must stop"))
        ),
    )
    client = viability.CappedPolicyClient(cap_path=str(path))
    with (
        attributed(
            Attribution(phase="confirm", budget="eval", arm=viability.ARM, task_id="154"), 154
        ),
        pytest.raises(InfraError, match="stopped"),
    ):
        client._client._transport(model="qwen/qwen3-8b", messages=[], max_tokens=1024)


def _validation_fixture(module: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from aea.privilege_judge import PrivilegeJudgeInput

    request = PrivilegeJudgeInput(
        task_spec="fixture",
        public_task_information="goal",
        designer_evidence_summary="historical only",
        learner_authorized_evidence=[],
        privileged_reference={"actions": ["private"]},
        candidate_artifact="program",
        candidate_artifact_type="python",
        candidate_change_summary="source changes",
        benchmark_contract_summary="original current episode only",
    )
    rows = []
    for name, expected in module.EXPECTED_CASES.items():
        rows.append(
            module.store_validation_input(
                name, request, task=110, expected=expected, role="regression"
            )
        )
    for name in module.REPEAT_CASES:
        original = next(r for r in rows if r["case_id"] == name)
        rows.append(
            {**original, "case_id": name + "__repeat2", "repeat_of": name, "role": "repeat"}
        )
    for task, index in module.SAVED_CASES:
        rows.append(
            module.store_validation_input(
                f"saved_{task}_C{index}",
                request,
                task=task,
                expected=None,
                role="inspection",
                call_index=index,
            )
        )
    module.write_json(
        module.FROZEN / "validation_manifest.json",
        {"cases": rows, "judge_config": module.JudgeConfig().model_dump(mode="json")},
    )
    outcomes = [
        {
            "case_id": r["case_id"],
            "result": {
                "decision": {"verdict": r["expected_verdict"] or "UNCERTAIN"},
                "source_sha256": module.digest("program"),
                "input_sha256": "0" * 64,
                "config_sha256": "0" * 64,
                "prompt_sha256": "0" * 64,
                "schema_sha256": "0" * 64,
            },
        }
        for r in rows
    ]
    return rows, outcomes


def test_fixed_labels_repeats_and_unlabeled_saved_inspections_are_frozen(viability: Any) -> None:
    rows, outcomes = _validation_fixture(viability)
    assert viability.verify_validation_inputs() == rows
    decision = viability.validation_decision(rows, outcomes)
    assert decision["decision"] == "JUDGE_GATE_READY" and len(decision["repeats"]) == 4
    assert all(r["agreement"] for r in decision["repeats"])
    content = (viability.PRIVATE / rows[0]["input_file"]).read_text()
    assert "expected_verdict" not in content and "archived_task110" not in content
    manifest = json.loads((viability.FROZEN / "validation_manifest.json").read_text())
    manifest["cases"][0]["expected_verdict"] = "PASS"
    viability.write_json(viability.FROZEN / "validation_manifest.json", manifest)
    with pytest.raises(ConfigError, match="labels changed"):
        viability.verify_validation_inputs()


@pytest.mark.parametrize("failure", ["wrong_verdict", "missing", "repeat_hash", "infrastructure"])
def test_validation_acceptance_failure_blocks_low(viability: Any, failure: str) -> None:
    rows, outcomes = _validation_fixture(viability)
    error = None
    if failure == "wrong_verdict":
        outcomes[0]["result"]["decision"]["verdict"] = "PASS"
    elif failure == "missing":
        outcomes.pop()
    elif failure == "repeat_hash":
        outcomes[13]["result"]["input_sha256"] = "changed repeat"
    else:
        error = {"kind": "smoke_cost_cap"}
    result = viability.validation_decision(rows, outcomes, error)
    assert result["decision"] == "JUDGE_GATE_NOT_READY"


def test_uncertain_rejects_candidate_but_allows_real_bounded_redesign(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.test_assistive_rules import HINT

    codes = [HINT + "\n# first\n", HINT + "\n# second\n", HINT + "\n# third\n"]
    sub, designer, shared, events = _design_fixture(
        viability,
        monkeypatch,
        codes,
        verdicts=["UNCERTAIN", "FAIL", "PASS"],
        outcomes=lambda phase, n: [i % 2 == 0 for i in range(n)],
    )
    result = viability.run_task(sub, 9, shared)
    assert designer.calls == 3 and result["search_accepted"]
    assert [r["requested_operation"] for r in result["candidates"]] == [
        "PROPOSE",
        "REPLACE_MECHANISM",
        "REPLACE_MECHANISM",
    ]
    assert "llm_privilege_uncertain" in result["candidates"][0]["privilege"][0]
    assert "llm_privilege_fail" in result["candidates"][1]["privilege"][0]
    assert all(e[1].startswith("C3:") for e in events if e[0] == "policy")
    assert len([e for e in events if e[0] == "certify"]) == 1


@pytest.mark.parametrize(
    "name",
    [
        "scoped_three_call_budget",
        "require_pass",
        "confirm",
        "assert_fresh_episode_ids",
        "validate_traces",
    ],
)
def test_downstream_execution_helpers_are_source_identical_to_frozen_v3(
    viability: Any, name: str
) -> None:
    old = (viability.ROOT / "scripts/e6_iterative_low_viability_v3.py").read_text()
    new = Path(viability.__file__).read_text()

    def body(source: str) -> str:
        nodes = [
            n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name
        ]
        assert len(nodes) == 1
        return ast.get_source_segment(source, nodes[0]) or ""

    assert body(old) == body(new)


def _result(module: Any, endpoints: int = 2, accepts: int = 1, bl: bool = True) -> dict[str, Any]:
    rows = {}
    for i, task in enumerate(module.TASKS):
        summary: dict[str, Any] = {
            "designer_calls": 3,
            "completed_without_infrastructure_failure": True,
            "candidates": [
                {"endpoint": [2, 4, "in_band"] if i < endpoints else None, "privilege": []}
            ],
            "search_accepted": i < accepts,
        }
        if i < accepts:
            summary["confirmation"] = {"n": 16, "in_band_l": bl, "in_band_t": False}
        rows[str(task)] = {"status": "completed", "summary": summary}
    return {"tasks": rows, "interruption": None}


def test_reporting_does_not_treat_true_leak_rejections_or_incomplete_k16_as_success(
    viability: Any,
) -> None:
    result = _result(viability)
    assert viability.decision_for(result, {})["decision"] == "LOW_IMPLEMENTATION_WORKS"
    result = _result(viability, bl=False)
    assert (
        viability.decision_for(result, {})["decision"]
        == "LOW_PIPELINE_FUNCTIONAL_BUT_NO_USEFUL_ENV"
    )
    result["interruption"] = {"kind": "smoke_cost_cap"}
    assert viability.decision_for(result, {})["decision"] == "INCOMPLETE"
    assert (
        viability.decision_for(result, {"bound_violation": True})["decision"]
        == "IMPLEMENTATION_FAILURE"
    )
    result = _result(viability, endpoints=0, accepts=0)
    for row in result["tasks"].values():
        row["summary"]["candidates"] = [{"privilege": ["llm_privilege_fail: offline"]}] * 3
    assert viability.decision_for(result, {})["decision"] == "INCOMPLETE"
    result["judge_precision_blocking_verified"] = True
    assert viability.decision_for(result, {})["decision"] == "JUDGE_GATE_BLOCKING"


@pytest.mark.parametrize(
    "bad",
    [
        {"cost": float("nan")},
        {"cost": float("inf")},
        {"cost": -1.0},
        {"prompt_tokens": -10},
        {"completion_tokens": "10"},
        {"prompt_tokens": True},
        {"completion_tokens": 1.5},
    ],
)
def test_malformed_returned_usage_retains_full_reservation_and_stops(
    viability: Any, bad: dict[str, Any]
) -> None:
    path = viability.RUN / "cap.json"
    viability.initialize_cap(path, "engineering")
    usage = {"prompt_tokens": 10, "completion_tokens": 3, "cost": None, **bad}
    calls = []

    def transport(**wire: Any) -> Any:
        calls.append(wire)
        return SimpleNamespace(usage=SimpleNamespace(**usage))

    guard = viability.CappedTransport(transport, path)
    with attributed(Attribution(phase="judge_admission", arm=viability.ARM, task_id="154"), 0):
        with pytest.raises(ConfigError, match="full reservation retained"):
            guard(model="deepseek-v4-flash", messages=[], max_tokens=2048)
        with pytest.raises(InfraError, match="stopped"):
            guard(model="deepseek-v4-flash", messages=[], max_tokens=2048)
    state = json.loads(path.read_text())
    records = viability.jsonl(path.with_suffix(".attempts.jsonl"))
    assert len(calls) == 1 and state["actual_usd"] == 0 and not state["inflight"]
    assert state["uncertain_usd"] == records[0]["reserved_usd"] > 0
    assert records[-1]["status"] == state["stopped"] == "invalid_usage"
    assert state["accounting_error"] is True
    assert viability.decision_for(_result(viability), state)["decision"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_nonfinite_or_negative_persisted_cost_refuses_dispatch(viability: Any, bad: float) -> None:
    path = viability.RUN / "cap.json"
    viability.initialize_cap(path, "engineering")
    state = json.loads(path.read_text())
    state["actual_usd"] = bad
    viability.write_json(path, state)
    with pytest.raises(ConfigError, match="monetary state"):
        viability.check_cap(path, "offline")


def test_success_requires_the_other_task_to_exhaust_and_all_accepted_k16_completed(
    viability: Any,
) -> None:
    result = _result(viability, endpoints=1)
    result["tasks"]["159"]["summary"]["designer_calls"] = 1
    assert viability.decision_for(result, {})["decision"] != "LOW_IMPLEMENTATION_WORKS"
    result["tasks"]["159"]["summary"]["designer_calls"] = 3
    assert viability.decision_for(result, {})["decision"] == "LOW_IMPLEMENTATION_WORKS"
    del result["tasks"]["154"]["summary"]["confirmation"]
    assert viability.decision_for(result, {})["decision"] == "INCOMPLETE"


def test_exact_archived_154_159_evidence_is_reused_and_order_tampering_rejected(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    prior = viability.ROOT / "runs/e6-iterative-low-viability-v3"
    required = [
        prior / f"task-{task}" / name
        for task in viability.TASKS
        for name in ("original_failures.json", "privileged_reference.json")
    ]
    if any(not path.exists() for path in required):
        pytest.skip("requires locally preserved ignored V3 evidence/reference artifacts")
    prior_manifest = (
        viability.ROOT
        / "experiments/alfworld_e6/frozen/iterative_low_viability_v3/input_manifest.json"
    )
    monkeypatch.setattr(viability, "PRIOR_MANIFEST", prior_manifest)
    rows = [
        r
        for r in json.loads(prior_manifest.read_text())["tasks"]
        if r["task_id"] in viability.TASKS
    ]
    imported = {}
    for row in rows:
        task = row["task_id"]
        for name in ("original_failures.json", "privileged_reference.json"):
            payload = (prior / f"task-{task}" / name).read_bytes()
            new = viability.RUN / f"task-{task}" / name
            viability.write_exact(new, payload)
            imported[str(new)] = hashlib.sha256(payload).hexdigest()
    viability.write_json(viability.RUN / "prepared.json", rows)
    viability.write_json(viability.FROZEN / "saved_candidates.json", [])
    viability.write_json(viability.PRIVATE / "saved_candidates.json", [])
    viability.write_json(
        viability.FROZEN / "input_manifest.json",
        {
            "tasks": [viability.public_task_metadata(r) for r in rows],
            "prior_manifest_sha256": viability.PRIOR_MANIFEST_SHA,
            "archived_file_hashes": {},
            "imported_file_hashes": imported,
            "saved_candidates_sha256": viability.digest(
                (viability.PRIVATE / "saved_candidates.json").read_text()
            ),
            "saved_candidate_metadata_sha256": viability.digest(
                (viability.FROZEN / "saved_candidates.json").read_text()
            ),
        },
    )
    assert [r["reference_id"] for r in viability.verify_input_set()] == [
        "f0a58f89e43dcbbb",
        "b68a542228b51665",
    ]
    path = viability.RUN / "task-154/original_failures.json"
    failures = json.loads(path.read_text())
    viability.write_json(path, list(reversed(failures)))
    with pytest.raises(ConfigError, match="content changed"):
        viability.verify_input_set()


def test_validation_runs_only_fixed_judge_calls_and_cannot_restart(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows, outcomes = _validation_fixture(viability)
    monkeypatch.setattr(viability, "ensure_frozen", lambda **kwargs: {"offline": True})
    monkeypatch.setattr(
        viability,
        "build",
        lambda **kwargs: pytest.fail("validation must not build policy substrate"),
    )
    outcomes[0]["result"]["request"] = {"large_raw_input": "x" * 1_000_000}
    planned = iter(outcomes)
    calls = []

    def make_judge(stage: str, task: str, phase: str) -> Any:
        assert stage == "validation" and phase == "judge_validation"
        result = next(planned)["result"]

        def judge(request: Any) -> Any:
            calls.append(request.model_dump(mode="json"))
            assert "case_id" not in request.model_dump(mode="json")
            return SimpleNamespace(as_record=lambda: result, verdict=result["decision"]["verdict"])

        return SimpleNamespace(judge=judge)

    monkeypatch.setattr(viability, "make_judge", make_judge)
    result = viability.validate()
    assert result["decision"] == "JUDGE_GATE_READY" and len(calls) == 21
    assert "request" not in result["outcomes"][0]["result"]
    assert (viability.VALIDATION / "result.json").stat().st_size < 100_000
    viability.verify_validation_result(result)
    assert len(list((viability.VALIDATION / "operations").glob("*.json"))) == 21
    for case in rows:
        if case["repeat_of"]:
            first = next(i for i, r in enumerate(rows) if r["case_id"] == case["repeat_of"])
            repeat = rows.index(case)
            assert calls[first] == calls[repeat]
    with pytest.raises(ConfigError, match="existing cap"):
        viability.validate()
    assert len(calls) == 21 and not (viability.RUN / "cap.json").exists()


def test_adaptation_requires_saved_replay_and_never_builds_early(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(viability, "ensure_frozen", lambda **kwargs: {})
    monkeypatch.setattr(viability, "verify_input_set", lambda: [])
    monkeypatch.setattr(viability, "build", lambda **kwargs: pytest.fail("early DESIGN"))
    viability.write_json(
        viability.RUN / "saved_replay.json",
        {"status": "interrupted", "cases": [], "interruption": {"kind": "offline"}},
    )
    with pytest.raises(ConfigError, match="replay has not completed"):
        viability.adapt()
    assert not (viability.RUN / "results.json").exists()


def test_independent_client_context_attribution_matches_request(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from aea.core.hashing import sha256_of
    from aea.llm.attribution import current_attribution
    from aea.llm.types import ChatResponse, ToolCall, Usage
    from aea.privilege_judge import JUDGE_TOOL_NAME, PrivilegeJudgeInput

    viability.initialize_cap(viability.VALIDATION / "cap.json", "validation")
    seen = []

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def complete(self, request: Any) -> Any:
            attr, seed = current_attribution()
            assert attr == request.attribution and seed == request.seed == 0
            seen.append(request)
            decision = PrivilegeDecision(
                verdict="PASS",
                leakage_score=0.0,
                information="generic",
                reference_evidence="none",
                public_evidence_check="goal",
                candidate_evidence="source",
                activation="all",
                leak_type="NONE",
                revision_reason="none",
            )
            return ChatResponse(
                content="",
                reasoning=None,
                tool_calls=(
                    ToolCall(id="offline", name=JUDGE_TOOL_NAME, arguments=decision.model_dump()),
                ),
                finish_reason="tool_calls",
                usage=Usage(prompt_tokens=10, completion_tokens=10),
                model="deepseek-v4-flash",
                provider=None,
                upstream_cost=None,
                response_id="offline",
                request_sha256=sha256_of({"provider": "deepseek", "request": request.model_dump()}),
                latency_ms=0,
                created_at=datetime.now(UTC),
            )

    monkeypatch.setattr(viability, "OpenAICompatibleClient", Client)
    monkeypatch.setattr(
        viability, "make_openai_transport", lambda **kwargs: lambda **wire: pytest.fail("no API")
    )
    monkeypatch.setattr(
        viability, "load_settings", lambda *args: SimpleNamespace(require=lambda name: "offline")
    )
    monkeypatch.setattr(viability, "load_pricing", lambda *args: None)
    judge = viability.make_judge("validation", "110", "judge_validation")
    record = judge.judge(
        PrivilegeJudgeInput(
            task_spec="fixture",
            public_task_information="goal",
            designer_evidence_summary="historical only",
            learner_authorized_evidence=[],
            privileged_reference={},
            candidate_artifact="source",
            candidate_artifact_type="python",
            candidate_change_summary="generic",
            benchmark_contract_summary="current episode only",
        )
    )
    assert record.verdict == "PASS" and len(seen) == 1
    assert current_attribution()[0].phase == "none"
    assert len(viability.jsonl(viability.VALIDATION / "judge_requests/requests.jsonl")) == 1


def test_missing_cap_does_not_reset_an_existing_paid_journal(viability: Any) -> None:
    viability.write_json(
        viability.VALIDATION / "operations/judge-01.json", {"status": "dispatched"}
    )
    with pytest.raises(ConfigError, match="existing cap/paid journal"):
        viability.initialize_cap(viability.VALIDATION / "cap.json", "validation")
    assert not (viability.VALIDATION / "cap.json").exists()


def test_prepare_original16_loop_reads_real_singleton_archives_and_keeps_exact_hashes(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior = viability.ROOT / "runs/e6-iterative-low-viability-v3"
    paths = [
        prior / f"task-{task}/original-{index:02}.json"
        for task in viability.TASKS
        for index in range(1, 17)
    ]
    if any(not path.exists() for path in paths):
        pytest.skip("requires locally preserved ignored original16 V3 artifacts")
    monkeypatch.setattr(viability, "PRIOR", prior)
    manifest = (
        viability.ROOT
        / "experiments/alfworld_e6/frozen/iterative_low_viability_v3/input_manifest.json"
    )
    rows = {r["task_id"]: r for r in json.loads(manifest.read_text())["tasks"]}
    for task in viability.TASKS:
        originals, hashes = viability.verified_originals(task, rows[task])
        assert len(originals) == len(hashes) == 16
        assert [r["episode_id"] for r in originals] == rows[task]["all_original_episode_ids"]
        assert [viability.digest(r) for r in originals] == rows[task]["all_original_trace_sha256"]
        assert viability.digest(originals) == rows[task]["original_zero_evidence_sha256"]
        changed = {
            **rows[task],
            "all_original_episode_ids": list(reversed(rows[task]["all_original_episode_ids"])),
        }
        with pytest.raises(ConfigError, match="original16 provenance"):
            viability.verified_originals(task, changed)


@pytest.mark.parametrize("payload", [{}, [], [{}, {}], ["not-a-trace"]])
def test_prepare_original_reader_refuses_non_singleton_archive_shapes(
    viability: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: Any
) -> None:
    monkeypatch.setattr(viability, "ROOT", tmp_path)
    monkeypatch.setattr(viability, "PRIOR", tmp_path / "prior")
    viability.write_json(viability.PRIOR / "task-154/original-01.json", payload)
    with pytest.raises(ConfigError, match="singleton list"):
        viability.verified_originals(154, {})


PRIVATE_CANARY = "PRIVATE_INSTANCE_FACT_AND_RAW_PROGRAM_MUST_STAY_LOCAL"


def test_validation_input_bytes_are_private_and_content_hash_preserved(viability: Any) -> None:
    from aea.privilege_judge import PrivilegeJudgeInput, canonical_json

    request = PrivilegeJudgeInput(
        task_spec="synthetic private task",
        public_task_information="public goal",
        designer_evidence_summary=PRIVATE_CANARY,
        learner_authorized_evidence=[],
        privileged_reference={"steps": [PRIVATE_CANARY]},
        candidate_artifact=PRIVATE_CANARY,
        candidate_artifact_type="python",
        candidate_change_summary=PRIVATE_CANARY,
        optional_runtime_surface_deltas={"after": PRIVATE_CANARY},
        benchmark_contract_summary="current episode only",
    )
    before = (canonical_json(request.model_dump(mode="json")) + "\n").encode()
    row = viability.store_validation_input(
        "saved_154_C1", request, task=154, expected=None, role="inspection", call_index=1
    )
    path = viability.private_input_path(row)
    assert path.is_relative_to(viability.PRIVATE)
    assert path.read_bytes() == before
    assert row["input_file_sha256"] == viability.digest(before.decode())
    assert row["input_bytes"] == len(before)
    assert PRIVATE_CANARY not in json.dumps(row)
    assert not (viability.FROZEN / row["input_file"]).exists()
    path.write_bytes(before + b" ")
    assert viability.digest(path.read_text()) != row["input_file_sha256"]
    with pytest.raises(ConfigError, match="locator"):
        viability.private_input_path({**row, "input_file": "../../public.json"})


def test_public_saved_and_task_metadata_never_export_source_or_reference_prose(
    viability: Any,
) -> None:
    saved = [
        {
            "task_id": 154,
            "call_index": 1,
            "arguments": {
                "families": [
                    {
                        "name": PRIVATE_CANARY,
                        "rules_code": PRIVATE_CANARY,
                        "mechanism_summary": PRIVATE_CANARY,
                        "why": PRIVATE_CANARY,
                    }
                ]
            },
        }
    ]
    metadata = viability.saved_candidate_metadata(saved)
    assert set(metadata[0]) == {
        "task_id",
        "call_index",
        "source_sha256",
        "source_bytes",
        "arguments_sha256",
    }
    assert metadata[0]["source_sha256"] == viability.digest(PRIVATE_CANARY)
    assert metadata[0]["source_bytes"] == len(PRIVATE_CANARY.encode())
    assert PRIVATE_CANARY not in json.dumps(metadata)
    row = {
        "task_id": 154,
        "reference_sha256": "a" * 64,
        "reference_reason": PRIVATE_CANARY,
        "reference_steps": 16,
        "reference": PRIVATE_CANARY,
        "goal": PRIVATE_CANARY,
    }
    public = viability.public_task_metadata(row)
    assert public == {"task_id": 154, "reference_sha256": "a" * 64, "reference_steps": 16}


def _private_result_fixture(module: Any) -> dict[str, Any]:
    cases, outcomes = _validation_fixture(module)
    full_rows, compact_rows = [], []
    for case, outcome in zip(cases, outcomes, strict=True):
        judge = outcome["result"]
        judge["decision"].update(
            {
                key: PRIVATE_CANARY
                for key in (
                    "information",
                    "reference_evidence",
                    "public_evidence_check",
                    "candidate_evidence",
                    "activation",
                    "revision_reason",
                )
            }
        )
        judge["decision"].update(leak_type="OTHER", leakage_score=0.5)
        judge.update(
            request={"raw": PRIVATE_CANARY},
            response={"raw": PRIVATE_CANARY},
            generated_uncertainty=PRIVATE_CANARY,
        )
        row = {
            "case_id": case["case_id"],
            "expected_verdict": case["expected_verdict"],
            "role": case["role"],
            "result": judge,
            "full_judge_record_sha256": module.digest(judge),
        }
        full_rows.append(row)
        compact_rows.append(
            {**row, "result": {k: v for k, v in judge.items() if k not in ("request", "response")}}
        )
    result = {
        **module.validation_decision(cases, compact_rows),
        "outcomes": compact_rows,
        "freeze": {"private_debug": PRIVATE_CANARY},
        "cap": {"private_debug": PRIVATE_CANARY},
    }
    module.write_json(module.VALIDATION / "result.json", result)
    for row in full_rows:
        module.append_jsonl(module.VALIDATION / "judgments.jsonl", row)
    return result


def test_public_validation_export_replaces_every_evidence_field_with_hash_and_length(
    viability: Any,
) -> None:
    result = _private_result_fixture(viability)
    private_payload = (viability.VALIDATION / "result.json").read_bytes()
    public = viability.public_validation_result(
        result, private_result_sha256=viability.digest(private_payload.decode())
    )
    assert PRIVATE_CANARY not in json.dumps(public)
    assert public["private_result_sha256"] == viability.digest(private_payload.decode())
    assert public["decision"] == "JUDGE_GATE_READY" and len(public["outcomes"]) == 21
    evidence = public["outcomes"][0]["evidence_fields"]
    assert evidence["reference_evidence"] == {
        "sha256": viability.digest(PRIVATE_CANARY),
        "bytes": len(PRIVATE_CANARY.encode()),
    }
    assert [r["verdict"] for r in public["outcomes"]] == [
        r["result"]["decision"]["verdict"] for r in result["outcomes"]
    ]
    assert (viability.VALIDATION / "result.json").read_bytes() == private_payload


def test_freeze_writes_only_public_metadata_and_verifies_private_result_bytes(
    viability: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    viability.initialize_cap(viability.VALIDATION / "cap.json", "validation")
    _private_result_fixture(viability)
    before = (viability.VALIDATION / "result.json").read_bytes()
    monkeypatch.setattr(viability, "ensure_frozen", lambda **kwargs: {})
    monkeypatch.setattr(viability, "write_prereg_template", lambda *args: None)
    viability.freeze_validation()
    public_path = viability.FROZEN / "validation_result.json"
    assert PRIVATE_CANARY not in public_path.read_text()
    assert (viability.VALIDATION / "result.json").read_bytes() == before
    viability.verify_frozen_validation_result()
    private = json.loads(before)
    private["extra_private_metadata"] = PRIVATE_CANARY
    viability.write_json(viability.VALIDATION / "result.json", private)
    with pytest.raises(ConfigError, match="public hash binding"):
        viability.verify_frozen_validation_result()


def test_public_report_and_console_do_not_export_private_error_or_cost_debug(
    viability: Any,
) -> None:
    viability.write_json(
        viability.RUN / "STOP.json",
        {"type": "ConfigError", "kind": "implementation", "reason": PRIVATE_CANARY},
    )
    result = viability.report()
    assert result["decision"] == "IMPLEMENTATION_FAILURE"
    assert PRIVATE_CANARY in (viability.PRIVATE / "report.json").read_text()
    assert PRIVATE_CANARY not in (viability.BASE / "report.json").read_text()
    assert PRIVATE_CANARY not in json.dumps(viability.public_stage_summary(result))


@pytest.mark.parametrize(
    "key,value",
    [
        ("endpoint_tasks", PRIVATE_CANARY),
        ("search_accepts", {"private": PRIVATE_CANARY}),
        ("completed_tasks", True),
        ("K16_B_L", -1),
        ("completed_K16", 1.5),
        ("engineering_only", PRIVATE_CANARY),
        ("fresh_scientific_efficacy", 1),
        ("end_to_end_functional_viability", [PRIVATE_CANARY]),
    ],
)
def test_public_report_rejects_private_values_under_allowed_scalar_keys(
    viability: Any, key: str, value: Any
) -> None:
    with pytest.raises(ConfigError) as error:
        viability.public_report({key: value})
    assert PRIVATE_CANARY not in str(error.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("returned_ledger_usd", PRIVATE_CANARY),
        ("conservative_committed_usd", {"private": PRIVATE_CANARY}),
        ("returned_ledger_usd", float("nan")),
        ("returned_ledger_usd", float("inf")),
        ("returned_ledger_usd", -1.0),
        ("conservative_committed_usd", True),
        ("call_rows", PRIVATE_CANARY),
        ("policy_rollout_rows", 1.5),
    ],
)
def test_public_cost_export_rejects_nested_nonfinite_or_non_numeric_values(
    viability: Any, key: str, value: Any
) -> None:
    cost = {
        "returned_ledger_usd": 0.0,
        "conservative_committed_usd": 0.0,
        "call_rows": 0,
        "policy_rollout_rows": 0,
        key: value,
    }
    with pytest.raises(ConfigError) as error:
        viability.public_report({"validation_cost": cost})
    assert PRIVATE_CANARY not in str(error.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("task_id", PRIVATE_CANARY),
        ("reference_status", PRIVATE_CANARY),
        ("reference_sha256", PRIVATE_CANARY),
        ("reference_id", PRIVATE_CANARY),
        ("all_original_episode_ids", [PRIVATE_CANARY]),
        ("selected_trace_sha256", [{"private": PRIVATE_CANARY}]),
        ("reference_ok", PRIVATE_CANARY),
        ("reference_steps", PRIVATE_CANARY),
        ("valid_episode_execution_indices", [PRIVATE_CANARY]),
        ("original_k16", PRIVATE_CANARY),
        ("all_original_trace_sha256", PRIVATE_CANARY),
    ],
)
def test_public_task_export_rejects_private_values_under_allowed_keys(
    viability: Any, key: str, value: Any
) -> None:
    with pytest.raises(ConfigError) as error:
        viability.public_task_metadata({key: value})
    assert PRIVATE_CANARY not in str(error.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("decision", [PRIVATE_CANARY]),
        ("status", {"raw": PRIVATE_CANARY}),
        ("validation_decision", PRIVATE_CANARY),
    ],
)
def test_public_console_enum_validation_never_uses_unhashable_private_values(
    viability: Any, key: str, value: Any
) -> None:
    with pytest.raises(ConfigError) as error:
        viability.public_stage_summary({key: value})
    assert PRIVATE_CANARY not in str(error.value)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("result", "decision", PRIVATE_CANARY),
        ("result", "cases_completed", PRIVATE_CANARY),
        ("row", "case_id", PRIVATE_CANARY),
        ("row", "role", PRIVATE_CANARY),
        ("row", "expected_verdict", PRIVATE_CANARY),
        ("row", "full_judge_record_sha256", PRIVATE_CANARY),
        ("judge", "input_sha256", PRIVATE_CANARY),
        ("judge", "request_sha256", {"raw": PRIVATE_CANARY}),
        ("decision", "verdict", PRIVATE_CANARY),
        ("decision", "leak_type", PRIVATE_CANARY),
        ("decision", "leakage_score", PRIVATE_CANARY),
        ("decision", "leakage_score", float("nan")),
        ("decision", "leakage_score", 1.1),
    ],
)
def test_public_validation_export_rejects_private_values_in_allowed_verdict_hash_fields(
    viability: Any, section: str, key: str, value: Any
) -> None:
    result = _private_result_fixture(viability)
    row = result["outcomes"][0]
    target = {
        "result": result,
        "row": row,
        "judge": row["result"],
        "decision": row["result"]["decision"],
    }[section]
    target[key] = value
    with pytest.raises(ConfigError) as error:
        viability.public_validation_result(result, private_result_sha256="0" * 64)
    assert PRIVATE_CANARY not in str(error.value)


@pytest.mark.parametrize("key", ["task_id", "call_index"])
def test_public_saved_metadata_rejects_private_text_disguised_as_identifier(
    viability: Any, key: str
) -> None:
    row = {
        "task_id": 154,
        "call_index": 1,
        "arguments": {"families": [{"rules_code": PRIVATE_CANARY}]},
        key: PRIVATE_CANARY,
    }
    with pytest.raises(ConfigError) as error:
        viability.saved_candidate_metadata([row])
    assert PRIVATE_CANARY not in str(error.value)
