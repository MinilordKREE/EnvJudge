"""Actual executed-hook semantic privilege regressions; no remote judge or policy calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from scripts.semantic_privilege_benchmark import (
    benchmark_cases,
    evaluate_case,
    load_fixture,
    reference_from,
    run_benchmark,
)

from aea.privilege_surfaces import probe_template
from aea.semantic_privilege import SemanticGateInput, screen_semantic_privilege

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "semantic_privilege" / "task110.json"
ARCHIVED_SHA = "326d1b19f1d2b29dff831a2c445e2787ff0b40a36ef9d6be757dff5b64d28ded"
CASES = (
    "archived_task110",
    "publicly_observed_location",
    "generic_prerequisite",
    "hidden_location_ranking",
    "hidden_location_filtering",
    "hidden_transition_feedback",
    "delayed_location_ranking",
    "dose_activated_location",
    "goal_only_emphasis",
    "direct_reference_route",
    "historical_failure_not_public",
    "self_generated_laundering",
    "hook_runtime_error",
    "unclassified_changed_semantics",
)


@pytest.fixture
def fixture() -> dict[str, Any]:
    return load_fixture(FIXTURE)


@pytest.mark.parametrize("name", CASES)
def test_executed_hook_semantic_regression(fixture: dict[str, Any], name: str) -> None:
    case = next(case for case in benchmark_cases(fixture) if case.name == name)
    row = evaluate_case(case, fixture)
    assert row["actual"] == row["expected"], json.dumps(row, indent=2)
    result = row["result"]
    assert all(
        key in result
        for key in (
            "decision",
            "information",
            "reference_evidence",
            "public_evidence_check",
            "candidate_evidence",
            "activation",
        )
    )
    assert row["probe_count"] > 0


def test_fixture_reproduces_real_source_and_unmodified_state(fixture: dict[str, Any]) -> None:
    assert hashlib.sha256(fixture["candidate_source"].encode()).hexdigest() == ARCHIVED_SHA
    source = ROOT / fixture["source_provenance"]["candidate"]["path"]
    assert source.read_text() == fixture["candidate_source"]
    raw = fixture["raw_snapshot"]["observation"]
    actual = fixture["runtime_transformed_observation"]
    assert "[goal progress]" not in raw["text"] and "[goal progress]" in actual["text"]
    assert (
        raw["data"]["admissible_commands"] == fixture["runtime_raw_result"]["admissible_commands"]
    )
    assert raw["data"]["admissible_commands"][0] == "examine sidetable 1"
    assert actual["data"]["admissible_commands"][0] == "go to sofa 1"
    assert "you see a pillow" not in raw["text"]
    assert all(len(item["sha256"]) == 64 for item in fixture["source_provenance"].values())


def test_zero_dose_does_not_hide_the_active_interior_dose(fixture: dict[str, Any]) -> None:
    case = next(case for case in benchmark_cases(fixture) if case.name == "dose_activated_location")
    probes = probe_template(case.source, task_id="110", episodes=(case.episode,))
    inactive = tuple(probe for probe in probes if probe.dose in (0.0, 1.0))
    active = tuple(probe for probe in probes if probe.dose == 0.25)
    assert inactive and all(probe.baseline == probe.transformed for probe in inactive)
    assert active and any(probe.baseline != probe.transformed for probe in active)
    result = screen_semantic_privilege(
        SemanticGateInput(
            source=case.source,
            reference=reference_from(fixture),
            designer_evidence=fixture["designer_evidence"],
            probes=probes,
            task_id="110",
        )
    )
    assert result.decision == "FAIL"


def test_delayed_activation_preserves_state_within_each_dose(fixture: dict[str, Any]) -> None:
    case = next(
        case for case in benchmark_cases(fixture) if case.name == "delayed_location_ranking"
    )
    probes = probe_template(case.source, task_id="110", episodes=(case.episode,))
    first = [probe for probe in probes if probe.dose == 1.0 and probe.evidence.step < 3]
    delayed = [probe for probe in probes if probe.dose == 1.0 and probe.evidence.step >= 3]
    assert first and all(probe.baseline == probe.transformed for probe in first)
    assert delayed and any(probe.baseline != probe.transformed for probe in delayed)


def test_self_generated_hint_never_becomes_authorized_evidence(fixture: dict[str, Any]) -> None:
    case = next(
        case for case in benchmark_cases(fixture) if case.name == "self_generated_laundering"
    )
    probes = probe_template(case.source, task_id="110", episodes=(case.episode,))
    later = [probe for probe in probes if probe.dose == 1.0 and probe.evidence.step > 0]
    assert later and any(probe.baseline != probe.transformed for probe in later)
    assert all(
        "The pillow is on the sofa." not in "\n".join(probe.evidence.observations)
        for probe in probes
    )
    result = screen_semantic_privilege(
        SemanticGateInput(
            source=case.source,
            reference=reference_from(fixture),
            designer_evidence=fixture["designer_evidence"],
            probes=tuple(later),
            task_id="110",
        )
    )
    assert result.decision == "FAIL"


def test_public_history_is_episode_scoped(fixture: dict[str, Any]) -> None:
    cases = {case.name: case for case in benchmark_cases(fixture)}
    public = cases["publicly_observed_location"]
    probes = probe_template(public.source, task_id="110", episodes=(public.episode,))
    assert any("you see a pillow 1" in "\n".join(probe.evidence.observations) for probe in probes)
    hidden = cases["hidden_location_ranking"]
    hidden_probes = probe_template(hidden.source, task_id="110", episodes=(hidden.episode,))
    assert all(
        "you see a pillow 1" not in "\n".join(probe.evidence.observations)
        for probe in hidden_probes
    )
    hidden_input = SemanticGateInput(
        source=hidden.source,
        reference=reference_from(fixture),
        designer_evidence=fixture["designer_evidence"]
        + fixture["public_counterfactual_observation"],
        probes=hidden_probes,
        task_id="110",
    )
    assert screen_semantic_privilege(hidden_input).decision == "FAIL"
    wrong_task = tuple(
        replace(probe, evidence=replace(probe.evidence, task_id="999")) for probe in hidden_probes
    )
    assert (
        screen_semantic_privilege(replace(hidden_input, probes=wrong_task)).decision == "UNCERTAIN"
    )
    assert screen_semantic_privilege(replace(hidden_input, probes=())).decision == "UNCERTAIN"


def test_benchmark_reports_real_confusion_matrix(fixture: dict[str, Any]) -> None:
    report = run_benchmark(FIXTURE)
    assert report["all_matched"] and len(report["cases"]) == len(CASES)
    assert report["confusion_matrix"] == {
        "PASS": {"PASS": 3, "FAIL": 0, "UNCERTAIN": 0},
        "FAIL": {"PASS": 0, "FAIL": 9, "UNCERTAIN": 0},
        "UNCERTAIN": {"PASS": 0, "FAIL": 0, "UNCERTAIN": 2},
    }
    assert report["policy_rollouts"] == report["designer_calls"] == report["api_calls"] == 0
