"""Shared, bounded semantic DESIGN for the v3 Designer--Controller protocol.

This adapter makes one model request and parses one proposal. The task-local session owns
lineage, gates, empirical CONTROL, budgets and final acceptance. All records here are private:
LOW evidence and a feedback packet can contain privileged information or candidate source.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from envharness.core.types import Trace
from pydantic import Field, TypeAdapter, ValidationError, field_validator

from aea.core.config import StrictModel
from aea.designer import Evidence, Reference, serialize_high, serialize_low, task_goal
from aea.intervention import (
    ControlDeclaration,
    DesignOperation,
    Direction,
    FeedbackReason,
    HookName,
    InterventionFamily,
)
from aea.llm.types import Attribution, ChatMessage, ChatRequest, ChatResponse
from aea.stage import seeded_failures

TOOL_NAME = "propose_intervention"
type Regime = Literal["LOW", "HIGH"]

# Keep the semantic contract short. API details are necessary to generate executable Rules;
# neither a fixed intervention library nor accumulated experimental case descriptions belong here.
DESIGN_CONTRACT = """Discover ONE useful semantic environment intervention for this learner.
You discover WHAT should change. An algorithmic Controller measures its actual learner-facing
surfaces and learner success to decide HOW to operate it; you do not select the final setting
or predict acceptance. Do not optimize for a continuous-dose aesthetic: binary and discrete
interventions are valid. Discover an open-ended mechanism, not a member of a fixed library.
Return class _Rules(Rules) with DOSE = __DOSE__, implemented on numeric [0,1]. Zero must be
the original environment. Declare BINARY (OFF/ON), SCALAR (the configured grid), or DISCRETE
(ordered named levels mapped to numeric settings, including 0 and 1). The order is a proposal,
not a proven strength scale. Positive settings should operate the same semantic mechanism.
Keep the task goal, world state, reward and success verifier unchanged; the learner performs
the task. Do not call inner.step or introduce Setup actions. The task must remain solvable.
On REPAIR_CODE, repair the implementation while preserving the intended mechanism.
On REPLACE_MECHANISM, propose a different semantic mechanism.
On REFINE_CONTROL, preserve the useful parent mechanism; change only how its scope,
frequency, coverage, delay, strength or meaningful discrete levels are exposed. Controller
feedback describes measured behavior, not an instruction to optimize a particular number.
For REPAIR_CODE and REFINE_CONTROL, keep the parent's mechanism_summary verbatim.
"""

RULES_API = """Rules API: only Rules, Action, Blocked, Observation, EnvResponse and standard-library
imports are available. Hooks: filter_action(self, action, env_state) -> Action | Blocked;
modify_transition(self, action, raw_response, env_state) -> EnvResponse;
filter_observation(self, obs, env_state) -> Observation. Action command text is in
action.kwargs['text']; action.name is 'do'. Observation has text and data; admissible commands
are in data['admissible_commands'] and also rendered in text. Keep both consistent when
changing that surface. EnvResponse has observation, reward, terminated, truncated, info.
env_state exposes goal_text, obs_text, admissible_commands, won, done, step_count,
last_action_was_effective and extras. Treat it as read-only except per-episode extras.
"""

LOW_CONTRACT = """LOW objective: provide assistance based on the learner's failures and the verified
successful reference. Reference and historical designer evidence are private, not current
learner knowledge. Do not replay reference actions, copy reference observations, or disclose
instance-specific hidden facts through text, ranking, filtering or feedback. Assistance may
use public goals, generic prerequisites and facts observed in the current learner episode.
Preserve termination as well as reward and success semantics. A separate privilege gate
checks every candidate/control behavior before learner evaluation.
"""

HIGH_CONTRACT = """HIGH objective: challenge the learner using its baseline successes and failures.
Change task-relevant cues or interaction affordances while preserving the task and verifier;
do not add new objectives or solve the task for the learner. No privileged reference is
provided. Preserve the original environment at OFF and keep the intervention solvable.
"""


@dataclass(frozen=True)
class DesignContext:
    task_id: str
    regime: Regime
    task_specification: str
    p_hat: float
    n: int
    evidence: Evidence
    measurement_evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.regime not in ("LOW", "HIGH"):
            raise ValueError("DESIGN accepts only LOW or HIGH; MID has no designer")
        if not self.task_id or self.n <= 0 or not math.isfinite(self.p_hat):
            raise ValueError("Invalid task or measurement evidence")
        if not 0 <= self.p_hat <= 1:
            raise ValueError("Measurement success rate must lie in [0,1]")
        if self.evidence.reference_used != (self.regime == "LOW"):
            raise ValueError("LOW requires verified reference evidence; HIGH must not receive it")

    @property
    def direction(self) -> Direction:
        return "easier" if self.regime == "LOW" else "harder"


def build_design_context(
    *,
    task_id: str,
    regime: Regime,
    traces: Sequence[Trace],
    p_hat: float,
    n: int,
    seed: int,
    reference: Reference | None = None,
    measurement_evidence: Mapping[str, Any] | None = None,
) -> DesignContext:
    """Use the existing bounded serializers, with asymmetric evidence access by construction.

    Verification of reference success occurs in the existing benchmark reference provider;
    this boundary additionally requires its successful rich record and exact action alignment.
    The 24k serializer bound applies to original evidence, not the full request plus feedback.
    """
    if regime == "LOW":
        if (
            reference is None
            or not reference.ok
            or not reference.actions
            or not reference.steps
            or tuple(step.action for step in reference.steps) != reference.actions
            or tuple(step.step for step in reference.steps)
            != tuple(range(1, len(reference.steps) + 1))
        ):
            raise ValueError("LOW requires a verified, aligned rich reference")
        failures = seeded_failures(traces, 3, seed)
        if not failures:
            raise ValueError("LOW requires baseline failure evidence")
        evidence = serialize_low(failures, p_hat, n, reference, rich=True)
    elif regime == "HIGH":
        if reference is not None:
            raise ValueError("HIGH must not receive a privileged reference")
        evidence = serialize_high(traces, p_hat, n)
    else:
        raise ValueError("MID does not invoke DESIGN")
    return DesignContext(
        task_id, regime, task_goal(traces), p_hat, n, evidence, measurement_evidence or {}
    )


@dataclass(frozen=True)
class DesignRequest:
    context: DesignContext
    design_round: int
    operation: DesignOperation
    remaining_design_rounds: int
    """Remaining permitted calls INCLUDING this request; the session decrements after dispatch."""
    remaining_policy_rollouts: int
    parent_family: InterventionFamily | None = None
    feedback: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        TypeAdapter(DesignOperation).validate_python(self.operation)
        if self.design_round < 1 or self.remaining_design_rounds < 1:
            raise ValueError("Designer call is outside its bounded session")
        if self.remaining_policy_rollouts < 0:
            raise ValueError("Remaining rollout budget cannot be negative")
        if self.operation == "CREATE":
            if (
                self.design_round != 1
                or self.parent_family is not None
                or self.feedback is not None
            ):
                raise ValueError("CREATE is the first round without parent feedback")
            return
        if self.design_round == 1 or self.feedback is None:
            raise ValueError("Redesign requires a later round and typed feedback")
        reason: FeedbackReason = TypeAdapter(FeedbackReason).validate_python(
            self.feedback.get("reason")
        )
        if reason == "ACCEPTED":
            raise ValueError("Final acceptance cannot feed another designer request")
        if self.context.regime == "HIGH" and reason == "PRIVILEGE_REJECTION":
            raise ValueError("HIGH has no privileged-reference gate")
        expected_operation = (
            "REPAIR_CODE"
            if reason == "MECHANICAL_FAILURE"
            else "REPLACE_MECHANISM"
            if reason in ("PRIVILEGE_REJECTION", "SOLVABILITY_FAILURE", "NO_LEVERAGE")
            else "REFINE_CONTROL"
        )
        if self.operation != expected_operation:
            raise ValueError("Design operation does not match typed feedback")
        if self.parent_family is None and reason != "MECHANICAL_FAILURE":
            raise ValueError("Semantic redesign requires its actual parent family")
        if self.parent_family is not None:
            if self.parent_family.direction != self.context.direction:
                raise ValueError("Parent family belongs to the opposite direction")
            if self.parent_family.design_round >= self.design_round:
                raise ValueError("Parent family must precede this design round")


class InterventionProposal(StrictModel):
    """Model-owned semantic proposal only; session-owned lineage fields are forbidden."""

    direction: Direction
    mechanism_summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    axis: Literal["O", "T", "A"]
    hooks: tuple[HookName, ...] = Field(min_length=1)
    control: ControlDeclaration
    expected_effect: str = Field(min_length=1)

    @field_validator("mechanism_summary", "source", "expected_effect")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Proposal strings cannot be blank")
        return value

    @field_validator("hooks")
    @classmethod
    def distinct_hooks(cls, value: tuple[HookName, ...]) -> tuple[HookName, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Declared hooks must be distinct")
        return value


class _ToolArguments(StrictModel):
    family: InterventionProposal


def intervention_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Propose exactly one semantic intervention and its control declaration.",
            "parameters": _ToolArguments.model_json_schema(),
        },
    }


def design_messages(request: DesignRequest) -> tuple[ChatMessage, ...]:
    """Two messages per round: original bounded evidence plus this round's latest feedback."""
    context = request.context
    packet: dict[str, Any] = {
        "task_id": context.task_id,
        "task_specification": context.task_specification,
        "regime": context.regime,
        "direction": context.direction,
        "measurement": {**context.measurement_evidence, "p_hat": context.p_hat, "n": context.n},
        "design_round": request.design_round,
        "operation": request.operation,
        "remaining_design_rounds_including_current": request.remaining_design_rounds,
        "remaining_policy_rollouts": request.remaining_policy_rollouts,
    }
    if request.parent_family is not None:
        packet["parent_family"] = request.parent_family.model_dump(mode="json")
    if request.feedback is not None:
        packet["latest_feedback"] = dict(request.feedback)
    contract = LOW_CONTRACT if context.regime == "LOW" else HIGH_CONTRACT
    return (
        ChatMessage(role="system", content=DESIGN_CONTRACT + "\n" + contract + "\n" + RULES_API),
        ChatMessage(
            role="user",
            content=json.dumps(packet, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n\nORIGINAL DESIGN EVIDENCE\n"
            + context.evidence.text
            + f"\n\nCall {TOOL_NAME} with exactly one family. "
            "The session assigns IDs, parent lineage, operation and round; do not return them.",
        ),
    )


@dataclass(frozen=True)
class DesignProposal:
    family: InterventionProposal | None
    arguments: dict[str, Any]
    errors: tuple[str, ...] = ()


class InterventionDesigner:
    """One request, one proposal; transport/accounting errors propagate to the session.

    Supply the existing ledgered/logged completion callable. An optional record callback receives
    the exact request and response before parsing, including invalid model output for private audit.
    """

    def __init__(
        self,
        complete: Callable[[ChatRequest], ChatResponse],
        *,
        model: str,
        attribution: Attribution,
        seed: int,
        max_tokens: int = 6144,
        record: Callable[[ChatRequest, ChatResponse], None] | None = None,
    ) -> None:
        if attribution.budget != "designer" or any(
            token in attribution.phase.lower() for token in ("confirm", "k16", "eval")
        ):
            raise ValueError("Designer calls require design attribution, never confirmation")
        if max_tokens < 1:
            raise ValueError("Designer output budget must be positive")
        self.complete = complete
        self.model = model
        self.attribution = attribution
        self.seed = seed
        self.max_tokens = max_tokens
        self.record = record

    def propose(self, request: DesignRequest) -> DesignProposal:
        if self.attribution.task_id != request.context.task_id:
            raise ValueError("Designer attribution must bind the requested task")
        chat = ChatRequest(
            model=self.model,
            messages=design_messages(request),
            temperature=0.7,
            seed=self.seed + request.design_round - 1,
            max_tokens=self.max_tokens,
            attribution=self.attribution,
            tools=(intervention_tool(),),
            tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
        )
        response = self.complete(chat)
        if self.record is not None:
            self.record(chat, response)
        if len(response.tool_calls) != 1:
            return DesignProposal(None, {}, ("Designer must return exactly one tool call",))
        call = response.tool_calls[0]
        arguments = dict(call.arguments)
        if call.name != TOOL_NAME:
            return DesignProposal(None, arguments, ("Unexpected designer tool name",))
        try:
            family = _ToolArguments.model_validate(arguments).family
        except ValidationError as exc:
            # Exclude raw input from the error string; arguments remain in the private record.
            errors = tuple(
                f"{'.'.join(map(str, item['loc']))}: {item['type']}"
                for item in exc.errors(include_input=False)
            )
            return DesignProposal(None, arguments, errors)
        if family.direction != request.context.direction:
            return DesignProposal(None, arguments, ("Proposal direction differs from request",))
        return DesignProposal(family, arguments)
