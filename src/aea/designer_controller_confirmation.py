"""Fresh, non-adaptive confirmation for v3; this module never calls DESIGN or CONTROL."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from envharness.core.types import Candidate, Trace

from aea.actuator import ActuatorCharacterizer, Characterization, probes_from_records
from aea.config import AEAConfig
from aea.core.io import append_jsonl, atomic_write_json, read_jsonl
from aea.core.trace import read_trace
from aea.errors import ConfigError, InfraError
from aea.evaluate import verdict
from aea.integrated_artifacts import method_state_sha256 as legacy_method_hash
from aea.intervention import InterventionFamily, V3Config, canonical_hash
from aea.intervention_gates import verify_saved_admission
from aea.io import read_corpus
from aea.llm.types import Attribution

if TYPE_CHECKING:
    from aea.controller import Controller, TaskRef


def candidate_hash(candidate: Candidate) -> str:
    return canonical_hash(candidate.model_dump(mode="json", exclude={"rationale"}))


def validate_traces(
    traces: list[Trace], n: int, task: TaskRef, candidate: Candidate, seen: set[str]
) -> None:
    ids = [trace.episode_id for trace in traces]
    if len(traces) != n:
        raise InfraError("Incomplete policy batch", kind="rollout")
    if not all(ids) or len(set(ids)) != n or seen.intersection(ids):
        raise ConfigError("Episode identity missing or reused across policy batches")
    for trace in traces:
        if not trace.error and (
            trace.rollout_seed != task.seed
            or candidate_hash(trace.candidate) != candidate_hash(candidate)
        ):
            raise ConfigError("Trace does not bind the dispatched task/candidate")
    seen.update(ids)


def method_state_sha256(run_dir: Path) -> str:
    """Bind search, private family/capture/admission records; exclude confirmation/ledgers."""
    return canonical_hash(
        {
            "shared_method_history": legacy_method_hash(run_dir),
            "designer_controller": {
                str(path.relative_to(run_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((run_dir / "designer_controller").rglob("*"))
                if path.is_file()
            },
        }
    )


def _search_evidence(
    run_dir: Path, task: TaskRef, config: AEAConfig, expected_sha256: str
) -> tuple[dict[str, tuple[str, Trace]], dict[str, Any]]:
    """Verify frozen per-task receipts against the independent global trace journal."""
    path = (
        run_dir / "designer_controller" / canonical_hash(task.task_id)[:16] / "search_traces.jsonl"
    )
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ConfigError("Frozen search evidence is missing or changed")
    records = read_jsonl(path)
    global_rows = read_jsonl(run_dir / "traces.jsonl")
    global_ids = [row.get("episode_id") for row in global_rows]
    if not global_ids or not all(global_ids) or len(set(global_ids)) != len(global_ids):
        raise ConfigError("Global search trace evidence is missing or has duplicate episode IDs")
    global_by_id = {row["episode_id"]: row for row in global_rows}
    by_id: dict[str, tuple[str, Trace]] = {}
    original_hash = candidate_hash(Candidate())
    for row in records:
        if set(row) != {"phase", "candidate_sha256", "trace"}:
            raise ConfigError("Invalid frozen search receipt schema")
        trace = Trace.model_validate(row["trace"])
        phase = row["phase"]
        if not isinstance(phase, str) or not (
            phase == "estimate" or phase.startswith("v3_control:")
        ):
            raise ConfigError("Frozen search receipt has an unexpected phase")
        if not trace.episode_id or trace.episode_id in by_id:
            raise ConfigError("Frozen search receipt has a duplicate or missing episode identity")
        if canonical_hash(global_by_id.get(trace.episode_id)) != canonical_hash(row["trace"]):
            raise ConfigError("Frozen search receipt is missing or changed in global traces")
        if not trace.error and (
            trace.rollout_seed != task.seed
            or candidate_hash(trace.candidate) != row["candidate_sha256"]
        ):
            raise ConfigError("Frozen search trace differs from its dispatched task/candidate")
        if phase == "estimate" and row["candidate_sha256"] != original_hash:
            raise ConfigError("Measurement must use the original environment")
        if phase != "estimate" and trace.error:
            raise ConfigError("An errored adaptation trace cannot support final acceptance")
        by_id[trace.episode_id] = (phase, trace)
    measurements = [
        event.payload
        for event in read_trace(run_dir / "events.jsonl")
        if event.kind == "measurement_evidence" and event.payload["task_id"] == task.task_id
    ]
    if len(measurements) != 1:
        raise ConfigError("Expected exactly one original measurement record")
    measurement = measurements[0]
    baseline = [trace for phase, trace in by_id.values() if phase == "estimate" and not trace.error]
    adaptation = [trace for phase, trace in by_id.values() if phase != "estimate"]
    baseline_ids = [trace.episode_id for trace in baseline]
    successes = sum(bool(trace.success) for trace in baseline)
    if (
        not baseline
        or len(baseline) > config.k
        or len(adaptation) > config.cap
        or measurement.get("episode_ids") != baseline_ids
        or measurement.get("n") != len(baseline)
        or measurement.get("baseline_rollouts") != len(baseline)
        or measurement.get("successes") != successes
        or measurement.get("p_hat") != successes / len(baseline)
        or measurement.get("adaptation_cap") != config.cap
        or measurement.get("errors_retried")
        != sum(bool(trace.error) for phase, trace in by_id.values() if phase == "estimate")
    ):
        raise ConfigError("Frozen traces disagree with measurement or rollout accounting")
    return by_id, measurement


def _verify_probe_evidence(
    acceptance: dict[str, Any],
    family: InterventionFamily,
    characterization: Characterization,
    search: dict[str, tuple[str, Trace]],
    task: TaskRef,
    config: AEAConfig,
) -> None:
    """Every summarized Controller probe must be backed by its actual immutable episodes."""
    used_ids: set[str] = set()
    used_levels: set[str] = set()
    levels = {level.level_id: level for level in characterization.positive_levels}
    for probe in acceptance["probes"]:
        level = levels.get(probe["level_id"])
        ids = probe["episode_ids"]
        if (
            level is None
            or level.level_id in used_levels
            or not isinstance(ids, list)
            or len(set(ids)) != len(ids)
            or used_ids.intersection(ids)
            or not probe["complete"]
            or probe["n"] not in config.probe
            or len(ids) != probe["n"]
            or probe["surface_signature"] != level.surface_signature
            or probe["setting"] != level.representative.value
        ):
            raise ConfigError("Controller probe has invalid effective-level or episode binding")
        expected_source = candidate_hash(family.render(level.representative, task.task_id))
        phase = f"v3_control:{family.family_id}:{level.level_id}"
        actual = [search.get(uid) for uid in ids]
        if any(
            row is None
            or row[0] != phase
            or row[1].error
            or candidate_hash(row[1].candidate) != expected_source
            for row in actual
        ):
            raise ConfigError("Controller probe lacks matching actual learner episodes")
        successes = sum(bool(row[1].success) for row in actual if row is not None)
        try:
            actual_verdict = verdict(successes, len(ids), config)
        except ValueError as exc:
            raise ConfigError("Controller probe lacks its required top-up episodes") from exc
        if probe["successes"] != successes or probe["verdict"] != actual_verdict:
            raise ConfigError("Controller summary differs from actual learner outcomes")
        used_ids.update(ids)
        used_levels.add(level.level_id)
    family_ids = {
        uid
        for uid, (phase, _) in search.items()
        if phase.startswith(f"v3_control:{family.family_id}:")
    }
    if used_ids != family_ids:
        raise ConfigError("Controller acceptance omits or adds final-family learner episodes")


def verify_final_environment(
    run_dir: Path, task: TaskRef, config: AEAConfig, control_config: V3Config
) -> Candidate:
    """Rebuild the frozen candidate and replay saved admission checks without API calls."""
    starts = [
        event.payload
        for event in read_trace(run_dir / "events.jsonl")
        if event.kind == "task_start" and event.payload["task_id"] == task.task_id
    ]
    if (
        len(starts) != 1
        or starts[0].get("method_config") != config.model_dump(mode="json")
        or starts[0].get("control_config") != control_config.model_dump(mode="json")
    ):
        raise ConfigError("Task's measurement configuration differs from confirmation")
    entries = [
        entry
        for entry in read_corpus(run_dir / "corpus.jsonl")
        if entry.aea.task_id == task.task_id
    ]
    if len(entries) != 1:
        raise ConfigError("Confirmation requires exactly one final environment")
    entry = entries[0]
    if entry.aea.seed != task.seed:
        raise ConfigError("Final environment task seed mismatch")
    candidate = entry.to_candidate()
    if entry.aea.kind == "kept":
        if candidate_hash(candidate) != candidate_hash(Candidate()):
            raise ConfigError("MID must retain the original environment")
        mid_freezes = [
            event.payload
            for event in read_trace(run_dir / "events.jsonl")
            if event.kind == "v3_mid_freeze" and event.payload["task_id"] == task.task_id
        ]
        if len(mid_freezes) != 1:
            raise ConfigError("MID requires exactly one frozen measurement receipt")
        evidence_sha256 = mid_freezes[0].get("search_evidence_sha256")
        if not isinstance(evidence_sha256, str):
            raise ConfigError("MID has no frozen measurement digest")
        search, measurement = _search_evidence(run_dir, task, config, evidence_sha256)
        if measurement["regime"] != "band" or any(
            phase != "estimate" for phase, _ in search.values()
        ):
            raise ConfigError("MID cannot contain adaptation episodes")
        if entry.aea.n_search != measurement["n"]:
            raise ConfigError("MID corpus search accounting differs from frozen measurement")
        return candidate
    directory = run_dir / "designer_controller" / canonical_hash(task.task_id)[:16]
    final = json.loads((directory / "final.json").read_text())
    rows = read_jsonl(directory / "session.jsonl")
    freezes = [row for row in rows if row["event"] == "final_family_freeze"]
    if len(freezes) != 1 or rows[-1] != freezes[0]:
        raise ConfigError("Expected exactly one terminal final family freeze")
    if freezes[0]["final_sha256"] != canonical_hash(final):
        raise ConfigError("Frozen final bundle changed")
    if final["method_config"] != config.model_dump(mode="json") or final[
        "v3_config"
    ] != control_config.model_dump(mode="json"):
        raise ConfigError("Confirmation configuration differs from frozen search")
    search, measurement = _search_evidence(run_dir, task, config, final["search_evidence_sha256"])
    family = InterventionFamily.model_validate(final["family"])
    if measurement["regime"] != ("zero" if family.direction == "easier" else "saturated"):
        raise ConfigError("Frozen family direction differs from original measurement")
    if entry.aea.n_search != sum(not trace.error for _, trace in search.values()):
        raise ConfigError("Final corpus search accounting differs from frozen learner episodes")
    probes = probes_from_records(
        json.loads((directory / f"D{family.design_round}.probes.json").read_text())
    )
    characterization = ActuatorCharacterizer(control_config).characterize_probes(
        family,
        task.task_id,
        probes,
        expected_coverage=[
            tuple(key) for key in final["characterization"]["coverage"]["episode_steps"]
        ],
    )
    if canonical_hash(characterization.as_record()) != canonical_hash(final["characterization"]):
        raise ConfigError("Frozen effective-level characterization changed")
    levels = [
        level
        for level in characterization.positive_levels
        if level.level_id == final["chosen_level_id"]
    ]
    if len(levels) != 1:
        raise ConfigError("Final level is not characterized")
    level = levels[0]
    expected = family.render(level.representative, task.task_id)
    if (
        candidate.in_env_actions
        or candidate_hash(candidate) != candidate_hash(expected)
        or final["candidate_sha256"] != candidate_hash(candidate)
    ):
        raise ConfigError("Final corpus differs from the accepted rendered candidate")
    if candidate_hash(Candidate.model_validate(final["candidate"])) != candidate_hash(candidate):
        raise ConfigError("Frozen candidate payload differs from corpus")
    acceptance = final["search_acceptance"]
    _verify_probe_evidence(acceptance, family, characterization, search, task, config)
    accepted = [
        p
        for p in acceptance["probes"]
        if p["level_id"] == level.level_id and p["verdict"] == "in_band" and p["complete"]
    ]
    if acceptance["reason"] != "ACCEPTED" or len(accepted) != 1:
        raise ConfigError("Final level lacks a complete Controller acceptance")
    probe = accepted[0]
    if (
        probe["n"] != config.probe[1]
        or not config.accept[0] <= probe["successes"] <= config.accept[1]
    ):
        raise ConfigError("Final level does not meet configured search acceptance")
    if not final["certification"]["ok"] or not any(
        row["event"] == "solvability"
        and row["candidate_sha256"] == candidate_hash(candidate)
        and row["result"] == final["certification"]
        for row in rows
    ):
        raise ConfigError("Final exact environment has no successful solvability witness")
    if family.direction == "easier":
        admission = verify_saved_admission(
            final["admission"],
            family,
            characterization,
            task_id=task.task_id,
            config=control_config,
        )
        admission.require(
            family, characterization, level, candidate, task_id=task.task_id, config=control_config
        )
    elif final["admission"] is not None:
        raise ConfigError("HIGH unexpectedly contains LOW privileged admission")
    return candidate


def confirm(host: Controller, task: TaskRef) -> dict[str, Any]:
    """Exactly 4x4 fresh episodes; failure leaves an unrepeatable partial confirmation.

    Invoke only after search has terminated. There is deliberately no automatic paid
    entry point in this implementation-only deliverable.
    """
    if not host.designer_controller:
        raise ConfigError("This confirmation path belongs only to the v3 selector")
    config = host.config
    if config.k != 16 or config.band_l != (0.2, 0.8) or config.band_t != (0.4, 0.6):
        raise ConfigError("This protocol retains the frozen K16 definitions")
    done = [
        e.payload
        for e in read_trace(host.run_dir / "events.jsonl")
        if e.kind == "task_done" and e.payload["task_id"] == task.task_id
    ]
    if len(done) != 1 or done[0]["outcome"] not in ("accepted", "kept"):
        raise ConfigError("Only a unique terminal accepted/kept task can enter K16")
    candidate = verify_final_environment(
        host.run_dir, task, config, host.designer_controller_config
    )
    before = method_state_sha256(host.run_dir)
    directory = host.run_dir / "v3_confirmation" / canonical_hash(task.task_id)[:16]
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with (directory / "started.json").open("x") as stream:
            json.dump(
                {"method_state_sha256": before, "candidate_sha256": candidate_hash(candidate)},
                stream,
            )
    except FileExistsError as exc:
        raise ConfigError("K16 already started; implicit retry/replacement is forbidden") from exc
    search = read_jsonl(host.run_dir / "traces.jsonl")
    seen = {str(row["episode_id"]) for row in search}
    traces: list[Trace] = []
    frozen_candidate_sha256 = candidate_hash(candidate)
    for _ in range(4):
        dispatched = candidate.model_copy(deep=True)
        batch = host.substrate.rollouts(
            task,
            dispatched,
            4,
            attribution=Attribution(
                phase="v3_k16",
                budget="eval",
                arm=host.arm,
                task_id=task.task_id,
            ),
        )
        for trace in batch:
            append_jsonl(directory / "traces.jsonl", trace.model_dump(mode="json"))
        if candidate_hash(dispatched) != frozen_candidate_sha256:
            raise ConfigError("K16 dispatch mutated the frozen candidate")
        validate_traces(batch, 4, task, candidate, seen)
        if any(trace.error for trace in batch):
            raise InfraError("K16 errored; no replacement or feedback", kind="confirmation")
        if method_state_sha256(host.run_dir) != before:
            raise ConfigError("K16 changed the frozen method state")
        traces.extend(batch)
    successes = sum(bool(trace.success) for trace in traces)
    result = {
        "task_id": task.task_id,
        "n": 16,
        "successes": successes,
        "learnable": config.learnable(successes, 16),
        "target": math.ceil(16 * config.band_t[0])
        <= successes
        <= math.floor(16 * config.band_t[1]),
        "reused": False,
        "episode_ids": [trace.episode_id for trace in traces],
        "candidate_sha256": candidate_hash(candidate),
        "method_state_sha256": before,
    }
    atomic_write_json(directory / "result.json", result)
    return result
