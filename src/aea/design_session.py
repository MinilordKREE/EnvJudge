"""Task-local MEASURE -> DESIGN <-> CONTROL for the explicit v3 selector.

Only this new path reopens DESIGN after empirical control feedback. Historical
selectors retain their own admission, budget and freeze semantics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from envharness.core.types import Candidate, Trace

from aea.actuator import (
    ActuatorCharacterizer,
    Characterization,
    CharacterizationError,
    EffectiveControlLevel,
)
from aea.core.io import append_jsonl
from aea.designer import BOUNDS, Reference, representative, serialize_low
from aea.errors import ConfigError, InfraError
from aea.estimate import EstimateResult
from aea.intervention import FeedbackReason, InterventionFamily, canonical_hash
from aea.intervention_control import ControllerFeedback, EnvironmentController
from aea.intervention_designer import DesignRequest, InterventionDesigner, build_design_context
from aea.intervention_gates import (
    PrivilegeAdmission,
    screen_low,
    validate_characterized_family,
    validate_family,
)
from aea.io import AeaMeta
from aea.privilege_judge import PrivilegeJudge
from aea.privilege_surfaces import ReplayEpisode, capture_episode
from aea.session import SESSION_LOCK
from aea.stage import seeded_failures, trace_actions
from aea.witness import Solvable, policy_shortest_success, solvable

if TYPE_CHECKING:
    from aea.controller import Controller, TaskOutcome, TaskRef


class DesignSession:
    """Bounded orchestration; gates are functions, CONTROL is not an LLM agent."""

    def __init__(self, host: Controller, task: TaskRef, estimate: EstimateResult) -> None:
        self.host = host
        self.task = task
        self.estimate = estimate
        self.config = host.designer_controller_config
        self.directory = host.run_dir / "designer_controller" / canonical_hash(task.task_id)[:16]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.journal = self.directory / "session.jsonl"
        self.final_family: InterventionFamily | None = None
        self.final_characterization: Characterization | None = None
        self.final_admission: PrivilegeAdmission | None = None
        self.final_candidate: Candidate | None = None
        self.final_level_id: str | None = None
        self._certified: dict[str, Solvable] = {}
        self._started = False
        self._ended = False

    def record(self, event: str, **payload: Any) -> None:
        append_jsonl(self.journal, {"event": event, "task_id": self.task.task_id, **payload})

    def remaining(self) -> int:
        return self.host.budget.account(self.task.task_id).remaining()

    def _feedback(
        self,
        reason: FeedbackReason,
        family: InterventionFamily | None,
        design_round: int,
        explanation: str,
    ) -> ControllerFeedback:
        return ControllerFeedback(
            reason=reason,
            family_id=family.family_id if family else f"{self.task.task_id}:D{design_round}",
            design_round=design_round,
            semantic_mechanism_id=family.semantic_mechanism_id if family else "unparsed",
            source_sha256=family.source_sha256 if family else canonical_hash(None),
            explanation=explanation,
            remaining_policy_rollouts=self.remaining(),
        )

    def _capture(self, traces: list[Trace], goal: str) -> tuple[ReplayEpisode, ...]:
        host, task = self.host, self.task
        with SESSION_LOCK:
            return tuple(
                capture_episode(
                    lambda: host.substrate.open_session(task, None, None),
                    task_id=task.task_id,
                    episode_id=trace.episode_id,
                    actions=tuple(trace_actions(trace)),
                    goal=goal,
                    max_steps=host.config.impl.policy_max_steps,
                    task_prompt=str(getattr(host.substrate, "task_prompt", "")),
                    action_format=str(
                        getattr(host.substrate, "policy_spec_kwargs", {}).get(
                            "action_format", "think_action"
                        )
                    ),
                )
                for trace in traces
            )

    def _judge(self) -> PrivilegeJudge:
        judge = self.host._privilege_judge
        if judge is not None:
            return judge
        factory = getattr(self.host.substrate, "privilege_judge", None)
        if not callable(factory):
            raise InfraError("Frozen privilege judge unavailable", kind="config")
        result: PrivilegeJudge = factory(self.host._attr(self.task, "v3_privilege", "none"))
        return result

    def certify(self, candidate: Candidate, *, low: bool) -> Solvable:
        """Cache only byte-identical rendered environments, never just captured equivalence."""
        key = canonical_hash(candidate.model_dump(mode="json", exclude={"rationale"}))
        if key in self._certified:
            self.record("solvability_reused", candidate_sha256=key)
            return self._certified[key]
        with SESSION_LOCK:
            result = solvable(
                candidate,
                lambda c: self.host.substrate.open_session(self.task, c, None),
                self.host.config,
                policy_success=None if low else policy_shortest_success(self.estimate.traces),
                oracle=self.host.substrate.has_oracle(),
                by_construction=False,
            )
        self.record("solvability", candidate_sha256=key, result=asdict(result))
        if result.source == "self_certify" or (
            not result.ok
            and any(
                any(
                    token in str(value)
                    for token in ("expert_error", "expert_timeout", "env_error", "expert_stuck")
                )
                for value in result.detail.values()
            )
        ):
            raise InfraError("Solvability could not be established", kind="solvability")
        if result.ok:
            self._certified[key] = result
        return result

    def run(self) -> TaskOutcome:
        from aea.controller import TaskOutcome

        if self._started or self.journal.exists():
            raise ConfigError(
                "DesignSession is single-use; partial sessions cannot silently restart"
            )
        self._started = True
        host, task, est = self.host, self.task, self.estimate
        if est.regime not in ("zero", "saturated"):
            raise ConfigError("MID must not construct a DesignSession")
        low = est.regime == "zero"
        self.record(
            "session_started",
            regime="LOW" if low else "HIGH",
            config=self.config.model_dump(mode="json"),
            method_config=host.config.model_dump(mode="json"),
        )
        reference: Reference | None = None
        if low:
            reference = host._lazy_reference(task)
            if reference is None:
                raise InfraError("Verified privileged reference unavailable", kind="reference")
            selected = list(seeded_failures(est.traces, 3, seed=task.seed))
        else:
            successes, failures = representative(est.traces, BOUNDS)
            selected = successes + failures
        context = build_design_context(
            task_id=task.task_id,
            regime="LOW" if low else "HIGH",
            traces=est.traces,
            p_hat=est.p_hat,
            n=est.n,
            seed=task.seed,
            reference=reference,
            measurement_evidence={
                "successes": est.successes,
                "probabilities": est.probabilities,
                "stop_reason": est.stop_reason,
            },
        )
        episodes = self._capture(selected, context.task_specification)
        if not episodes or any(episode.error or not episode.snapshots for episode in episodes):
            raise InfraError("Original characterization replay unavailable", kind="capture")
        # Immutable suite across rounds; no new policy calls or privileged prefixes enter it.
        self.record(
            "capture_suite",
            episodes=[
                {"episode_id": e.episode_id, "steps": len(e.snapshots), "error": e.error}
                for e in episodes
            ],
        )
        characterizer = ActuatorCharacterizer(self.config)
        algorithm = EnvironmentController(host.config, self.config)
        designer = InterventionDesigner(
            host._designer(),
            model=host.substrate.designer_model(),
            attribution=host._attr(task, "v3_design_low" if low else "v3_design_high", "designer"),
            seed=task.seed,
            record=lambda request, response: self.record(
                "designer_io",
                request=request.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            ),
        )
        parent: InterventionFamily | None = None
        feedback: ControllerFeedback | None = None
        for design_round in range(1, self.config.max_design_rounds + 1):
            # A new round must afford one complete in-band measurement. No calibration reserve.
            if self.remaining() < host.config.probe[1]:
                self.record(
                    "design_budget_stop", remaining=self.remaining(), required=host.config.probe[1]
                )
                break
            operation = feedback.operation if feedback else "CREATE"
            if operation is None:
                raise ConfigError("Accepted feedback cannot reopen DESIGN")
            request = DesignRequest(
                context=context,
                design_round=design_round,
                operation=operation,
                remaining_design_rounds=self.config.max_design_rounds - design_round + 1,
                remaining_policy_rollouts=self.remaining(),
                parent_family=parent,
                feedback=feedback.as_record() if feedback else None,
            )
            proposal = designer.propose(request)
            self.record(
                "designer_proposal",
                design_round=design_round,
                operation=operation,
                arguments=proposal.arguments,
                errors=proposal.errors,
            )
            if proposal.family is None:
                feedback = self._feedback(
                    "MECHANICAL_FAILURE", parent, design_round, "; ".join(proposal.errors)
                )
                self.record("feedback", **feedback.as_record())
                continue
            preserve = operation in ("REFINE_CONTROL", "REPAIR_CODE") and parent is not None
            family = InterventionFamily(
                **proposal.family.model_dump(),
                family_id=f"{task.task_id}:D{design_round}",
                parent_family_id=parent.family_id if parent else None,
                design_round=design_round,
                operation=operation,
                semantic_mechanism_id=parent.semantic_mechanism_id
                if preserve and parent
                else canonical_hash({"task": task.task_id, "round": design_round}),
            )
            previous = parent
            parent = family
            self.record("family_proposed", family=family.model_dump(mode="json"))
            if (
                preserve
                and previous is not None
                and family.mechanism_summary != previous.mechanism_summary
            ):
                feedback = self._feedback(
                    "MECHANICAL_FAILURE",
                    family,
                    design_round,
                    "Refinement/repair must preserve the parent mechanism_summary verbatim.",
                )
                self.record("feedback", **feedback.as_record())
                parent = previous  # a rejected declaration cannot replace the semantic anchor
                continue
            gate = validate_family(
                family,
                task_id=task.task_id,
                goal=context.task_specification,
                reference=reference,
                baseline_traces=selected,
            )
            if not gate.ok:
                assert gate.failure is not None
                feedback = self._feedback(
                    gate.failure, family, design_round, "; ".join(gate.issues)
                )
                self.record("feedback", **feedback.as_record())
                continue
            try:
                characterization = characterizer.characterize(family, task.task_id, episodes)
            except CharacterizationError as exc:
                feedback = self._feedback("MECHANICAL_FAILURE", family, design_round, str(exc))
                self.record("feedback", **feedback.as_record())
                continue
            self.record("characterization", characterization=characterization.as_record())
            # Full runtime surfaces remain private; public artifacts contain hashes/counts only.
            (self.directory / f"D{design_round}.probes.json").write_text(
                json.dumps([asdict(p) for p in characterization.raw_probes], sort_keys=True)
            )
            gate = validate_characterized_family(
                family, characterization, task_id=task.task_id, config=self.config
            )
            if not gate.ok:
                assert gate.failure is not None
                feedback = self._feedback(
                    gate.failure, family, design_round, "; ".join(gate.issues)
                )
                self.record("feedback", **feedback.as_record())
                continue
            admission: PrivilegeAdmission | None = None
            if low:
                assert reference is not None
                admission = screen_low(
                    family,
                    characterization,
                    task_id=task.task_id,
                    reference=reference,
                    designer_evidence=serialize_low(selected, est.p_hat, est.n, None).text,
                    goal=context.task_specification,
                    judge=self._judge(),
                    audit_dir=self.directory / "privilege",
                    record=lambda record: self.record("privilege", record=record),
                    config=self.config,
                )
                if not admission.ok:
                    feedback = self._feedback(
                        "PRIVILEGE_REJECTION",
                        family,
                        design_round,
                        "; ".join(admission.result.issues),
                    )
                    self.record("feedback", **feedback.as_record())
                    continue
            if not characterization.positive_levels:
                feedback = self._feedback(
                    "NO_LEVERAGE",
                    family,
                    design_round,
                    "Every nominal setting equals OFF on the fixed suite.",
                )
                self.record("feedback", **feedback.as_record())
                continue
            strongest = characterization.positive_levels[-1]
            candidate = family.render(strongest.representative, task.task_id)
            if admission:
                admission.require(
                    family,
                    characterization,
                    strongest,
                    candidate,
                    task_id=task.task_id,
                    config=self.config,
                )
            guard = self.certify(candidate, low=low)
            if not guard.ok:
                feedback = self._feedback(
                    "SOLVABILITY_FAILURE",
                    family,
                    design_round,
                    "Strongest effective level is uncertified.",
                )
                self.record("feedback", **feedback.as_record())
                continue
            self.record(
                "provisional_family",
                family_id=family.family_id,
                characterization_sha256=characterization.sha256,
            )

            def run(
                level: EffectiveControlLevel,
                n: int,
                *,
                bound_family: InterventionFamily = family,
                bound_characterization: Characterization = characterization,
                bound_admission: PrivilegeAdmission | None = admission,
            ) -> list[Trace]:
                actual = bound_family.render(level.representative, task.task_id)
                if bound_admission:
                    bound_admission.require(
                        bound_family,
                        bound_characterization,
                        level,
                        actual,
                        task_id=task.task_id,
                        config=self.config,
                    )
                return host._rollouts(
                    task, actual, n, f"v3_control:{bound_family.family_id}:{level.level_id}"
                )

            decision = algorithm.calibrate(
                family, characterization, run=run, remaining=self.remaining
            )
            feedback = decision.feedback
            self.record("controller_decision", **feedback.as_record())
            if decision.accepted_level is None:
                continue
            chosen = decision.accepted_level
            final = family.render(chosen.representative, task.task_id)
            if admission:
                admission.require(
                    family,
                    characterization,
                    chosen,
                    final,
                    task_id=task.task_id,
                    config=self.config,
                )
            final_guard = self.certify(final, low=low)
            if not final_guard.ok:
                feedback = self._feedback(
                    "SOLVABILITY_FAILURE",
                    family,
                    design_round,
                    "The in-band level failed final exact-environment certification.",
                )
                self.record("feedback", **feedback.as_record())
                continue
            self.final_family = family
            self.final_characterization = characterization
            self.final_admission = admission
            self.final_candidate = final
            self.final_level_id = chosen.level_id
            self._ended = True
            final_record = {
                "search_evidence_sha256": hashlib.sha256(
                    (self.directory / "search_traces.jsonl").read_bytes()
                ).hexdigest(),
                "family": family.model_dump(mode="json"),
                "characterization": characterization.as_record(),
                "chosen_level_id": chosen.level_id,
                "candidate": final.model_dump(mode="json"),
                "candidate_sha256": canonical_hash(
                    final.model_dump(mode="json", exclude={"rationale"})
                ),
                "certification": asdict(final_guard),
                "admission": admission.as_record() if admission else None,
                "v3_config": self.config.model_dump(mode="json"),
                "method_config": host.config.model_dump(mode="json"),
                "search_acceptance": feedback.as_record(),
            }
            (self.directory / "final.json").write_text(
                json.dumps(final_record, sort_keys=True, indent=2) + "\n"
            )
            self.record(
                "final_family_freeze",
                family_id=family.family_id,
                level_id=chosen.level_id,
                final_sha256=canonical_hash(final_record),
            )
            ev = decision.evaluation
            assert ev is not None
            host._write_corpus(
                task,
                final,
                AeaMeta(
                    kind="knob",
                    task_id=task.task_id,
                    seed=task.seed,
                    round=design_round,
                    regime=est.regime,
                    family=family.family_id,
                    source="llm",
                    axis=family.axis,
                    d=chosen.representative.value,
                    p_hat=ev.p_hat,
                    candidate_id=f"{family.family_id}:{chosen.level_id}",
                    n_search=host.baseline_budget.account(task.task_id).spent
                    + host.budget.account(task.task_id).spent,
                ),
            )
            return TaskOutcome(
                task,
                "accepted",
                "",
                est.regime,
                est.p_hat,
                detail={
                    "family_id": family.family_id,
                    "effective_level_id": chosen.level_id,
                    "design_round": design_round,
                },
            )
        self._ended = True
        reason = feedback.reason if feedback else "CONTROL_EXHAUSTED"
        self.record("session_exhausted", reason=reason, remaining=self.remaining())
        return TaskOutcome(task, "dropped", reason, est.regime, est.p_hat)


def run_designer_controller(
    host: Controller, task: TaskRef, estimate: EstimateResult
) -> TaskOutcome:
    session = DesignSession(host, task, estimate)
    host.design_sessions[task.task_id] = session
    return session.run()
