"""Bounded controller outcomes use distinct characterized effects, not nominal doses."""

from __future__ import annotations

from collections import Counter

import pytest
from envharness.core.types import Candidate, Trace

from aea.actuator import ActuatorCharacterizer, EffectiveControlLevel
from aea.config import AEAConfig
from aea.errors import BudgetExhausted, InfraError
from aea.intervention import InterventionFamily, V3Config
from aea.intervention_control import ControllerDecision, EnvironmentController
from tests.unit.test_actuator import episode, family


class Runner:
    def __init__(self, outcomes: dict[float, list[int]], cap: int = 80) -> None:
        self.outcomes = outcomes
        self.cap = cap
        self.spent = 0
        self.calls: list[tuple[float, int]] = []
        self.positions: Counter[float] = Counter()

    def remaining(self) -> int:
        return self.cap - self.spent

    def run(self, level: EffectiveControlLevel, n: int) -> list[Trace]:
        if self.spent + n > self.cap:
            raise BudgetExhausted("test cap", budget="adapt", cap=self.cap, spent=self.spent)
        setting = level.representative.value
        self.calls.append((setting, n))
        start = self.positions[setting]
        selected = self.outcomes[setting][start : start + n]
        self.positions[setting] += n
        traces = [
            Trace(
                episode_id=f"policy-{self.spent + index}",
                iteration_id="control",
                task_id="synthetic",
                candidate=Candidate(),
                success=bool(ok),
            )
            for index, ok in enumerate(selected)
        ]
        self.spent += len(traces)
        return traces


def calibrate(
    f: InterventionFamily,
    runner: Runner,
    *,
    config: AEAConfig | None = None,
    control: V3Config | None = None,
) -> ControllerDecision:
    char = ActuatorCharacterizer(control).characterize(f, "synthetic", (episode(),))
    return EnvironmentController(config or AEAConfig(), control).calibrate(
        f,
        char,
        run=runner.run,
        remaining=runner.remaining,
    )


@pytest.mark.parametrize("direction", ["easier", "harder"])
def test_c_binary_direct_band_accepts_without_inventing_interior_settings(direction: str) -> None:
    f = family(kind="BINARY").model_copy(update={"direction": direction})
    runner = Runner({1.0: [1, 0, 1, 0, 1, 0, 1, 0]})
    decision = calibrate(f, runner)
    assert decision.feedback.reason == "ACCEPTED"
    assert decision.accepted_level is not None and decision.accepted_level.representative.value == 1
    assert runner.calls == [(1, 4), (1, 4)]
    assert len(decision.feedback.probes) == 1
    assert decision.feedback.probes[0].n == 8
    assert decision.feedback.operation is None


@pytest.mark.parametrize(("direction", "success"), [("easier", 1), ("harder", 0)])
def test_d_binary_overshoot_requests_control_refinement(direction: str, success: int) -> None:
    runner = Runner({1.0: [success] * 4})
    decision = calibrate(family(kind="BINARY").model_copy(update={"direction": direction}), runner)
    assert decision.feedback.reason == "OVERPOWERED_BINARY"
    assert decision.feedback.operation == "REFINE_CONTROL"
    assert decision.accepted_level is None and runner.calls == [(1, 4)]


@pytest.mark.parametrize(("direction", "success"), [("easier", 0), ("harder", 1)])
def test_e_no_leverage_requests_new_mechanism(direction: str, success: int) -> None:
    runner = Runner({1.0: [success] * 4})
    decision = calibrate(family().model_copy(update={"direction": direction}), runner)
    assert decision.feedback.reason == "NO_LEVERAGE"
    assert decision.feedback.operation == "REPLACE_MECHANISM"
    assert runner.calls == [(1, 4)]


def test_f_discrete_gap_returns_insufficient_resolution_without_bisecting() -> None:
    f = family('"low" if self.DOSE <= 0.5 else "high"')
    runner = Runner({0.5: [0] * 4, 1.0: [1] * 4})
    decision = calibrate(f, runner)
    assert decision.feedback.reason == "INSUFFICIENT_RESOLUTION"
    assert decision.feedback.operation == "REFINE_CONTROL"
    assert runner.calls == [(1, 4), (0.5, 4)]
    assert len({probe.surface_signature for probe in decision.feedback.probes}) == 2


def test_g_weakest_positive_overshoot_requests_attenuation() -> None:
    runner = Runner({0.5: [1] * 4, 1.0: [1] * 4})
    decision = calibrate(family('"low" if self.DOSE <= 0.5 else "high"'), runner)
    assert decision.feedback.reason == "INSUFFICIENT_ATTENUATION"
    assert decision.feedback.operation == "REFINE_CONTROL"
    assert runner.calls == [(1, 4), (0.5, 4)]


def test_h_equivalent_nominal_settings_never_receive_independent_noisy_probes() -> None:
    # These hypothetical opposite endpoint results belong to the SAME captured effect.
    # The representative's 4/4 result must not induce a retry of an alias returning 0/4.
    runner = Runner({0.25: [0] * 4, 0.5: [0] * 4, 0.75: [0] * 4, 1.0: [1] * 4})
    decision = calibrate(family('"same"'), runner)
    assert decision.feedback.reason == "INSUFFICIENT_ATTENUATION"
    assert runner.calls == [(1, 4)]
    assert decision.feedback.effective_level_count == 2
    assert decision.feedback.nominal_setting_count == 5


def test_j_explicit_target_and_probe_settings_are_used() -> None:
    runner = Runner({1.0: [1, 0, 0, 0, 0, 0]})
    config = AEAConfig(probe=(2, 6), accept=(1, 1), band_t=(0.1, 0.3))
    decision = calibrate(family(kind="BINARY"), runner, config=config)
    assert decision.feedback.reason == "ACCEPTED"
    assert runner.calls == [(1, 2), (1, 4)]
    assert decision.evaluation is not None and decision.evaluation.successes == 1


def test_partial_topup_budget_retains_first_batch_and_fresh_episode_ids() -> None:
    runner = Runner({1.0: [1, 0, 1, 0]}, cap=6)
    decision = calibrate(family(kind="BINARY"), runner)
    assert decision.feedback.reason == "CONTROL_EXHAUSTED"
    assert decision.feedback.remaining_policy_rollouts == 2
    assert runner.spent == 4
    (probe,) = decision.feedback.probes
    assert not probe.complete and probe.n == 4 and probe.successes == 2 and probe.verdict is None
    assert len(set(probe.episode_ids)) == 4


def test_maximum_probe_count_includes_initial_strongest() -> None:
    runner = Runner({value: [1] * 4 for value in (0.25, 0.5, 0.75, 1)})
    decision = calibrate(family(), runner, control=V3Config(max_control_probes=2))
    assert decision.feedback.reason == "CONTROL_EXHAUSTED"
    assert runner.calls == [(1, 4), (0.25, 4)]
    assert len(decision.feedback.probes) == 2


def test_non_monotone_recurrence_is_preserved_without_reprobing_alias() -> None:
    runner = Runner({1.0: [1] * 4})
    decision = calibrate(family('"" if self.DOSE == 0.5 else "same"'), runner)
    assert decision.feedback.diagnostics == ("NON_MONOTONE_CONTROL_SURFACE",)
    assert runner.calls == [(1, 4)]


def test_all_identity_has_no_policy_calls() -> None:
    runner = Runner({})
    decision = calibrate(family('""'), runner)
    assert decision.feedback.reason == "NO_LEVERAGE"
    assert runner.calls == []


def test_incomplete_policy_return_is_infrastructure_error() -> None:
    runner = Runner({1.0: [1]})
    with pytest.raises(InfraError):
        calibrate(family(kind="BINARY"), runner)


def test_strongest_weakest_then_ordinal_gaps_no_monotonic_pruning() -> None:
    runner = Runner({1: [1] * 4, 0.25: [0] * 4, 0.5: [1] * 4, 0.75: [1, 0] * 4})
    decision = calibrate(family(), runner)
    assert decision.feedback.reason == "ACCEPTED"
    assert runner.calls == [(1, 4), (0.25, 4), (0.5, 4), (0.75, 4), (0.75, 4)]
    assert len(decision.feedback.probes) == 4
