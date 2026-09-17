"""LLM-free v3 control characterization on synthetic original episode prefixes."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, replace
from types import SimpleNamespace
from typing import Any, cast

import pytest
from envharness.core.types import Action, EnvResponse, Observation
from pydantic import ValidationError

from aea.actuator import (
    ActuatorCharacterizer,
    Characterization,
    CharacterizationError,
    probes_from_records,
    validate_characterization,
)
from aea.intervention import ControlDeclaration, InterventionFamily, NominalSetting, V3Config
from aea.privilege_surfaces import RawSnapshot, ReplayEpisode, probe_template
from aea.semantic_privilege import SurfaceProbe

GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
HEADER = "class _Rules(Rules):\n    DOSE = __DOSE__\n"


def family(effect: str = "str(self.DOSE)", *, kind: str = "SCALAR") -> InterventionFamily:
    source = (
        HEADER
        + """
    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        effect = EFFECT
        if not effect:
            return obs
        return Observation(text=obs.text + " " + effect, data=obs.data)
""".replace("EFFECT", effect)
    )
    control: dict[str, Any] = {"kind": kind}
    if kind != "BINARY":
        control["settings"] = [{"value": value} for value in GRID]
    return InterventionFamily.model_validate(
        {
            "family_id": "synthetic-1",
            "direction": "easier",
            "mechanism_summary": "generic support",
            "source": source,
            "axis": "O",
            "control": control,
            "expected_effect": "support",
            "semantic_mechanism_id": "semantic-1",
        }
    )


def episode() -> ReplayEpisode:
    initial = Observation(text="A room.", data={"admissible_commands": ["look", "wait"]})
    later = Observation(text="Still a room.", data={"admissible_commands": ["look", "wait"]})
    action = Action(name="do", kwargs={"text": "look"})
    response = EnvResponse(
        observation=later, reward=0.0, terminated=False, truncated=False, info={}
    )
    return ReplayEpisode(
        "synthetic",
        "episode-1",
        "Explore.",
        (
            RawSnapshot(initial, SimpleNamespace(extras={})),
            RawSnapshot(later, SimpleNamespace(extras={}), action, response),
        ),
    )


def saved(
    f: InterventionFamily | None = None,
) -> tuple[InterventionFamily, tuple[SurfaceProbe, ...]]:
    f = f or family(kind="BINARY")
    probes = probe_template(
        f.source, "synthetic", (episode(),), [s.value for s in f.control.nominal_settings()]
    )
    return f, probes


def characterize_saved(
    f: InterventionFamily, probes: list[SurfaceProbe] | tuple[SurfaceProbe, ...]
) -> Characterization:
    return ActuatorCharacterizer().characterize_probes(
        f, "synthetic", probes, expected_coverage=[("episode-1", 0), ("episode-1", 1)]
    )


def test_a_scalar_has_five_distinct_captured_operating_points() -> None:
    f = family()
    result = ActuatorCharacterizer().characterize(f, "synthetic", (episode(),))
    assert len(result.levels) == 5
    assert len(result.positive_levels) == 4
    assert [level.representative.value for level in result.levels] == list(GRID)
    assert result.coverage["expected_count"] == result.coverage["actual_count"] == 10
    assert result.diagnostics == ()
    validate_characterization(f, result, "synthetic")
    assert (
        result.level_for(0.5).rendered_source_sha256
        == hashlib.sha256(f.render(0.5, "synthetic").rules_code.encode()).hexdigest()
    )
    record = json.dumps(result.as_record())
    assert "A room." not in record and "class _Rules" not in record


def test_b_scalar_collapses_into_three_levels_with_maximum_representatives() -> None:
    f = family('"gentle" if self.DOSE <= 0.5 else "strong"')
    result = ActuatorCharacterizer().characterize(f, "synthetic", (episode(),))
    assert len(result.levels) == 3
    assert [level.representative.value for level in result.positive_levels] == [0.5, 1.0]
    assert result.level_for(0.25) is result.level_for(0.5)
    assert result.level_for(0.75) is result.level_for(1.0)
    assert result.positive_levels[0].equivalent_settings == result.positive_levels[0].settings


def test_i_recurrence_is_diagnostic_and_identity_aliases_are_off() -> None:
    f = family('"" if self.DOSE == 0.5 else "same"')
    result = ActuatorCharacterizer().characterize(f, "synthetic", (episode(),))
    assert len(result.levels) == 2
    assert result.diagnostics == ("NON_MONOTONE_CONTROL_SURFACE",)
    assert result.off_level.representative.value == 0.5
    assert result.level_for(0.5).is_off
    assert len(result.positive_levels) == 1
    assert result.positive_levels[0].representative.value == 1.0


def test_equal_effect_signatures_ignore_template_bytes_and_setting_values() -> None:
    f = family('"same"')
    changed = f.model_copy(update={"source": f.source + "\n# harmless extra source bytes\n"})
    a = ActuatorCharacterizer().characterize(f, "synthetic", (episode(),))
    b = ActuatorCharacterizer().characterize(changed, "synthetic", (episode(),))
    assert a.positive_levels[0].surface_signature == b.positive_levels[0].surface_signature
    assert (
        a.positive_levels[0].rendered_source_sha256 != b.positive_levels[0].rendered_source_sha256
    )
    assert a.sha256 != b.sha256
    assert len(a.positive_levels[0].settings) == 4


def test_binary_is_a_valid_two_level_actuator() -> None:
    result = ActuatorCharacterizer().characterize(family(kind="BINARY"), "synthetic", (episode(),))
    assert len(result.levels) == 2
    assert [s.value for s in result.settings] == [0, 1]


def test_discrete_named_settings_render_existing_numeric_dose_template() -> None:
    f = family().model_copy(
        update={
            "control": ControlDeclaration(
                kind="DISCRETE",
                settings=(
                    NominalSetting(value=0, name="OFF"),
                    NominalSetting(value=0.5, name="gentle"),
                    NominalSetting(value=1, name="strong"),
                ),
            )
        }
    )
    result = ActuatorCharacterizer().characterize(f, "synthetic", (episode(),))
    assert len(result.levels) == 3
    assert "DOSE = 0.5" in f.render(result.settings[1], "synthetic").rules_code
    assert "gentle" not in json.dumps(result.as_record())


def test_default_scalar_grid_and_search_envelope_are_explicit() -> None:
    config = V3Config()
    assert len(config.scalar_grid) == 17
    assert config.max_design_rounds == 3 and config.max_control_probes == 5
    assert len(ControlDeclaration().nominal_settings()) == 17
    with pytest.raises(ValidationError):
        V3Config.model_validate({"probe": [4, 8]})


@pytest.mark.parametrize(
    "control",
    [
        {"kind": "DISCRETE"},
        {"kind": "DISCRETE", "settings": [{"value": 0}, {"value": 0.5}]},
        {"kind": "SCALAR", "settings": [{"value": 0}, {"value": 1}, {"value": 0.5}]},
        {"kind": "BINARY", "settings": [{"value": 0}, {"value": 0.5}, {"value": 1}]},
        {"kind": "DISCRETE", "settings": [{"value": 0, "name": "x"}, {"value": 1, "name": "x"}]},
    ],
)
def test_invalid_control_declarations_rejected(control: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ControlDeclaration.model_validate(control)


@pytest.mark.parametrize("value", [True, "0.5", float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_nominal_values_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        NominalSetting(value=value)


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "error",
        "coverage",
        "wrong_task",
        "wrong_dose",
        "wrong_baseline",
        "off",
        "missing_channel",
        "nan",
    ],
)
def test_incomplete_or_inconsistent_saved_capture_is_rejected(defect: str) -> None:
    f, original = saved()
    probes = list(copy.deepcopy(original))
    p = probes[-1]
    if defect == "missing":
        probes.pop()
    elif defect == "duplicate":
        probes.append(p)
    elif defect == "error":
        probes[-1] = replace(p, error="unsupported replay")
    elif defect == "coverage":
        probes[-1] = replace(p, coverage=())
    elif defect == "wrong_task":
        probes[-1] = replace(p, evidence=replace(p.evidence, task_id="other"))
    elif defect == "wrong_dose":
        probes[-1] = replace(p, dose=0.6)
    elif defect == "wrong_baseline":
        probes[-1] = replace(p, baseline={**p.baseline, "final_prompt": "different original"})
    elif defect == "off":
        p = probes[0]
        probes[0] = replace(p, transformed={**p.transformed, "final_prompt": "changed OFF"})
    elif defect == "missing_channel":
        surface = dict(p.transformed)
        del surface["feedback"]
        probes[-1] = replace(p, transformed=surface)
    else:
        probes[-1] = replace(
            p, transformed={**p.transformed, "feedback": {"invalid": float("nan")}}
        )
    with pytest.raises(CharacterizationError):
        characterize_saved(f, probes)


def test_decoder_roundtrip_is_stable_and_raw_mutation_invalidates_binding() -> None:
    f, probes = saved()
    result = characterize_saved(f, probes)
    decoded = probes_from_records(json.loads(json.dumps([asdict(p) for p in probes])))
    assert characterize_saved(f, decoded).sha256 == result.sha256
    # Dataclass freezing cannot freeze arbitrary nested maps: validation must recompute them.
    cast(dict[str, Any], result.raw_probes[-1].transformed)["final_prompt"] = "mutation"
    with pytest.raises(CharacterizationError):
        validate_characterization(f, result, "synthetic")


def test_hidden_audit_values_do_not_create_a_level_but_stopping_flags_do() -> None:
    f, probes = saved(family('""', kind="BINARY"))
    base = characterize_saved(f, probes)
    changed = list(copy.deepcopy(probes))
    p = changed[-1]
    transformed = dict(p.transformed)
    transformed["observation"] = {**transformed["observation"], "data": {"hidden": "audit only"}}
    transformed["transition"] = {
        **transformed["transition"],
        "reward": 4.0,
        "info": {"hidden": True},
    }
    changed[-1] = replace(p, transformed=transformed)
    hidden = characterize_saved(f, changed)
    assert (
        len(hidden.levels) == 1
        and hidden.off_level.surface_signature == base.off_level.surface_signature
    )
    assert hidden.raw_probe_sha256 != base.raw_probe_sha256
    transformed = copy.deepcopy(transformed)
    transformed["transition"]["truncated"] = True
    changed[-1] = replace(p, transformed=transformed)
    stopped = characterize_saved(f, changed)
    assert len(stopped.positive_levels) == 1


@pytest.mark.parametrize(
    "channel", ["admissible_commands", "formatted_observation_history", "feedback", "action"]
)
def test_actual_order_history_feedback_and_action_changes_are_distinct(channel: str) -> None:
    f, probes = saved(family('""', kind="BINARY"))
    changed = list(copy.deepcopy(probes))
    p = changed[-1]
    replacements: dict[str, Any] = {
        "admissible_commands": ["wait", "look"],
        "formatted_observation_history": ["earlier support"],
        "feedback": {"blocked": True, "blocked_reason": "wait"},
        "action": {"name": "do", "kwargs": {"text": "wait"}},
    }
    changed[-1] = replace(p, transformed={**p.transformed, channel: replacements[channel]})
    assert len(characterize_saved(f, changed).positive_levels) == 1


def test_delayed_hook_activation_survives_prefix_capture() -> None:
    f = family('"support" if getattr(self, "count", 0) > 1 else ""', kind="BINARY")
    source = f.source.replace(
        "        effect =", '        self.count = getattr(self, "count", 0) + 1\n        effect ='
    )
    f = f.model_copy(update={"source": source})
    result = ActuatorCharacterizer().characterize(f, "synthetic", (episode(),))
    assert len(result.positive_levels) == 1
    positive = [p for p in result.raw_probes if p.dose == 1]
    assert positive[0].baseline["final_prompt"] == positive[0].transformed["final_prompt"]
    assert positive[1].baseline["final_prompt"] != positive[1].transformed["final_prompt"]


def test_replay_prefix_coverage_cannot_be_inferred_from_survivors() -> None:
    f, probes = saved()
    with pytest.raises(CharacterizationError):
        ActuatorCharacterizer().characterize_probes(
            f, "synthetic", probes, expected_coverage=[("episode-1", 1)]
        )
    with pytest.raises(CharacterizationError):
        ActuatorCharacterizer().characterize(
            f, "synthetic", (replace(episode(), error="short capture"),)
        )
    with pytest.raises(CharacterizationError):
        ActuatorCharacterizer().characterize(f, "synthetic", (episode(), episode()))


@pytest.mark.parametrize("field", ["dose", "step", "observations", "coverage", "schema"])
def test_saved_decoder_rejects_type_coercions_and_unknown_fields(field: str) -> None:
    _, probes = saved()
    records = json.loads(json.dumps([asdict(p) for p in probes]))
    if field == "dose":
        records[0]["dose"] = False
    elif field == "step":
        records[0]["evidence"]["step"] = "0"
    elif field == "observations":
        records[0]["evidence"]["observations"] = "not a list"
    elif field == "coverage":
        records[0]["coverage"] = "not a list"
    else:
        records[0]["evidence"]["unknown"] = True
    with pytest.raises(CharacterizationError):
        probes_from_records(records)


def test_effective_level_metadata_edit_invalidates_characterization() -> None:
    f, probes = saved()
    result = characterize_saved(f, probes)
    altered = replace(result.levels[-1], representative=NominalSetting(value=0.5))
    with pytest.raises(CharacterizationError):
        validate_characterization(
            f, replace(result, levels=(*result.levels[:-1], altered)), "synthetic"
        )
