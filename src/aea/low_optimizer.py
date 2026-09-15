"""Experimental LOW DESIGN: two proposals, typed feedback, then an irreversible freeze.

The caller supplies certification, measurement and remaining rollout budget. This module
does not choose acceptance thresholds, run CONTROL, or receive confirmation evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from envharness.core.types import Candidate, Trace

from aea.designer import (
    ASSIST_CONTRACT,
    ASSIST_OBJECTIVE,
    DESIGN_ASSIST_TOOL,
    ENVIRONMENT_SURFACE,
    AssistFamily,
    Evidence,
    EvidenceBounds,
    Reference,
    identity_at_zero,
    privilege_check,
    trajectory_text,
)
from aea.errors import BudgetExhausted, ConfigError
from aea.evaluate import Eval
from aea.families import FamilyContext, validate_rules_template
from aea.llm.types import Attribution, ChatMessage, ChatRequest, ChatResponse
from aea.witness import Solvable

MAX_OPTIMIZER_CALLS = 2
ITERATIVE_ASSIST_TOOL = copy.deepcopy(DESIGN_ASSIST_TOOL)
ITERATIVE_ASSIST_TOOL["function"]["description"] = (
    "Diagnose the bottleneck and propose exactly ONE parameterised assistive Rules family."
)
_FAMILIES = ITERATIVE_ASSIST_TOOL["function"]["parameters"]["properties"]["families"]
_FAMILIES.update(minItems=1, maxItems=1)

type Operation = Literal["REPAIR_CODE", "REPLACE_MECHANISM"]
type Category = Literal["mechanical", "privilege", "solvability", "no_leverage", "duplicate"]


@dataclass(frozen=True)
class Feedback:
    operation: Operation
    category: Category
    candidate_id: str
    source: str
    source_sha256: str
    mechanism: str
    reason: str
    remaining_calls: int
    remaining_policy: int
    endpoint: tuple[int, int, str] | None = None
    failed_rollout: str | None = None
    failed_episode_id: str | None = None

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


def iterative_messages(
    evidence: Evidence,
    feedback: Feedback | None = None,
    *,
    previous_source: str | None = None,
) -> tuple[ChatMessage, ...]:
    """I's neutral input is built from original evidence; it never redacts a D packet."""
    if feedback is not None and previous_source is not None:
        raise ValueError("feedback and independent proposal inputs are mutually exclusive")
    objective = ASSIST_OBJECTIVE.replace(
        "up to two parameterised ASSISTIVE environment interventions, most promising first, each",
        "exactly ONE parameterised ASSISTIVE environment intervention",
    )
    text = f"{objective}\n\n{evidence.text}"
    if feedback is not None:
        instruction = (
            "Preserve the intended support mechanism; repair the implementation."
            if feedback.operation == "REPAIR_CODE"
            else (
                "Propose a different support mechanism; "
                "do not merely strengthen the same failed trick."
            )
        )
        if feedback.category == "no_leverage":
            instruction += (
                " The previous support mechanism failed to change learner behavior at maximum "
                "assistance. Replace the support mechanism, not its numeric dose."
            )
        text += "\n\nTYPED DESIGN FEEDBACK\n" + json.dumps(feedback.as_record(), sort_keys=True)
        text += "\n" + instruction
    elif previous_source is not None:
        text += (
            "\n\nProduce a different valid assistive Rules family from your previous proposal."
            "\nPrevious proposal source (provided only to avoid duplication):\n" + previous_source
        )
    text += "\n\nCall diagnose_and_propose_assistance with exactly ONE family."
    return (
        ChatMessage(
            role="system",
            content="You design assistive environment interventions under a strict contract.\n"
            + ASSIST_CONTRACT
            + "\n\n"
            + ENVIRONMENT_SURFACE,
        ),
        ChatMessage(role="user", content=text),
    )


def propose_low(
    complete: Callable[[ChatRequest], ChatResponse],
    *,
    model: str,
    evidence: Evidence,
    feedback: Feedback | None,
    attribution: Attribution,
    seed: int,
    previous_source: str | None = None,
) -> dict[str, Any]:
    response = complete(
        ChatRequest(
            model=model,
            messages=iterative_messages(evidence, feedback, previous_source=previous_source),
            temperature=0.7,
            seed=seed,
            max_tokens=6144,
            attribution=attribution,
            tools=(ITERATIVE_ASSIST_TOOL,),
            tool_choice={
                "type": "function",
                "function": {"name": "diagnose_and_propose_assistance"},
            },
        )
    )
    if len(response.tool_calls) != 1:
        return {"schema_error": "designer must return exactly one tool call"}
    call = response.tool_calls[0]
    if call.name != "diagnose_and_propose_assistance":
        return {"schema_error": "unexpected designer tool name"}
    return dict(call.arguments)


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    parent_candidate_id: str | None
    optimizer_call_index: int
    requested_operation: str
    source: str
    source_sha256: str
    mechanism: str
    structural: tuple[str, ...]
    privilege: tuple[str, ...]
    solvability: str | None
    endpoint: tuple[int, int, str] | None
    rejection_reason: str | None
    remaining_calls: int
    remaining_policy: int

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DesignResult:
    status: Literal["viable", "unresolved", "inconclusive", "budget_unresolved"]
    reason: str = ""
    family: AssistFamily | None = None
    endpoint: Eval | None = None
    candidate_id: str | None = None


class LowEnvironmentOptimizer:
    """Task-local DESIGN state. Every completed call appends one immutable gate record."""

    def __init__(
        self,
        evidence: Evidence,
        failures: Sequence[Trace],
        reference: Reference,
        goal: str,
        *,
        task_id: str,
        propose: Callable[[Feedback | None, int], dict[str, Any]],
        certify: Callable[[Candidate], Solvable],
        measure: Callable[[AssistFamily, float], Eval],
        remaining: Callable[[], int],
        endpoint_reserve: int = 16,
    ) -> None:
        self.evidence = evidence
        self.failures = tuple(failures)
        self.reference = reference
        self.goal = goal
        self.task_id = task_id
        self.propose = propose
        self.certify = certify
        self.measure = measure
        self.remaining = remaining
        self.endpoint_reserve = endpoint_reserve
        self.history: tuple[CandidateRecord, ...] = ()
        self.rejections: tuple[Feedback, ...] = ()
        self.current: AssistFamily | None = None
        self.frozen: AssistFamily | None = None
        self._seen: set[str] = set()
        self._started = False

    @property
    def remaining_calls(self) -> int:
        return MAX_OPTIMIZER_CALLS - len(self.history)

    def _validate(self, args: dict[str, Any]) -> tuple[AssistFamily | None, list[str], list[str]]:
        raw = args.get("families")
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
            return None, [str(args.get("schema_error") or "exactly one family object required")], []
        f = raw[0]
        required = ("name", "axis", "mechanism_summary", "why", "rules_code", "direction")
        if any(not isinstance(f.get(k), str) or not f[k].strip() for k in required):
            return None, ["all family fields must be nonempty strings"], []
        if f["axis"] not in ("O", "T", "A") or f["direction"] != "easier_with_d":
            return None, ["axis must be O/T/A and direction must be easier_with_d"], []
        template = f["rules_code"]
        report = validate_rules_template(template, task_id=self.task_id)
        structural = list(report.reasons)
        if "__DOSE__" not in template:
            structural.append("missing __DOSE__ placeholder")
        if structural:
            return None, structural, []
        zero = identity_at_zero(template, task_id=self.task_id)
        # API exceptions at zero are mechanical; observed changed hooks violate preservation.
        mechanical = [r for r in zero if r.startswith("identity check raised")]
        semantic = [r for r in zero if r not in mechanical]
        priv = privilege_check(
            template, reference=self.reference, failures=self.failures, goal=self.goal
        )
        if mechanical or semantic or priv:
            return None, mechanical, [*semantic, *priv]
        name = re.sub(r"[^a-z0-9_]", "_", f["name"].lower())[:40]
        return AssistFamily(name, f["axis"], template, f["mechanism_summary"], f["why"]), [], []

    def run(self) -> DesignResult:
        if self._started:
            raise RuntimeError("DESIGN is single-use; CONTROL cannot reopen it")
        self._started = True
        if not self.reference.ok:
            return DesignResult("inconclusive", "reference_unavailable")
        feedback: Feedback | None = None
        for call_index in range(1, MAX_OPTIMIZER_CALLS + 1):
            if self.remaining() < self.endpoint_reserve:
                return DesignResult("budget_unresolved", "endpoint_and_calibration_reserve")
            args = self.propose(feedback, call_index)
            raw = args.get("families")
            f = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], dict) else {}
            source = str(f.get("rules_code") or "")
            mechanism = str(f.get("mechanism_summary") or "")
            sha = hashlib.sha256(source.encode()).hexdigest()
            cid = f"{self.task_id}:C{call_index}:{sha}"
            duplicate = sha in self._seen
            self._seen.add(sha)
            family, structural, privilege = self._validate(args)
            self.current = family
            guard_text: str | None = None
            endpoint: Eval | None = None
            reason = ""
            category: Category = "mechanical"
            operation: Operation = "REPAIR_CODE"
            status: Literal["unresolved", "inconclusive", "budget_unresolved"] = "unresolved"
            if duplicate:
                reason, category, operation = (
                    "duplicate source hash",
                    "duplicate",
                    "REPLACE_MECHANISM",
                )
            elif privilege:
                reason, category, operation = "; ".join(privilege), "privilege", "REPLACE_MECHANISM"
            elif structural:
                reason = "; ".join(structural)
            else:
                assert family is not None
                candidate = family.make(1.0, FamilyContext(self.task_id, ()))
                assert candidate is not None
                try:
                    guard = self.certify(candidate)
                    guard_text = json.dumps(
                        {"ok": guard.ok, "source": guard.source, "detail": guard.detail},
                        sort_keys=True,
                    )
                    infra = guard.source == "self_certify" or (
                        not guard.ok
                        and any(
                            r in ("expert_error", "expert_timeout", "env_error", "expert_stuck")
                            for r in guard.detail.values()
                        )
                    )
                    if infra:
                        reason, status = "certification_inconclusive", "inconclusive"
                    elif not guard.ok:
                        reason = "uncertified: " + guard_text
                        category, operation = "solvability", "REPLACE_MECHANISM"
                    else:
                        endpoint = self.measure(family, 1.0)
                        if any(t.error for t in endpoint.traces):
                            reason, status = "endpoint_infrastructure_error", "inconclusive"
                            endpoint = None
                        elif endpoint.verdict == "too_hard":
                            reason = "maximum assistance has no operational leverage"
                            category, operation = "no_leverage", "REPLACE_MECHANISM"
                except BudgetExhausted:
                    reason, status = "policy_budget", "budget_unresolved"
                except (AssertionError, ConfigError):
                    raise
                except Exception as exc:
                    reason, status = f"{type(exc).__name__}: {exc}", "inconclusive"
            counts = (endpoint.successes, endpoint.n, endpoint.verdict) if endpoint else None
            record = CandidateRecord(
                cid,
                self.history[-1].candidate_id if self.history else None,
                call_index,
                feedback.operation if feedback else "PROPOSE",
                source,
                sha,
                mechanism,
                tuple(structural),
                tuple(privilege),
                guard_text,
                counts,
                reason or None,
                MAX_OPTIMIZER_CALLS - call_index,
                self.remaining(),
            )
            self.history += (record,)
            if not reason:
                assert family is not None and endpoint is not None
                self.frozen = family
                return DesignResult("viable", family=family, endpoint=endpoint, candidate_id=cid)
            if status != "unresolved":
                return DesignResult(status, reason)
            failed = next((t for t in endpoint.traces if not t.success), None) if endpoint else None
            feedback = Feedback(
                operation,
                category,
                cid,
                source,
                sha,
                mechanism,
                reason,
                self.remaining_calls,
                self.remaining(),
                counts,
                trajectory_text(
                    "candidate_failure", failed, EvidenceBounds(steps_head=6, steps_tail=3)
                )
                if failed
                else None,
                failed.episode_id if failed else None,
            )
            self.rejections += (feedback,)
        return DesignResult("unresolved", self.history[-1].rejection_reason or "call_cap")
