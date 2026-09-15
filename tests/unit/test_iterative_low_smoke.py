"""Offline checks for the experiment driver's physical cap and shared-C1 comparison."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aea.errors import InfraError
from aea.witness import Solvable
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.unit.test_assistive_rules import HINT, NOT_IDENTITY, _reply
from tests.unit.test_iterative_low import REF
from tests.unit.test_llm_v1 import _trace


@pytest.fixture
def smoke() -> Any:
    return importlib.import_module("scripts.e6_iterative_low_smoke")


def _wire() -> dict[str, Any]:
    return {
        "model": "qwen/qwen3-8b",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 16,
    }


def test_physical_cap_refuses_before_transport(smoke: Any, tmp_path: Path) -> None:
    called: list[dict[str, Any]] = []
    path = tmp_path / "cap.json"
    smoke.write_json(
        path, {"actual_usd": 11.9999, "uncertain_usd": 0, "inflight": {}, "attempts": 0}
    )
    capped = smoke.CappedTransport(lambda **wire: called.append(wire), path)
    with pytest.raises(InfraError, match="stopped: cost_cap"):
        capped(**_wire())
    assert called == [] and json.loads(path.read_text())["attempts"] == 0
    state = json.loads(path.read_text())
    assert state["stopped"] == "cost_cap"
    state["actual_usd"] = 0.0  # an ended concurrent reservation must not reopen the experiment
    smoke.write_json(path, state)
    with pytest.raises(InfraError, match="stopped: cost_cap"):
        capped(**_wire())
    assert called == []


def test_ambiguous_attempt_stays_charged_when_retried(smoke: Any, tmp_path: Path) -> None:
    calls = 0

    def transport(**wire: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("response lost after dispatch")
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, cost=0))

    path = tmp_path / "cap.json"
    capped = smoke.CappedTransport(transport, path)
    with pytest.raises(TimeoutError):
        capped(**_wire())
    first = json.loads(path.read_text())
    assert first["uncertain_usd"] > 0 and first["inflight"] == {}
    capped(**_wire())
    final = json.loads(path.read_text())
    assert final["attempts"] == 2 and final["actual_usd"] > 0
    assert final["uncertain_usd"] == first["uncertain_usd"] and final["inflight"] == {}
    assert smoke.committed_cost(final) == final["actual_usd"] + final["uncertain_usd"]
    assert [row["status"] for row in smoke.jsonl(path.with_suffix(".attempts.jsonl"))] == [
        "ambiguous_failure",
        "returned",
    ]


def test_shared_c1_has_one_physical_evaluation_and_regressed_c2_is_not_hidden(
    smoke: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "RUN", tmp_path)
    smoke.write_json(tmp_path / "task-9" / "original_failures.json", [_trace(False).model_dump()])
    smoke.write_json(tmp_path / "task-9" / "privileged_reference.json", REF.as_record())
    replies = iter([_reply(HINT), _reply(NOT_IDENTITY), _reply(HINT.replace("!", "?"))])
    designer = ScriptedDesigner(lambda request: next(replies))
    guarded: list[Any] = []
    physical: list[tuple[str, int]] = []
    validations: list[dict[str, Any]] = []
    validate = smoke.LowEnvironmentOptimizer._validate

    def counted_validate(optimizer: Any, arguments: dict[str, Any]) -> Any:
        validations.append(arguments)
        return validate(optimizer, arguments)

    def certify(candidate: Any, *args: Any, **kwargs: Any) -> Solvable:
        guarded.append(candidate)
        return Solvable(True, "oracle")

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        attribution = kwargs["attribution"]
        physical.append((attribution.phase, n))
        return [
            _trace(attribution.arm == "I" and i % 2 == 0, candidate=candidate) for i in range(n)
        ]

    monkeypatch.setattr(smoke, "solvable", certify)
    monkeypatch.setattr(smoke.LowEnvironmentOptimizer, "_validate", counted_validate)
    sub = SimpleNamespace(
        designer=lambda: designer,
        designer_model=lambda: "fake-designer",
        rollouts=rollouts,
        has_oracle=lambda: True,
    )
    shared: dict[str, Any] = {}
    d = smoke.run_arm(sub, 9, "D", shared)
    i = smoke.run_arm(sub, 9, "I", shared)
    assert designer.calls == 3 and len(guarded) == 2 and len(validations) == 3
    assert sum(n for _, n in physical) == 12
    assert d["logical_rollouts"] == d["physical_rollouts"] == 4
    assert i["logical_rollouts"] == 12 and i["physical_rollouts"] == 8
    assert d["designer_calls_logical"] == i["designer_calls_logical"] == 2
    assert d["designer_calls_physical"] == 2 and i["designer_calls_physical"] == 1
    assert d["candidates"][0] == i["candidates"][0] == shared["c1"]
    assert smoke.stage_for(shared["c1"]) == 3 and d["gate"] == 0 and i["gate"] == 5
    assert i["search_accepted"] and not d["search_accepted"]
    second_d = "\n".join(message.content for message in designer.requests[1].messages)
    second_i = "\n".join(message.content for message in designer.requests[2].messages)
    assert "TYPED DESIGN FEEDBACK" in second_d and "too_hard" in second_d
    assert "Produce a different valid assistive Rules family" in second_i
    assert all(
        token not in second_i for token in ("TYPED DESIGN FEEDBACK", "too_hard", "no_leverage")
    )
    inputs = smoke.jsonl(tmp_path / "task-9" / "I" / "designer_inputs.jsonl")
    assert len(inputs) == 1 and inputs[0]["call_index"] == 2
    assert not inputs[0]["feedback_supplied"] and inputs[0]["independently_constructed_match"]


def test_identical_final_environments_share_one_k16_confirmation(
    smoke: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "RUN", tmp_path)
    calls: list[int] = []

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        calls.append(n)
        assert kwargs["attribution"].budget == "eval"
        return [_trace(i % 2 == 0, candidate=candidate) for i in range(n)]

    arms = {
        arm: {"search_accepted": True, "final_environment_hash": "same", "final_candidate": {}}
        for arm in ("D", "I")
    }
    smoke.confirm(SimpleNamespace(rollouts=rollouts), 9, arms)
    assert calls == [16]
    assert arms["D"]["confirmation"] == arms["I"]["confirmation"]
    assert (
        arms["D"]["logical_confirmation_rollouts"]
        == arms["I"]["logical_confirmation_rollouts"]
        == 16
    )
    assert arms["D"]["physical_confirmation_rollouts"] == 16
    assert arms["I"]["physical_confirmation_rollouts"] == 0
    assert arms["D"]["gate"] == arms["I"]["gate"] == 6


def test_bound_violation_stops_later_calls_and_is_implementation_failure(
    smoke: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "RUN", tmp_path)
    calls = 0

    def transport(**wire: Any) -> Any:
        nonlocal calls
        calls += 1
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=17, cost=0))

    capped = smoke.CappedTransport(transport, tmp_path / "cap.json")
    with pytest.raises(InfraError, match="exceeded conservative cost bound"):
        capped(**_wire())
    with pytest.raises(InfraError, match="bound_violation"):
        capped(**_wire())
    assert calls == 1
    smoke.write_json(tmp_path / "prepared.json", [{"reference_ok": True}] * 4)
    smoke.write_json(
        tmp_path / "results.json",
        {"tasks": {}, "interruption": {"kind": "smoke_design_inconclusive"}},
    )
    assert smoke.report()["decision"] == "IMPLEMENTATION_FAILURE"


def test_confirmed_privilege_audit_overrides_interrupt_label(
    smoke: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "RUN", tmp_path)
    smoke.write_json(tmp_path / "prepared.json", [{"reference_ok": True}] * 4)
    smoke.write_json(
        tmp_path / "results.json",
        {"tasks": {}, "interruption": {"kind": "smoke_rollout"}},
    )
    smoke.write_json(
        tmp_path / "cap.json",
        {"actual_usd": 0.05, "uncertain_usd": 0, "inflight": {}, "attempts": 1},
    )
    smoke.write_json(
        tmp_path / "correctness_audit.json",
        {"decision": "IMPLEMENTATION_FAILURE", "gate": "privilege_isolation"},
    )
    assert smoke.report()["decision"] == "IMPLEMENTATION_FAILURE"
