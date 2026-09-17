"""Actual ALFWorld fixed-prefix characterization; no external model or policy calls."""

from __future__ import annotations

import pytest

from aea.actuator import ActuatorCharacterizer
from aea.intervention import Direction, InterventionFamily
from aea.intervention_gates import validate_characterized_family
from aea.privilege_surfaces import capture_episode
from aea.session import DEFAULT_RESET_OPTIONS, open_session

pytestmark = pytest.mark.integration

# A generic synthetic hook: no reference observation, location, route or GT action fixture.
SOURCE = """class _Rules(Rules):
    DOSE = __DOSE__
    def filter_observation(self, obs, env_state):
        if self.DOSE > 0:
            text = obs.text + "\\nReview the current visible options."
            return Observation(text=text, data=obs.data)
        return obs
"""


@pytest.mark.parametrize("direction", ["easier", "harder"])
def test_real_original_capture_and_equivalent_settings(direction: Direction) -> None:
    # This tests capture/identity/control representation, not intervention efficacy.
    episode = capture_episode(
        lambda: open_session(None, 0, DEFAULT_RESET_OPTIONS),
        task_id="0",
        episode_id="v3-offline-real-prefix",
        actions=("look", "look"),
        goal="offline capture; no reference supplied",
    )
    assert episode.error is None and len(episode.snapshots) == 3
    family = InterventionFamily(
        family_id="synthetic-runtime",
        semantic_mechanism_id="synthetic-runtime",
        direction=direction,
        mechanism_summary="Synthetic observation marker for replay validation",
        source=SOURCE,
        axis="O",
        expected_effect="No efficacy claim",
    )
    characterizer = ActuatorCharacterizer()
    result = characterizer.characterize(family, "0", (episode,))
    assert len(result.settings) == 17
    assert len(result.levels) == 2 and len(result.positive_levels) == 1
    assert len(result.positive_levels[0].equivalent_settings) == 16
    assert result.coverage["actual_count"] == 51
    assert result.off_level.is_off
    assert validate_characterized_family(family, result, task_id="0").ok
