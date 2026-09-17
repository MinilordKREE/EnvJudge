"""Offline v3 task reconstruction and strict, metadata-only publication projection.

The builder returns PRIVATE records. Only ``public_task_metadata`` is publishable. Neither
function dispatches a model, learner or environment. Physical summaries reuse the existing
auditor on task-filtered temporary metadata journals, never copying raw request files.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from envharness.core.types import Candidate
from pydantic import TypeAdapter, ValidationError

from aea.actuator import ActuatorCharacterizer, Characterization, probes_from_records
from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.core.io import read_jsonl
from aea.designer_controller_confirmation import (
    candidate_hash,
    method_state_sha256,
    verify_final_environment,
)
from aea.errors import ConfigError
from aea.evaluate import verdict
from aea.intervention import (
    DesignOperation,
    FeedbackReason,
    InterventionFamily,
    V3Config,
    canonical_hash,
)
from aea.intervention_gates import PrivilegeAdmission, verify_saved_admission
from aea.llm.ledger import LedgerRow, read_ledger, summarize
from aea.llm.physical_audit import physical_summary

SCHEMA_VERSION = 1
PHASES = ("measurement", "adaptation", "designer", "judge", "confirmation", "other")
_REGIMES = {"zero": "LOW", "band": "MID", "saturated": "HIGH"}
_FEEDBACK_REASONS = tuple(TypeAdapter(FeedbackReason).json_schema()["enum"])
_OPERATIONS = tuple(TypeAdapter(DesignOperation).json_schema()["enum"])


def _rows(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path) if path.exists() else []


def _number(value: Any, *, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected numeric metadata")
    if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("Numeric metadata outside allowed range")
    return float(value)


def _count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Expected nonnegative integer metadata")
    return value


def _hash(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected SHA256 metadata")
    return value


def _identity(value: Any) -> str | None:
    return None if value is None else canonical_hash(value)


def _enum(value: Any, choices: tuple[str, ...]) -> str:
    return value if isinstance(value, str) and value in choices else "other"


def _phase(row: LedgerRow) -> str:
    if row.budget == "designer":
        return "designer"
    if row.budget in ("eval", "confirm") or row.phase == "v3_k16":
        return "confirmation"
    if row.phase == "estimate":
        return "measurement"
    if row.phase.startswith("v3_control:"):
        return "adaptation"
    if row.phase == "v3_privilege":
        return "judge"
    return "other"


def _logical(run_dir: Path, task_id: str) -> dict[str, Any]:
    merged = run_dir / "ledger.jsonl"
    paths = [merged] if merged.exists() else sorted(run_dir.glob("ledger.*.jsonl"))
    rows = [row for path in paths for row in read_ledger(path) if row.task_id == task_id]
    summaries = {
        phase: summarize([row for row in rows if _phase(row) == phase]) for phase in PHASES
    }
    total = summarize(rows)
    return {
        "status": "recorded" if paths else "unavailable",
        "logical_calls": total.calls,
        "logical_usd": total.usd,
        "ledger_rollouts": total.rollouts,
        "calls_by_phase": {phase: item.calls for phase, item in summaries.items()},
        "usd_by_phase": {phase: item.usd for phase, item in summaries.items()},
        "rollouts_by_phase": {phase: item.rollouts for phase, item in summaries.items()},
        "infra_retries": total.infra_retries,
        "infra_failures": total.infra_failures,
        "ledger_rows": [row.model_dump(mode="json") for row in rows],
    }


def _physical(run_dir: Path, task_id: str) -> dict[str, Any] | None:
    paths = sorted((run_dir / "physical").rglob("attempts.*.jsonl"))
    if not paths:
        return None
    rows = []
    for path in paths:
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            raise ConfigError("Physical audit journal has an incomplete line")
        rows.extend(_rows(path))
    selected = [row for row in rows if str(row.get("attribution", {}).get("task_id")) == task_id]
    # Keep the existing physical accounting formula as the single source of truth.
    with TemporaryDirectory(prefix="aea-v3-physical-") as directory:
        journal = Path(directory) / "attempts.task.jsonl"
        journal.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in selected))
        result = physical_summary(directory)
    if any(result[key] for key in ("inflight", "invalid_usage", "incomplete_journal_lines")):
        raise ConfigError("Task physical accounting is incomplete or invalid")
    return result


def _audit_session(
    directory: Path,
    task: TaskRef,
    rows: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    regime: str,
    task_start: Mapping[str, Any],
) -> tuple[AEAConfig, V3Config]:
    try:
        config = AEAConfig.model_validate(task_start["method_config"])
        control_config = V3Config.model_validate(task_start["control_config"])
    except (KeyError, ValidationError) as exc:
        raise ConfigError("Task start lacks valid recorded method/control configuration") from exc
    if config.method_version != "llm_v3_designer_controller":
        raise ConfigError("Artifact belongs to a different method selector")
    if not rows:
        if regime != "MID":
            raise ConfigError("Adapted task has no Designer--Controller session")
        return config, control_config
    starts = [row for row in rows if row["event"] == "session_started"]
    if len(starts) != 1 or rows[0] != starts[0] or regime == "MID":
        raise ConfigError("Invalid task-local design session start")
    if any(str(row.get("task_id")) != task.task_id for row in rows):
        raise ConfigError("Session mixes task identities")
    if starts[0].get("method_config") != config.model_dump(mode="json") or starts[0].get(
        "config"
    ) != control_config.model_dump(mode="json"):
        raise ConfigError("Session configuration differs from recorded task start")
    families: dict[str, InterventionFamily] = {}
    captures: dict[str, Characterization] = {}
    admissions: dict[str, PrivilegeAdmission] = {}
    provisional: set[str] = set()
    decisions: dict[str, dict[str, Any]] = {}
    successes: set[str] = set()
    episodes = {row["episode_id"]: row for row in traces}
    seen_probe_episodes: set[str] = set()
    rounds: list[int] = []
    current: InterventionFamily | None = None
    frozen = False
    for index, row in enumerate(rows):
        event = row["event"]
        if frozen:
            raise ConfigError("Session contains events after final freeze")
        if event == "designer_proposal":
            rounds.append(_count(row["design_round"]))
            if (
                rounds != list(range(1, len(rounds) + 1))
                or len(rounds) > control_config.max_design_rounds
            ):
                raise ConfigError("Designer rounds are not a bounded consecutive sequence")
        elif event == "family_proposed":
            current = InterventionFamily.model_validate(row["family"])
            if current.family_id in families or current.design_round != rounds[-1]:
                raise ConfigError("Duplicate family identity or wrong design round")
            families[current.family_id] = current
        elif event == "characterization":
            family_id = row["characterization"]["family_id"]
            family = families[family_id]
            if family_id in captures:
                raise ConfigError("Family has multiple characterizations")
            raw = json.loads((directory / f"D{family.design_round}.probes.json").read_text())
            captured = ActuatorCharacterizer(control_config).characterize_probes(
                family,
                task.task_id,
                probes_from_records(raw),
                expected_coverage=[
                    tuple(key) for key in row["characterization"]["coverage"]["episode_steps"]
                ],
            )
            if canonical_hash(captured.as_record()) != canonical_hash(row["characterization"]):
                raise ConfigError("Saved characterization changed")
            captures[family_id] = captured
        elif event == "privilege":
            if regime != "LOW" or current is None:
                raise ConfigError("Privilege decision appears outside LOW family")
            admissions[current.family_id] = verify_saved_admission(
                row["record"],
                current,
                captures[current.family_id],
                task_id=task.task_id,
                config=control_config,
            )
        elif event == "solvability" and row["result"]["ok"]:
            successes.add(_hash(row["candidate_sha256"]))
        elif event == "provisional_family":
            family = families[row["family_id"]]
            captured = captures[family.family_id]
            if row["characterization_sha256"] != captured.sha256 or not captured.positive_levels:
                raise ConfigError("Provisional family lacks its characterization")
            strongest = family.render(captured.positive_levels[-1].representative, task.task_id)
            if candidate_hash(strongest) not in successes:
                raise ConfigError("Provisional family lacks strongest-level solvability")
            provisional.add(family.family_id)
        elif event == "controller_decision":
            family = families[row["family_id"]]
            captured = captures[family.family_id]
            if family.family_id not in provisional or family.family_id in decisions:
                raise ConfigError("Controller requires one gated provisional family")
            if (
                row["source_sha256"] != family.source_sha256
                or row["design_round"] != family.design_round
            ):
                raise ConfigError("Controller decision source or round mismatch")
            if len(row["probes"]) > control_config.max_control_probes:
                raise ConfigError("Controller exceeded its distinct-level probe cap")
            if (
                row["probes"]
                and row["probes"][0]["level_id"] != captured.positive_levels[-1].level_id
            ):
                raise ConfigError(
                    "Controller did not begin with strongest proposed effective level"
                )
            seen_levels: set[str] = set()
            for probe in row["probes"]:
                level_id = probe["level_id"]
                if level_id in seen_levels:
                    raise ConfigError("Duplicate effective-level policy probe")
                seen_levels.add(level_id)
                level = next(
                    (level for level in captured.positive_levels if level.level_id == level_id),
                    None,
                )
                if (
                    level is None
                    or probe["surface_signature"] != level.surface_signature
                    or probe["setting"] != level.representative.value
                ):
                    raise ConfigError("Policy probe does not bind its effective level")
                candidate = family.render(level.representative, task.task_id)
                if regime == "LOW":
                    if family.family_id not in admissions:
                        raise ConfigError("LOW policy probe has no privilege admission")
                    admissions[family.family_id].require(
                        family,
                        captured,
                        level,
                        candidate,
                        task_id=task.task_id,
                        config=control_config,
                    )
                ids = probe["episode_ids"]
                if (
                    len(ids) != probe["n"]
                    or len(set(ids)) != len(ids)
                    or seen_probe_episodes.intersection(ids)
                ):
                    raise ConfigError("Controller probe episode identities are reused or missing")
                saved = [episodes[episode] for episode in ids]
                if any(
                    item.get("error")
                    or candidate_hash(Candidate.model_validate(item["candidate"]))
                    != candidate_hash(candidate)
                    for item in saved
                ):
                    raise ConfigError("Probe trace does not match rendered environment")
                if sum(bool(item["success"]) for item in saved) != probe["successes"]:
                    raise ConfigError("Controller probe success count differs from traces")
                if probe["complete"] is True:
                    if probe["n"] not in config.probe or probe["verdict"] != verdict(
                        probe["successes"], probe["n"], config
                    ):
                        raise ConfigError("Complete probe disagrees with frozen evaluation rule")
                elif probe["complete"] is not False or probe["verdict"] is not None:
                    raise ConfigError("Incomplete probe cannot have an acceptance verdict")
                seen_probe_episodes.update(ids)
            decisions[family.family_id] = row
        elif event == "final_family_freeze":
            if (
                index != len(rows) - 1
                or row["family_id"] not in decisions
                or decisions[row["family_id"]]["reason"] != "ACCEPTED"
            ):
                raise ConfigError(
                    "Final freeze must follow Controller acceptance and end the session"
                )
            frozen = True
    return config, control_config


def build_task_artifact(run_dir: Path, task_id: str) -> dict[str, Any]:
    """Reconstruct one terminal task privately and fail on inconsistent admission/accounting."""
    task_id = str(task_id)
    events = [
        row
        for row in _rows(run_dir / "events.jsonl")
        if str(row.get("payload", {}).get("task_id")) == task_id
    ]
    starts = [row["payload"] for row in events if row["kind"] == "task_start"]
    done = [row["payload"] for row in events if row["kind"] == "task_done"]
    measured = [row["payload"] for row in events if row["kind"] == "measurement_evidence"]
    if len(starts) != 1 or len(done) != 1 or len(measured) != 1:
        raise ConfigError("Artifact requires one complete task attempt and measurement")
    outcome, measurement = done[0], measured[0]
    regime = _REGIMES[measurement["regime"]]
    task = TaskRef(task_id, starts[0]["seed"])
    traces = [
        row for row in _rows(run_dir / "traces.jsonl") if row.get("rollout_seed") == task.seed
    ]
    ids = [row["episode_id"] for row in traces]
    if len(ids) != len(set(ids)):
        raise ConfigError("Method trace episode identity reused")
    directory = run_dir / "designer_controller" / canonical_hash(task_id)[:16]
    session = _rows(directory / "session.jsonl")
    config, control_config = _audit_session(directory, task, session, traces, regime, starts[0])
    has_final = outcome["outcome"] in ("accepted", "kept")
    candidate = (
        verify_final_environment(run_dir, task, config, control_config) if has_final else None
    )
    if not has_final and (directory / "final.json").exists():
        raise ConfigError("Dropped task unexpectedly has a final environment")
    final = (
        json.loads((directory / "final.json").read_text())
        if has_final and regime != "MID"
        else None
    )
    baseline = _count(outcome["baseline_rollouts"])
    adaptation = _count(outcome["adaptation_rollouts"])
    valid = [row for row in traces if not row.get("error")]
    original = candidate_hash(Candidate())
    baseline_valid = [
        row
        for row in valid
        if candidate_hash(Candidate.model_validate(row["candidate"])) == original
    ]
    if (
        baseline != measurement["n"]
        or baseline != len(baseline_valid)
        or adaptation != len(valid) - baseline
    ):
        raise ConfigError("Measurement/adaptation accounting differs from valid method traces")
    if (
        outcome["n_search"] != baseline + adaptation
        or baseline > config.k
        or adaptation > config.cap
    ):
        raise ConfigError("Search accounting exceeds or contradicts separate budgets")
    if outcome["outcome"] != "infra_error":
        recorded_probes = {
            episode
            for row in session
            if row["event"] == "controller_decision"
            for probe in row["probes"]
            for episode in probe["episode_ids"]
        }
        actual_adaptation = {
            row["episode_id"]
            for row in valid
            if candidate_hash(Candidate.model_validate(row["candidate"])) != original
        }
        if recorded_probes != actual_adaptation:
            raise ConfigError("Controller history omits charged adaptation episodes")
    confirmation_dir = run_dir / "v3_confirmation" / canonical_hash(task_id)[:16]
    confirmation_traces = _rows(confirmation_dir / "traces.jsonl")
    current_hash = method_state_sha256(run_dir)
    if (confirmation_dir / "result.json").exists():
        confirmation = json.loads((confirmation_dir / "result.json").read_text())
        confirm_ids = [row["episode_id"] for row in confirmation_traces]
        if (
            candidate is None
            or confirmation["n"] != 16
            or len(confirmation_traces) != 16
            or len(set(confirm_ids)) != 16
            or set(confirm_ids).intersection(ids)
        ):
            raise ConfigError("Completed K16 lacks sixteen fresh final-environment traces")
        if confirmation["method_state_sha256"] != current_hash or confirmation[
            "candidate_sha256"
        ] != candidate_hash(candidate):
            raise ConfigError("Confirmation changed the method or final environment")
        if confirmation["episode_ids"] != confirm_ids or any(
            row.get("error")
            or row.get("rollout_seed") != task.seed
            or candidate_hash(Candidate.model_validate(row["candidate"]))
            != candidate_hash(candidate)
            for row in confirmation_traces
        ):
            raise ConfigError("K16 trace or candidate binding mismatch")
        successes = sum(bool(row["success"]) for row in confirmation_traces)
        if (
            confirmation["successes"] != successes
            or confirmation["learnable"] != (4 <= successes <= 12)
            or confirmation["target"] != (7 <= successes <= 9)
            or confirmation["reused"] is not False
        ):
            raise ConfigError("K16 result differs from fixed fresh-confirmation definitions")
        confirmation = {**confirmation, "status": "completed"}
    else:
        confirmation = {
            "status": "incomplete"
            if (confirmation_dir / "started.json").exists()
            else "pending"
            if has_final
            else "not_applicable"
        }
    references = [
        row
        for row in _rows(run_dir / "privileged_references.jsonl")
        if str(row.get("task_id")) == task_id
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "method_version": "llm_v3_designer_controller",
        "task_id": task_id,
        "regime": regime,
        "outcome": outcome,
        "method_state_sha256": current_hash,
        "measurement_evidence": measurement,
        "events": events,
        "session": session,
        "method_traces": traces,
        "privileged_references": references,
        "final_environment": final,
        "candidate": candidate.model_dump(mode="json") if candidate is not None else None,
        "rollout_accounting": {
            "measurement": baseline,
            "adaptation": adaptation,
            "search": baseline + adaptation,
            "confirmation": len(confirmation_traces),
            "invalid_method_traces": len(traces) - len(valid),
        },
        "usd_accounting": {**_logical(run_dir, task_id), "physical": _physical(run_dir, task_id)},
        "k16": confirmation,
        "confirmation_traces": confirmation_traces,
    }


def _setting(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "value": _number(record["value"], maximum=1),
        "name_sha256": None if record.get("name_sha256") is None else _hash(record["name_sha256"]),
    }


def _characterization(record: Mapping[str, Any]) -> dict[str, Any]:
    coverage = record["coverage"]
    return {
        "family_id_sha256": _identity(record["family_id"]),
        "source_sha256": _hash(record["source_sha256"]),
        "control_sha256": _hash(record["control_sha256"]),
        "settings": [_setting(setting) for setting in record["settings"]],
        "levels": [
            {
                "level_id_sha256": _identity(level["level_id"]),
                "surface_signature": _hash(level["surface_signature"]),
                "equivalent_settings": [_setting(setting) for setting in level["settings"]],
                "representative": _setting(level["representative"]),
                "order": _count(level["order"]),
                "is_off": level["is_off"] is True,
                "rendered_source_sha256": _hash(level["rendered_source_sha256"]),
            }
            for level in record["levels"]
        ],
        "coverage": {
            "complete": coverage["complete"] is True,
            "expected_count": _count(coverage["expected_count"]),
            "actual_count": _count(coverage["actual_count"]),
            "episode_step_count": len(coverage["episode_steps"]),
            "episode_count": len({item[0] for item in coverage["episode_steps"]}),
        },
        "diagnostics": [
            _enum(item, ("NON_MONOTONE_CONTROL_SURFACE",)) for item in record["diagnostics"]
        ],
        "raw_probe_sha256": _hash(record["raw_probe_sha256"]),
        "record_sha256": canonical_hash(record),
    }


def _feedback(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reason": _enum(record["reason"], _FEEDBACK_REASONS),
        "operation": None
        if record.get("operation") is None
        else _enum(record["operation"], _OPERATIONS),
        "family_id_sha256": _identity(record["family_id"]),
        "semantic_mechanism_id_sha256": _identity(record["semantic_mechanism_id"]),
        "source_sha256": _hash(record["source_sha256"]),
        "design_round": _count(record["design_round"]),
        "remaining_policy_rollouts": _count(record["remaining_policy_rollouts"]),
        "policy_rollouts": sum(_count(probe["n"]) for probe in record["probes"]),
        "effective_level_count": _count(record["effective_level_count"]),
        "nominal_setting_count": _count(record["nominal_setting_count"]),
        "probes": [
            {
                "level_id_sha256": _identity(probe["level_id"]),
                "surface_signature": _hash(probe["surface_signature"]),
                "setting": _number(probe["setting"], maximum=1),
                "successes": _count(probe["successes"]),
                "n": _count(probe["n"]),
                "verdict": None
                if probe["verdict"] is None
                else _enum(probe["verdict"], ("in_band", "too_hard", "too_easy")),
                "complete": probe["complete"] is True,
                "episode_ids_sha256": canonical_hash(probe["episode_ids"]),
            }
            for probe in record["probes"]
        ],
        "explanation_sha256": _identity(record.get("explanation")),
        "record_sha256": canonical_hash(record),
    }


def _public_physical(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    counts = (
        "attempts",
        "returned",
        "ambiguous_failures",
        "invalid_usage",
        "inflight",
        "upstream_reported_count",
        "estimate_exceeded_count",
        "incomplete_journal_lines",
    )
    costs = (
        "upstream_reported_usd",
        "returned_upper_rate_usd",
        "returned_conservative_usd",
        "retained_ambiguous_estimate_usd",
        "invalid_usage_estimate_usd",
        "inflight_estimate_usd",
        "conservative_total_usd",
    )
    return {
        **{key: _count(record[key]) for key in counts},
        **{key: _number(record[key]) for key in costs},
        "pricing_file_sha256": [_hash(value) for value in record["pricing_file_sha256"]],
        "usd_cap": None if record.get("usd_cap") is None else _number(record["usd_cap"]),
    }


def public_task_metadata(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild an allowlist; never forward arbitrary object fields or source-derived strings."""
    task_id = artifact["task_id"]
    if not isinstance(task_id, str) or re.fullmatch(r"[0-9]{1,12}", task_id) is None:
        raise ValueError("Public ALFWorld task ID must be numeric")
    rows, measurement, usd = (
        artifact["session"],
        artifact["measurement_evidence"],
        artifact["usd_accounting"],
    )
    families = [row["family"] for row in rows if row["event"] == "family_proposed"]
    privilege = [row["record"] for row in rows if row["event"] == "privilege"]
    k16, candidate = artifact["k16"], artifact["candidate"]
    return {
        "schema_version": SCHEMA_VERSION,
        "method_version": "llm_v3_designer_controller",
        "task_id": task_id,
        "regime": _enum(artifact["regime"], ("LOW", "MID", "HIGH")),
        "outcome": _enum(
            artifact["outcome"]["outcome"], ("accepted", "kept", "dropped", "infra_error")
        ),
        "reason": _enum(artifact["outcome"].get("reason"), (*_FEEDBACK_REASONS, "budget", "")),
        "reason_sha256": _identity(artifact["outcome"].get("reason")),
        "method_state_sha256": _hash(artifact["method_state_sha256"]),
        "measurement_evidence": {
            "successes": _count(measurement["successes"]),
            "n": _count(measurement["n"]),
            "p_hat": _number(measurement["p_hat"], maximum=1),
            "probabilities": {
                label: _number(measurement["probabilities"][key], maximum=1)
                for key, label in _REGIMES.items()
            },
            "stop_reason": _enum(measurement["stop_reason"], ("confidence", "k_max")),
            "errors_retried": _count(measurement["errors_retried"]),
            "record_sha256": canonical_hash(measurement),
        },
        "designer_calls": {
            "count": sum(row["event"] == "designer_io" for row in rows),
            "proposal_count": sum(row["event"] == "designer_proposal" for row in rows),
        },
        "candidate_lineage": [
            {
                "family_id_sha256": _identity(family["family_id"]),
                "parent_family_id_sha256": _identity(family["parent_family_id"]),
                "semantic_mechanism_id_sha256": _identity(family["semantic_mechanism_id"]),
                "design_round": _count(family["design_round"]),
                "operation": _enum(family["operation"], _OPERATIONS),
                "direction": _enum(family["direction"], ("easier", "harder")),
                "axis": _enum(family["axis"], ("O", "T", "A")),
                "control_kind": _enum(family["control"]["kind"], ("BINARY", "SCALAR", "DISCRETE")),
                "source_sha256": hashlib.sha256(family["source"].encode()).hexdigest(),
                "control_sha256": canonical_hash(family["control"]),
                "record_sha256": canonical_hash(family),
            }
            for family in families
        ],
        "characterizations": [
            _characterization(row["characterization"])
            for row in rows
            if row["event"] == "characterization"
        ],
        "control_trace": [_feedback(row) for row in rows if row["event"] == "controller_decision"],
        "gate_feedback": [_feedback(row) for row in rows if row["event"] == "feedback"],
        "privilege_decisions": [
            {
                "verdict": _enum(
                    record["result"]["decision"]["verdict"], ("PASS", "FAIL", "UNCERTAIN")
                ),
                **{
                    key: _hash(record[key])
                    for key in ("source_sha256", "control_sha256", "characterization_sha256")
                },
                **{
                    key: _hash(record["result"][key])
                    for key in ("input_sha256", "config_sha256", "prompt_sha256", "schema_sha256")
                },
                "doses": [_number(value, maximum=1) for value in record["doses"]],
                "record_sha256": canonical_hash(record),
            }
            for record in privilege
        ],
        "privileged_references": [
            {
                "n_steps": _count(record["n_steps"]),
                "actions_sha256": canonical_hash(record["actions"]),
                "provenance_id_sha256": _identity(record.get("reference_id")),
                "record_sha256": canonical_hash(record),
            }
            for record in artifact["privileged_references"]
        ],
        "solvability": [
            {
                "candidate_sha256": _hash(row["candidate_sha256"]),
                "reused": row["event"] == "solvability_reused",
                "ok": None if row["event"] == "solvability_reused" else row["result"]["ok"] is True,
                "source": None
                if row["event"] == "solvability_reused"
                else _enum(
                    row["result"]["source"],
                    ("oracle", "policy_replay", "uncertified", "self_certify", "by_construction"),
                ),
                "record_sha256": canonical_hash(row),
            }
            for row in rows
            if row["event"] in ("solvability", "solvability_reused")
        ],
        "freeze": [
            {
                "family_id_sha256": _identity(row["family_id"]),
                "level_id_sha256": _identity(row["level_id"]),
                "final_sha256": _hash(row["final_sha256"]),
            }
            for row in rows
            if row["event"] == "final_family_freeze"
        ],
        "final_environment": None
        if candidate is None
        else {
            "kind": "kept" if artifact["regime"] == "MID" else "intervention",
            "candidate_sha256": candidate_hash(Candidate.model_validate(candidate)),
            "record_sha256": canonical_hash(artifact["final_environment"]),
        },
        "rollout_accounting": {
            key: _count(artifact["rollout_accounting"][key])
            for key in (
                "measurement",
                "adaptation",
                "search",
                "confirmation",
                "invalid_method_traces",
            )
        },
        "usd_accounting": {
            "status": _enum(usd["status"], ("recorded", "unavailable")),
            "logical_calls": _count(usd["logical_calls"]),
            "logical_usd": _number(usd["logical_usd"]),
            "ledger_rollouts": _count(usd["ledger_rollouts"]),
            "calls_by_phase": {phase: _count(usd["calls_by_phase"][phase]) for phase in PHASES},
            "usd_by_phase": {phase: _number(usd["usd_by_phase"][phase]) for phase in PHASES},
            "rollouts_by_phase": {
                phase: _count(usd["rollouts_by_phase"][phase]) for phase in PHASES
            },
            "infra_retries": _count(usd["infra_retries"]),
            "infra_failures": _count(usd["infra_failures"]),
            "physical": _public_physical(usd["physical"]),
        },
        "k16": {
            "status": _enum(
                k16["status"], ("completed", "pending", "not_applicable", "incomplete")
            ),
            "n": _count(k16.get("n", 0)),
            "successes": _count(k16.get("successes", 0)),
            "learnable": k16.get("learnable") is True,
            "target": k16.get("target") is True,
            "reused": k16.get("reused") is True,
            "record_sha256": canonical_hash(k16),
        },
        "private_artifact_sha256": canonical_hash(artifact),
    }
