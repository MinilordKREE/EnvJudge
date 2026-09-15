"""Prospective single-arm viability orchestration; only offline fixtures and transports."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Trace

from aea.errors import InfraError
from aea.semantic_privilege import Decision
from tests.unit.test_llm_v1 import _trace


@pytest.fixture
def viability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = importlib.import_module("scripts.e6_iterative_low_viability")
    monkeypatch.setattr(module, "RUN", tmp_path / "run")
    monkeypatch.setattr(module, "FROZEN", tmp_path / "frozen")
    monkeypatch.setattr(module, "ensure_frozen", lambda **kwargs: {"offline_test": True})
    module.write_json(module.FROZEN / "used_task_audit.json", {"never_used_ids": list(range(20))})
    return module


def _wire() -> dict[str, Any]:
    return {
        "model": "qwen/qwen3-8b",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 16,
    }


def _returned(**wire: Any) -> Any:
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, cost=0))


def _cap_update(module: Any, **changes: Any) -> None:
    path = module.RUN / "cap.json"
    state = json.loads(path.read_text())
    state.update(changes)
    module.write_json(path, state)


def test_physical_screening_cap_is_eight_and_sticky(viability: Any) -> None:
    viability.initialize_cap()
    _cap_update(viability, actual_usd=7.99999)
    calls: list[Any] = []
    capped = viability.CappedTransport(
        lambda **wire: calls.append(wire), viability.RUN / "cap.json"
    )
    with pytest.raises(InfraError, match="screening_cost_cap"):
        capped(**_wire())
    assert calls == []
    _cap_update(viability, actual_usd=0, phase="adaptation")
    with pytest.raises(InfraError, match="screening_cost_cap"):
        capped(**_wire())
    assert calls == [] and json.loads((viability.RUN / "cap.json").read_text())["attempts"] == 0


def test_child_policy_factory_uses_twenty_total_cap_and_preserves_screening_cost(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viability.initialize_cap()
    _cap_update(viability, actual_usd=12.5, phase="adaptation", screening_committed_usd=6.0)

    def fake_init(self: Any, **kwargs: Any) -> None:
        self._client = SimpleNamespace(_transport=_returned)

    monkeypatch.setattr(viability.AeaLLMClient, "__init__", fake_init)
    client = viability.CappedPolicyClient(cap_path=str(viability.RUN / "cap.json"))
    assert isinstance(client._client._transport, viability.CappedTransport)
    client._client._transport(**_wire())
    state = json.loads((viability.RUN / "cap.json").read_text())
    assert state["actual_usd"] > 12.5 and state["screening_committed_usd"] == 6.0
    assert state["attempts"] == 1
    _cap_update(viability, actual_usd=19.99999)
    with pytest.raises(InfraError, match="cost_cap"):
        client._client._transport(**_wire())
    assert json.loads((viability.RUN / "cap.json").read_text())["attempts"] == 1


def test_failed_transport_reservation_is_retained_across_retry(viability: Any) -> None:
    viability.initialize_cap()
    count = 0

    def transport(**wire: Any) -> Any:
        nonlocal count
        count += 1
        if count == 1:
            raise TimeoutError("response lost after dispatch")
        return _returned(**wire)

    capped = viability.CappedTransport(transport, viability.RUN / "cap.json")
    with pytest.raises(TimeoutError):
        capped(**_wire())
    first = json.loads((viability.RUN / "cap.json").read_text())
    capped(**_wire())
    second = json.loads((viability.RUN / "cap.json").read_text())
    assert first["uncertain_usd"] > 0
    assert second["uncertain_usd"] == first["uncertain_usd"]
    assert second["actual_usd"] > 0 and second["attempts"] == 2 and second["inflight"] == {}
    assert viability.committed_cost(second) == second["actual_usd"] + second["uncertain_usd"]


@pytest.mark.parametrize("first_success_index", [1, 3])
def test_screen_stops_on_first_success_then_exactly_four_zero_tasks(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    first_success_index: int,
) -> None:
    calls: list[tuple[int, int]] = []
    counts: dict[int, int] = {}

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        number = int(task.task_id)
        assert n == 1 and not candidate.rules_code and not candidate.in_env_actions
        counts[number] = counts.get(number, 0) + 1
        calls.append((number, n))
        trace = _trace(number == 0 and counts[number] == first_success_index, candidate=candidate)
        trace.rollout_seed = number
        trace.episode_id = f"original-{number}-{counts[number]}"
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    result = json.loads((viability.RUN / "screening.json").read_text())
    assert result["status"] == "qualified" and result["qualified"] == [1, 2, 3, 4]
    assert counts == {0: first_success_index, 1: 16, 2: 16, 3: 16, 4: 16}
    assert len(calls) == 64 + first_success_index
    assert result["tasks"]["0"]["status"] == "rejected_first_success"
    assert all(len(result["tasks"][str(t)]["episodes"]) == 16 for t in [1, 2, 3, 4])
    before = list(calls)
    with pytest.raises(viability.ConfigError, match="already started"):
        viability.screen()
    assert calls == before


def test_strict_pool_rejects_recovered_provider_retry_without_resampling(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts: dict[int, int] = {}
    monkeypatch.setattr(viability, "STRICT_PROVIDER_ERRORS", True, raising=False)

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        number = int(task.task_id)
        counts[number] = counts.get(number, 0) + 1
        if number == 0:
            viability.append_jsonl(
                viability.RUN / "ledger.offline.jsonl",
                {
                    "event": "infra_retry",
                    "phase": kwargs["attribution"].phase,
                    "task_id": str(number),
                },
            )
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = number
        trace.episode_id = f"retry-test-{number}-{counts[number]}"
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    result = json.loads((viability.RUN / "screening.json").read_text())
    assert result["qualified"] == [1, 2, 3, 4] and counts[0] == 1
    assert result["tasks"]["0"]["status"] == "rejected_provider_error"
    assert result["tasks"]["0"]["episodes"][0]["provider_retry_or_failure_events"] == 1


def test_pool_never_extends_beyond_frozen_twenty_ids(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        number = int(task.task_id)
        calls.append(number)
        trace = _trace(True, candidate=candidate)
        trace.rollout_seed = number
        trace.episode_id = f"first-success-{number}"
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    result = json.loads((viability.RUN / "screening.json").read_text())
    assert calls == list(range(20))
    assert result["status"] == "INSUFFICIENT_FRESH_LOW" and result["qualified"] == []


def test_reused_episode_identity_stops_pool_as_implementation_failure(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        nonlocal calls
        calls += 1
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = int(task.task_id)
        trace.episode_id = "duplicate-episode"
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    result = json.loads((viability.RUN / "screening.json").read_text())
    assert calls == 2 and result["status"] == "IMPLEMENTATION_FAILURE"
    assert "reused" in result["interruption"]["reason"]
    assert result["qualified"] == []


def test_freeze_uses_all_sixteen_then_seeded_three_and_one_reference_per_task(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aea.designer import Reference, serialize_low
    from aea.stage import seeded_failures
    from tests.unit.test_iterative_low import REF

    seen: dict[int, int] = {}
    reference_calls: list[int] = []

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        number = int(task.task_id)
        seen[number] = seen.get(number, 0) + 1
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = number
        trace.episode_id = f"freeze-{number}-{seen[number]}"
        return [trace]

    def provider(task: Any) -> Any:
        number = int(task.task_id)
        reference_calls.append(number)
        return REF if number < 2 else Reference(False, "fixture-unavailable")

    sub = SimpleNamespace(
        rollouts=rollouts,
        reference_provider=lambda cfg: provider,
        env_import="frozen-fixture",
        reset_options={"split": "train", "repetition_threshold": 0},
        max_steps=50,
        task_prompt="frozen-policy",
        policy_spec_kwargs={"action_format": "think_action", "max_history": 200},
    )
    monkeypatch.setattr(viability, "build", lambda **kwargs: sub)
    viability.screen()
    viability.freeze_inputs()
    manifest = json.loads((viability.RUN / "input_manifest.json").read_text())
    assert reference_calls == [0, 1, 2, 3] and seen == {0: 16, 1: 16, 2: 16, 3: 16}
    assert [r["task_id"] for r in manifest["tasks"]] == [0, 1, 2, 3]
    assert [r["reference_status"] for r in manifest["tasks"]] == [
        "REFERENCE_AVAILABLE",
        "REFERENCE_AVAILABLE",
        "REFERENCE_UNAVAILABLE",
        "REFERENCE_UNAVAILABLE",
    ]
    for row in manifest["tasks"]:
        task = row["task_id"]
        originals: list[Trace] = []
        for index in range(1, 17):
            originals.extend(
                viability.Trace.model_validate(r)
                for r in json.loads(
                    (viability.RUN / f"task-{task}/original-{index:02}.json").read_text()
                )
            )
        failures = seeded_failures(originals, 3, seed=task)
        assert row["evidence_ids"] == [t.episode_id for t in failures]
        assert len(row["all_original_episode_ids"]) == 16 and row["evidence_n"] == 16
        reference = viability.read_reference(task)
        assert (
            row["designer_evidence_sha256"]
            == serialize_low(failures, 0.0, 16, reference, rich=True).sha256
        )
    with pytest.raises(viability.ConfigError, match="already frozen"):
        viability.freeze_inputs()
    assert reference_calls == [0, 1, 2, 3]


def test_changed_screening_trace_cannot_become_frozen_designer_evidence(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[int, int] = {}
    reference_calls: list[Any] = []

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        number = int(task.task_id)
        calls[number] = calls.get(number, 0) + 1
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = number
        trace.episode_id = f"untampered-{number}-{calls[number]}"
        return [trace]

    sub = SimpleNamespace(
        rollouts=rollouts, reference_provider=lambda cfg: lambda task: reference_calls.append(task)
    )
    monkeypatch.setattr(viability, "build", lambda **kwargs: sub)
    viability.screen()
    path = viability.RUN / "task-0/original-01.json"
    changed = json.loads(path.read_text())
    changed[0]["steps"][0]["raw_observation"]["text"] += "\nWRAPPER_OUTPUT_CANNOT_LAUNDER"
    viability.write_json(path, changed)
    with pytest.raises(viability.ConfigError, match="changed before evidence freeze"):
        viability.freeze_inputs()
    assert reference_calls == [] and not (viability.RUN / "input_manifest.json").exists()


def _design_fixture(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    codes: list[str],
    verdicts: list[Decision] | None = None,
    outcomes: Any = None,
) -> tuple[Any, Any, dict[str, Any], list[Any]]:
    from dataclasses import replace

    from aea.semantic_low import SemanticAdmissionError
    from aea.semantic_privilege import SemanticGateInput, screen_semantic_privilege
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
    viability.initialize_cap()
    _cap_update(viability, phase="adaptation")
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
            result = screen_semantic_privilege(SemanticGateInput(family.template, REF, "", (), "9"))
            result = replace(
                result,
                decision=decision,
                findings=tuple(replace(f, decision=decision) for f in result.findings),
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


def test_semantic_uncertain_stops_before_certification_policy_and_redesign(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_assistive_rules import HINT

    sub, designer, shared, events = _design_fixture(
        viability,
        monkeypatch,
        [HINT, HINT + "\n# unused"],
        verdicts=["UNCERTAIN"],
    )
    result = viability.run_task(sub, 9, shared)
    assert result["status"] == "inconclusive" and "semantic_privilege_uncertain" in result["reason"]
    assert designer.calls == 1 and result["adaptation_rollouts"] == 0
    assert result["candidates"][0]["remaining_calls"] == 2
    assert not any(e[0] in ["certify", "policy"] for e in events)
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


def test_original_screening_rejects_a_wrapped_environment_trace(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from envharness.core.types import Candidate

    calls = 0

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        nonlocal calls
        calls += 1
        trace = _trace(False, candidate=Candidate(rules_code="WRONG_WRAPPED_ENVIRONMENT"))
        trace.rollout_seed = int(task.task_id)
        trace.episode_id = "wrong-original-source"
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    result = json.loads((viability.RUN / "screening.json").read_text())
    assert calls == 1 and result["status"] == "IMPLEMENTATION_FAILURE" and result["qualified"] == []


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


def test_decision_separates_functional_failure_and_infrastructure_and_prioritizes_correctness(
    viability: Any,
) -> None:
    def results(confirmed: int, viable: int, referenced: int = 4) -> dict[str, Any]:
        return {
            "tasks": {
                str(i): {
                    "original": {"reference_ok": i < referenced},
                    "status": "completed" if i < referenced else "reference_unavailable",
                    "summary": {
                        "status": "inconclusive",
                        "reason": "semantic_privilege_uncertain",
                        "first_viable_family_index": 1 if i < viable else None,
                        "confirmation": {"in_band_l": i < confirmed, "in_band_t": False},
                    },
                }
                for i in range(4)
            },
            "interruption": None,
        }

    assert viability.decision_for(results(0, 0), {})["decision"] == "LOW_NOT_WORKING"
    assert viability.decision_for(results(0, 2), {})["decision"] == "LOW_PARTIAL_SIGNAL"
    assert viability.decision_for(results(1, 1), {})["decision"] == "LOW_PARTIAL_SIGNAL"
    assert viability.decision_for(results(2, 2), {})["decision"] == "LOW_VIABLE"
    assert viability.decision_for(results(0, 0, 2), {})["decision"] == "INCONCLUSIVE"
    limited = results(0, 0)
    limited["interruption"] = {"kind": "smoke_cost_cap", "reason": "cap"}
    assert viability.decision_for(limited, {})["decision"] == "INCONCLUSIVE"
    already_viable = results(2, 2)
    already_viable["interruption"] = {"kind": "smoke_cost_cap", "reason": "later cap"}
    assert viability.decision_for(already_viable, {})["decision"] == "LOW_VIABLE"
    already_viable["correctness_audit"] = {"decision": "IMPLEMENTATION_FAILURE"}
    assert viability.decision_for(already_viable, {})["decision"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize(
    "error", ["provider request retries exhausted", "environment transition failed"]
)
def test_terminal_episode_error_stops_pool_without_replacement(
    viability: Any, monkeypatch: pytest.MonkeyPatch, error: str
) -> None:
    calls = 0

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        nonlocal calls
        calls += 1
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = int(task.task_id)
        trace.episode_id = "terminal-error"
        trace.error = error
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    result = json.loads((viability.RUN / "screening.json").read_text())
    assert calls == 1 and result["status"] == "INCONCLUSIVE" and result["qualified"] == []
    assert result["interruption"]["kind"] == "policy_episode"
    assert error in result["interruption"]["reason"]
    assert (viability.RUN / "STOP.json").exists()
