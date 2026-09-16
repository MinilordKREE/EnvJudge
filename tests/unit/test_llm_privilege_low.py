"""Admission and exact runtime compaction, without model or environment calls."""

from __future__ import annotations

import copy
import gzip
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate, Observation

import aea.llm_privilege_low as adapter
import aea.semantic_privilege as old_local
from aea.designer import AssistFamily, serialize_low
from aea.errors import ConfigError, InfraError
from aea.evaluate import Eval
from aea.families import FamilyContext
from aea.llm_privilege_low import (
    JudgedLowOptimizer,
    LLMLowPrivilegeScreen,
    SemanticAdmissionError,
    compact_low_input,
)
from aea.low_optimizer import Feedback
from aea.privilege_judge import LLMPrivilegeJudge, canonical_json, text_sha256
from aea.privilege_surfaces import RawSnapshot, ReplayEpisode
from aea.semantic_privilege import AuthorizedEvidence, SurfaceProbe
from aea.witness import Solvable
from tests.unit.test_assistive_rules import HINT, _reply
from tests.unit.test_iterative_low import REF
from tests.unit.test_privilege_judge import decision_args, judge_input, judge_response


def probe(*, episode: str = "fresh", step: int = 0, dose: float = 1.0) -> SurfaceProbe:
    observations = tuple(["initial raw"] + ["observed relation"] * step)
    actions = tuple(["look"] * step)
    surface = {
        "observation": {"text": observations[-1], "data": {}},
        "admissible_commands": ["look", "inspect"],
        "action": None,
        "feedback": {},
        "transition": {},
        "final_prompt": observations[-1],
        "formatted_observation_history": list(observations),
    }
    after = {
        **surface,
        "observation": {"text": observations[-1] + " GENERIC_HINT", "data": {}},
        "admissible_commands": ["inspect", "look"],
    }
    return SurfaceProbe(
        AuthorizedEvidence("9", episode, step, "goal", observations, actions, ("look", "inspect")),
        dose,
        surface,
        after,
        ("same_original_state", "policy_formatter", "filter_observation"),
    )


def compact(probes: tuple[SurfaceProbe, ...]) -> Any:
    return compact_low_input(
        candidate_artifact=HINT,
        reference=REF,
        designer_evidence="HISTORICAL_SECRET",
        probes=probes,
        task_id="9",
        goal="goal",
        candidate_change_summary="Generic support",
    )


def test_compaction_preserves_all_temporal_contexts_and_actual_order() -> None:
    probes = (probe(), probe(dose=0.25), probe(episode="other"), probe(step=1))
    evidence = compact(probes)
    public = canonical_json(evidence.learner_authorized_evidence)
    assert "HISTORICAL_SECRET" not in public and "GENERIC_HINT" not in public
    effects = evidence.optional_runtime_surface_deltas
    pool = effects["value_table"]
    groups = effects["groups"]
    assert effects["activation_table"][groups[0]["activations_ref"]] == {
        "fresh": {"1.0": [[0, 1]], "0.25": [[0, 0]]},
        "other": {"1.0": [[0, 0]]},
    }
    order_changes = [
        change
        for group in groups
        for change in group["changes"]
        if change["path"][0] == "admissible_commands"
    ]
    assert [(pool[c["before_ref"]], pool[c["after_ref"]]) for c in order_changes] == [
        ("look", "inspect"),
        ("inspect", "look"),
    ]
    assert evidence.capture_coverage["probe_count"] == 4
    assert evidence.capture_coverage["complete"] is True
    assert "K16" not in canonical_json(evidence.model_dump(mode="json"))


def test_repeated_history_unchanged_text_is_not_a_changed_leaf() -> None:
    item = probe(step=2)
    evidence = compact((item,))
    groups = evidence.optional_runtime_surface_deltas["groups"]
    assert all(
        c["path"][0] != "formatted_observation_history"
        for group in groups
        for c in group["changes"]
    )


@pytest.mark.parametrize("issue", ["task", "goal", "history", "conflict"])
def test_bad_authorization_provenance_raises(issue: str) -> None:
    item = probe()
    if issue == "task":
        item = replace(item, evidence=replace(item.evidence, task_id="different"))
    elif issue == "goal":
        item = replace(item, evidence=replace(item.evidence, goal="different"))
    elif issue == "history":
        item = replace(item, evidence=replace(item.evidence, step=2))
    else:
        item = replace(item, evidence=replace(item.evidence, observations=("CANDIDATE_GENERATED",)))
    with pytest.raises(ConfigError):
        compact((probe(), item))


def make_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdicts: list[str]
) -> LLMLowPrivilegeScreen:
    pending = iter(verdicts)
    judge = LLMPrivilegeJudge(lambda request: judge_response(request, decision_args(next(pending))))

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("old semantic grammar must not be called")

    monkeypatch.setattr(old_local, "screen_semantic_privilege", forbidden)
    monkeypatch.setattr(
        adapter,
        "probe_template",
        lambda *args, **kwargs: tuple(probe(dose=d / 16) for d in range(17)),
    )
    screen = LLMLowPrivilegeScreen(
        judge=judge,
        task_id="9",
        reference=REF,
        designer_evidence="historical",
        failures=(),
        goal="goal",
        open_original_session=forbidden,
        max_bisections=4,
        audit_dir=tmp_path,
        record=lambda record: None,
    )
    screen._episodes = (
        ReplayEpisode("9", "fresh", "goal", (RawSnapshot(Observation(text="initial raw"), None),)),
    )
    return screen


def test_pass_audit_and_exact_source_dose_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    screen = make_screen(tmp_path, monkeypatch, ["PASS", "UNCERTAIN"])
    family = AssistFamily("hint", "O", HINT)
    result = screen.screen(family)
    screen.require_pass(family, 1.0)
    rendered = family.make(1.0, FamilyContext("9", ()))
    assert rendered is not None
    screen.require_pass_candidate(rendered)
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass_candidate(Candidate(rules_code=rendered.rules_code + "\n"))
    for changed, dose in [(family, 0.1), (replace(family, template=HINT + "\n"), 1.0)]:
        with pytest.raises(SemanticAdmissionError):
            screen.require_pass(changed, dose)
    path = tmp_path / f"{result.input_sha256}.input.json.gz"
    assert text_sha256(gzip.decompress(path.read_bytes()).decode()) == result.input_sha256
    screen.screen(family)
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass(family, 1.0)


@pytest.mark.parametrize("verdict", ["FAIL", "UNCERTAIN"])
def test_both_rejections_replace_then_pass_before_solvability(verdict: str) -> None:
    feedbacks: list[Feedback | None] = []
    events: list[str] = []

    def propose(feedback: Feedback | None, index: int) -> dict[str, Any]:
        feedbacks.append(feedback)
        return _reply(HINT + "\n" * index)[1]

    count = 0

    def screen(family: AssistFamily) -> Any:
        nonlocal count
        count += 1
        events.append("judge")
        return LLMPrivilegeJudge(
            lambda request: judge_response(
                request, decision_args(verdict if count == 1 else "PASS")
            )
        ).judge(judge_input(family.template))

    def certify(candidate: Candidate) -> Solvable:
        events.append("solvability")
        return Solvable(True, "oracle", {})

    def measure(family: AssistFamily, dose: float) -> Eval:
        events.append("policy")
        return Eval(4, 8, "in_band")

    optimizer = JudgedLowOptimizer(
        serialize_low([], 0.0, 16, REF, rich=True),
        [],
        REF,
        "goal",
        task_id="9",
        propose=propose,
        certify=certify,
        measure=measure,
        remaining=lambda: 30,
        screen=screen,
    )
    result = optimizer.run()
    assert result.status == "viable" and len(optimizer.history) == 2
    assert feedbacks[1] is not None and feedbacks[1].operation == "REPLACE_MECHANISM"
    assert feedbacks[1].category == "privilege"
    assert events == ["judge", "judge", "solvability", "policy"]
    assert optimizer.history[0].endpoint is None and optimizer.history[0].solvability is None
    with pytest.raises(RuntimeError):
        optimizer.run()


def test_judge_exception_propagates_without_redesign() -> None:
    def broken(family: AssistFamily) -> Any:
        raise InfraError("judge accounting failed")

    def forbidden(*args: Any) -> Any:
        raise AssertionError("must not reach solvability or policy")

    optimizer = JudgedLowOptimizer(
        serialize_low([], 0.0, 16, REF, rich=True),
        [],
        REF,
        "goal",
        task_id="9",
        propose=lambda feedback, index: _reply(HINT)[1],
        certify=forbidden,
        measure=forbidden,
        remaining=lambda: 30,
        screen=broken,
    )
    with pytest.raises(InfraError):
        optimizer.run()
    assert not optimizer.history and not optimizer.rejections


@pytest.mark.parametrize("before,after", [({"success": 0}, {"success": False}), ([1], [True])])
def test_nested_bool_integer_changes_are_preserved(before: Any, after: Any) -> None:
    changes = adapter._changes({"transition": {"info": before}}, {"transition": {"info": after}})
    assert len(changes) == 1
    assert type(changes[0]["before"]) is int and type(changes[0]["after"]) is bool


def test_empty_original_capture_is_safe_uncertain_not_false_corruption() -> None:
    missing = SurfaceProbe(
        AuthorizedEvidence("9", "missing", 0, "", ()),
        0.0,
        {},
        {},
        error="original reset unavailable",
    )
    evidence = compact((missing,))
    assert evidence.capture_coverage["complete"] is False

    def forbidden(*args: Any) -> Any:
        raise AssertionError("missing capture must not dispatch a judge call")

    assert LLMPrivilegeJudge(forbidden).judge(evidence).verdict == "UNCERTAIN"


def test_uncaptured_doses_cannot_be_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    screen = make_screen(tmp_path, monkeypatch, [])
    monkeypatch.setattr(adapter, "probe_template", lambda *args, **kwargs: (probe(),))
    result = screen.screen(AssistFamily("hint", "O", HINT))
    assert result.verdict == "UNCERTAIN" and result.request is None
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass(AssistFamily("hint", "O", HINT), 1.0)


def test_compacted_groups_reconstruct_every_transformed_surface_exactly() -> None:
    probes: list[SurfaceProbe] = []
    for episode in ("fresh", "other"):
        for step in range(3):
            for dose in (0.0, 0.5, 1.0):
                item = probe(episode=episode, step=step, dose=dose)
                long_base = "Public unchanged context. " * 80
                item = replace(item, baseline={**item.baseline, "final_prompt": long_base})
                after = copy.deepcopy(dict(item.transformed))
                after["admissible_commands"] = ["inspect"] if dose == 0.5 else ["look", "inspect"]
                after["final_prompt"] = long_base + " Brief support."
                after["transition"] = {"info": {"success": False if dose == 0.5 else 0}}
                after["feedback"] = {"new_field": "visible feedback"}
                after["formatted_observation_history"] = [
                    text + " prior wrapper reminder"
                    for text in item.baseline["formatted_observation_history"]
                ]
                probes.append(replace(item, transformed=after))
    evidence = compact(tuple(probes))
    effects = evidence.optional_runtime_surface_deltas
    values = dict(effects["value_table"])
    assert effects["string_edit_table"]
    for key, edit in effects["string_edit_table"].items():
        base = values[edit["base_ref"]]
        prefix, suffix = edit["prefix_chars"], edit["suffix_chars"]
        assert base[prefix : len(base) - suffix if suffix else len(base)] == edit["removed_text"]
        values[key] = base[:prefix] + edit["inserted_text"] + (base[-suffix:] if suffix else "")
        assert text_sha256(values[key]) == edit["after_sha256"]
    for item in probes:
        reconstructed = copy.deepcopy(dict(item.baseline))
        for group in effects["groups"]:
            ranges = (
                effects["activation_table"][group["activations_ref"]]
                .get(item.evidence.episode_id, {})
                .get(str(item.dose), [])
            )
            if not any(first <= item.evidence.step <= last for first, last in ranges):
                continue
            for change in group["changes"]:
                path = change["path"]
                node = reconstructed
                for key in path[:-1]:
                    node = node[key]
                key = path[-1]
                if change["before_present"]:
                    assert canonical_json(node[key]) == canonical_json(values[change["before_ref"]])
                if change["after_present"]:
                    node[key] = copy.deepcopy(values[change["after_ref"]])
                else:
                    del node[key]
        assert canonical_json(reconstructed) == canonical_json(dict(item.transformed))
