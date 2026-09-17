"""Deterministic, replay-scoped equivalence classes of learner-facing control effects.

Numeric doses propose an order; exact surface-delta signatures determine distinct captured
operating points. This is neither a semantic intensity score nor a proof over unseen states.
Raw replay evidence is retained privately for admission; metadata binds its exact contents.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from aea.intervention import InterventionFamily, NominalSetting, V3Config, canonical_hash
from aea.privilege_surfaces import ReplayEpisode, probe_template
from aea.semantic_privilege import AuthorizedEvidence, SurfaceProbe

type CoverageKey = tuple[str, int]


class CharacterizationError(ValueError):
    """Replay is incomplete, inconsistent, or not an identity at OFF."""


@dataclass(frozen=True)
class EffectiveControlLevel:
    level_id: str
    surface_signature: str
    settings: tuple[NominalSetting, ...]
    representative: NominalSetting
    order: int
    is_off: bool
    rendered_source_sha256: str
    coverage: Mapping[str, Any]

    @property
    def equivalent_settings(self) -> tuple[NominalSetting, ...]:
        return self.settings

    @property
    def representative_setting(self) -> NominalSetting:
        return self.representative

    @property
    def rendered_source_hash(self) -> str:
        return self.rendered_source_sha256

    def as_record(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id,
            "surface_signature": self.surface_signature,
            "settings": [setting.as_record() for setting in self.settings],
            "representative": self.representative.as_record(),
            "order": self.order,
            "is_off": self.is_off,
            "rendered_source_sha256": self.rendered_source_sha256,
            "coverage": copy.deepcopy(dict(self.coverage)),
        }


@dataclass(frozen=True)
class Characterization:
    task_id: str
    family_id: str
    source_sha256: str
    control_sha256: str
    settings: tuple[NominalSetting, ...]
    levels: tuple[EffectiveControlLevel, ...]
    coverage: Mapping[str, Any]
    diagnostics: tuple[str, ...]
    raw_probes: tuple[SurfaceProbe, ...]
    raw_probe_sha256: str

    @property
    def positive_levels(self) -> tuple[EffectiveControlLevel, ...]:
        """Distinct nonidentity effects, in the Designer's proposed nominal order."""
        return tuple(level for level in self.levels if not level.is_off)

    @property
    def off_level(self) -> EffectiveControlLevel:
        return next(level for level in self.levels if level.is_off)

    def level_for(self, setting: NominalSetting | float) -> EffectiveControlLevel:
        value = setting.value if isinstance(setting, NominalSetting) else setting
        for level in self.levels:
            if any(member.value == value for member in level.settings):
                return level
        raise KeyError(value)

    def as_record(self) -> dict[str, Any]:
        """Audit metadata only: no candidate source or learner/reference surface text."""
        return {
            "version": "replay_surface_equivalence_v1",
            "scope": "captured_original_episode_prefixes",
            "task_id": self.task_id,
            "family_id": self.family_id,
            "source_sha256": self.source_sha256,
            "control_sha256": self.control_sha256,
            "settings": [setting.as_record() for setting in self.settings],
            "levels": [level.as_record() for level in self.levels],
            "coverage": copy.deepcopy(dict(self.coverage)),
            "diagnostics": list(self.diagnostics),
            "raw_probe_sha256": self.raw_probe_sha256,
        }

    @property
    def sha256(self) -> str:
        return canonical_hash(self.as_record())


def _visible(surface: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "final_prompt",
        "observation",
        "admissible_commands",
        "action",
        "feedback",
        "transition",
        "formatted_observation_history",
    }
    if not required.issubset(surface):
        raise CharacterizationError("incomplete learner-facing surface channels")
    observation, transition = surface["observation"], surface["transition"]
    if not isinstance(observation, Mapping) or not isinstance(transition, Mapping):
        raise CharacterizationError("invalid observation or transition surface")
    if not isinstance(surface["final_prompt"], str):
        raise CharacterizationError("invalid formatted policy observation")
    if not isinstance(surface["admissible_commands"], list) or not isinstance(
        surface["formatted_observation_history"], list
    ):
        raise CharacterizationError("invalid command/history surface")
    # final_prompt includes any observation.data actually formatted to the learner. Raw
    # data/info/reward may contain audit-only hidden state and are excluded from equivalence.
    # Stopping flags change observable interaction availability, including HIGH horizons.
    return {
        "final_prompt": surface["final_prompt"],
        "observation": {"text": observation["text"]} if "text" in observation else {},
        "admissible_commands": surface["admissible_commands"],
        "action": surface["action"],
        "feedback": surface["feedback"],
        "transition": {
            key: transition[key] for key in ("terminated", "truncated") if key in transition
        },
        "formatted_observation_history": surface["formatted_observation_history"],
    }


def _delta(baseline: Mapping[str, Any], transformed: Mapping[str, Any]) -> dict[str, Any]:
    # Preserve exact field values and list order; equality uses JSON types, not Python's
    # bool/int coercion. Hashing only these changed visible fields excludes nominal dose.
    return {
        key: {"before": baseline[key], "after": transformed[key]}
        for key in sorted(baseline)
        if canonical_hash(baseline[key]) != canonical_hash(transformed[key])
    }


def _coverage_keys(expected: Sequence[CoverageKey]) -> tuple[CoverageKey, ...]:
    keys = tuple(expected)
    if not keys or len(set(keys)) != len(keys):
        raise CharacterizationError("expected replay coverage must be nonempty and unique")
    for episode_id, step in keys:
        if not isinstance(episode_id, str) or not episode_id or type(step) is not int or step < 0:
            raise CharacterizationError("invalid expected episode/step identity")
    for episode_id in {episode_id for episode_id, _ in keys}:
        steps = sorted(step for episode, step in keys if episode == episode_id)
        if steps != list(range(len(steps))):
            raise CharacterizationError("expected replay must contain a complete prefix from reset")
    return tuple(sorted(keys))


class ActuatorCharacterizer:
    def __init__(self, config: V3Config | None = None) -> None:
        self.config = config or V3Config()

    def characterize(
        self, family: InterventionFamily, task_id: str, episodes: Sequence[ReplayEpisode]
    ) -> Characterization:
        if not episodes or any(
            episode.error or episode.task_id != task_id or not episode.snapshots
            for episode in episodes
        ):
            raise CharacterizationError("trusted complete original replay episodes are required")
        if len({episode.episode_id for episode in episodes}) != len(episodes):
            raise CharacterizationError("replay episode identifiers must be unique")
        settings = family.control.nominal_settings(self.config.scalar_grid)
        probes = probe_template(family.source, task_id, episodes, [s.value for s in settings])
        expected = [(ep.episode_id, step) for ep in episodes for step in range(len(ep.snapshots))]
        return self.characterize_probes(
            family, task_id, probes, settings=settings, expected_coverage=expected
        )

    def characterize_probes(
        self,
        family: InterventionFamily,
        task_id: str,
        probes: Sequence[SurfaceProbe],
        *,
        settings: Sequence[NominalSetting] | None = None,
        expected_coverage: Sequence[CoverageKey],
    ) -> Characterization:
        try:
            return self._characterize_probes(
                family, task_id, probes, settings=settings, expected_coverage=expected_coverage
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, CharacterizationError):
                raise
            raise CharacterizationError("malformed or non-finite replay evidence") from exc

    def _characterize_probes(
        self,
        family: InterventionFamily,
        task_id: str,
        probes: Sequence[SurfaceProbe],
        *,
        settings: Sequence[NominalSetting] | None,
        expected_coverage: Sequence[CoverageKey],
    ) -> Characterization:
        declared = family.control.nominal_settings(self.config.scalar_grid)
        selected = tuple(settings) if settings is not None else declared
        if selected != declared:
            raise CharacterizationError("nominal settings differ from the declared control grid")
        expected = _coverage_keys(expected_coverage)
        private = copy.deepcopy(tuple(probes))
        by_key: dict[tuple[float, str, int], SurfaceProbe] = {}
        values = {setting.value for setting in selected}
        expected_set = set(expected)
        for probe in private:
            evidence = probe.evidence
            if (
                type(probe.dose) not in (int, float)
                or type(evidence.step) is not int
                or not isinstance(evidence.episode_id, str)
            ):
                raise CharacterizationError("invalid probe dose or episode/step identity")
            probe_key = (probe.dose, evidence.episode_id, evidence.step)
            if probe.error is not None:
                raise CharacterizationError("replay capture contains an error")
            if evidence.task_id != task_id or probe.dose not in values:
                raise CharacterizationError("probe task or nominal setting identity mismatch")
            if (evidence.episode_id, evidence.step) not in expected_set or probe_key in by_key:
                raise CharacterizationError("unexpected or duplicate replay surface")
            if not {"policy_formatter", "same_original_state"}.issubset(probe.coverage):
                raise CharacterizationError("missing original-state or formatter capture coverage")
            by_key[probe_key] = probe
        if len(by_key) != len(expected) * len(selected):
            raise CharacterizationError("incomplete replay coverage across settings and prefixes")
        # Canonical order makes serialization independent of producer enumeration order.
        private = tuple(
            by_key[(setting.value, ep, step)] for setting in selected for ep, step in expected
        )
        signatures: list[str] = []
        baselines: dict[CoverageKey, str] = {}
        evidence_hashes: dict[CoverageKey, str] = {}
        for setting in selected:
            deltas: list[dict[str, Any]] = []
            for episode_id, step in expected:
                probe = by_key[(setting.value, episode_id, step)]
                baseline, transformed = _visible(probe.baseline), _visible(probe.transformed)
                key = (episode_id, step)
                baseline_hash, evidence_hash = (
                    canonical_hash(baseline),
                    canonical_hash(asdict(probe.evidence)),
                )
                if key in baselines and (
                    baselines[key] != baseline_hash or evidence_hashes[key] != evidence_hash
                ):
                    raise CharacterizationError(
                        "original state/history differs between nominal settings"
                    )
                baselines[key], evidence_hashes[key] = baseline_hash, evidence_hash
                delta = _delta(baseline, transformed)
                if setting.value == 0.0 and delta:
                    raise CharacterizationError(
                        "OFF must preserve the original learner-facing surface"
                    )
                deltas.append({"episode_id": episode_id, "step": step, "delta": delta})
            signatures.append(canonical_hash(deltas))
        grouped: dict[str, list[NominalSetting]] = {}
        last_position: dict[str, int] = {}
        for index, (signature, setting) in enumerate(zip(signatures, selected, strict=True)):
            grouped.setdefault(signature, []).append(setting)
            last_position[signature] = index
        levels: list[EffectiveControlLevel] = []
        for order, signature in enumerate(sorted(grouped, key=lambda s: last_position[s])):
            members = tuple(grouped[signature])
            representative = members[-1]
            rendered = family.render(representative, task_id)
            levels.append(
                EffectiveControlLevel(
                    level_id="surface-" + signature,
                    surface_signature=signature,
                    settings=members,
                    representative=representative,
                    order=order,
                    is_off=signature == signatures[0],
                    rendered_source_sha256=hashlib.sha256(rendered.rules_code.encode()).hexdigest(),
                    coverage={"complete": True, "episode_step_count": len(expected)},
                )
            )
        compressed = [sig for i, sig in enumerate(signatures) if i == 0 or sig != signatures[i - 1]]
        diagnostics = (
            ("NON_MONOTONE_CONTROL_SURFACE",) if len(set(compressed)) < len(compressed) else ()
        )
        try:
            raw_hash = canonical_hash([asdict(probe) for probe in private])
        except (TypeError, ValueError) as exc:
            raise CharacterizationError("raw replay evidence is not exact finite JSON") from exc
        return Characterization(
            task_id=task_id,
            family_id=family.family_id,
            source_sha256=family.source_sha256,
            control_sha256=family.control_sha256,
            settings=selected,
            levels=tuple(levels),
            coverage={
                "complete": True,
                "expected_count": len(expected) * len(selected),
                "actual_count": len(private),
                "episode_steps": expected,
            },
            diagnostics=diagnostics,
            raw_probes=private,
            raw_probe_sha256=raw_hash,
        )


def validate_characterization(
    family: InterventionFamily,
    characterization: Characterization,
    task_id: str,
    config: V3Config | None = None,
) -> None:
    """Recompute admission bindings from private evidence, refusing stale or edited metadata.

    Replay provenance is the trusted local capture boundary; saved probes must come from
    that producer. This verifies consistency, not authenticity of arbitrary external probes.
    """
    try:
        expected = tuple(tuple(key) for key in characterization.coverage["episode_steps"])
        computed = ActuatorCharacterizer(config).characterize_probes(
            family,
            task_id,
            characterization.raw_probes,
            settings=characterization.settings,
            expected_coverage=expected,
        )
        if computed.sha256 != characterization.sha256:
            raise CharacterizationError(
                "characterization does not match source/control/raw evidence"
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise CharacterizationError("invalid characterization binding") from exc


def probes_from_records(records: Sequence[Mapping[str, Any]]) -> tuple[SurfaceProbe, ...]:
    """Decode private dataclass JSON records, preserving all evidence and surface fields."""
    probes: list[SurfaceProbe] = []
    for record in records:
        try:
            if set(record) != {"evidence", "dose", "baseline", "transformed", "coverage", "error"}:
                raise CharacterizationError("unexpected saved probe schema")
            raw = dict(record["evidence"])
            if set(raw) != {
                "task_id",
                "episode_id",
                "step",
                "goal",
                "observations",
                "actions",
                "admissible_commands",
            }:
                raise CharacterizationError("unexpected saved authorized-evidence schema")
            for field in ("task_id", "episode_id", "goal"):
                if not isinstance(raw[field], str):
                    raise CharacterizationError("invalid saved evidence text")
            if type(raw["step"]) is not int or raw["step"] < 0:
                raise CharacterizationError("invalid saved evidence step")
            for field in ("observations", "actions", "admissible_commands"):
                if not isinstance(raw[field], (tuple, list)) or any(
                    not isinstance(item, str) for item in raw[field]
                ):
                    raise CharacterizationError("invalid saved evidence history")
                raw[field] = tuple(raw[field])
            if type(record["dose"]) not in (int, float):
                raise CharacterizationError("invalid saved nominal value")
            if not isinstance(record["coverage"], (tuple, list)) or any(
                not isinstance(item, str) for item in record["coverage"]
            ):
                raise CharacterizationError("invalid saved hook coverage")
            if record["error"] is not None and not isinstance(record["error"], str):
                raise CharacterizationError("invalid saved capture error")
            if not isinstance(record["baseline"], Mapping) or not isinstance(
                record["transformed"], Mapping
            ):
                raise CharacterizationError("invalid saved surface maps")
            probe = SurfaceProbe(
                evidence=AuthorizedEvidence(**raw),
                dose=record["dose"],
                baseline=copy.deepcopy(record["baseline"]),
                transformed=copy.deepcopy(record["transformed"]),
                coverage=tuple(record["coverage"]),
                error=record["error"],
            )
            canonical_hash(asdict(probe))
        except (KeyError, TypeError, ValueError) as exc:
            raise CharacterizationError("invalid saved probe data") from exc
        probes.append(probe)
    return tuple(probes)
