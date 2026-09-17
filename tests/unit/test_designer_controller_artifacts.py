"""Strict v3 artifact projection and reconstruction on synthetic offline sessions."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.io import append_jsonl
from aea.designer_controller_artifacts import build_task_artifact, public_task_metadata
from aea.designer_controller_confirmation import confirm
from aea.errors import ConfigError
from aea.intervention import V3Config
from aea.llm.ledger import LedgerRow
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.unit.test_designer_controller_confirmation import install_confirmation
from tests.unit.test_designer_controller_session import Regime, TableSubstrate, proposal, run


@pytest.mark.parametrize("regime", ["LOW", "HIGH", "MID"])
def test_terminal_artifacts_reconstruct_all_branches_and_fresh_k16(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    regime: Regime,
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path,
        regime,
        [] if regime == "MID" else [proposal(regime, "A")],
        {} if regime == "MID" else {("A", 1): [True, False]},
    )
    before = public_task_metadata(build_task_artifact(tmp_path, "3"))
    assert before["regime"] == regime and before["k16"]["status"] == "pending"
    assert before["usd_accounting"]["status"] == "unavailable"
    assert before["usd_accounting"]["physical"] is None
    assert before["rollout_accounting"]["adaptation"] == (0 if regime == "MID" else 8)
    assert len(before["characterizations"]) == (0 if regime == "MID" else 1)
    if regime != "MID":
        assert before["control_trace"][0]["reason"] == "ACCEPTED"
        assert before["candidate_lineage"][0]["operation"] == "CREATE"
    install_confirmation(monkeypatch, host, substrate)
    confirm(host, TaskRef("3", 3))
    public = public_task_metadata(build_task_artifact(tmp_path, "3"))
    assert public["k16"]["status"] == "completed" and public["k16"]["successes"] == 8
    assert public["rollout_accounting"]["confirmation"] == 16
    assert public["method_state_sha256"] == before["method_state_sha256"]


@pytest.mark.parametrize("custom", ["target", "control", "both"])
def test_mid_artifact_uses_recorded_nondefault_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    custom: str,
) -> None:
    config = AEAConfig(
        method_version="llm_v3_designer_controller",
        accept=(2, 6) if custom in ("target", "both") else (3, 5),
    )
    control = (
        V3Config(max_design_rounds=2, max_control_probes=3, scalar_grid=(0.0, 0.5, 1.0))
        if custom in ("control", "both")
        else V3Config()
    )
    designer = ScriptedDesigner(("must_not_call", {}))
    substrate = TableSubstrate("MID", designer, {})
    host = Controller(
        config, substrate, tmp_path, "synthetic-mid-config", designer_controller_config=control
    )
    outcome = host.run([TaskRef("3", 3)])[0]
    assert outcome.outcome == "kept" and designer.calls == 0 and not host.design_sessions
    before = public_task_metadata(build_task_artifact(tmp_path, "3"))
    assert before["regime"] == "MID" and before["k16"]["status"] == "pending"
    assert not before["candidate_lineage"] and before["rollout_accounting"]["adaptation"] == 0
    install_confirmation(monkeypatch, host, substrate)
    confirm(host, TaskRef("3", 3))
    after = public_task_metadata(build_task_artifact(tmp_path, "3"))
    assert after["k16"]["status"] == "completed" and after["k16"]["n"] == 16


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("method_config", "missing"),
        ("control_config", "missing"),
        ("method_config", None),
        ("control_config", None),
        ("method_config", {"method_version": "not-a-method"}),
        ("control_config", {"max_design_rounds": 0}),
        ("control_config", {"scalar_grid": [0, 0.5, 0.5, 1]}),
    ],
)
def test_mid_artifact_refuses_missing_or_malformed_recorded_config(
    tmp_path: Path,
    field: str,
    bad: Any,
) -> None:
    run(tmp_path, "MID", [], {})
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    start = next(row["payload"] for row in rows if row["kind"] == "task_start")
    if bad == "missing":
        del start[field]
    else:
        start[field] = bad
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ConfigError, match="valid recorded method/control configuration"):
        build_task_artifact(tmp_path, "3")


def test_adapted_session_config_must_match_recorded_task_start(tmp_path: Path) -> None:
    run(tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]})
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    start = next(row["payload"] for row in rows if row["kind"] == "task_start")
    start["control_config"]["max_design_rounds"] = 2
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ConfigError, match="differs from recorded task start"):
        build_task_artifact(tmp_path, "3")


def test_public_projection_rebuilds_every_untrusted_string_and_mapping(tmp_path: Path) -> None:
    run(tmp_path, "LOW", [proposal("LOW", "A")], {("A", 1): [True, False]})
    artifact = build_task_artifact(tmp_path, "3")
    sentinel = "SYNTHETIC_PRIVATE_DO_NOT_PUBLISH"
    poisoned = copy.deepcopy(artifact)
    poisoned["unexpected"] = {sentinel: sentinel}
    poisoned["outcome"]["reason"] = sentinel
    poisoned["measurement_evidence"]["private"] = sentinel
    for row in poisoned["session"]:
        row["private"] = sentinel
        if row["event"] == "family_proposed":
            row["family"].update(
                family_id=sentinel,
                mechanism_summary=sentinel,
                source=sentinel,
                expected_effect=sentinel,
                semantic_mechanism_id=sentinel,
            )
            row["family"]["control"]["settings"][0]["name"] = sentinel
        elif row["event"] == "characterization":
            char = row["characterization"]
            char["family_id"] = sentinel
            char["coverage"]["episode_steps"] = [[sentinel, 0]]
            char["coverage"]["unexpected"] = sentinel
            for level in char["levels"]:
                level["level_id"] = sentinel
                level["coverage"] = {sentinel: sentinel}
        elif row["event"] == "controller_decision":
            row.update(family_id=sentinel, explanation=sentinel)
            row["probes"][0]["episode_ids"] = [sentinel]
        elif row["event"] == "privilege":
            row["record"]["result"]["decision"]["information"] = sentinel
    public = public_task_metadata(poisoned)
    assert sentinel not in json.dumps(public)
    assert public["reason"] == "other"
    assert len(public["candidate_lineage"][0]["source_sha256"]) == 64


def ledger(
    event: str, phase: str, *, budget: str = "search", usd: float = 0.0, task: str = "3"
) -> dict[str, Any]:
    return LedgerRow.model_validate(
        {
            "schema_version": 1,
            "ts": datetime.now(UTC),
            "run_id": "synthetic",
            "event": event,
            "phase": phase,
            "budget": budget,
            "arm": "test",
            "task_id": task,
            "seed": int(task),
            "model": "synthetic",
            "usd": usd,
        }
    ).model_dump(mode="json")


def test_accounting_sums_call_costs_only_with_v3_phase_and_task_separation(tmp_path: Path) -> None:
    run(tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]})
    rows = [
        ledger("call", "estimate", usd=1),
        ledger("call", "v3_control:3:D1:level", usd=2),
        ledger("call", "v3_design_high", budget="designer", usd=3),
        ledger("call", "v3_privilege", budget="none", usd=4),
        ledger("call", "v3_k16", budget="eval", usd=5),
        ledger("rollout", "v3_control:3:D1:level", usd=200),
        ledger("call", "estimate", usd=999, task="4"),
    ]
    for row in rows:
        append_jsonl(tmp_path / "ledger.part.jsonl", row)
        append_jsonl(tmp_path / "ledger.jsonl", row)
    public = public_task_metadata(build_task_artifact(tmp_path, "3"))
    cost = public["usd_accounting"]
    assert cost["logical_usd"] == 15 and cost["logical_calls"] == 5
    assert cost["ledger_rollouts"] == 1
    assert cost["usd_by_phase"] == {
        "measurement": 1,
        "adaptation": 2,
        "designer": 3,
        "judge": 4,
        "confirmation": 5,
        "other": 0,
    }
    assert public["rollout_accounting"]["search"] == 18


def physical_rows(task: str, amount: float) -> list[dict[str, Any]]:
    common = {
        "attempt_id": "synthetic-attempt-" + task,
        "attribution": {"task_id": task},
        "pricing_file_sha256": "1" * 64,
        "attempt_estimate_usd": amount,
    }
    return [
        {**common, "status": "started"},
        {
            **common,
            "status": "returned",
            "upstream_usd": amount,
            "usage_valid": True,
            "upper_rate_usd": amount,
            "conservative_usd": amount,
            "estimate_exceeded": False,
        },
    ]


def test_physical_audit_is_scoped_per_task_and_reuses_existing_cost_definition(
    tmp_path: Path,
) -> None:
    run(tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]})
    for row in [*physical_rows("3", 2.5), *physical_rows("4", 9.5)]:
        append_jsonl(tmp_path / "physical" / "attempts.synthetic.jsonl", row)
    cost = public_task_metadata(build_task_artifact(tmp_path, "3"))["usd_accounting"]["physical"]
    assert cost["attempts"] == cost["returned"] == 1
    assert cost["conservative_total_usd"] == 2.5
    assert cost["inflight"] == 0


def test_unclosed_physical_attempt_prevents_terminal_artifact(tmp_path: Path) -> None:
    run(tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]})
    append_jsonl(tmp_path / "physical" / "attempts.synthetic.jsonl", physical_rows("3", 2.5)[0])
    with pytest.raises(ConfigError, match="physical accounting"):
        build_task_artifact(tmp_path, "3")


def mutate_session(path: Path, change: Any) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    change(rows)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.mark.parametrize(
    "mode", ["duplicate_probe", "after_freeze", "missing_admission", "wrong_count", "wrong_level"]
)
def test_invalid_controller_history_fails_closed(tmp_path: Path, mode: str) -> None:
    _, host, _, _, _ = run(tmp_path, "LOW", [proposal("LOW", "A")], {("A", 1): [True, False]})

    def change(rows: list[dict[str, Any]]) -> None:
        decision = next(row for row in rows if row["event"] == "controller_decision")
        if mode == "duplicate_probe":
            decision["probes"].append(copy.deepcopy(decision["probes"][0]))
        elif mode == "after_freeze":
            rows.append(
                copy.deepcopy(next(row for row in rows if row["event"] == "designer_proposal"))
            )
        elif mode == "missing_admission":
            rows[:] = [row for row in rows if row["event"] != "privilege"]
        elif mode == "wrong_count":
            decision["probes"][0]["successes"] = 0
        else:
            decision["probes"][0]["setting"] = 0.5

    mutate_session(host.design_sessions["3"].journal, change)
    with pytest.raises(ConfigError):
        build_task_artifact(tmp_path, "3")


def test_dropped_task_records_all_provisional_rounds_without_false_final(tmp_path: Path) -> None:
    run(tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [False]}, rounds=1)
    public = public_task_metadata(build_task_artifact(tmp_path, "3"))
    assert public["outcome"] == "dropped" and public["final_environment"] is None
    assert public["k16"]["status"] == "not_applicable"
    assert public["control_trace"][0]["reason"] == "OVERPOWERED_BINARY"
    assert public["control_trace"][0]["operation"] == "REFINE_CONTROL"
    assert not public["freeze"] and public["rollout_accounting"]["adaptation"] == 4


@pytest.mark.parametrize("field", ["task_id", "number", "hash"])
def test_invalid_public_scalar_cannot_smuggle_arbitrary_text(tmp_path: Path, field: str) -> None:
    run(tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]})
    artifact = build_task_artifact(tmp_path, "3")
    if field == "task_id":
        artifact["task_id"] = "PRIVATE_TEXT"
    elif field == "number":
        artifact["rollout_accounting"]["search"] = "PRIVATE_TEXT"
    else:
        artifact["method_state_sha256"] = "PRIVATE_TEXT"
    with pytest.raises(ValueError):
        public_task_metadata(artifact)
