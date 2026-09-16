"""Schema failures must survive JSON persistence without changing admission or audit."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from aea.errors import ConfigError
from aea.llm.types import ChatRequest, ToolCall
from aea.privilege_judge import (
    JudgeRecord,
    PrivilegeDecision,
    canonical_json,
    validation_error_summary,
)
from aea.privilege_witness import (
    WITNESS_TOOL_NAME,
    WitnessCheck,
    WitnessCheckingPrivilegeJudge,
    blind_witness_input,
    validate_witness_record,
)
from tests.unit.test_llm_privilege_low import compact, probe
from tests.unit.test_privilege_judge import decision_args, judge_input, judge_response


def malformed_witness() -> dict[str, Any]:
    # Eleven otherwise well-shaped anchors exercise the actual nested-input repr failure.
    anchor = {
        "kind": "source",
        "start_line": 1,
        "end_line": 1,
        "excerpt": "generic artifact",
        "activation_kind": "UNCONDITIONAL",
        "condition_excerpt": None,
    }
    return {
        "candidate_grounding": "SUPPORTED",
        "claim_relation": "SAME",
        "authorization": "NOT_ESTABLISHED",
        "authorization_basis": "NONE",
        "public_anchors": [],
        "information": "Generic support",
        "candidate_anchors": [dict(anchor) for _ in range(11)],
        "explanation": "Check the exact source.",
    }


def validation_error(model: Any, value: Any) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(value)
    return caught.value


def test_nested_witness_error_summary_ignores_json_dictionary_order() -> None:
    original = malformed_witness()
    persisted = json.loads(canonical_json(original))
    first = validation_error(WitnessCheck, original)
    second = validation_error(WitnessCheck, persisted)
    assert str(first) != str(second)  # The previous implementation is demonstrably unstable.
    assert validation_error_summary(first) == validation_error_summary(second)
    assert json.loads(validation_error_summary(first)) == [
        {"loc": ["candidate_anchors"], "type": "too_long"}
    ]


def test_main_judge_error_summary_ignores_error_and_nested_key_order() -> None:
    original = {
        **decision_args(),
        "extra_z": {"z": "PRIVATE_VALUE_SENTINEL", "a": 2},
        "extra_a": {"z": 3, "a": 4},
    }
    first = validation_error(PrivilegeDecision, original)
    second = validation_error(PrivilegeDecision, json.loads(canonical_json(original)))
    assert str(first) != str(second)
    assert validation_error_summary(first) == validation_error_summary(second)
    assert "PRIVATE_VALUE_SENTINEL" not in validation_error_summary(first)
    assert "input_value" not in validation_error_summary(first)


@pytest.mark.parametrize("invalid_stage", ["draft", "witness"])
def test_schema_failure_record_replays_after_sorted_json_persistence(invalid_stage: str) -> None:
    requests: list[ChatRequest] = []

    def complete(request: ChatRequest) -> Any:
        requests.append(request)
        if len(requests) == 1:
            args = decision_args("FAIL")
            if invalid_stage == "draft":
                args["extra_z"] = {"z": 1, "a": 2}
                args["extra_a"] = {"z": 3, "a": 4}
            return judge_response(request, args)
        assert len(requests) == 2 and invalid_stage == "witness"
        response = judge_response(request)
        return response.model_copy(
            update={
                "tool_calls": (
                    ToolCall(
                        id="malformed-witness",
                        name=WITNESS_TOOL_NAME,
                        arguments=malformed_witness(),
                    ),
                )
            }
        )

    evidence = judge_input()
    record = WitnessCheckingPrivilegeJudge(complete).judge(evidence)
    assert record.verdict == "UNCERTAIN" and record.generated_uncertainty
    assert len(requests) == (1 if invalid_stage == "draft" else 2)
    persisted = JudgeRecord.model_validate_json(canonical_json(record.as_record()))
    validate_witness_record(persisted, evidence)
    assert persisted.as_record() == record.as_record()


def test_runtime_display_indices_preserve_every_original_value_without_mutation() -> None:
    evidence = compact((probe(), probe(step=1), probe(dose=0.25), probe(episode="other")))
    original = canonical_json(evidence.model_dump(mode="json"))
    decision = PrivilegeDecision.model_validate(decision_args("FAIL"))
    displayed = blind_witness_input(evidence, decision)["optional_runtime_surface_deltas"]
    assert displayed is not evidence.optional_runtime_surface_deltas
    for group_index, group in enumerate(displayed["groups"]):
        assert group.pop("group_index") == group_index
        for change_index, change in enumerate(group["changes"]):
            assert change.pop("change_index") == change_index
    assert canonical_json(displayed) == canonical_json(evidence.optional_runtime_surface_deltas)
    assert canonical_json(evidence.model_dump(mode="json")) == original
    displayed["value_table"]["new_marker"] = "display mutation"
    assert canonical_json(evidence.model_dump(mode="json")) == original


@pytest.mark.parametrize("conflict", ["group", "change"])
def test_display_index_never_overwrites_an_existing_evidence_field(conflict: str) -> None:
    evidence = compact((probe(),))
    runtime = evidence.optional_runtime_surface_deltas
    if conflict == "group":
        runtime["groups"][0]["group_index"] = "original metadata"
    else:
        runtime["groups"][0]["changes"][0]["change_index"] = "original metadata"
    original = canonical_json(evidence.model_dump(mode="json"))
    with pytest.raises(ConfigError):
        blind_witness_input(evidence, PrivilegeDecision.model_validate(decision_args("FAIL")))
    assert canonical_json(evidence.model_dump(mode="json")) == original
