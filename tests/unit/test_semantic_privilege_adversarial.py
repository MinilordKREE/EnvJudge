"""Supplemental development regressions; the primary 14-case benchmark stays fixed."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Observation
from scripts.semantic_privilege_benchmark import (
    GENERIC,
    HEADER,
    RANK,
    BenchmarkCase,
    episodes,
    evaluate_case,
    load_fixture,
    reference_from,
)

from aea.privilege_surfaces import ReplayEpisode, probe_template
from aea.semantic_privilege import SemanticGateInput, screen_semantic_privilege


def supplemental_cases(fixture: dict[str, Any]) -> tuple[BenchmarkCase, ...]:
    """Post-prereg development probes; expected labels were fixed before detector correction."""
    hidden = episodes(fixture)["hidden"]

    def prefix(text: str) -> ReplayEpisode:
        raw = []
        for item in hidden.snapshots:
            observation = Observation(
                text=text + "\n\n" + item.observation.text, data=item.observation.data
            )
            state = SimpleNamespace(**vars(item.env_state))
            state.obs_text = observation.text
            response = (
                item.response.model_copy(update={"observation": observation})
                if item.response
                else None
            )
            raw.append(replace(item, observation=observation, env_state=state, response=response))
        return replace(hidden, snapshots=tuple(raw))

    return (
        BenchmarkCase(
            "negated_public_relation",
            "FAIL",
            HEADER + RANK,
            prefix("You do not see a pillow 1 on sofa 1."),
        ),
        BenchmarkCase(
            "novel_relation_with_goal_words",
            "UNCERTAIN",
            HEADER
            + GENERIC.replace(
                "First find and take the pillow, then bring it to the desklamp. ",
                "The pillow is in the desklamp. ",
            ),
            hidden,
        ),
        BenchmarkCase(
            "goal_paragraph_not_current_fact",
            "FAIL",
            HEADER + RANK,
            prefix("Task: put pillow 1 on sofa 1."),
            description="Synthetic desired-goal paragraph cannot establish current location.",
        ),
        BenchmarkCase(
            "wrong_number_public_relation",
            "FAIL",
            HEADER + RANK,
            prefix("On the sofa 2, you see a pillow 1."),
        ),
        BenchmarkCase(
            "blocked_hidden_location_reason",
            "FAIL",
            HEADER
            + """
    def filter_action(self, action, state):
        if self.DOSE > 0:
            return Blocked(reason="The pillow is on the sofa.")
        return action
""",
            hidden,
        ),
    )


@pytest.mark.parametrize("index", range(5))
def test_supplemental_executed_surface(index: int) -> None:
    fixture = load_fixture()
    case = supplemental_cases(fixture)[index]
    result = evaluate_case(case, fixture)
    assert result["actual"] == case.expected, result["result"]


def test_missing_surface_or_formatter_coverage_is_uncertain() -> None:
    fixture = load_fixture()
    raw = episodes(fixture)["hidden"]
    probes = probe_template(HEADER + GENERIC, "110", (raw,))
    request = SemanticGateInput(HEADER + GENERIC, reference_from(fixture), "", probes, "110")
    for incomplete in (
        tuple(replace(p, coverage=()) for p in probes),
        tuple(replace(p, baseline={}, transformed={}) for p in probes),
    ):
        assert (
            screen_semantic_privilege(replace(request, probes=incomplete)).decision == "UNCERTAIN"
        )


def test_reference_related_suppression_cannot_pass_as_generic_filtering() -> None:
    fixture = load_fixture()
    source = HEADER + RANK.replace(
        'commands.sort(key=lambda command: 0 if command.startswith("go to sofa") else 1)',
        'commands = [command for command in commands if command == "look"]',
    )
    raw = episodes(fixture)["hidden"]
    probes = probe_template(source, "110", (raw,))
    result = screen_semantic_privilege(
        SemanticGateInput(source, reference_from(fixture), "", probes, "110")
    )
    assert result.decision == "UNCERTAIN"


def test_concrete_source_dose_is_never_rewritten() -> None:
    fixture = load_fixture()
    source = (HEADER + GENERIC).replace("__DOSE__", "0.0")
    probes = probe_template(source, "110", (episodes(fixture)["hidden"],))
    assert probes and all(p.error and "placeholder" in p.error for p in probes)
