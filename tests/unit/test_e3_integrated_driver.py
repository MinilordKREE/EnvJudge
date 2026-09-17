"""Offline E3 launch/confirmation/audit integration with synthetic episodes only."""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Action, Candidate, Trace
from scripts import e3_integrated as driver
from scripts import make_tables_e3_integrated as tables

from aea.controller import TaskRef
from aea.core.io import append_jsonl, atomic_write_json, read_json
from aea.errors import ConfigError, InfraError
from aea.estimate import regime_probabilities
from aea.integrated_artifacts import build_task_artifact, method_state_sha256, public_task_metadata
from aea.io import AeaMeta, entry_from_candidate, write_corpus_entry
from aea.llm.physical_audit import physical_summary
from aea.llm.types import Attribution

SOURCE = "class _Rules(Rules):\n    DOSE = __DOSE__\n    TASK = __TASK_ID__\n"
SOURCE_SHA = hashlib.sha256(SOURCE.encode()).hexdigest()


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "private"
    base.mkdir()
    frozen = tmp_path / "frozen.json"
    atomic_write_json(frozen, {"synthetic": True})
    monkeypatch.setattr(driver, "BASE", base)
    monkeypatch.setattr(driver, "FROZEN", frozen)
    monkeypatch.setattr(driver, "STOP", threading.Event())
    monkeypatch.setattr(driver, "emit", lambda **kwargs: None)
    monkeypatch.setattr(driver, "ensure_frozen", lambda **kwargs: {})

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Offline fixture attempted API or environment construction")

    monkeypatch.setattr(driver, "build", forbidden)
    monkeypatch.setattr(driver, "OpenAICompatibleClient", forbidden)
    return base


def _trace(task: int, index: int, phase: str, candidate: Candidate, success: bool) -> Trace:
    return Trace(
        episode_id=f"synthetic-{task}-{phase}-{index}",
        iteration_id=f"{phase}-{task}-{index}",
        task_id="alfworld-corpus-ours-release",
        rollout_seed=task,
        candidate=candidate,
        success=success,
    )


def _entry(
    directory: Path, task: int, candidate: Candidate, *, kept: bool = False, dose: float = 0.5
) -> None:
    write_corpus_entry(
        directory / "corpus.jsonl",
        entry_from_candidate(
            "synthetic/game.json",
            candidate,
            AeaMeta(
                kind="kept" if kept else "knob",
                task_id=str(task),
                seed=task,
                d=None if kept else dose,
                regime="band" if kept else "saturated",
                family=None if kept else "synthetic",
            ),
        ),
    )


def _high_admission(directory: Path) -> None:
    append_jsonl(
        directory / "events.jsonl",
        {
            "kind": "family_frozen",
            "payload": {
                "task_id": "7",
                "family": "synthetic",
                "source_sha256": SOURCE_SHA,
                "direction": "harder_with_d",
            },
        },
    )
    append_jsonl(
        directory / "designer_calls.jsonl",
        {
            "task_id": "7",
            "accepted_sources": [{"name": "synthetic", "source_sha256": SOURCE_SHA}],
            "arguments": {"families": [{"name": "synthetic", "rules_code": SOURCE}]},
        },
    )


class SyntheticSubstrate:
    def __init__(self, directory: Path, *, mutate: bool = False, duplicate: bool = False) -> None:
        self.run_dir = directory
        self.run_id = "synthetic"
        self.calls: list[tuple[int, str, str]] = []
        self.mutate = mutate
        self.duplicate = duplicate

    def rollouts(
        self, task: TaskRef, candidate: Candidate, n: int, *, attribution: Attribution
    ) -> list[Trace]:
        self.calls.append((n, attribution.phase, driver.candidate_sha(candidate)))
        offset = 4 * (len(self.calls) - 1)
        traces = [
            _trace(int(task.task_id), offset + i, "confirm", candidate, offset + i < 5)
            for i in range(n)
        ]
        if self.duplicate and len(self.calls) == 1:
            traces[0].episode_id = "existing-search-episode"
        if self.mutate and len(self.calls) == 1:
            append_jsonl(self.run_dir / "designer_calls.jsonl", {"task_id": task.task_id})
        return traces


@pytest.mark.parametrize("kept", [True, False])
def test_fresh_k16_runs_for_original_mid_and_accepted_high(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, kept: bool
) -> None:
    candidate = (
        Candidate()
        if kept
        else Candidate(rules_code=SOURCE.replace("__DOSE__", "0.5").replace("__TASK_ID__", "'7'"))
    )
    _entry(isolated, 7, candidate, kept=kept)
    if not kept:
        _high_admission(isolated)
    append_jsonl(isolated / "traces.jsonl", {"episode_id": "existing-search-episode"})
    sub = SyntheticSubstrate(isolated)
    before = method_state_sha256(isolated)

    def forbidden(*args: Any) -> None:
        raise AssertionError("MID/HIGH unexpectedly consulted LOW privilege reference")

    monkeypatch.setattr(driver, "verify_low_final", forbidden)
    result = driver.confirm(
        sub,
        7,
        {"outcome": "kept" if kept else "accepted", "regime": "band" if kept else "saturated"},
    )
    assert result["n"] == 16 and result["successes"] == 5
    assert result["reused"] is False and result["learnable"] and not result["target"]
    assert [call[0] for call in sub.calls] == [4, 4, 4, 4]
    assert all(call[2] == driver.candidate_sha(candidate) for call in sub.calls)
    assert len(driver.rows(isolated / "confirmation_traces.jsonl")) == 16
    assert before == method_state_sha256(isolated)


def test_dropped_task_never_constructs_or_probes_final_environment(isolated: Path) -> None:
    sub = SyntheticSubstrate(isolated)
    result = driver.confirm(sub, 2, {"outcome": "dropped", "regime": "zero"})
    assert result["status"] == "not_applicable" and result["n"] == 0
    assert sub.calls == []
    assert not (isolated / "confirmation_started.json").exists()


def test_mid_cannot_release_an_intervention_as_original(isolated: Path) -> None:
    _entry(isolated, 7, Candidate(rules_code="synthetic hidden intervention"), kept=True)
    sub = SyntheticSubstrate(isolated)
    with pytest.raises(ConfigError, match="original environment"):
        driver.confirm(sub, 7, {"outcome": "kept", "regime": "band"})
    assert sub.calls == []


@pytest.mark.parametrize("fault", ["mutate", "duplicate"])
def test_k16_rejects_history_mutation_and_reused_search_episode(isolated: Path, fault: str) -> None:
    _entry(isolated, 7, Candidate(), kept=True)
    append_jsonl(isolated / "traces.jsonl", {"episode_id": "existing-search-episode"})
    sub = SyntheticSubstrate(isolated, **{fault: True})
    expected = "modified frozen" if fault == "mutate" else "fresh and distinct"
    with pytest.raises(ConfigError, match=expected):
        driver.confirm(sub, 7, {"outcome": "kept", "regime": "band"})


def test_partial_task_restart_refused_before_any_new_call(isolated: Path) -> None:
    directory = isolated / "task-7"
    atomic_write_json(directory / "started.json", {"synthetic": True})
    with pytest.raises(ConfigError, match="already started"):
        driver.run_task(7)
    assert not (directory / "confirmation_started.json").exists()


@pytest.mark.parametrize("fault", [None, "FAIL", "dose", "source", "rendered", "setup"])
def test_low_confirmation_enforces_exact_admission(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    """Witness semantics are tested elsewhere; this checks the driver's admission binding."""
    input_path = isolated / "synthetic.input.json.gz"
    input_path.write_bytes(gzip.compress(b"{}"))
    record = SimpleNamespace(
        verdict="FAIL" if fault == "FAIL" else "PASS",
        source_sha256="0" * 64 if fault == "source" else SOURCE_SHA,
    )
    evidence = SimpleNamespace(candidate_artifact=SOURCE, task_spec={"task_id": "7"})
    monkeypatch.setattr(driver, "JudgeRecord", SimpleNamespace(model_validate=lambda value: record))
    monkeypatch.setattr(
        driver,
        "PrivilegeJudgeInput",
        SimpleNamespace(
            model_validate_json=lambda value: evidence,
        ),
    )
    checks = []
    monkeypatch.setattr(driver, "validate_witness_record", lambda *args: checks.append(args))
    append_jsonl(
        isolated / "llm_privilege.jsonl",
        {
            "result": {},
            "input_artifact": str(input_path),
            "doses": [1.0] if fault == "dose" else [0.5],
        },
    )
    rendered = SOURCE.replace("__DOSE__", "0.5").replace("__TASK_ID__", "'7'")
    candidate = Candidate(
        rules_code="synthetic different source" if fault == "rendered" else rendered,
        in_env_actions=[Action(name="do", kwargs={"text": "synthetic setup"})]
        if fault == "setup"
        else [],
    )
    if fault is None:
        driver.verify_low_final(isolated, candidate, 0.5)
    else:
        with pytest.raises(ConfigError):
            driver.verify_low_final(isolated, candidate, 0.5)
    assert len(checks) == 1


@pytest.mark.parametrize("field", ["inflight", "invalid_usage", "incomplete_journal_lines"])
def test_physical_close_rejects_unresolved_attempts(field: str) -> None:
    summary = physical_summary(Path("/tmp/nonexistent-synthetic-physical-journal"))
    summary[field] = 1
    with pytest.raises((ConfigError, InfraError)):
        driver.physical_closed(summary)


def test_physical_close_allows_retained_ambiguous_failure() -> None:
    summary = physical_summary(Path("/tmp/nonexistent-synthetic-physical-journal"))
    summary.update(
        ambiguous_failures=1, retained_ambiguous_estimate_usd=0.2, conservative_total_usd=0.2
    )
    driver.physical_closed(summary)


def test_rate_charges_unsuccessful_tasks_and_counts_each_environment() -> None:
    result = tables.rate(
        [
            {"task": "0", "learnable": True},
            {"task": "0", "learnable": True},
            {"task": "1", "learnable": False},
            {"task": "outside", "learnable": True},
        ],
        {"0": 10, "1": 20, "2": 30},
        ["0", "1", "2"],
        random.Random(3),
    )
    assert result["envs"] == 3 and result["learnable"] == 2
    assert result["rollouts"] == 60 and result["per_1000"] == 2000 / 60


def _synthetic_complete_task(directory: Path, task: int) -> int:
    """Generate exact raw/logical records consumed by the real all-task offline auditor."""
    regime = "saturated" if task in (1, 3) else "zero" if task == 2 else "band"
    outcome = "accepted" if task == 1 else "dropped" if task in (2, 3) else "kept"
    baseline = 10 if regime != "band" else 6
    successes = 10 if regime == "saturated" else 0 if regime == "zero" else 3
    probs = regime_probabilities(successes, baseline - successes, (0.2, 0.8))
    adaptation = 8 if task == 1 else 4 if task == 3 else 0
    candidate = (
        Candidate(
            rules_code=SOURCE.replace("__DOSE__", "1.0").replace("__TASK_ID__", repr(str(task)))
        )
        if task in (1, 3)
        else Candidate()
    )
    traces = [_trace(task, i, "estimate", Candidate(), i < successes) for i in range(baseline)]
    if adaptation:
        traces += [
            _trace(task, i, "dose:synthetic", candidate, i < (3 if task == 1 else 4))
            for i in range(adaptation)
        ]

    def event(kind: str, **payload: Any) -> None:
        append_jsonl(
            directory / "events.jsonl",
            {
                "kind": kind,
                "payload": {"task_id": str(task), **payload},
            },
        )

    event("task_start", seed=task)
    event(
        "estimate",
        regime=regime,
        p_hat=successes / baseline,
        n=baseline,
        probabilities=probs,
        stop="confidence",
    )
    event(
        "measurement_evidence",
        regime=regime,
        p_hat=successes / baseline,
        n=baseline,
        successes=successes,
        probabilities=probs,
        stop_reason="confidence",
        errors_retried=0,
        baseline_rollouts=baseline,
        adaptation_cap=30,
        episode_ids=[trace.episode_id for trace in traces[:baseline]],
    )
    if regime == "saturated":
        append_jsonl(
            directory / "designer_calls.jsonl",
            {
                "task_id": str(task),
                "evidence_sha256": SOURCE_SHA,
                "accepted_sources": [{"name": "synthetic", "source_sha256": SOURCE_SHA}],
                "accepted": ["synthetic"],
                "arguments": {
                    "families": [
                        {
                            "name": "synthetic",
                            "rules_code": SOURCE,
                            "axis": "O",
                            "mechanism_summary": "synthetic mechanism",
                        }
                    ]
                },
            },
        )
        event("solvable", family="synthetic", d=1.0, ok=True, source="policy_replay")
        event(
            "endpoint",
            family="synthetic",
            source_sha256=SOURCE_SHA,
            d=1.0,
            s=3 if task == 1 else 4,
            n=adaptation,
            verdict="in_band" if task == 1 else "too_easy",
        )
    if task == 1:
        event(
            "family_frozen", family="synthetic", source_sha256=SOURCE_SHA, direction="harder_with_d"
        )
    event(
        "task_done",
        regime=regime,
        outcome=outcome,
        reason=""
        if outcome != "dropped"
        else "reference_unavailable"
        if task == 2
        else "no_leverage",
        n_search=baseline + adaptation,
        baseline_rollouts=baseline,
        adaptation_rollouts=adaptation,
        p_hat=successes / baseline,
    )
    if outcome != "dropped":
        _entry(directory, task, candidate, kept=outcome == "kept", dose=1.0)
    for trace in traces:
        append_jsonl(directory / "traces.jsonl", trace.model_dump(mode="json"))
    before = method_state_sha256(directory)
    confirmation = driver.confirm(
        SyntheticSubstrate(directory), task, {"outcome": outcome, "regime": regime}
    )
    atomic_write_json(directory / "confirmation.json", confirmation)
    eval_traces = [
        Trace.model_validate(row) for row in driver.rows(directory / "confirmation_traces.jsonl")
    ]
    for phase, budget, group in (
        ("estimate", "search", traces[:baseline]),
        ("dose:synthetic", "search", traces[baseline:]),
        ("confirm_0", "eval", eval_traces),
    ):
        if not group:
            continue
        append_jsonl(
            directory / "physical_batches.jsonl",
            {
                "task_id": str(task),
                "phase": phase,
                "budget": budget,
                "n": len(group),
                "candidate_sha256": driver.candidate_sha(group[0].candidate),
            },
        )
        for trace in group:
            append_jsonl(
                directory / "all_physical_traces.jsonl",
                {
                    "phase": phase,
                    "budget": budget,
                    "trace": trace.model_dump(mode="json"),
                    "candidate_sha256": driver.candidate_sha(trace.candidate),
                },
            )
            append_jsonl(
                directory / "ledger.jsonl",
                {
                    "event": "rollout",
                    "task_id": str(task),
                    "phase": phase,
                    "budget": budget,
                    "rollout_uid": trace.episode_id,
                    "usd": 0,
                },
            )
    artifact = build_task_artifact(
        directory,
        str(task),
        k16=confirmation,
        physical_accounting=physical_summary(directory / "physical"),
        frozen_method_sha256=before,
    )
    atomic_write_json(directory / "task_artifact.json", artifact)
    atomic_write_json(directory / "task_metadata.json", public_task_metadata(artifact))
    return baseline + adaptation


def test_complete_thirty_task_synthetic_audit_and_performance_report(
    isolated: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tables, "RESULTS", tmp_path / "public/results")
    monkeypatch.setattr(tables, "REPORT", tmp_path / "public/report.md")
    atomic_write_json(isolated / "execution_status.json", {"complete": True, "failures": []})
    atomic_write_json(isolated / "manifest.json", {"git_sha": "a" * 40})
    charged = sum(_synthetic_complete_task(isolated / f"task-{task}", task) for task in range(30))
    report = tables.report()
    assert report["execution_audit"]["status"] == "PASS"
    assert report["execution_audit"]["tasks"] == 30
    assert report["primary"]["envs"] == 28
    assert report["primary"]["learnable"] == 28
    assert report["primary"]["rollouts"] == charged == 204
    assert report["primary"]["per_1000"] == 28000 / charged
    assert report["transformed_only"]["envs"] == 1
    assert report["budget_matched_to_original_e3"] is False
    assert report["execution_audit"]["accounting"]["confirmation_rollouts"] == 448
    assert report["execution_audit"]["accounting"]["physical_policy_episodes"] == 652
    assert len(read_json(tables.RESULTS / "task_metadata.json")) == 30
    assert "synthetic harder family" not in (tables.RESULTS / "report.json").read_text()


@pytest.mark.parametrize(
    "fault, label",
    [
        ("endpoint_count", "fixed search acceptance"),
        ("missing_endpoint", "endpoint evidence"),
        ("dose_source", "CONTROL source hash unchanged"),
    ],
)
def test_report_audit_rejects_invalid_endpoint_and_control_source(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, fault: str, label: str
) -> None:
    monkeypatch.setattr(driver, "TASKS", (1,))
    atomic_write_json(isolated / "execution_status.json", {"complete": True, "failures": []})
    directory = isolated / "task-1"
    _synthetic_complete_task(directory, 1)
    events = driver.rows(directory / "events.jsonl")
    if fault == "endpoint_count":
        next(row for row in events if row["kind"] == "endpoint")["payload"]["s"] = 2
    elif fault == "missing_endpoint":
        events = [row for row in events if row["kind"] != "endpoint"]
    else:
        events.append(
            {
                "kind": "dose_evaluation",
                "payload": {
                    "task_id": "1",
                    "family": "synthetic",
                    "source_sha256": "0" * 64,
                    "d": 0.5,
                    "s": 4,
                    "n": 8,
                    "verdict": "in_band",
                },
            }
        )
    (directory / "events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in events))
    current = method_state_sha256(directory)
    confirmation = read_json(directory / "confirmation.json")
    binding = read_json(directory / "confirmation_started.json")
    binding["method_state_sha256"] = current
    atomic_write_json(directory / "confirmation_started.json", binding)
    artifact = build_task_artifact(
        directory,
        "1",
        k16=confirmation,
        physical_accounting=physical_summary(directory / "physical"),
        frozen_method_sha256=current,
    )
    atomic_write_json(directory / "task_artifact.json", artifact)
    atomic_write_json(directory / "task_metadata.json", public_task_metadata(artifact))
    with pytest.raises(ConfigError, match=label):
        tables.audit()


@pytest.mark.parametrize(
    "fault", ["seed", "candidate", "duplicate", "provider_mismatch", "pricing_mismatch"]
)
def test_returned_trace_binding_stops_invalid_batches(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    monkeypatch.setattr(driver, "SEEN_EPISODES", set())
    candidate = Candidate()
    traces = [_trace(7, index, "binding", candidate, False) for index in range(2)]
    if fault == "seed":
        traces[0].rollout_seed = 8
    elif fault == "candidate":
        traces[0].candidate = Candidate(rules_code="synthetic undispatched source")
    elif fault == "duplicate":
        traces[0].episode_id = traces[1].episode_id
    else:
        traces[0].error = fault
    with pytest.raises(ConfigError):
        driver.validate_returned_traces(traces, 2, 7, candidate)


def test_returned_trace_binding_preserves_baseline_infra_retry_and_detects_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(driver, "SEEN_EPISODES", set())
    candidate = Candidate()
    trace = _trace(7, 0, "binding", candidate, False)
    trace.error = "synthetic environment subprocess error"
    trace.rollout_seed = None
    driver.validate_returned_traces([trace], 1, 7, candidate)
    with pytest.raises(ConfigError, match="reused across"):
        driver.validate_returned_traces([trace], 1, 7, candidate)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing_freeze",
        "direction",
        "frozen_hash",
        "admitted_hash",
        "template",
        "task",
        "dose",
        "setup",
        "second_designer",
        "third_proposal",
    ],
)
def test_high_final_requires_exact_admitted_frozen_source(
    isolated: Path, fault: str | None
) -> None:
    _high_admission(isolated)
    events = driver.rows(isolated / "events.jsonl")
    calls = driver.rows(isolated / "designer_calls.jsonl")
    if fault == "missing_freeze":
        events = []
    elif fault == "direction":
        events[0]["payload"]["direction"] = "easier_with_d"
    elif fault == "frozen_hash":
        events[0]["payload"]["source_sha256"] = "0" * 64
    elif fault == "admitted_hash":
        calls[0]["accepted_sources"][0]["source_sha256"] = "0" * 64
    elif fault == "template":
        calls[0]["arguments"]["families"][0]["rules_code"] += "# changed template"
    elif fault == "second_designer":
        calls.append(calls[0])
    elif fault == "third_proposal":
        calls[0]["arguments"]["families"] = [
            {"rules_code": SOURCE + "# different first"},
            {"rules_code": SOURCE + "# different second"},
            {"rules_code": SOURCE},
        ]
    for name, rows in (("events.jsonl", events), ("designer_calls.jsonl", calls)):
        (isolated / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    candidate = Candidate(
        rules_code=SOURCE.replace("__DOSE__", "0.5").replace("__TASK_ID__", "'7'"),
        in_env_actions=[Action(name="do", kwargs={"text": "synthetic setup"})]
        if fault == "setup"
        else [],
    )
    args = (isolated, 8 if fault == "task" else 7, candidate, 1.0 if fault == "dose" else 0.5)
    if fault is None:
        driver.verify_high_final(*args)
    else:
        with pytest.raises(ConfigError):
            driver.verify_high_final(*args)
