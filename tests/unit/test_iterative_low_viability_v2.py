"""Corrected screening semantics, using only local fake episodes and transports."""

from __future__ import annotations

import ast
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

from aea.errors import ConfigError, InfraError
from tests.unit.test_iterative_low import REF
from tests.unit.test_iterative_low_viability import _cap_update, _returned, _wire
from tests.unit.test_llm_v1 import _trace


@pytest.fixture
def viability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = importlib.import_module("scripts.e6_iterative_low_viability_v2")
    monkeypatch.setattr(module, "RUN", tmp_path / "run")
    monkeypatch.setattr(module, "FROZEN", tmp_path / "frozen")
    monkeypatch.setattr(module, "ensure_frozen", lambda **kwargs: {"offline_test": True})
    module.write_json(
        module.FROZEN / "used_task_audit.json", {"never_used_ids": list(range(150, 170))}
    )
    return module


def _json(module: Any, name: str) -> Any:
    return json.loads((module.RUN / name).read_text())


def _screen(
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[dict[str, Any]],
    *,
    callback: Callable[[int, int, Any], None] | None = None,
    other_success: bool = False,
) -> dict[int, int]:
    counts: dict[int, int] = {}

    def rollouts(task: Any, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        number = int(task.task_id)
        assert n == 1 and not candidate.rules_code and not candidate.in_env_actions
        counts[number] = counts.get(number, 0) + 1
        execution = counts[number]
        outcome = (
            outcomes[execution - 1]
            if number == 150 and execution <= len(outcomes)
            else {"success": other_success}
        )
        if callback is not None:
            callback(number, execution, kwargs["attribution"])
        trace = _trace(bool(outcome.get("success", False)), candidate=candidate)
        trace.error = outcome.get("error")
        trace.subprocess_stderr = outcome.get("stderr")
        trace.rollout_seed = outcome.get("seed", number)
        trace.episode_id = outcome.get("episode_id", f"screen-{number}-execution-{execution}")
        if outcome.get("wrong_candidate"):
            trace.candidate = Candidate(rules_code="unrequested wrapper")
        if outcome.get("retry"):
            module.append_jsonl(
                module.RUN / "ledger.offline.jsonl",
                {
                    "phase": kwargs["attribution"].phase,
                    "event": "infra_retry",
                    "error_kind": "timeout",
                },
            )
        return [trace]

    monkeypatch.setattr(module, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    module.screen()
    return counts


def test_a_recovered_provider_retries_preserve_sixteen_valid_failures(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _screen(viability, monkeypatch, [{"retry": True} for _ in range(16)])
    result = _json(viability, "screening.json")
    row = result["tasks"]["150"]
    assert result["status"] == "qualified" and result["qualified"] == [150, 151, 152, 153]
    assert row["status"] == "CONFIRMED_ZERO"
    assert (row["valid_episodes"], row["valid_successes"], row["executions"]) == (16, 0, 16)
    assert row["valid_episode_indices"] == list(range(1, 17))
    assert len(row["recoveries"]) == 16
    assert all(r["status"] == "RECOVERED_PROVIDER_ERROR" for r in row["recoveries"])
    assert counts == {150: 16, 151: 16, 152: 16, 153: 16}


@pytest.mark.parametrize("failures", [0, 5])
def test_b_e_first_valid_success_stops_even_after_recovered_retry(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    failures: int,
) -> None:
    counts = _screen(viability, monkeypatch, [{}] * failures + [{"success": True, "retry": True}])
    result = _json(viability, "screening.json")
    row = result["tasks"]["150"]
    assert row["status"] == "NON_ZERO" and row["valid_successes"] == 1
    assert row["valid_episodes"] == counts[150] == failures + 1
    assert result["qualified"] == [151, 152, 153, 154]
    assert len(row["recoveries"]) == 1


@pytest.mark.parametrize("valid_failures", [3, 15])
def test_c_d_f_exhausted_infrastructure_does_not_complete_or_qualify_task(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    valid_failures: int,
) -> None:
    attempts = viability.MAX_EPISODE_EXECUTIONS_PER_VALID_SLOT
    assert attempts == 3
    counts = _screen(
        viability,
        monkeypatch,
        [{}] * valid_failures + [{"error": "provider timeout", "success": True}] * attempts,
    )
    result = _json(viability, "screening.json")
    row = result["tasks"]["150"]
    assert row["status"] == "INFRA_INCONCLUSIVE"
    assert (row["valid_episodes"], row["valid_successes"]) == (valid_failures, 0)
    assert counts[150] == valid_failures + attempts
    assert result["qualified"] == [151, 152, 153, 154]
    invalid = row["episodes"][-attempts:]
    assert [r["slot_attempt"] for r in invalid] == [1, 2, 3]
    assert all(r["target_valid_index"] == valid_failures + 1 for r in invalid)
    assert all(
        not r["is_valid"] and r["behavioral_success"] is None and r["successes"] == 0
        for r in invalid
    )
    assert not (viability.RUN / f"task-150/original-{valid_failures + 1:02}.json").exists()


def test_invalid_executions_are_excluded_from_exact_frozen_evidence(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes: list[dict[str, Any]] = [
        {"error": "network lost", "success": True},
        {},
        {},
        {"error": "network lost"},
    ]
    outcomes.extend({} for _ in range(14))
    _screen(viability, monkeypatch, outcomes)
    result = _json(viability, "screening.json")
    row = result["tasks"]["150"]
    assert row["status"] == "CONFIRMED_ZERO"
    assert row["valid_episode_indices"] == [2, 3, *range(5, 19)]
    assert row["valid_episodes"] == 16 and row["executions"] == 18
    assert row["recovered_episode_executions"] == 2
    provider_calls: list[int] = []

    def provider(task: Any) -> Any:
        provider_calls.append(int(task.task_id))
        return REF

    fake = SimpleNamespace(
        reference_provider=lambda cfg: provider,
        env_import="offline.fixture",
        reset_options={},
        max_steps=50,
        task_prompt="fixture",
        policy_spec_kwargs={"action_format": "think_action", "max_history": 50},
    )
    monkeypatch.setattr(viability, "build", lambda **kwargs: fake)
    viability.freeze_inputs()
    prepared = _json(viability, "prepared.json")
    assert provider_calls == [150, 151, 152, 153]
    frozen = prepared[0]
    expected_ids = [f"screen-150-execution-{i}" for i in row["valid_episode_indices"]]
    assert frozen["all_original_episode_ids"] == expected_ids
    assert frozen["valid_episode_execution_indices"] == row["valid_episode_indices"]
    traces = [
        Trace.model_validate(_json(viability, f"task-150/original-{i:02}.json")[0])
        for i in range(1, 17)
    ]
    expected_selected = viability.seeded_failures(traces, 3, seed=150)
    assert frozen["evidence_ids"] == [t.episode_id for t in expected_selected]
    assert len(frozen["evidence_ids"]) == 3 and set(frozen["evidence_ids"]) <= set(expected_ids)
    for valid_index, execution in enumerate(row["valid_episode_indices"], 1):
        assert _json(viability, f"task-150/original-{valid_index:02}.json") == _json(
            viability, f"task-150/original-execution-{execution:02}.json"
        )
    with pytest.raises(ConfigError, match="already frozen"):
        viability.freeze_inputs()
    assert len(provider_calls) == 4


def test_g_recovered_physical_retry_retains_failed_reservation_and_valid_behavior(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    physical_count = 0

    def transport(**wire: Any) -> Any:
        nonlocal physical_count
        physical_count += 1
        if physical_count == 1:
            raise TimeoutError("ambiguous dispatched response")
        return _returned(**wire)

    def callback(task: int, execution: int, attribution: Any) -> None:
        if (task, execution) != (150, 1):
            return
        capped = viability.CappedTransport(transport, viability.RUN / "cap.json")
        with pytest.raises(TimeoutError):
            capped(**_wire())
        before = _json(viability, "cap.json")
        capped(**_wire())
        after = _json(viability, "cap.json")
        assert after["uncertain_usd"] == before["uncertain_usd"] > 0
        assert after["actual_usd"] > 0 and after["attempts"] == 2

    _screen(viability, monkeypatch, [{}] * 16, callback=callback)
    row = _json(viability, "screening.json")["tasks"]["150"]
    assert row["status"] == "CONFIRMED_ZERO" and row["valid_episodes"] == 16
    assert row["recovered_provider_errors"] == 1
    assert row["episodes"][0]["physical_provider_errors"] == 1
    state = _json(viability, "cap.json")
    attempts = viability.jsonl(viability.RUN / "cap.attempts.jsonl")
    assert [r["status"] for r in attempts] == ["ambiguous_failure", "returned"]
    assert state["uncertain_usd"] == attempts[0]["reserved_usd"]
    assert viability.committed_cost(state) == state["actual_usd"] + state["uncertain_usd"]
    assert not state["inflight"] and physical_count == 2


def test_exited_worker_orphan_is_reserved_once_and_next_execution_is_fresh(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def callback(task: int, execution: int, attribution: Any) -> None:
        if (task, execution) == (150, 1):
            _cap_update(viability, inflight={"worker-request": 0.031}, attempts=1)
        elif (task, execution) == (150, 2):
            state = _json(viability, "cap.json")
            assert (
                state["uncertain_usd"] == 0.031
                and state["inflight"] == {}
                and state["attempts"] == 1
            )
            before = (viability.RUN / "cap.attempts.jsonl").read_bytes()
            assert (
                viability.reconcile_screening_inflight(task, attribution.phase, child_returned=True)
                == 0
            )
            assert (viability.RUN / "cap.attempts.jsonl").read_bytes() == before

    counts = _screen(viability, monkeypatch, [{"error": "subprocess timeout"}], callback=callback)
    row = _json(viability, "screening.json")["tasks"]["150"]
    assert row["status"] == "CONFIRMED_ZERO" and counts[150] == 17
    assert row["recovered_episode_executions"] == 1 and row["recovered_provider_errors"] == 1
    assert row["episodes"][0]["behavioral_success"] is None
    attempts = viability.jsonl(viability.RUN / "cap.attempts.jsonl")
    assert len(attempts) == 1 and attempts[0]["attempt"] == "worker-request"
    assert attempts[0]["status"] == "orphan_reconciled"
    assert attempts[0]["reserved_usd"] == 0.031 and attempts[0]["behavioral_outcome"] is None
    state = _json(viability, "cap.json")
    assert viability.committed_cost(state) == 0.031 and state["attempts"] == 1


def test_unknown_worker_completion_stops_without_retry_or_reservation_refund(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked: list[tuple[int, int]] = []

    def callback(task: int, execution: int, attribution: Any) -> None:
        invoked.append((task, execution))
        _cap_update(viability, inflight={"unresolved-worker": 0.037}, attempts=1)
        raise TimeoutError("dispatcher did not return a trace")

    _screen(viability, monkeypatch, [], callback=callback)
    result = _json(viability, "screening.json")
    assert result["status"] == "INCONCLUSIVE" and result["qualified"] == []
    assert result["tasks"]["150"]["valid_episodes"] == 0
    state = _json(viability, "cap.json")
    assert state["inflight"] == {"unresolved-worker": 0.037} and state["uncertain_usd"] == 0
    assert state["attempts"] == 1 and invoked == [(150, 1)]
    assert viability.jsonl(viability.RUN / "cap.attempts.jsonl") == []
    with pytest.raises(InfraError, match="completion unknown"):
        viability.reconcile_screening_inflight(150, "screen", child_returned=False)
    assert _json(viability, "cap.json")["inflight"] == state["inflight"]


def test_screening_cost_limit_stops_globally_without_dispatching_or_retrying(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    physical: list[Any] = []
    invoked: list[tuple[int, int]] = []

    def callback(task: int, execution: int, attribution: Any) -> None:
        invoked.append((task, execution))
        _cap_update(viability, actual_usd=7.5, uncertain_usd=0.49999)
        capped = viability.CappedTransport(
            lambda **wire: physical.append(wire), viability.RUN / "cap.json"
        )
        with pytest.raises(InfraError, match="screening_cost_cap"):
            capped(**_wire())

    _screen(
        viability, monkeypatch, [{"error": "smoke_cost_cap: request stopped"}], callback=callback
    )
    result = _json(viability, "screening.json")
    assert result["status"] == "SCREENING_COST_LIMIT" and result["qualified"] == []
    assert list(result["tasks"]) == ["150"] and invoked == [(150, 1)] and physical == []
    assert result["tasks"]["150"]["valid_episodes"] == 0
    state = _json(viability, "cap.json")
    assert state["attempts"] == 0 and state["uncertain_usd"] == 0.49999
    summary = viability.report()
    assert summary["final_viability_decision"] == "INCONCLUSIVE"
    assert summary["screening_status"] == "SCREENING_COST_LIMIT"
    assert summary["efficacy_evidence_available"] is False


@pytest.mark.parametrize(
    "defect",
    [
        {"wrong_candidate": True},
        {"seed": 149},
        {"error": "provider_mismatch: wrong provider"},
        {"error": "subprocess exit 1", "stderr": "InfraError(kind=provider_mismatch)"},
    ],
)
def test_even_errored_execution_with_wrong_provenance_stops_globally(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    defect: dict[str, Any],
) -> None:
    counts = _screen(viability, monkeypatch, [{"error": "provider timeout", **defect}])
    result = _json(viability, "screening.json")
    assert result["status"] == "IMPLEMENTATION_FAILURE" and result["qualified"] == []
    assert result["tasks"]["150"]["valid_episodes"] == 0 and counts == {150: 1}


def test_duplicate_identity_in_invalid_then_valid_execution_is_not_replayed(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _screen(
        viability,
        monkeypatch,
        [{"error": "timeout", "episode_id": "repeated"}, {"episode_id": "repeated"}],
    )
    result = _json(viability, "screening.json")
    assert result["status"] == "IMPLEMENTATION_FAILURE" and counts == {150: 2}
    assert result["tasks"]["150"]["valid_episodes"] == 0


def test_twenty_nonzero_ids_exhaust_pool_without_expansion(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _screen(viability, monkeypatch, [], other_success=True)
    result = _json(viability, "screening.json")
    assert result["status"] == "INSUFFICIENT_FRESH_LOW" and result["qualified"] == []
    assert counts == dict.fromkeys(range(150, 170), 1)
    assert all(
        r["status"] == "NON_ZERO" and r["valid_episodes"] == 1 for r in result["tasks"].values()
    )
    assert viability.report()["final_viability_decision"] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "name",
    [
        "config",
        "scoped_three_call_budget",
        "require_pass",
        "make_screen",
        "run_task",
        "assert_fresh_episode_ids",
        "confirm",
        "adapt",
        "decision_for",
    ],
)
def test_adaptation_method_functions_remain_identical_to_frozen_original(name: str) -> None:
    original = importlib.import_module("scripts.e6_iterative_low_viability")
    corrected = importlib.import_module("scripts.e6_iterative_low_viability_v2")

    def function_source(module: Any) -> str:
        source = Path(module.__file__).read_text()
        node = next(
            n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        return "\n".join(source.splitlines()[start - 1 : node.end_lineno])

    assert function_source(corrected) == function_source(original)
