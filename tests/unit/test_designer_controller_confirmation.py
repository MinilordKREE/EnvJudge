"""Fresh K16 is isolated from v3 search, with no API or real learner execution."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

from aea.controller import Controller, TaskRef
from aea.designer_controller_confirmation import confirm, method_state_sha256
from aea.errors import ConfigError, InfraError
from aea.intervention import canonical_hash
from aea.llm.types import Attribution
from tests.unit.test_designer_controller_session import Regime, TableSubstrate, proposal, run
from tests.unit.test_llm_v1 import _trace


def install_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    host: Controller,
    substrate: TableSubstrate,
    mutate: Callable[[list[Trace], int], None] | None = None,
) -> list[Attribution]:
    calls: list[Attribution] = []

    def rollouts(
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        assert attribution.phase == "v3_k16" and attribution.budget == "eval"
        assert n == 4
        index = len(calls)
        calls.append(attribution)
        traces = [
            _trace(i % 2 == 0, candidate=candidate).model_copy(
                update={
                    "episode_id": f"fresh-k16-{index}-{i}",
                    "iteration_id": "v3_k16",
                    "task_id": task.task_id,
                    "rollout_seed": task.seed,
                }
            )
            for i in range(n)
        ]
        if mutate is not None:
            mutate(traces, index)
        return traces

    monkeypatch.setattr(substrate, "rollouts", rollouts)
    return calls


def confirmed_directory(host: Controller) -> Path:
    return host.run_dir / "v3_confirmation" / canonical_hash("3")[:16]


@pytest.mark.parametrize("regime", ["LOW", "HIGH", "MID"])
def test_fresh_k16_preserves_method_state_and_never_returns_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    regime: Regime,
) -> None:
    outcome, host, substrate, designer, judge = run(
        tmp_path,
        regime,
        [] if regime == "MID" else [proposal(regime, "A")],
        {} if regime == "MID" else {("A", 1): [True, False]},
    )
    assert outcome.outcome in ("accepted", "kept")
    before = method_state_sha256(tmp_path)
    design_calls, judge_calls = designer.calls, len(judge.sources)
    baseline = host.baseline_budget.account("3").spent
    adaptation = host.budget.account("3").spent
    calls = install_confirmation(monkeypatch, host, substrate)
    result = confirm(host, TaskRef("3", 3))
    assert len(calls) == 4
    assert result["n"] == 16 and result["successes"] == 8
    assert result["learnable"] and result["target"] and result["reused"] is False
    assert len(set(result["episode_ids"])) == 16
    search_ids = {
        json.loads(line)["episode_id"]
        for line in (tmp_path / "traces.jsonl").read_text().splitlines()
    }
    assert not search_ids.intersection(result["episode_ids"])
    assert result["method_state_sha256"] == before == method_state_sha256(tmp_path)
    assert designer.calls == design_calls and len(judge.sources) == judge_calls
    assert host.baseline_budget.account("3").spent == baseline
    assert host.budget.account("3").spent == adaptation
    assert (confirmed_directory(host) / "result.json").exists()
    with pytest.raises(ConfigError, match="already started"):
        confirm(host, TaskRef("3", 3))
    assert len(calls) == 4


@pytest.mark.parametrize(
    "mode", ["within_batch", "across_batches", "search_reuse", "wrong_seed", "wrong_candidate"]
)
def test_invalid_fresh_trace_binding_stops_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]}
    )
    search_id = json.loads((tmp_path / "traces.jsonl").read_text().splitlines()[0])["episode_id"]

    def mutate(traces: list[Trace], batch: int) -> None:
        if mode == "within_batch":
            traces[1] = traces[1].model_copy(update={"episode_id": traces[0].episode_id})
        elif mode == "across_batches" and batch == 1:
            traces[0] = traces[0].model_copy(update={"episode_id": "fresh-k16-0-0"})
        elif mode == "search_reuse":
            traces[0] = traces[0].model_copy(update={"episode_id": search_id})
        elif mode == "wrong_seed":
            traces[0] = traces[0].model_copy(update={"rollout_seed": 99})
        elif mode == "wrong_candidate":
            traces[0] = traces[0].model_copy(update={"candidate": Candidate()})

    calls = install_confirmation(monkeypatch, host, substrate, mutate)
    with pytest.raises(ConfigError):
        confirm(host, TaskRef("3", 3))
    assert len(calls) == (2 if mode == "across_batches" else 1)
    assert not (confirmed_directory(host) / "result.json").exists()
    with pytest.raises(ConfigError, match="already started"):
        confirm(host, TaskRef("3", 3))


def test_method_mutation_during_k16_is_detected_after_first_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]}
    )

    def mutate(traces: list[Trace], batch: int) -> None:
        journal = host.design_sessions["3"].journal
        journal.write_text(
            journal.read_text() + json.dumps({"event": "synthetic_illegal_feedback"}) + "\n"
        )

    calls = install_confirmation(monkeypatch, host, substrate, mutate)
    with pytest.raises(ConfigError, match="changed the frozen method state"):
        confirm(host, TaskRef("3", 3))
    assert len(calls) == 1 and not (confirmed_directory(host) / "result.json").exists()


@pytest.mark.parametrize("target", ["final_bundle", "corpus", "captured_probes"])
def test_tampered_frozen_environment_is_rejected_before_any_k16_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path, "LOW", [proposal("LOW", "A")], {("A", 1): [True, False]}
    )
    directory = host.design_sessions["3"].directory
    if target == "final_bundle":
        path = directory / "final.json"
        value = json.loads(path.read_text())
        value["family"]["source"] += "\n# modified synthetic source\n"
    elif target == "corpus":
        path = host.corpus_path
        value = json.loads(path.read_text())
        value["rules_code"] += "\n# modified synthetic source\n"
    else:
        path = directory / "D1.probes.json"
        value = json.loads(path.read_text())
        positive = next(probe for probe in value if probe["dose"] > 0)
        positive["transformed"]["final_prompt"] += " modified synthetic surface"
    path.write_text(json.dumps(value) + "\n")
    calls = install_confirmation(monkeypatch, host, substrate)
    with pytest.raises(ConfigError):
        confirm(host, TaskRef("3", 3))
    assert not calls


def test_errored_confirmation_is_not_retried_or_fed_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, host, substrate, designer, judge = run(
        tmp_path, "LOW", [proposal("LOW", "A")], {("A", 1): [True, False]}
    )

    def mutate(traces: list[Trace], batch: int) -> None:
        traces[0] = traces[0].model_copy(update={"error": "synthetic provider failure"})

    calls = install_confirmation(monkeypatch, host, substrate, mutate)
    with pytest.raises(InfraError, match="no replacement or feedback"):
        confirm(host, TaskRef("3", 3))
    assert len(calls) == 1 and designer.calls == 1 and len(judge.sources) == 1
    assert not (confirmed_directory(host) / "result.json").exists()
    with pytest.raises(ConfigError, match="already started"):
        confirm(host, TaskRef("3", 3))


def test_dropped_task_cannot_enter_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, host, substrate, _, _ = run(
        tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [False]}, rounds=1
    )
    assert outcome.outcome == "dropped"
    calls = install_confirmation(monkeypatch, host, substrate)
    with pytest.raises(ConfigError, match="terminal accepted/kept"):
        confirm(host, TaskRef("3", 3))
    assert not calls


@pytest.mark.parametrize("regime", ["LOW", "HIGH", "MID"])
@pytest.mark.parametrize(
    "target", ["global_missing", "global_outcome", "private_missing", "private_outcome"]
)
def test_frozen_search_receipts_are_required_before_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, regime: Regime, target: str
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path,
        regime,
        [] if regime == "MID" else [proposal(regime, "A")],
        {} if regime == "MID" else {("A", 1): [True, False]},
    )
    directory = host.run_dir / "designer_controller" / canonical_hash("3")[:16]
    path = (
        host.run_dir / "traces.jsonl"
        if target.startswith("global")
        else directory / "search_traces.jsonl"
    )
    if target.endswith("missing"):
        path.write_text("")
    else:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        trace = rows[0] if target.startswith("global") else rows[0]["trace"]
        trace["success"] = not trace["success"]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    calls = install_confirmation(monkeypatch, host, substrate)
    with pytest.raises(ConfigError):
        confirm(host, TaskRef("3", 3))
    assert not calls
    assert not (confirmed_directory(host) / "started.json").exists()


def test_in_band_summary_must_match_actual_accepted_episode_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1): [True, False]}
    )
    directory = host.design_sessions["3"].directory
    path = directory / "final.json"
    final = json.loads(path.read_text())
    final["search_acceptance"]["probes"][0]["successes"] = 3  # Still inside 3..5/8.
    path.write_text(json.dumps(final))
    journal = directory / "session.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    rows[-1]["final_sha256"] = canonical_hash(final)
    journal.write_text("".join(json.dumps(row) + "\n" for row in rows))
    calls = install_confirmation(monkeypatch, host, substrate)
    with pytest.raises(ConfigError, match="actual learner outcomes"):
        confirm(host, TaskRef("3", 3))
    assert not calls


def test_measurement_summary_must_match_actual_baseline_episodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, host, substrate, _, _ = run(tmp_path, "MID", [], {})
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    measurement = next(row["payload"] for row in rows if row["kind"] == "measurement_evidence")
    measurement["n"] -= 1
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    calls = install_confirmation(monkeypatch, host, substrate)
    with pytest.raises(ConfigError, match="measurement or rollout accounting"):
        confirm(host, TaskRef("3", 3))
    assert not calls


def test_dispatch_cannot_mutate_candidate_then_return_matching_changed_traces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, host, substrate, _, _ = run(
        tmp_path, "LOW", [proposal("LOW", "A")], {("A", 1): [True, False]}
    )
    calls = install_confirmation(monkeypatch, host, substrate)
    original = substrate.rollouts

    def mutate(
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        candidate.rules_code += "\n# mutated during synthetic dispatch\n"
        return original(task, candidate, n, attribution=attribution, reset_options=reset_options)

    monkeypatch.setattr(substrate, "rollouts", mutate)
    with pytest.raises(ConfigError, match="mutated the frozen candidate"):
        confirm(host, TaskRef("3", 3))
    assert len(calls) == 1
    assert not (confirmed_directory(host) / "result.json").exists()
    with pytest.raises(ConfigError, match="already started"):
        confirm(host, TaskRef("3", 3))
    assert len(calls) == 1
