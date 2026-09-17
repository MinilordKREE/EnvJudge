"""Unified AEA task records and a deliberately narrow public metadata projection.

The builder returns PRIVATE records, including designer inputs and candidate source. Only
``public_task_metadata`` is suitable for publication. Neither function writes files or runs
models. The driver owns private storage, confirmation dispatch and publication review.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_METHOD_FILES = (
    "events.jsonl",
    "designer_calls.jsonl",
    "low_candidates.jsonl",
    "llm_privilege.jsonl",
    "privileged_references.jsonl",
    "corpus.jsonl",
    "traces.jsonl",
)
_REGIMES = {"zero": "LOW", "band": "MID", "saturated": "HIGH"}
_VERDICTS = {"in_band", "too_hard", "too_easy"}
_OUTCOMES = {"accepted", "kept", "dropped", "infra_error", "pending"}
_REASONS = {
    "budget",
    "exhausted",
    "no_leverage",
    "no_valid_proposal",
    "reference_unavailable",
    "no_failed_rollout",
    "uncertified",
    "endpoint_and_calibration_reserve",
    "policy_budget",
    "certification_inconclusive",
    "endpoint_infrastructure_error",
    "infeasible",
    "optimizer_call_cap",
    "designer_call_cap",
    "control_infeasible",
}
_SOLVABILITY = {"by_construction", "policy_replay", "oracle", "self_certify", "uncertified"}
_LEAK_TYPES = {
    "NONE",
    "DIRECT_ANSWER",
    "REFERENCE_ACTION",
    "HIDDEN_ENTITY",
    "HIDDEN_RELATION",
    "HIDDEN_ROUTE",
    "SOLUTION_ORDERING",
    "TRANSITION_DISCLOSURE",
    "OTHER",
}


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Expected JSON objects in {path.name}")
    return rows


def _task_rows(path: Path, task_id: str, *, unscoped: bool = False) -> list[dict[str, Any]]:
    result = []
    for row in _rows(path):
        metadata = row.get("payload", row.get("aea", row))
        key = metadata.get("task_id")
        if key is None and unscoped:
            key = str(row.get("candidate_id", "")).split(":", 1)[0]
        if str(key) == task_id:
            result.append(row)
    return result


def method_state_sha256(run_dir: Path) -> str:
    """Bind the terminal method history; eval ledgers and confirmation files are excluded.

    Call before K16 and supply that digest to the builder afterwards. This checks that
    confirmation cannot silently mutate the measured/design/frozen-controller history.
    """
    files = {name: run_dir / name for name in _METHOD_FILES}
    for directory in ("llm_privilege_inputs", "raw/designer", "raw/judge"):
        for path in sorted((run_dir / directory).rglob("*")):
            if path.is_file():
                files[str(path.relative_to(run_dir))] = path
    return _digest(
        {
            name: hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            for name, path in files.items()
        }
    )


def _phase(value: Any) -> str:
    phase = str(value or "")
    if phase == "estimate":
        return "measurement"
    if phase.startswith("dose:") or phase in {"probe", "endpoint", "control"}:
        return "adaptation"
    if phase.startswith("design"):
        return "designer"
    if "privilege" in phase or "judge" in phase:
        return "judge"
    if phase.startswith("confirm") or phase == "k16":
        return "confirmation"
    return "other"


def _hash(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected SHA256 digest")
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected finite numeric metadata")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Expected finite nonnegative numeric metadata")
    return float(value)


def _count(value: Any) -> int:
    number = _number(value)
    if number != int(number):
        raise ValueError("Expected integer count")
    return int(number)


def _enum(value: Any, choices: set[str], *, default: str = "other") -> str:
    return value if isinstance(value, str) and value in choices else default


def _nullable_number(value: Any) -> float | None:
    return None if value is None else _number(value)


def _identity(value: Any) -> str | None:
    return None if value is None else _digest(value)


def _guard(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ValueError("Malformed solvability record")
    return dict(value)


def _endpoint(value: Any, *, source: Any = None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            raise ValueError("Malformed endpoint tuple")
        value = {"s": value[0], "n": value[1], "verdict": value[2], "d": 1.0}
    if not isinstance(value, Mapping):
        raise ValueError("Malformed endpoint")
    s = _count(value.get("s", value.get("successes", 0)))
    n = _count(value.get("n", 0))
    if s > n:
        raise ValueError("Success count exceeds episode count")
    dose = _number(value.get("d", 1.0))
    if dose > 1:
        raise ValueError("Dose exceeds one")
    return {
        "source_sha256": _hash(source or value.get("source_sha256")),
        "d": dose,
        "successes": s,
        "n": n,
        "verdict": _enum(value.get("verdict"), _VERDICTS),
    }


def _confirmation(k16: Mapping[str, Any] | None, has_final: bool) -> dict[str, Any]:
    result = dict(k16 or {"status": "pending" if has_final else "not_applicable"})
    status = _enum(result.get("status"), {"completed", "not_applicable", "pending", "error"})
    if status == "other":
        raise ValueError("Invalid K16 status")
    result["status"] = status
    if status == "completed":
        s, n = _count(result["successes"]), _count(result["n"])
        if not has_final or n != 16 or s > n:
            raise ValueError("Completed K16 requires a final environment and 16 episodes")
        for key, value in (("learnable", 4 <= s <= 12), ("target", 7 <= s <= 9)):
            if key in result and result[key] is not value:
                raise ValueError(f"K16 {key} disagrees with the fixed band")
            result[key] = value
        if not result.get("evidence_sha256"):
            raise ValueError("Completed K16 requires an evidence digest")
    if result.get("evidence_sha256") is not None:
        _hash(result["evidence_sha256"])
    return result


def _high_lineage(
    task_id: str, designers: list[dict[str, Any]], payloads: list[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Join the original one-shot proposal records to their actual validation/probe events.

    This does not rerun generated source or infer validation from an endpoint. The integrated
    controller records exact accepted source identities, including duplicate-name cases.
    """
    result = []
    for call_index, call in enumerate(designers, 1):
        accepted = Counter(
            (item["name"], _hash(item["source_sha256"]))
            for item in call.get("accepted_sources", [])
        )
        raw_families = call.get("arguments", {}).get("families", [])
        if not isinstance(raw_families, list):
            continue
        for proposal_index, raw in enumerate(raw_families[:2], 1):
            family = raw if isinstance(raw, dict) else {}
            name = re.sub(r"[^a-z0-9_]", "_", str(family.get("name") or "llm_family").lower())[:40]
            source = str(family.get("rules_code") or "")
            source_sha = hashlib.sha256(source.encode()).hexdigest()
            mechanism = str(family.get("mechanism_summary") or "").strip()
            # Distinguish a malformed first proposal from a later valid proposal with the
            # same normalized name and source. All code validation itself stays recorded.
            eligible = family.get("axis") in ("O", "T", "A") and bool(mechanism)
            valid = eligible and accepted[(name, source_sha)] > 0
            if valid:
                accepted[(name, source_sha)] -= 1
            structural = (
                []
                if valid
                else [
                    str(reason)
                    for reason in call.get("rejected", [])
                    if str(reason).startswith(name + ":") or not isinstance(raw, dict)
                ]
            )
            if not valid and not structural:
                structural = ["Proposal absent from recorded accepted sources"]
            guard = next(
                (
                    body
                    for kind, body in payloads
                    if valid and kind == "solvable" and body.get("family") == name
                ),
                None,
            )
            endpoint = next(
                (
                    body
                    for kind, body in payloads
                    if valid
                    and kind in {"endpoint", "family_endpoint"}
                    and body.get("family") == name
                    and body.get("source_sha256") == source_sha
                ),
                None,
            )
            rejection = "; ".join(structural) or None
            if guard is not None and not guard.get("ok"):
                rejection = "uncertified"
            if endpoint is not None and endpoint.get("verdict") == "too_easy":
                rejection = "no_leverage"
            result.append(
                {
                    "candidate_id": f"{task_id}:H{proposal_index}:{source_sha}",
                    "parent_candidate_id": None,
                    "optimizer_call_index": call_index,
                    "proposal_index": proposal_index,
                    "requested_operation": "PROPOSE",
                    "source": source,
                    "source_sha256": source_sha,
                    "mechanism": mechanism,
                    "validation_status": "accepted" if valid else "rejected",
                    "privilege_applicability": "not_applicable",
                    "structural": structural,
                    "privilege": [],
                    "solvability": None if guard is None else json.dumps(guard, sort_keys=True),
                    "endpoint": None
                    if endpoint is None
                    else [endpoint["s"], endpoint["n"], endpoint["verdict"]],
                    "rejection_reason": rejection,
                    "remaining_calls": 0,
                    "remaining_policy": None,
                }
            )
    return result


def build_task_artifact(
    run_dir: Path,
    task_id: str,
    *,
    k16: Mapping[str, Any] | None = None,
    ledger_paths: Sequence[Path] = (),
    physical_accounting: Mapping[str, Any] | None = None,
    frozen_method_sha256: str | None = None,
) -> dict[str, Any]:
    """Collect the single attempt's complete private records without dispatching anything.

    ``ledger_paths`` overrides discovery, useful when call and rollout ledgers are separate.
    Otherwise a merged ledger takes precedence over its parts, preventing double counting.
    The caller must keep this return value in gitignored private storage.
    """
    task_id = str(task_id)
    current_hash = method_state_sha256(run_dir)
    if frozen_method_sha256 is not None and current_hash != _hash(frozen_method_sha256):
        raise ValueError("Method history changed during K16 confirmation")
    events = _task_rows(run_dir / "events.jsonl", task_id)
    starts = [event for event in events if event["kind"] == "task_start"]
    if len(starts) > 1:
        raise ValueError("Unified artifacts require an isolated task attempt")
    payloads = [(event["kind"], event["payload"]) for event in events]
    done: dict[str, Any] = next(
        (body for kind, body in reversed(payloads) if kind == "task_done"), {}
    )
    estimate: dict[str, Any] = next(
        (body for kind, body in reversed(payloads) if kind == "estimate"), {}
    )
    measurement: dict[str, Any] = next(
        (body for kind, body in reversed(payloads) if kind == "measurement_evidence"), {}
    )
    designers = _task_rows(run_dir / "designer_calls.jsonl", task_id)
    candidates = _task_rows(run_dir / "low_candidates.jsonl", task_id, unscoped=True)
    if estimate.get("regime", done.get("regime")) == "saturated":
        candidates = _high_lineage(task_id, designers, payloads)
    privileges = _task_rows(run_dir / "llm_privilege.jsonl", task_id)
    references = _task_rows(run_dir / "privileged_references.jsonl", task_id)
    corpus = _task_rows(run_dir / "corpus.jsonl", task_id)
    if len(corpus) > 1:
        raise ValueError("A task attempt may release at most one final environment")
    final = corpus[0] if corpus else None
    seed = starts[0]["payload"].get("seed") if starts else None
    traces = [
        row
        for row in _rows(run_dir / "traces.jsonl")
        if str(row.get("task_id")) == task_id
        or (seed is not None and row.get("rollout_seed") == seed)
    ]
    if not ledger_paths:
        merged = run_dir / "ledger.jsonl"
        ledger_paths = [merged] if merged.exists() else sorted(run_dir.glob("ledger.*.jsonl"))
    resolved = [path.resolve() for path in ledger_paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Duplicate ledger paths would double count spending")
    ledger = [row for path in ledger_paths for row in _task_rows(path, task_id)]
    calls = [row for row in ledger if row.get("event") == "call"]
    rollouts = [row for row in ledger if row.get("event") == "rollout"]
    calls_by_phase = Counter(_phase(row.get("phase")) for row in calls)
    rollouts_by_phase = Counter(_phase(row.get("phase")) for row in rollouts)
    usd_by_phase: dict[str, float] = {}
    for row in calls:
        phase = _phase(row.get("phase"))
        usd_by_phase[phase] = usd_by_phase.get(phase, 0.0) + _number(row.get("usd", 0.0))
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "regime": _REGIMES.get(str(estimate.get("regime", done.get("regime")))),
        "method_state_sha256": current_hash,
        "history_unchanged_during_k16": True if frozen_method_sha256 is not None else None,
        "outcome": done,
        "measurement_evidence": {
            "estimate": estimate,
            "measurement": measurement,
            "traces": [
                trace
                for trace in traces
                if str(trace.get("iteration_id", "")).startswith("estimate")
            ],
        },
        "designer_calls": designers,
        "candidate_lineage": candidates,
        "privilege_decisions": privileges,
        "privileged_references": references,
        "solvability": [body for kind, body in payloads if kind == "solvable"],
        "endpoint": [body for kind, body in payloads if kind in {"endpoint", "family_endpoint"}],
        "control_trace": [body for kind, body in payloads if kind in {"dose_control", "bracket"}],
        "freeze": (
            [body for kind, body in payloads if kind == "family_frozen"]
            or [
                body
                for kind, body in payloads
                if kind in {"high_family_frozen", "low_family_frozen"}
            ]
        ),
        "final_environment": final,
        "rollout_accounting": {
            "search_charged": done.get("n_search"),
            "baseline_rollouts": done.get("baseline_rollouts", estimate.get("n")),
            "adaptation_rollouts": done.get("adaptation_rollouts"),
            "ledger_rollouts": len(rollouts),
            "by_phase": dict(rollouts_by_phase),
            "recorded_method_traces": len(traces),
            "rollout_events": [
                body for kind, body in payloads if kind in {"rollouts", "rollout_errors"}
            ],
        },
        "usd_accounting": {
            "logical_calls": len(calls),
            "logical_usd": sum(usd_by_phase.values()),
            "calls_by_phase": dict(calls_by_phase),
            "usd_by_phase": usd_by_phase,
            "physical": dict(physical_accounting) if physical_accounting is not None else None,
            "ledger_rows": ledger,
        },
        "k16": _confirmation(k16, final is not None),
        "events": events,
        "traces": traces,
    }


def _public_candidate(record: Mapping[str, Any]) -> dict[str, Any]:
    guard = _guard(record.get("solvability"))
    return {
        "candidate_id_sha256": _identity(record.get("candidate_id")),
        "parent_candidate_id_sha256": _identity(record.get("parent_candidate_id")),
        "source_sha256": _hash(record.get("source_sha256")),
        "optimizer_call_index": _count(record.get("optimizer_call_index", 0)),
        "proposal_index": (
            None if record.get("proposal_index") is None else _count(record["proposal_index"])
        ),
        "validation_status": _enum(
            record.get("validation_status"),
            {"accepted", "rejected"},
            default="rejected" if record.get("structural") else "accepted",
        ),
        "privilege_applicability": _enum(
            record.get("privilege_applicability"),
            {"required", "not_applicable"},
            default="required",
        ),
        "requested_operation": _enum(
            record.get("requested_operation"), {"PROPOSE", "REPAIR_CODE", "REPLACE_MECHANISM"}
        ),
        "structural_issue_count": len(record.get("structural") or []),
        "privilege_issue_count": len(record.get("privilege") or []),
        "solvability": None
        if guard is None
        else {
            "ok": guard.get("ok") is True,
            "source": _enum(guard.get("source"), _SOLVABILITY),
            "record_sha256": _digest(guard),
        },
        "endpoint": _endpoint(record.get("endpoint"), source=record.get("source_sha256")),
        "rejection_reason_sha256": _identity(record.get("rejection_reason")),
        "remaining_calls": _count(record.get("remaining_calls", 0)),
        "remaining_policy": (
            None if record.get("remaining_policy") is None else _count(record["remaining_policy"])
        ),
        "record_sha256": _digest(record),
    }


def public_task_metadata(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Build a new allowlisted object; arbitrary names, strings and paths never pass through."""
    task_id = str(artifact["task_id"])
    if re.fullmatch(r"[0-9]{1,12}", task_id) is None:
        raise ValueError("Public ALFWorld task IDs must be numeric")
    estimate = artifact["measurement_evidence"]["estimate"]
    outcome = artifact["outcome"]
    designers = artifact["designer_calls"]
    lineage = [_public_candidate(record) for record in artifact["candidate_lineage"]]
    decisions = []
    for record in artifact["privilege_decisions"]:
        result = record["result"]
        decision = result["decision"]
        decisions.append(
            {
                "verdict": _enum(decision.get("verdict"), {"PASS", "FAIL", "UNCERTAIN"}),
                "leak_type": _enum(decision.get("leak_type"), _LEAK_TYPES, default="OTHER"),
                "source_sha256": _hash(result.get("source_sha256")),
                "input_sha256": _hash(result.get("input_sha256")),
                "prompt_sha256": _hash(result.get("prompt_sha256")),
                "schema_sha256": _hash(result.get("schema_sha256")),
                "config_sha256": _hash(result.get("config_sha256")),
                "request_sha256": _hash(result.get("request_sha256")),
                "response_sha256": _hash(result.get("response_sha256")),
                "record_sha256": _digest(record),
                "doses": [_number(dose) for dose in record.get("doses", [])],
            }
        )
    solvability = [
        {
            "family_id_sha256": _identity(record.get("family")),
            "d": _nullable_number(record.get("d")),
            "ok": record.get("ok") is True,
            "source": _enum(record.get("source"), _SOLVABILITY),
            "record_sha256": _digest(record),
        }
        for record in artifact["solvability"]
    ]
    if not solvability:
        solvability = [record["solvability"] for record in lineage if record.get("solvability")]
    endpoints = [_endpoint(record) for record in artifact["endpoint"]]
    if not endpoints:
        endpoints = [record["endpoint"] for record in lineage if record.get("endpoint")]
    final = artifact["final_environment"]
    final_meta = final.get("aea", {}) if final is not None else {}
    rollout = artifact["rollout_accounting"]
    usd = artifact["usd_accounting"]
    phases = {"measurement", "adaptation", "designer", "judge", "confirmation", "other"}
    confirmation = artifact["k16"]
    physical = usd.get("physical")
    public_physical: dict[str, Any] | None = None
    if physical is not None:
        public_physical = {
            key: _number(physical[key])
            for key in (
                "upstream_reported_usd",
                "returned_upper_rate_usd",
                "returned_conservative_usd",
                "retained_ambiguous_estimate_usd",
                "invalid_usage_estimate_usd",
                "inflight_estimate_usd",
                "conservative_total_usd",
            )
            if key in physical
        }
        public_physical.update(
            {
                key: _count(physical[key])
                for key in (
                    "attempts",
                    "returned",
                    "ambiguous_failures",
                    "invalid_usage",
                    "inflight",
                    "upstream_reported_count",
                    "estimate_exceeded_count",
                    "incomplete_journal_lines",
                )
                if key in physical
            }
        )
        public_physical["pricing_file_sha256"] = [
            _hash(value) for value in physical.get("pricing_file_sha256", [])
        ]
        if physical.get("usd_cap") is not None:
            raise ValueError("Integrated experiment has no USD cap")
        public_physical["usd_cap"] = None
        public_physical["record_sha256"] = _digest(physical)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "regime": _enum(artifact.get("regime"), {"LOW", "MID", "HIGH"}, default="pending"),
        "method_state_sha256": _hash(artifact.get("method_state_sha256")),
        "history_unchanged_during_k16": (
            None
            if artifact.get("history_unchanged_during_k16") is None
            else artifact["history_unchanged_during_k16"] is True
        ),
        "outcome": _enum(outcome.get("outcome"), _OUTCOMES, default="pending"),
        "reason_category": _enum(
            outcome.get("reason"),
            _REASONS,
            default=("none" if not outcome.get("reason") else "other"),
        ),
        "reason_sha256": _identity(outcome.get("reason")),
        "measurement_evidence": {
            "n": _count(estimate.get("n", 0)),
            "p_hat": _nullable_number(estimate.get("p_hat")),
            "successes": (
                None
                if not artifact["measurement_evidence"]["measurement"]
                else _count(artifact["measurement_evidence"]["measurement"]["successes"])
            ),
            "stop": _enum(estimate.get("stop"), {"confidence", "k_max"}, default="pending"),
            "probabilities": {
                name: _number(estimate.get("probabilities", {}).get(old, 0))
                for old, name in _REGIMES.items()
            },
            "record_sha256": _digest(artifact["measurement_evidence"]),
        },
        "designer_calls": {
            "count": len(designers),
            "records": [
                {
                    "optimizer_call_index": _count(record.get("optimizer_call_index", 0)),
                    "evidence_sha256": _hash(record.get("evidence_sha256")),
                    "record_sha256": _digest(record),
                }
                for record in designers
            ],
        },
        "candidate_lineage": lineage,
        "privilege_decisions": decisions,
        "privileged_references": [
            {
                "n_steps": _count(record.get("n_steps", 0)),
                "actions_sha256": _digest(record.get("actions", [])),
                "provenance_id_sha256": _identity(record.get("reference_id")),
                "record_sha256": _digest(record),
            }
            for record in artifact["privileged_references"]
        ],
        "solvability": solvability,
        "endpoint": endpoints,
        "control_trace": [
            {
                "family_id_sha256": _identity(record.get("family")),
                "status": _enum(record.get("status"), {"accepted", "exhausted", "budget"}),
                "history": [_endpoint(item) for item in record.get("history", [])],
                "record_sha256": _digest(record),
            }
            for record in artifact["control_trace"]
        ],
        "freeze": [
            {
                "family_id_sha256": _identity(record.get("family")),
                "source_sha256": _hash(record.get("source_sha256")),
                "direction": _enum(record.get("direction"), {"easier_with_d", "harder_with_d"}),
                "record_sha256": _digest(record),
            }
            for record in artifact["freeze"]
        ],
        "final_environment": None
        if final is None
        else {
            "environment_sha256": _digest(final),
            "kind": _enum(final_meta.get("kind"), {"kept", "knob", "stage"}),
            "d": _nullable_number(final_meta.get("d")),
        },
        "rollout_accounting": {
            "search_charged": None
            if rollout["search_charged"] is None
            else _count(rollout["search_charged"]),
            "baseline_rollouts": (
                None
                if rollout["baseline_rollouts"] is None
                else _count(rollout["baseline_rollouts"])
            ),
            "adaptation_rollouts": (
                None
                if rollout["adaptation_rollouts"] is None
                else _count(rollout["adaptation_rollouts"])
            ),
            "ledger_rollouts": _count(rollout["ledger_rollouts"]),
            "recorded_method_traces": _count(rollout["recorded_method_traces"]),
            "by_phase": {phase: _count(rollout["by_phase"].get(phase, 0)) for phase in phases},
        },
        "usd_accounting": {
            "logical_calls": _count(usd["logical_calls"]),
            "logical_usd": _number(usd["logical_usd"]),
            "calls_by_phase": {
                phase: _count(usd["calls_by_phase"].get(phase, 0)) for phase in phases
            },
            "usd_by_phase": {phase: _number(usd["usd_by_phase"].get(phase, 0)) for phase in phases},
            "physical": public_physical,
        },
        "k16": {
            "status": _enum(
                confirmation.get("status"), {"completed", "not_applicable", "pending", "error"}
            ),
            "successes": _count(confirmation.get("successes", 0)),
            "n": _count(confirmation.get("n", 0)),
            "learnable": confirmation.get("learnable") is True,
            "target": confirmation.get("target") is True,
            "reused": confirmation.get("reused") is True,
            "evidence_sha256": _hash(confirmation.get("evidence_sha256")),
            "record_sha256": _digest(confirmation),
        },
        "private_artifact_sha256": _digest(artifact),
    }
