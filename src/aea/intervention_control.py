"""Algorithmic empirical control of distinct, captured intervention levels.

No language model, numeric-dose bracket, or intensity oracle is used here. Nominal
order is a search proposal only. Equivalence comes exclusively from characterization.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any

from envharness.core.types import Trace

from aea.actuator import Characterization, EffectiveControlLevel
from aea.config import AEAConfig
from aea.errors import BudgetExhausted, ConfigError, InfraError
from aea.evaluate import Eval, evaluate
from aea.intervention import DesignOperation, FeedbackReason, InterventionFamily, V3Config


def feedback_operation(reason: FeedbackReason) -> DesignOperation | None:
    if reason == "ACCEPTED":
        return None
    if reason == "MECHANICAL_FAILURE":
        return "REPAIR_CODE"
    if reason in ("NO_LEVERAGE", "PRIVILEGE_REJECTION", "SOLVABILITY_FAILURE"):
        return "REPLACE_MECHANISM"
    return "REFINE_CONTROL"


@dataclass(frozen=True)
class LevelProbe:
    level_id: str
    surface_signature: str
    setting: float
    successes: int
    n: int
    verdict: str | None
    complete: bool
    episode_ids: tuple[str, ...]


@dataclass(frozen=True)
class ControllerFeedback:
    reason: FeedbackReason
    family_id: str
    design_round: int
    semantic_mechanism_id: str
    source_sha256: str
    explanation: str
    probes: tuple[LevelProbe, ...] = ()
    effective_level_count: int = 0
    nominal_setting_count: int = 0
    diagnostics: tuple[str, ...] = ()
    remaining_policy_rollouts: int = 0

    @property
    def operation(self) -> DesignOperation | None:
        return feedback_operation(self.reason)

    def as_record(self) -> dict[str, Any]:
        return {**asdict(self), "operation": self.operation}


@dataclass(frozen=True)
class ControllerDecision:
    feedback: ControllerFeedback
    accepted_level: EffectiveControlLevel | None = None
    evaluation: Eval | None = None


class EnvironmentController:
    """One provisional family, bounded distinct-level search, then typed feedback.

    Strongest proposed level first, weakest next, then the middle of the largest
    remaining ordinal gap. No region is eliminated on a noisy monotonicity assumption.
    An in-band result is provisional until the caller certifies that exact environment.
    """

    def __init__(self, config: AEAConfig, control_config: V3Config | None = None) -> None:
        self.config = config
        self.control_config = control_config or V3Config()

    def calibrate(
        self,
        family: InterventionFamily,
        characterization: Characterization,
        *,
        run: Callable[[EffectiveControlLevel, int], list[Trace]],
        remaining: Callable[[], int],
    ) -> ControllerDecision:
        if characterization.family_id != family.family_id:
            raise ConfigError("Controller characterization belongs to another family")
        if characterization.source_sha256 != family.source_sha256:
            raise ConfigError("Controller characterization source mismatch")
        levels = tuple(characterization.positive_levels)
        probes: list[LevelProbe] = []
        tested: set[int] = set()
        seen_signatures: set[str] = set()

        def finish(
            reason: FeedbackReason,
            explanation: str,
            level: EffectiveControlLevel | None = None,
            evaluation: Eval | None = None,
        ) -> ControllerDecision:
            return ControllerDecision(
                ControllerFeedback(
                    reason=reason,
                    family_id=family.family_id,
                    design_round=family.design_round,
                    semantic_mechanism_id=family.semantic_mechanism_id,
                    source_sha256=family.source_sha256,
                    explanation=explanation,
                    probes=tuple(probes),
                    effective_level_count=len(characterization.levels),
                    nominal_setting_count=len(characterization.settings),
                    diagnostics=tuple(characterization.diagnostics),
                    remaining_policy_rollouts=remaining(),
                ),
                level,
                evaluation,
            )

        if not levels:
            return finish("NO_LEVERAGE", "All characterized settings equal original OFF.")
        no_leverage = "too_hard" if family.direction == "easier" else "too_easy"
        overshoot = "too_easy" if family.direction == "easier" else "too_hard"
        while len(tested) < min(len(levels), self.control_config.max_control_probes):
            if not tested:
                index = len(levels) - 1
            elif 0 not in tested:
                index = 0
            else:
                # Largest untested ordinal gap; deterministic midpoint, no raw-dose math.
                boundaries = [-1, *sorted(tested), len(levels)]
                gaps = [
                    (right - left - 1, left, right)
                    for left, right in pairwise(boundaries)
                    if right - left > 1
                ]
                _, left, right = max(gaps, key=lambda gap: (gap[0], -gap[1]))
                index = (left + right) // 2
            level = levels[index]
            if level.surface_signature in seen_signatures:
                raise ConfigError("Characterizer supplied duplicate effective levels")
            traces: list[Trace] = []

            def batch(
                n: int,
                bound_level: EffectiveControlLevel = level,
                collected: list[Trace] = traces,
            ) -> list[Trace]:
                result = run(bound_level, n)
                if len(result) != n or any(trace.error for trace in result):
                    raise InfraError("Incomplete effective-level policy batch", kind="rollout")
                collected.extend(result)
                return result

            try:
                ev = evaluate(batch, self.config)
            except BudgetExhausted:
                if traces:
                    probes.append(
                        LevelProbe(
                            level.level_id,
                            level.surface_signature,
                            level.representative.value,
                            sum(bool(trace.success) for trace in traces),
                            len(traces),
                            None,
                            False,
                            tuple(trace.episode_id for trace in traces),
                        )
                    )
                return finish("CONTROL_EXHAUSTED", "Budget cannot complete the next probe batch.")
            tested.add(index)
            seen_signatures.add(level.surface_signature)
            probes.append(
                LevelProbe(
                    level.level_id,
                    level.surface_signature,
                    level.representative.value,
                    ev.successes,
                    ev.n,
                    ev.verdict,
                    True,
                    tuple(trace.episode_id for trace in ev.traces),
                )
            )
            if ev.verdict == "in_band":
                return finish(
                    "ACCEPTED", "A distinct effective level meets the search target.", level, ev
                )
            if len(tested) == 1 and ev.verdict == no_leverage:
                return finish(
                    "NO_LEVERAGE",
                    "Strongest proposed effective level remains on the baseline side.",
                )
            if len(levels) == 1:
                reason: FeedbackReason = (
                    "OVERPOWERED_BINARY"
                    if family.control.kind == "BINARY"
                    else "INSUFFICIENT_ATTENUATION"
                )
                return finish(
                    reason,
                    "Positive level overshoots; preserve the mechanism and refine control.",
                )

        if len(tested) < len(levels):
            return finish(
                "CONTROL_EXHAUSTED",
                "Distinct levels remain after bounded search; refine if another round remains.",
            )
        verdicts = {probe.verdict for probe in probes}
        if no_leverage in verdicts and overshoot in verdicts:
            return finish(
                "INSUFFICIENT_RESOLUTION",
                "Levels fall on both sides of the target; none was accepted.",
            )
        if verdicts == {overshoot}:
            return finish(
                "INSUFFICIENT_ATTENUATION", "Every positive effective level overshoots the target."
            )
        return finish("CONTROL_EXHAUSTED", "All distinct levels were measured without acceptance.")
