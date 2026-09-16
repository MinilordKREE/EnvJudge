"""LOW admission adapter for the independent, benchmark-neutral LLM judge.

The original optimizer owns lineage, call limits and freeze. Only its candidate admission
is extended. Raw replay and exact serialization never invoke the old semantic analyzer.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace

from aea.designer import AssistFamily, Reference
from aea.errors import ConfigError
from aea.families import FamilyContext
from aea.low_optimizer import LowEnvironmentOptimizer
from aea.privilege_judge import (
    JudgeRecord,
    PrivilegeJudge,
    PrivilegeJudgeInput,
    canonical_json,
    text_sha256,
)
from aea.privilege_surfaces import ReplayEpisode, capture_episode, probe_template
from aea.semantic_low import SemanticAdmissionError as SemanticAdmissionError
from aea.semantic_low import reachable_screen_doses
from aea.semantic_privilege import SurfaceProbe
from aea.session import Session
from aea.stage import trace_actions

_REQUIRED_SURFACES = frozenset(
    {
        "observation",
        "admissible_commands",
        "action",
        "feedback",
        "transition",
        "final_prompt",
        "formatted_observation_history",
    }
)


def _changes(before: Any, after: Any, path: tuple[str | int, ...] = ()) -> list[dict[str, Any]]:
    """Exact recursive comparison; preserve list ordering and all changed text verbatim."""
    if isinstance(before, dict) and isinstance(after, dict):
        result: list[dict[str, Any]] = []
        for key in sorted(before.keys() | after.keys()):
            if key in before and key in after:
                result.extend(_changes(before[key], after[key], (*path, key)))
            else:
                result.append(
                    {
                        "path": [*path, key],
                        "before_present": key in before,
                        "after_present": key in after,
                        "before": before.get(key),
                        "after": after.get(key),
                    }
                )
        return result
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [
            change
            for i, (b, a) in enumerate(zip(before, after, strict=True))
            for change in _changes(b, a, (*path, i))
        ]
    if type(before) is type(after) and before == after:
        return []
    return [
        {
            "path": list(path),
            "before_present": True,
            "after_present": True,
            "before": before,
            "after": after,
        }
    ]


def _pack_runtime(groups: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    """Exact shared activations and optional single-level string edits, not summaries."""
    activation_table: dict[str, Any] = {}
    coverage_table: dict[str, Any] = {}
    activation_ids: dict[str, str] = {}
    coverage_ids: dict[str, str] = {}
    edits: dict[str, Any] = {}
    # Every base value stays literal. Edits never chain, and every original public
    # observation is already a before value or a separate unchanged literal.
    protected = {change["before_ref"] for group in groups for change in group["changes"]}
    for group in groups:
        for change in group["changes"]:
            before_ref, after_ref = change["before_ref"], change["after_ref"]
            before, after = values[before_ref], values[after_ref]
            if after_ref in protected or not isinstance(before, str) or not isinstance(after, str):
                continue
            prefix = 0
            while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
                prefix += 1
            suffix = 0
            while (
                suffix < min(len(before), len(after)) - prefix
                and before[len(before) - suffix - 1] == after[len(after) - suffix - 1]
            ):
                suffix += 1
            edit = {
                "base_ref": before_ref,
                "prefix_chars": prefix,
                "suffix_chars": suffix,
                "removed_text": before[prefix : len(before) - suffix if suffix else len(before)],
                "inserted_text": after[prefix : len(after) - suffix if suffix else len(after)],
                "after_sha256": text_sha256(after),
            }
            existing_size = len(canonical_json(edits.get(after_ref, after)).encode())
            if len(canonical_json(edit).encode()) < existing_size:
                edits[after_ref] = edit
        for field, table, identifiers, id_prefix in (
            ("activations", activation_table, activation_ids, "a"),
            ("coverage", coverage_table, coverage_ids, "c"),
        ):
            value = group.pop(field)
            key = canonical_json(value)
            if key not in identifiers:
                identifiers[key] = f"{id_prefix}{len(table)}"
                table[identifiers[key]] = value
            group[field + "_ref"] = identifiers[key]
    return {
        "encoding": "Exact recursive leaf changes; list indices preserve order; unequal-length "
        "lists are supplied whole. Unchanged leaves are omitted only by exact equality. "
        "Resolve before_ref/after_ref using value_table or string_edit_table. Resolve "
        "each group's activations_ref and coverage_ref using the corresponding tables.",
        "string_edit_encoding": "An edited value is base[:prefix_chars] + inserted_text + "
        "the last suffix_chars of base (empty when zero). removed_text is the exact "
        "removed base middle. Counts are Unicode characters. All bases are literal "
        "value_table entries; edits never chain. after_sha256 binds the reconstructed text.",
        "value_table": {key: value for key, value in values.items() if key not in edits},
        "string_edit_table": edits,
        "activation_table": activation_table,
        "coverage_table": coverage_table,
        "groups": groups,
        "activation_encoding": (
            "episode_id -> dose -> inclusive [first,last] authorized step ranges; "
            "[t,t] is a singleton. Every integer in each range is an activation."
        ),
    }


def compact_low_input(
    *,
    candidate_artifact: str,
    reference: Reference,
    designer_evidence: str,
    probes: Sequence[SurfaceProbe],
    task_id: str,
    goal: str,
    candidate_change_summary: str = "",
) -> PrivilegeJudgeInput:
    """Losslessly de-duplicate scoped raw evidence and every actual changed surface.

    The complete raw probes are separately audit-hashed by the caller. Unchanged leaves
    are omitted by equality only; no grammar, labels, sampling, or semantic summarizer is
    used. Equal changes share a group, preserving every episode/step/dose activation.
    """
    values: dict[str, Any] = {}
    value_ids: dict[str, str] = {}

    def intern(value: Any) -> str:
        key = canonical_json(value)
        if key not in value_ids:
            identifier = f"v{len(values)}"
            values[identifier] = value
            value_ids[key] = identifier
        return value_ids[key]

    episodes: dict[str, dict[str, Any]] = {}
    groups: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    all_doses: set[float] = set()
    for probe in probes:
        evidence = probe.evidence
        if evidence.task_id != task_id:
            raise ConfigError("Judge evidence task mismatch")
        if probe.error and not evidence.observations:
            errors.append(probe.error)
            continue
        if evidence.goal != goal:
            raise ConfigError("Judge evidence goal mismatch")
        if (
            evidence.step < 0
            or len(evidence.observations) != evidence.step + 1
            or len(evidence.actions) != evidence.step
        ):
            raise ConfigError("Judge evidence is not an exact original episode prefix")
        if not 0.0 <= probe.dose <= 1.0:
            raise ConfigError("Judge probe dose outside [0,1]")
        all_doses.add(probe.dose)
        episode = episodes.setdefault(
            evidence.episode_id,
            {
                "task_id": task_id,
                "episode_id": evidence.episode_id,
                "records": {},
            },
        )
        for index, observation in enumerate(evidence.observations):
            record = {
                "step": index,
                "observation_ref": intern(observation),
                "preceding_action_ref": intern(evidence.actions[index - 1]) if index else None,
            }
            previous = episode["records"].setdefault(index, record)
            if any(previous[key] != value for key, value in record.items()):
                raise ConfigError("Conflicting original evidence for the same episode prefix")
        current = episode["records"][evidence.step]
        commands = intern(list(evidence.admissible_commands))
        if current.setdefault("visible_actions_ref", commands) != commands:
            raise ConfigError("Conflicting original actions at the same activation")
        if probe.error:
            errors.append(probe.error)
        complete_fields = probe.baseline.keys() >= _REQUIRED_SURFACES and (
            probe.transformed.keys() >= _REQUIRED_SURFACES
        )
        if not complete_fields:
            errors.append("Incomplete before/after learner-facing surfaces")
        if "same_original_state" not in probe.coverage or "policy_formatter" not in probe.coverage:
            errors.append("Missing same-state or final policy formatter coverage")
        if probe.baseline.get("admissible_commands") != list(evidence.admissible_commands):
            errors.append("Baseline commands differ from authorized current commands")
        changes = _changes(dict(probe.baseline), dict(probe.transformed))
        for change in changes:
            change["before_ref"] = intern(change.pop("before"))
            change["after_ref"] = intern(change.pop("after"))
        # Group individual exact changes, rather than growing copies of an entire
        # changed history. Each group still retains ALL activation prefixes and doses.
        for individual in ([change] for change in changes) if changes else [[]]:
            key = canonical_json(
                {"changes": individual, "coverage": sorted(probe.coverage), "error": probe.error}
            )
            group = groups.setdefault(
                key,
                {
                    "changes": individual,
                    "coverage": sorted(probe.coverage),
                    "error": probe.error,
                    "activations": {},
                },
            )
            by_dose = group["activations"].setdefault(evidence.episode_id, {})
            steps = by_dose.setdefault(str(probe.dose), [])
            if evidence.step not in steps:
                steps.append(evidence.step)
    if not probes:
        errors.append("No runtime probes captured for this adapter")
    if not reference.ok or not reference.steps:
        errors.append("Verified rich reference is unavailable")
    for group in groups.values():
        for by_dose in group["activations"].values():
            for dose, steps in by_dose.items():
                ranges: list[list[int]] = []
                for step in sorted(steps):
                    if ranges and step == ranges[-1][1] + 1:
                        ranges[-1][1] = step
                    else:
                        ranges.append([step, step])
                by_dose[dose] = ranges
    public_episodes = [
        {**episode, "records": [episode["records"][index] for index in sorted(episode["records"])]}
        for _, episode in sorted(episodes.items())
    ]
    return PrivilegeJudgeInput(
        task_spec={"benchmark": "ALFWorld", "task_id": task_id},
        public_task_information={"instruction": goal},
        designer_evidence_summary=designer_evidence,
        learner_authorized_evidence={
            "origin": "Trusted original unwrapped environment; no candidate output.",
            "scope": "At episode/step t only records 0..t of that same episode are authorized.",
            "persistent_memory": "None authorized across episodes.",
            "episodes": public_episodes,
        },
        privileged_reference=json.loads(canonical_json(asdict(reference))),
        candidate_artifact=candidate_artifact,
        candidate_artifact_type="python_rules_template",
        candidate_change_summary=candidate_change_summary,
        optional_runtime_surface_deltas=_pack_runtime(list(groups.values()), values),
        benchmark_contract_summary=(
            "Rules hooks may alter observations, admissible command order/filtering, actions and "
            "transition feedback while preserving the original task and verifier. __DOSE__ in "
            "[0,1] controls support; zero must be identity. No reward/verifier manipulation, "
            "reference replay, or privileged disclosure. Candidate state may remember only "
            "what the learner was authorized to observe in that episode. The public instruction "
            "describes a requested outcome, not the current location/state. Generic household "
            "task prerequisites and tool semantics are public domain knowledge. Designer "
            "failure trajectories and the successful reference do not grant cross-episode memory."
        ),
        capture_coverage={
            "complete": not errors,
            "errors": sorted(set(errors)),
            "probe_count": len(probes),
            "doses": sorted(all_doses),
            "episode_count": len(episodes),
            "omissions": "Only exact unchanged leaves",
            "raw_probe_sha256": text_sha256(canonical_json([asdict(p) for p in probes])),
        },
    )


class JudgedLowOptimizer(LowEnvironmentOptimizer):
    """Both judge rejection verdicts use the existing bounded replacement state machine."""

    def __init__(
        self, *args: Any, screen: Callable[[AssistFamily], JudgeRecord], **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._judge_screen = screen

    def _validate(self, args: dict[str, Any]) -> tuple[AssistFamily | None, list[str], list[str]]:
        family, structural, privilege = super()._validate(args)
        if family is None or structural or privilege:
            return family, structural, privilege
        source_sha = text_sha256(family.template)
        if any(record.source_sha256 == source_sha for record in self.history):
            return family, structural, privilege
        record = self._judge_screen(family)
        if record.source_sha256 != source_sha:
            raise ConfigError("Independent judge result binds the wrong candidate source")
        if record.verdict == "PASS":
            return family, [], []
        decision = record.decision
        reason = (
            "llm_privilege_"
            + decision.verdict.lower()
            + ": "
            + canonical_json(
                {
                    "judge_version": record.version,
                    "judge_input_sha256": record.input_sha256,
                    "leak_type": decision.leak_type,
                    "revision_reason": decision.revision_reason,
                }
            )
        )
        return None, [], [reason]


def _write_verified(path: Path, payload: bytes) -> None:
    if path.exists():
        if gzip.decompress(path.read_bytes()) != payload:
            raise ConfigError("Existing privilege judge audit artifact is corrupt")
    else:
        path.write_bytes(gzip.compress(payload, mtime=0))


class LLMLowPrivilegeScreen:
    def __init__(
        self,
        *,
        judge: PrivilegeJudge,
        task_id: str,
        reference: Reference,
        designer_evidence: str,
        failures: Sequence[Trace],
        goal: str,
        open_original_session: Callable[[], Session],
        max_bisections: int,
        audit_dir: Path,
        record: Callable[[dict[str, Any]], None],
        max_steps: int = 50,
        task_prompt: str = "",
        action_format: str = "think_action",
    ) -> None:
        self.judge = judge
        self.task_id = task_id
        self.reference = reference
        self.designer_evidence = designer_evidence
        self.failures = tuple(failures)
        self.goal = goal
        self.open_original_session = open_original_session
        self.max_bisections = max_bisections
        self.audit_dir = audit_dir
        self.record = record
        self.max_steps = max_steps
        self.task_prompt = task_prompt
        self.action_format = action_format
        self._episodes: tuple[ReplayEpisode, ...] | None = None
        self._admitted: dict[str, tuple[AssistFamily, tuple[float, ...], str]] = {}

    def _capture(self) -> tuple[ReplayEpisode, ...]:
        if self._episodes is None:
            self._episodes = tuple(
                capture_episode(
                    self.open_original_session,
                    task_id=self.task_id,
                    episode_id=trace.episode_id,
                    actions=tuple(trace_actions(trace)),
                    goal=self.goal,
                    max_steps=self.max_steps,
                    task_prompt=self.task_prompt,
                    action_format=self.action_format,
                )
                for trace in self.failures
            )
        return self._episodes

    def screen(self, family: AssistFamily) -> JudgeRecord:
        source_sha = text_sha256(family.template)
        self._admitted.pop(source_sha, None)
        doses = reachable_screen_doses(self.max_bisections)
        episodes = self._capture()
        probes = probe_template(family.template, self.task_id, episodes, doses)
        evidence = compact_low_input(
            candidate_artifact=family.template,
            reference=self.reference,
            designer_evidence=self.designer_evidence,
            probes=probes,
            task_id=self.task_id,
            goal=self.goal,
            candidate_change_summary=family.mechanism_summary,
        )
        expected = {
            (episode.episode_id, step, dose)
            for episode in episodes
            for step in range(len(episode.snapshots))
            for dose in doses
        }
        actual = {(probe.evidence.episode_id, probe.evidence.step, probe.dose) for probe in probes}
        if not expected or actual != expected or len(actual) != len(probes):
            coverage = evidence.capture_coverage
            assert isinstance(coverage, dict)
            errors = coverage["errors"]
            assert isinstance(errors, list)
            evidence = evidence.model_copy(
                update={
                    "capture_coverage": {
                        **coverage,
                        "complete": False,
                        "errors": [
                            *errors,
                            "Captured activation grid is incomplete or duplicated",
                        ],
                        "expected_probe_count": len(expected),
                    }
                }
            )
        payload = canonical_json(evidence.model_dump(mode="json")).encode()
        input_sha = text_sha256(payload.decode())
        raw = canonical_json([asdict(probe) for probe in probes]).encode()
        raw_sha = text_sha256(raw.decode())
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        input_path = self.audit_dir / f"{input_sha}.input.json.gz"
        raw_path = self.audit_dir / f"{raw_sha}.probes.json.gz"
        _write_verified(input_path, payload)
        _write_verified(raw_path, raw)
        result = self.judge.judge(evidence)
        if result.source_sha256 != source_sha or result.input_sha256 != input_sha:
            raise ConfigError("Independent judge audit input/source binding mismatch")
        self.record(
            {
                "task_id": self.task_id,
                "family": family.name,
                "doses": doses,
                "input_artifact": str(input_path),
                "raw_probe_artifact": str(raw_path),
                "result": result.as_record(),
            }
        )
        if result.verdict == "PASS":
            coverage = evidence.capture_coverage
            if not isinstance(coverage, Mapping) or coverage.get("complete") is not True:
                raise ConfigError("Judge attempted PASS on incomplete adapter evidence")
            self._admitted[source_sha] = (family, doses, input_sha)
        return result

    def require_pass(self, family: AssistFamily, dose: float) -> None:
        admission = self._admitted.get(text_sha256(family.template))
        if admission is None or dose not in admission[1]:
            raise SemanticAdmissionError("No independent judge PASS for exact source and dose")

    def require_pass_candidate(self, candidate: Candidate, dose: float = 1.0) -> None:
        for family, doses, _input_sha in self._admitted.values():
            if dose in doses:
                expected = family.make(dose, FamilyContext(self.task_id, ()))
                if (
                    expected is not None
                    and candidate.rules_code == expected.rules_code
                    and candidate.in_env_actions == expected.in_env_actions
                ):
                    return
        raise SemanticAdmissionError("No independent judge PASS for rendered candidate and dose")
