"""Exact frozen D/I prompt isolation and semantic admission/accounting orchestration."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aea.designer import serialize_low
from aea.llm.types import Attribution
from aea.low_optimizer import Feedback, iterative_messages, propose_low
from aea.semantic_low import SemanticAdmissionError
from aea.semantic_privilege import Decision, SemanticGateInput, screen_semantic_privilege
from aea.witness import Solvable
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.unit.test_assistive_rules import HINT, _reply
from tests.unit.test_iterative_low import REF
from tests.unit.test_llm_v1 import _trace


@pytest.fixture
def smoke() -> Any:
    return importlib.import_module("scripts.e6_iterative_low_semantic_smoke")


@pytest.mark.parametrize(
    "category,operation,reason,endpoint",
    [
        ("mechanical", "REPAIR_CODE", "VALIDATOR_CANARY undefined DOSE", None),
        (
            "privilege",
            "REPLACE_MECHANISM",
            "SEMANTIC_FAIL_CANARY gate verdict FAIL HIDDEN_RELATION",
            None,
        ),
        ("solvability", "REPLACE_MECHANISM", "SOLVABILITY_CANARY oracle verifier_fail", None),
        ("no_leverage", "REPLACE_MECHANISM", "ROLLOUT_CANARY s/n=0/4 too_hard", (0, 4, "too_hard")),
        ("no_leverage", "REPLACE_MECHANISM", "UNUSED_EASY_CANARY too_easy", (4, 4, "too_easy")),
    ],
)
def test_exact_actual_proposal_requests_exclude_all_evaluator_information_from_i(
    category: Any,
    operation: Any,
    reason: str,
    endpoint: Any,
) -> None:
    evidence = serialize_low([_trace(False)], 0.0, 10, REF, rich=True)
    feedback = Feedback(
        operation,
        category,
        "9:C1:hash",
        HINT,
        "source_hash",
        "hint",
        reason,
        1,
        16,
        endpoint,
        "ROLLOUT_TRACE_CANARY",
        "episode_canary",
    )
    designer = ScriptedDesigner(lambda request: _reply(HINT))
    common: dict[str, Any] = {
        "model": "fake",
        "evidence": evidence,
        "attribution": Attribution(),
        "seed": 10,
    }
    propose_low(designer, **common, feedback=feedback)
    propose_low(designer, **common, feedback=None, previous_source=HINT)
    d, i = designer.requests
    assert d.messages == iterative_messages(evidence, feedback)
    assert i.messages == iterative_messages(evidence, None, previous_source=HINT)
    d_text = "\n".join(message.content for message in d.messages)
    i_text = "\n".join(message.content for message in i.messages)
    assert reason in d_text and "ROLLOUT_TRACE_CANARY" in d_text
    assert all(
        token not in i_text
        for token in (
            reason,
            "TYPED DESIGN FEEDBACK",
            "SEMANTIC_FAIL_CANARY",
            "SOLVABILITY_CANARY",
            "VALIDATOR_CANARY",
            "ROLLOUT_TRACE_CANARY",
            "too_hard",
            "too_easy",
            '"endpoint"',
            '"remaining_policy"',
            '"reason"',
            '"category"',
            '"failed_episode_id"',
        )
    )
    assert evidence.text in i_text and HINT in i_text


def test_shared_semantic_c1_and_uncertain_d2_preserve_independent_i2_opportunity(
    smoke: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke, "RUN", tmp_path)
    smoke.write_json(tmp_path / "task-9/original_failures.json", [_trace(False).model_dump()])
    smoke.write_json(tmp_path / "task-9/privileged_reference.json", REF.as_record())
    codes = [HINT, HINT + "\n# second D\n", HINT + "\n# second I\n"]
    replies = iter([_reply(code) for code in codes])
    designer = ScriptedDesigner(lambda request: next(replies))
    physical: list[tuple[str, int]] = []
    screens: list[str] = []
    admitted: set[str] = set()
    shared: dict[str, Any] = {"semantic_records": []}

    class Screen:
        def screen(self, family: Any) -> Any:
            screens.append(family.template)
            base = screen_semantic_privilege(SemanticGateInput(family.template, REF, "", (), "9"))
            verdict: Decision = "UNCERTAIN" if family.template == codes[1] else "PASS"
            result = replace(
                base,
                decision=verdict,
                findings=tuple(replace(f, decision=verdict) for f in base.findings),
            )
            shared["semantic_records"].append({"result": result.as_record()})
            if verdict == "PASS":
                admitted.add(family.template)
            return result

        def require_pass(self, family: Any, dose: float) -> None:
            if family.template not in admitted:
                raise SemanticAdmissionError("not admitted")

    def rollouts(task: Any, candidate: Any, n: int, **kwargs: Any) -> list[Any]:
        physical.append((kwargs["attribution"].phase, n))
        return [
            _trace(kwargs["attribution"].arm == "I" and j % 2 == 0, candidate=candidate)
            for j in range(n)
        ]

    monkeypatch.setattr(smoke, "solvable", lambda *args, **kwargs: Solvable(True, "oracle"))
    sub = SimpleNamespace(
        designer=lambda: designer,
        designer_model=lambda: "fake",
        has_oracle=lambda: True,
        rollouts=rollouts,
    )
    shared["screen"] = Screen()
    d = smoke.run_arm(sub, 9, "D", shared)
    i = smoke.run_arm(sub, 9, "I", shared)
    assert d["gate"] is None and d["gate_name"] == "SEMANTIC_UNCERTAIN"
    assert i["search_accepted"] and i["gate"] == 6
    assert screens == codes and designer.calls == 3
    assert d["candidates"][0] == i["candidates"][0]
    assert sum(n for _, n in physical) == 12
    assert d["logical_rollouts"] == 4 and i["logical_rollouts"] == 12
    assert i["physical_rollouts"] == 8
    assert "TYPED DESIGN FEEDBACK" not in "\n".join(
        m.content for m in designer.requests[2].messages
    )


def test_missing_exact_admission_is_implementation_failure(smoke: Any) -> None:
    def deny(*args: Any) -> None:
        raise SemanticAdmissionError("wrong source")

    with pytest.raises(smoke.ConfigError, match="admission binding failed"):
        smoke.require_pass(SimpleNamespace(require_pass=deny), object(), 1.0)


def test_exact_decision_rules_allow_strong_without_two_improvements_and_unranked_i(
    smoke: Any,
) -> None:
    c1 = {"endpoint": (0, 4, "too_hard")}

    def row(task: str, d: int, i: int | None, confirmed: bool = False) -> dict[str, Any]:
        return {
            "original": {"task_id": task},
            "status": "completed",
            "c1_failed": True,
            "paired_ordinal": i is not None,
            "c1": c1,
            "arms": {
                "D": {"gate": d, "candidates": [{}, {}], "confirmation": {"in_band_l": confirmed}},
                "I": {"gate": i, "candidates": [{}, {}]},
            },
        }

    tie = row("129", 5, 5)
    tie["c1_failed"] = False
    single = {
        "tasks": {"114": row("114", 7, 1, True), "126": tie, "129": tie},
        "interruption": None,
    }
    assert smoke.decision_for(single, 3, {})["decision"] == "ITERATIVE_LOW_STRONG_SIGNAL"
    censored = {
        "tasks": {"114": row("114", 5, None), "126": row("126", 5, 1), "129": tie},
        "interruption": None,
    }
    outcome = smoke.decision_for(censored, 3, {})
    assert outcome["decision"] == "ITERATIVE_LOW_SIGNAL" and outcome["C2_improves_C1"]["D"] == 2

    partial = {"tasks": {"114": row("114", 7, 1, True)}, "interruption": None}
    assert smoke.decision_for(partial, 3, {})["decision"] == "INCONCLUSIVE"
