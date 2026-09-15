"""Real ALFWorld original-state replay and task110 gate; no policy or model call."""

from __future__ import annotations

import pytest
from scripts.semantic_privilege_benchmark import load_fixture, reference_from

from aea.privilege_surfaces import capture_episode, probe_template
from aea.semantic_privilege import SemanticGateInput, screen_semantic_privilege
from aea.session import DEFAULT_RESET_OPTIONS, TASK_LABEL, open_session

pytestmark = pytest.mark.integration


def test_task110_original_replay_and_semantic_screen() -> None:
    fixture = load_fixture()
    episode = capture_episode(
        lambda: open_session(None, 110, DEFAULT_RESET_OPTIONS),
        task_id="110",
        episode_id="offline-real-110",
        actions=("go to sidetable 1",),
        goal=fixture["goal"],
    )
    assert episode.error is None and len(episode.snapshots) == 2
    assert episode.seed == 110 and episode.reset_options
    assert episode.reset_options["task_id"] == TASK_LABEL
    assert episode.snapshots[0].observation.text == fixture["reference"]["steps"][0]["observation"]
    assert tuple(episode.snapshots[0].observation.data["admissible_commands"]) == tuple(
        fixture["reference"]["steps"][0]["admissible"]
    )
    assert episode.snapshots[1].observation.text == fixture["raw_snapshot"]["observation"]["text"]
    source = fixture["candidate_source"]
    probes = probe_template(source, "110", (episode,))
    result = screen_semantic_privilege(
        SemanticGateInput(
            source, reference_from(fixture), fixture["designer_evidence"], probes, "110"
        )
    )
    assert result.decision == "FAIL"
    assert any(
        "sofa" in finding.information and finding.decision == "FAIL" for finding in result.findings
    )
    assert all("pillow 1 on sofa 1" not in "\n".join(p.evidence.observations) for p in probes)
