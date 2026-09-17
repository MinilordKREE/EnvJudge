"""Synthetic, offline checks of shared DESIGN evidence and bounded request semantics."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

import pytest
from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea.designer import Reference, ReferenceStep
from aea.intervention import DesignOperation, InterventionFamily
from aea.intervention_designer import (
    TOOL_NAME,
    DesignContext,
    DesignRequest,
    InterventionDesigner,
    build_design_context,
    design_messages,
    intervention_tool,
)
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from tests.fixtures.fake_designer import ScriptedDesigner, tool_response

SECRET = "SYNTHETIC_PRIVATE_REFERENCE_SENTINEL"
SOURCE = "class _Rules(Rules):\n    DOSE = __DOSE__\n"
REFERENCE = Reference(
    True,
    "pass",
    ("synthetic_action",),
    (ReferenceStep(1, SECRET, ("synthetic_action",), "synthetic_action"),),
)


def trace(success: bool = False, *, episode: str = "baseline", length: int = 2) -> Trace:
    steps = []
    for i in range(length):
        obs = Observation(
            text=f"Task: complete the synthetic exercise\n\nSTEP_{i:03d}_" + "x" * 350,
            data={"admissible_commands": ["look"]},
        )
        steps.append(
            Step(
                raw_action=Action(name="do", kwargs={"text": "look"}),
                raw_observation=obs,
                filtered_observation=obs,
                policy_raw_response="<think>" + "r" * 300 + "</think>",
            )
        )
    return Trace(
        episode_id=episode,
        iteration_id="estimate-synthetic",
        task_id="synthetic",
        candidate=Candidate(),
        kind="baseline",
        steps=steps,
        success=success,
        duration_steps=length,
    )


def context(regime: Literal["LOW", "HIGH"] = "LOW") -> DesignContext:
    return build_design_context(
        task_id="synthetic",
        regime=regime,
        traces=[trace(regime == "HIGH")],
        p_hat=0.0 if regime == "LOW" else 1.0,
        n=10,
        seed=7,
        reference=REFERENCE if regime == "LOW" else None,
    )


def first(regime: Literal["LOW", "HIGH"] = "LOW") -> DesignRequest:
    return DesignRequest(context(regime), 1, "CREATE", 3, 30)


def payload(direction: str = "easier", kind: str = "BINARY") -> dict[str, Any]:
    control: dict[str, Any] = {"kind": kind}
    if kind == "DISCRETE":
        control["settings"] = [
            {"value": 0, "name": "OFF"},
            {"value": 0.5, "name": "mild"},
            {"value": 1, "name": "full"},
        ]
    return {
        "family": {
            "direction": direction,
            "mechanism_summary": "Synthetic mechanism",
            "source": SOURCE,
            "axis": "O",
            "hooks": ["filter_observation"],
            "control": control,
            "expected_effect": "Move success toward the configured band",
        }
    }


def parent(direction: str = "easier") -> InterventionFamily:
    return InterventionFamily(
        **payload(direction)["family"],
        family_id="host_family_1",
        semantic_mechanism_id="host_mechanism_1",
        design_round=1,
        operation="CREATE",
    )


def adapter(complete: Any, **kwargs: Any) -> InterventionDesigner:
    return InterventionDesigner(
        complete,
        model="synthetic-designer",
        seed=7,
        attribution=Attribution(phase="design", budget="designer", task_id="synthetic"),
        **kwargs,
    )


def test_evidence_asymmetry_and_short_open_ended_contract() -> None:
    low, high = design_messages(first()), design_messages(first("HIGH"))
    assert SECRET in low[1].content and SECRET not in high[1].content
    assert "PRIVILEGED REFERENCE TRAJECTORY" not in high[1].content
    assert "REPRESENTATIVE TRAJECTORIES" in high[1].content
    assert len(low) == len(high) == 2
    assert len(low[0].content) < 4000 and len(high[0].content) < 4000
    assert "binary and discrete" in low[0].content
    assert "not a member of a fixed library" in high[0].content
    assert "REFINE_CONTROL" in low[0].content


@pytest.mark.parametrize(
    "bad",
    [
        None,
        Reference(False, "failed"),
        Reference(True, "pass", ("synthetic_action",)),
        Reference(True, "pass", ("different",), REFERENCE.steps),
        Reference(True, "pass", REFERENCE.actions, (replace(REFERENCE.steps[0], step=2),)),
    ],
)
def test_low_rejects_absent_unverified_or_unaligned_reference(bad: Reference | None) -> None:
    with pytest.raises(ValueError, match="aligned rich reference"):
        build_design_context(
            task_id="synthetic",
            regime="LOW",
            traces=[trace()],
            p_hat=0,
            n=10,
            seed=7,
            reference=bad,
        )


def test_high_refuses_reference_even_before_serialization() -> None:
    with pytest.raises(ValueError, match="HIGH must not receive"):
        build_design_context(
            task_id="synthetic",
            regime="HIGH",
            traces=[trace(True)],
            p_hat=1,
            n=10,
            seed=7,
            reference=REFERENCE,
        )


def test_evidence_bound_is_preserved_and_low_uses_at_most_three_failures() -> None:
    ctx = build_design_context(
        task_id="synthetic",
        regime="LOW",
        p_hat=0,
        n=10,
        seed=7,
        reference=REFERENCE,
        traces=[trace(episode=f"baseline-{i}", length=50) for i in range(5)],
    )
    assert len(ctx.evidence.text) <= 24_000
    assert ctx.evidence.n_traces == 3
    assert SECRET in ctx.evidence.text
    assert "STEP_020_" not in ctx.evidence.text
    assert "STEP_000_" in ctx.evidence.text
    assert "x" * 321 not in ctx.evidence.text
    assert "r" * 241 not in ctx.evidence.text


@pytest.mark.parametrize(
    ("reason", "operation"),
    [
        ("MECHANICAL_FAILURE", "REPAIR_CODE"),
        ("PRIVILEGE_REJECTION", "REPLACE_MECHANISM"),
        ("SOLVABILITY_FAILURE", "REPLACE_MECHANISM"),
        ("NO_LEVERAGE", "REPLACE_MECHANISM"),
        ("OVERPOWERED_BINARY", "REFINE_CONTROL"),
        ("INSUFFICIENT_ATTENUATION", "REFINE_CONTROL"),
        ("INSUFFICIENT_RESOLUTION", "REFINE_CONTROL"),
        ("NON_MONOTONE_CONTROL_SURFACE", "REFINE_CONTROL"),
        ("CONTROL_EXHAUSTED", "REFINE_CONTROL"),
    ],
)
def test_typed_feedback_and_parent_binding(reason: str, operation: DesignOperation) -> None:
    req = DesignRequest(
        context(),
        2,
        operation,
        2,
        22,
        parent(),
        {"reason": reason, "probes": [{"level_id": "level_1", "s": 4, "n": 4}]},
    )
    text = design_messages(req)[1].content
    assert '"operation": "' + operation + '"' in text
    assert '"reason": "' + reason + '"' in text
    assert text.count('"latest_feedback"') == 1
    assert "host_family_1" in text and "host_mechanism_1" in text


def test_adapter_does_not_accumulate_previous_feedback_or_conversation() -> None:
    complete = ScriptedDesigner((TOOL_NAME, payload()))
    designer = adapter(complete)
    designer.propose(
        DesignRequest(
            context(),
            2,
            "REFINE_CONTROL",
            2,
            22,
            parent(),
            {"reason": "OVERPOWERED_BINARY", "detail": "OLDER_FEEDBACK_SENTINEL"},
        )
    )
    designer.propose(
        DesignRequest(
            context(),
            3,
            "REFINE_CONTROL",
            1,
            14,
            parent(),
            {"reason": "INSUFFICIENT_ATTENUATION", "detail": "CURRENT_FEEDBACK_SENTINEL"},
        )
    )
    assert len(complete.requests[-1].messages) == 2
    text = complete.requests[-1].messages[-1].content
    assert "CURRENT_FEEDBACK_SENTINEL" in text and "OLDER_FEEDBACK_SENTINEL" not in text
    assert complete.requests[-1].seed == 9


@pytest.mark.parametrize("reason", ["ACCEPTED", "UNREGISTERED_REASON"])
def test_terminal_or_untyped_feedback_cannot_restart_design(reason: str) -> None:
    with pytest.raises(ValueError):
        DesignRequest(context(), 2, "REFINE_CONTROL", 2, 22, parent(), {"reason": reason})


def test_feedback_operation_and_budget_are_checked() -> None:
    with pytest.raises(ValueError, match="does not match"):
        DesignRequest(
            context(), 2, "REPLACE_MECHANISM", 2, 22, parent(), {"reason": "OVERPOWERED_BINARY"}
        )
    with pytest.raises(ValueError, match="bounded session"):
        replace(first(), remaining_design_rounds=0)
    with pytest.raises(ValueError, match="actual parent"):
        DesignRequest(
            context(), 2, "REFINE_CONTROL", 2, 22, feedback={"reason": "OVERPOWERED_BINARY"}
        )
    # A malformed proposal has no valid parent family, but can receive mechanical repair.
    DesignRequest(
        context(),
        2,
        "REPAIR_CODE",
        2,
        30,
        feedback={"reason": "MECHANICAL_FAILURE", "schema_errors": ["missing family"]},
    )


@pytest.mark.parametrize("regime", ["LOW", "HIGH"])
@pytest.mark.parametrize("kind", ["BINARY", "SCALAR", "DISCRETE"])
def test_shared_request_schema_accepts_all_control_kinds(
    regime: Literal["LOW", "HIGH"], kind: str
) -> None:
    request = first(regime)
    complete = ScriptedDesigner((TOOL_NAME, payload(request.context.direction, kind)))
    result = adapter(complete).propose(request)
    assert result.family is not None and not result.errors
    assert result.family.control.kind == kind
    assert "family_id" not in result.family.model_dump()
    chat = complete.requests[0]
    assert chat.attribution.budget == "designer" and chat.max_tokens == 6144
    assert chat.temperature == 0.7 and chat.seed == 7
    assert chat.tools == (intervention_tool(),)
    assert chat.tool_choice == {"type": "function", "function": {"name": TOOL_NAME}}


@pytest.mark.parametrize(
    "alteration",
    [
        "extra_lineage",
        "missing_source",
        "blank_summary",
        "opposite_direction",
        "invalid_hook",
        "invalid_control",
        "second_family",
    ],
)
def test_invalid_model_payload_is_mechanical_feedback_not_trusted(alteration: str) -> None:
    args = payload()
    family = args["family"]
    if alteration == "extra_lineage":
        family["family_id"] = "FORGED_PRIVATE_ID"
    elif alteration == "missing_source":
        del family["source"]
    elif alteration == "blank_summary":
        family["mechanism_summary"] = " "
    elif alteration == "opposite_direction":
        family["direction"] = "harder"
    elif alteration == "invalid_hook":
        family["hooks"] = ["inner_step"]
    elif alteration == "invalid_control":
        family["control"] = {"kind": "DISCRETE", "settings": [{"value": -1}]}
    else:
        args["second_family"] = dict(family)
    result = adapter(ScriptedDesigner((TOOL_NAME, args))).propose(first())
    assert result.family is None and result.errors
    assert result.arguments == args
    assert "FORGED_PRIVATE_ID" not in " ".join(result.errors)


@pytest.mark.parametrize("mode", ["wrong_tool", "missing_tool", "two_tools"])
def test_invalid_tool_calls_are_recorded_before_rejection(mode: str) -> None:
    recorded: list[ChatResponse] = []

    def complete(request: ChatRequest) -> ChatResponse:
        response = tool_response(request, "wrong" if mode == "wrong_tool" else TOOL_NAME, payload())
        if mode != "wrong_tool":
            response = response.model_copy(
                update={
                    "tool_calls": () if mode == "missing_tool" else response.tool_calls * 2,
                }
            )
        return response

    result = adapter(complete, record=lambda request, response: recorded.append(response)).propose(
        first()
    )
    assert result.family is None and result.errors and len(recorded) == 1


def test_provider_failures_propagate_and_confirmation_attribution_is_refused() -> None:
    def complete(request: ChatRequest) -> ChatResponse:
        raise RuntimeError("synthetic transport interruption")

    with pytest.raises(RuntimeError, match="transport interruption"):
        adapter(complete).propose(first())
    with pytest.raises(ValueError, match="never confirmation"):
        InterventionDesigner(
            complete,
            model="synthetic",
            seed=0,
            attribution=Attribution(phase="confirm_0", budget="eval"),
        )
    with pytest.raises(ValueError, match="requested task"):
        adapter(complete).propose(replace(first(), context=replace(context(), task_id="different")))
