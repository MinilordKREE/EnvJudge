"""Synthetic privacy, accounting and confirmation-boundary integration checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aea.integrated_artifacts import (
    build_task_artifact,
    method_state_sha256,
    public_task_metadata,
)

SECRET = "synthetic private witness location omega"
SHA = hashlib.sha256(SECRET.encode()).hexdigest()


def _write(directory: Path, filename: str, rows: list[dict[str, object]]) -> None:
    (directory / filename).write_text("".join(json.dumps(row) + "\n" for row in rows))


def _event(kind: str, **payload: object) -> dict[str, object]:
    return {"kind": kind, "payload": {"task_id": "42", **payload}}


def _base(directory: Path, regime: str = "band", outcome: str = "kept") -> None:
    _write(
        directory,
        "events.jsonl",
        [
            _event("task_start", seed=42),
            _event(
                "estimate",
                regime=regime,
                p_hat=0.5,
                n=10,
                stop="confidence",
                probabilities={"zero": 0.03, "band": 0.94, "saturated": 0.03},
            ),
            _event("task_done", outcome=outcome, reason="", regime=regime, n_search=10),
        ],
    )
    if outcome in {"kept", "accepted"}:
        _write(
            directory,
            "corpus.jsonl",
            [
                {
                    "game_file": SECRET,
                    "rules_code": "",
                    "in_env_actions": [],
                    "aea": {"task_id": "42", "kind": "kept" if outcome == "kept" else "knob"},
                }
            ],
        )


def test_mid_has_every_stage_and_fresh_k16_without_designer(tmp_path: Path) -> None:
    _base(tmp_path)
    frozen = method_state_sha256(tmp_path)
    private = build_task_artifact(
        tmp_path,
        "42",
        frozen_method_sha256=frozen,
        k16={
            "status": "completed",
            "successes": 5,
            "n": 16,
            "reused": False,
            "evidence_sha256": SHA,
        },
    )
    public = public_task_metadata(private)
    assert public["regime"] == "MID"
    assert public["designer_calls"]["count"] == 0
    for stage in (
        "candidate_lineage",
        "privilege_decisions",
        "solvability",
        "endpoint",
        "control_trace",
        "freeze",
    ):
        assert public[stage] == []
    assert public["k16"]["learnable"] is True
    assert public["k16"]["target"] is False
    assert public["k16"]["reused"] is False
    assert public["history_unchanged_during_k16"] is True
    assert public["final_environment"]["kind"] == "kept"
    assert SECRET not in json.dumps(public)
    assert SECRET in json.dumps(private)


def test_public_projection_removes_raw_source_prompts_names_and_witnesses(tmp_path: Path) -> None:
    _base(tmp_path, "zero", "accepted")
    _write(
        tmp_path,
        "designer_calls.jsonl",
        [
            {
                "task_id": "42",
                "optimizer_call_index": 1,
                "evidence": SECRET,
                "evidence_sha256": SHA,
                "arguments": {"source": SECRET},
                "feedback": SECRET,
            }
        ],
    )
    _write(
        tmp_path,
        "low_candidates.jsonl",
        [
            {
                "candidate_id": "42:C1:" + SECRET,
                "parent_candidate_id": SECRET,
                "optimizer_call_index": 1,
                "requested_operation": "PROPOSE",
                "source": SECRET,
                "source_sha256": SHA,
                "mechanism": SECRET,
                "structural": [],
                "privilege": [],
                "solvability": json.dumps({"ok": True, "source": "oracle", "detail": SECRET}),
                "endpoint": [3, 8, "in_band"],
                "rejection_reason": SECRET,
                "remaining_calls": 2,
                "remaining_policy": 12,
            }
        ],
    )
    _write(
        tmp_path,
        "llm_privilege.jsonl",
        [
            {
                "task_id": "42",
                "family": SECRET,
                "doses": [0.0, 0.5, 1.0],
                "input_artifact": SECRET,
                "raw_probe_artifact": SECRET,
                "result": {
                    "source_sha256": SHA,
                    "input_sha256": SHA,
                    "prompt_sha256": SHA,
                    "schema_sha256": SHA,
                    "config_sha256": SHA,
                    "request_sha256": SHA,
                    "response_sha256": SHA,
                    "request": SECRET,
                    "response": SECRET,
                    "decision": {
                        "verdict": "PASS",
                        "leak_type": "NONE",
                        "information": SECRET,
                        "candidate_evidence": SECRET,
                    },
                },
            }
        ],
    )
    _write(
        tmp_path,
        "privileged_references.jsonl",
        [
            {
                "task_id": "42",
                "actions": [SECRET],
                "n_steps": 1,
                "steps": [SECRET],
            }
        ],
    )
    private = build_task_artifact(
        tmp_path,
        "42",
        physical_accounting={
            "returned_conservative_usd": 1.5,
            "retained_ambiguous_estimate_usd": 0.2,
            "conservative_total_usd": 1.7,
            "raw_requests": SECRET,
        },
    )
    private["unknown_future_field"] = SECRET
    public = public_task_metadata(private)
    assert SECRET not in json.dumps(public)
    assert public["candidate_lineage"][0]["source_sha256"] == SHA
    assert public["solvability"][0]["ok"] is True
    assert public["endpoint"][0]["successes"] == 3
    assert public["privilege_decisions"][0]["verdict"] == "PASS"
    assert public["usd_accounting"]["physical"]["conservative_total_usd"] == 1.7
    assert "unknown_future_field" not in public


def test_merged_ledger_not_counted_twice_and_rollout_cost_not_added(tmp_path: Path) -> None:
    _base(tmp_path)
    rows = [
        {"task_id": "42", "event": "call", "phase": "estimate", "usd": 0.3},
        {"task_id": "42", "event": "call", "phase": "privilege_judge", "usd": 0.2},
        {"task_id": "42", "event": "rollout", "phase": "estimate", "usd": 0.3},
        {"task_id": "999", "event": "call", "phase": "estimate", "usd": 900},
    ]
    _write(tmp_path, "ledger.jsonl", rows)
    _write(tmp_path, "ledger.part.jsonl", rows)
    public = public_task_metadata(build_task_artifact(tmp_path, "42"))
    assert public["usd_accounting"]["logical_usd"] == 0.5
    assert public["usd_accounting"]["logical_calls"] == 2
    assert public["rollout_accounting"]["ledger_rollouts"] == 1
    assert public["usd_accounting"]["usd_by_phase"]["judge"] == 0.2
    with pytest.raises(ValueError, match="Duplicate ledger"):
        build_task_artifact(tmp_path, "42", ledger_paths=[tmp_path / "ledger.jsonl"] * 2)


def test_history_digest_allows_confirmation_but_detects_post_k16_redesign(tmp_path: Path) -> None:
    _base(tmp_path)
    frozen = method_state_sha256(tmp_path)
    _write(tmp_path, "confirm.jsonl", [{"private": SECRET}])
    _write(tmp_path, "ledger.jsonl", [{"task_id": "42", "event": "call", "usd": 0.1}])
    assert method_state_sha256(tmp_path) == frozen
    _write(tmp_path, "designer_calls.jsonl", [{"task_id": "42", "new": SECRET}])
    with pytest.raises(ValueError, match="history changed"):
        build_task_artifact(tmp_path, "42", frozen_method_sha256=frozen)


def test_confirmation_rejects_incomplete_or_inconsistent_results(tmp_path: Path) -> None:
    _base(tmp_path)
    with pytest.raises(ValueError, match="16 episodes"):
        build_task_artifact(
            tmp_path,
            "42",
            k16={
                "status": "completed",
                "n": 8,
                "successes": 4,
                "evidence_sha256": SHA,
            },
        )
    with pytest.raises(ValueError, match="target disagrees"):
        build_task_artifact(
            tmp_path,
            "42",
            k16={
                "status": "completed",
                "n": 16,
                "successes": 5,
                "target": True,
                "evidence_sha256": SHA,
            },
        )
    with pytest.raises(ValueError, match="evidence digest"):
        build_task_artifact(tmp_path, "42", k16={"status": "completed", "n": 16, "successes": 5})


def test_high_lineage_and_terminal_control_are_projected_without_generated_names(
    tmp_path: Path,
) -> None:
    _base(tmp_path, "saturated", "dropped")
    _write(
        tmp_path,
        "designer_calls.jsonl",
        [
            {
                "task_id": "42",
                "evidence_sha256": SHA,
                "arguments": {"families": [{"name": SECRET, "rules_code": SECRET}]},
            }
        ],
    )
    with (tmp_path / "events.jsonl").open("a") as handle:
        for event in [
            _event("endpoint", family=SECRET, source_sha256=SHA, d=1, s=0, n=4, verdict="too_hard"),
            _event(
                "high_family_frozen", family=SECRET, source_sha256=SHA, direction="harder_with_d"
            ),
            _event(
                "bracket",
                family=SECRET,
                status="exhausted",
                history=[
                    {"d": 1, "s": 0, "n": 4, "verdict": "too_hard"},
                    {"d": 0.5, "s": 4, "n": 4, "verdict": "too_easy"},
                ],
            ),
        ]:
            handle.write(json.dumps(event) + "\n")
    public = public_task_metadata(build_task_artifact(tmp_path, "42"))
    assert len(public["candidate_lineage"]) == 1
    assert public["freeze"][0]["direction"] == "harder_with_d"
    assert public["endpoint"][0]["verdict"] == "too_hard"
    assert public["control_trace"][0]["status"] == "exhausted"
    assert public["final_environment"] is None
    assert public["k16"]["status"] == "not_applicable"
    assert SECRET not in json.dumps(public)


def test_second_attempt_and_malformed_public_scalars_are_rejected(tmp_path: Path) -> None:
    _base(tmp_path)
    artifact = build_task_artifact(tmp_path, "42")
    artifact["usd_accounting"]["logical_usd"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        public_task_metadata(artifact)
    with (tmp_path / "events.jsonl").open("a") as handle:
        handle.write(json.dumps(_event("task_start")) + "\n")
    with pytest.raises(ValueError, match="isolated task attempt"):
        build_task_artifact(tmp_path, "42")


def test_released_trace_label_is_scoped_by_task_seed(tmp_path: Path) -> None:
    _base(tmp_path)
    _write(
        tmp_path,
        "traces.jsonl",
        [
            {
                "task_id": "alfworld-corpus",
                "rollout_seed": 42,
                "iteration_id": "estimate-42-0",
                "episode_id": "synthetic-episode-1",
                "steps": [SECRET],
            },
            {
                "task_id": "alfworld-corpus",
                "rollout_seed": 999,
                "iteration_id": "estimate-999-0",
                "episode_id": "synthetic-unrelated",
                "steps": [],
            },
        ],
    )
    artifact = build_task_artifact(tmp_path, "42")
    assert len(artifact["measurement_evidence"]["traces"]) == 1
    assert artifact["rollout_accounting"]["recorded_method_traces"] == 1
    assert artifact["traces"][0]["episode_id"] == "synthetic-episode-1"


def test_high_private_lineage_joins_exact_validated_source_and_runtime_evidence(
    tmp_path: Path,
) -> None:
    _base(tmp_path, "saturated", "accepted")
    families = [
        {"name": "same_name", "rules_code": SECRET, "axis": "invalid", "mechanism_summary": SECRET},
        {"name": "same_name", "rules_code": SECRET, "axis": "O", "mechanism_summary": SECRET},
    ]
    _write(
        tmp_path,
        "designer_calls.jsonl",
        [
            {
                "task_id": "42",
                "evidence_sha256": SHA,
                "arguments": {"families": families},
                "accepted": ["same_name"],
                "accepted_sources": [{"name": "same_name", "source_sha256": SHA}],
                "rejected": ["same_name: axis must be O, T or A"],
            }
        ],
    )
    with (tmp_path / "events.jsonl").open("a") as handle:
        for event in [
            _event("solvable", family="same_name", d=1, ok=True, source="policy_replay"),
            _event(
                "endpoint", family="same_name", source_sha256=SHA, d=1, s=4, n=8, verdict="in_band"
            ),
        ]:
            handle.write(json.dumps(event) + "\n")
    artifact = build_task_artifact(tmp_path, "42")
    first, second = artifact["candidate_lineage"]
    assert first["validation_status"] == "rejected" and first["endpoint"] is None
    assert second["validation_status"] == "accepted" and second["endpoint"] == [4, 8, "in_band"]
    assert first["parent_candidate_id"] is None and second["parent_candidate_id"] is None
    assert first["optimizer_call_index"] == second["optimizer_call_index"] == 1
    assert second["privilege_applicability"] == "not_applicable"
    public = public_task_metadata(artifact)
    assert SECRET not in json.dumps(public) and "same_name" not in json.dumps(public)
    assert public["candidate_lineage"][1]["remaining_policy"] is None
    assert public["candidate_lineage"][1]["solvability"]["ok"] is True
