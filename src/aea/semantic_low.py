"""Admission-only adapter around the frozen iterative LOW optimizer.

The original optimizer, proposal prompts, budgets and CONTROL remain unchanged. Semantic
FAIL uses its existing privilege feedback route. UNCERTAIN records the attempted candidate
and stops before certification or measurement, without consuming a redesign opportunity.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, NoReturn

from envharness.core.types import Trace

from aea.designer import AssistFamily, Reference
from aea.low_optimizer import CandidateRecord, DesignResult, LowEnvironmentOptimizer
from aea.privilege_surfaces import ReplayEpisode, capture_episode, probe_template
from aea.semantic_privilege import (
    AuthorizedEvidence,
    SemanticGateInput,
    SemanticGateResult,
    SurfaceProbe,
    screen_semantic_privilege,
)
from aea.session import Session
from aea.stage import trace_actions


def reachable_screen_doses(max_bisections: int) -> tuple[float, ...]:
    """All possible doses visited by the unchanged bounded binary CONTROL, plus identity."""
    if not 0 <= max_bisections <= 5:
        raise ValueError("semantic screening supports at most 5 bisections")
    denominator = 2**max_bisections
    return tuple(round(i / denominator, 6) for i in range(denominator + 1))


class SemanticAdmissionError(RuntimeError):
    """No semantic admission exists for this exact candidate and dose."""


class _UncertainAdmissionError(Exception):
    pass


class ScreenedLowOptimizer(LowEnvironmentOptimizer):
    """Reuse the complete existing state machine; extend only its admission boundary."""

    def __init__(
        self,
        *args: Any,
        screen: Callable[[AssistFamily], SemanticGateResult],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._semantic_screen = screen

    def _validate(self, args: dict[str, Any]) -> tuple[AssistFamily | None, list[str], list[str]]:
        family, structural, privilege = super()._validate(args)
        if family is None or structural or privilege:
            return family, structural, privilege
        sha = hashlib.sha256(family.template.encode()).hexdigest()
        if any(record.source_sha256 == sha for record in self.history):
            return family, structural, privilege  # existing duplicate handling owns rejection
        try:
            result = self._semantic_screen(family)
        except Exception as exc:
            self._stop_uncertain(
                family, f"semantic_privilege_uncertain: {type(exc).__name__}: {exc}"
            )
        expected = (
            "FAIL"
            if any(f.decision == "FAIL" for f in result.findings)
            else "UNCERTAIN"
            if any(f.decision == "UNCERTAIN" for f in result.findings)
            else "PASS"
        )
        if result.source_sha256 != sha or not result.findings or result.decision != expected:
            self._stop_uncertain(family, "semantic_privilege_uncertain: inconsistent gate result")
        if result.decision == "PASS":
            return family, [], []
        witnesses = [asdict(f) for f in result.findings if f.decision == result.decision][:3]
        reason = (
            "semantic_privilege_"
            + result.decision.lower()
            + ": "
            + json.dumps(
                {
                    "gate_version": result.version,
                    "gate_input_sha256": result.input_sha256,
                    "findings": witnesses,
                },
                sort_keys=True,
            )
        )
        if result.decision == "FAIL":
            return None, [], [reason]
        return self._stop_uncertain(family, reason)

    def _stop_uncertain(self, family: AssistFamily, reason: str) -> NoReturn:
        sha = hashlib.sha256(family.template.encode()).hexdigest()
        # The old optimizer has no uncertain validation verdict. Record this attempt here
        # and unwind its run; do not misclassify uncertainty as mechanical/solvability failure.
        call_index = len(self.history) + 1
        self.current = family
        self.history += (
            CandidateRecord(
                candidate_id=f"{self.task_id}:C{call_index}:{sha}",
                parent_candidate_id=self.history[-1].candidate_id if self.history else None,
                optimizer_call_index=call_index,
                requested_operation=self.rejections[-1].operation if self.rejections else "PROPOSE",
                source=family.template,
                source_sha256=sha,
                mechanism=family.mechanism_summary,
                structural=(),
                privilege=(reason,),
                solvability=None,
                endpoint=None,
                rejection_reason=reason,
                remaining_calls=self.remaining_calls - 1,
                remaining_policy=self.remaining(),
            ),
        )
        raise _UncertainAdmissionError(reason)

    def run(self) -> DesignResult:
        try:
            return super().run()
        except _UncertainAdmissionError as exc:
            return DesignResult("inconclusive", str(exc))


class LowPrivilegeScreen:
    """Task-local, arm-neutral admission with replayable audit inputs and exact-dose checks."""

    def __init__(
        self,
        *,
        task_id: str,
        reference: Reference,
        designer_evidence: str,
        failures: Sequence[Trace],
        goal: str,
        open_original_session: Callable[[], Session],
        max_bisections: int,
        audit_dir: Path,
        record: Callable[[dict[str, Any]], None],
        max_steps: int = 50,
        task_prompt: str = "",
        action_format: str = "think_action",
    ) -> None:
        self.task_id = task_id
        self.reference = reference
        self.designer_evidence = designer_evidence
        self.failures = tuple(failures)
        self.goal = goal
        self.open_original_session = open_original_session
        self.max_bisections = max_bisections
        self.max_steps = max_steps
        self.audit_dir = audit_dir
        self.record = record
        self.task_prompt = task_prompt
        self.action_format = action_format
        self._episodes: tuple[ReplayEpisode, ...] | None = None
        self._admitted: dict[str, tuple[float, ...]] = {}

    def _capture(self) -> tuple[ReplayEpisode, ...]:
        if self._episodes is None:
            self._episodes = tuple(
                replace(
                    capture_episode(
                        self.open_original_session,
                        task_id=self.task_id,
                        episode_id=trace.episode_id,
                        actions=tuple(trace_actions(trace)),
                        goal=self.goal,
                        max_steps=self.max_steps,
                    ),
                    task_prompt=self.task_prompt,
                    action_format=self.action_format,
                )
                for trace in self.failures
            )
        return self._episodes

    def screen(self, family: AssistFamily) -> SemanticGateResult:
        self._admitted.pop(hashlib.sha256(family.template.encode()).hexdigest(), None)
        doses: tuple[float, ...] = ()
        try:
            doses = reachable_screen_doses(self.max_bisections)
            probes = probe_template(family.template, self.task_id, self._capture(), doses)
        except Exception as exc:
            probes = (
                SurfaceProbe(
                    AuthorizedEvidence(self.task_id, "unavailable", 0, self.goal, ()),
                    0.0,
                    {},
                    {},
                    error=f"screening inputs unavailable: {type(exc).__name__}: {exc}",
                ),
            )
        request = SemanticGateInput(
            family.template, self.reference, self.designer_evidence, probes, self.task_id
        )
        result = screen_semantic_privilege(request)
        # Store exact privileged inputs separately from optimizer feedback and policy prompts.
        # Hash-addressed gzip avoids quadratic raw-history duplication in the JSONL index.
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        path = self.audit_dir / f"{result.input_sha256}.json.gz"
        payload = json.dumps(asdict(request), sort_keys=True, ensure_ascii=False, default=str)
        if hashlib.sha256(payload.encode()).hexdigest() != result.input_sha256:
            raise SemanticAdmissionError("semantic audit input hash mismatch")
        if path.exists():
            if gzip.decompress(path.read_bytes()) != payload.encode():
                raise SemanticAdmissionError("existing semantic audit artifact is corrupt")
        else:
            path.write_bytes(gzip.compress(payload.encode(), mtime=0))
        self.record(
            {
                "task_id": self.task_id,
                "family": family.name,
                "doses": doses,
                "input_artifact": str(path),
                "result": result.as_record(),
            }
        )
        if result.decision == "PASS":
            self._admitted[result.source_sha256] = doses
        return result

    def require_pass(self, family: AssistFamily, dose: float) -> None:
        source_sha256 = hashlib.sha256(family.template.encode()).hexdigest()
        if dose not in self._admitted.get(source_sha256, ()):
            raise SemanticAdmissionError(
                f"No PASS admission for source={source_sha256}, dose={dose:g}"
            )
