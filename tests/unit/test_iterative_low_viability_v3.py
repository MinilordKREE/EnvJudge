"""One-task top-up and frozen-core continuation; offline episodes/transports only."""

from __future__ import annotations

import ast
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

from aea.errors import ConfigError, InfraError
from aea.stage import seeded_failures
from tests.unit.test_iterative_low_viability import _cap_update, _returned, _wire
from tests.unit.test_llm_v1 import _trace


@pytest.fixture
def viability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = importlib.import_module("scripts.e6_iterative_low_viability_v3")
    monkeypatch.setattr(module, "RUN", tmp_path / "run")
    monkeypatch.setattr(module, "FROZEN", tmp_path / "frozen")
    monkeypatch.setattr(module, "ensure_frozen", lambda **kwargs: {"offline_test": True})
    module.write_json(
        module.FROZEN / "used_task_audit.json",
        {"never_used_ids": list(range(163, 173)), "smallest_never_used": 163},
    )
    return module


def _json(module: Any, name: str) -> Any:
    return json.loads((module.RUN / name).read_text())


def _screen(
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[dict[str, Any]],
    *,
    callback: Callable[[int, int, Any], None] | None = None,
    other_success: bool = False,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    monkeypatch.setattr(module, "verify_core", lambda: [])
    monkeypatch.setattr(
        module,
        "import_core",
        lambda: {"core_manifest_sha256": "offline-core", "all_episode_ids": []},
    )

    def rollouts(task: Any, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        number = int(task.task_id)
        assert number >= 163 and n == 1
        assert not candidate.rules_code and not candidate.in_env_actions
        counts[number] = counts.get(number, 0) + 1
        execution = counts[number]
        outcome = (
            outcomes[execution - 1]
            if number == 163 and execution <= len(outcomes)
            else {"success": other_success}
        )
        if callback:
            callback(number, execution, kwargs["attribution"])
        trace = _trace(bool(outcome.get("success", False)), candidate=candidate)
        trace.error = outcome.get("error")
        trace.rollout_seed = number
        trace.episode_id = f"topup-{number}-execution-{execution}"
        if outcome.get("retry"):
            module.append_jsonl(
                module.RUN / "ledger.offline.jsonl",
                {
                    "phase": kwargs["attribution"].phase,
                    "event": "infra_retry",
                    "error_kind": "timeout",
                },
            )
        return [trace]

    monkeypatch.setattr(module, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    module.screen()
    return counts


def test_committed_three_task_core_has_exact_original_and_seeded_evidence() -> None:
    module = importlib.import_module("scripts.e6_iterative_low_viability_v3")
    path = (
        module.ROOT
        / "experiments/alfworld_e6/results/iterative_low_viability_v2"
        / "screening_qualified_evidence.json"
    )
    manifest = json.loads(path.read_text())
    expected = {
        154: (
            "0c8c2a77903761785db4820dab64499147099638dde761b156beced5e8c58f27",
            "d4b442dff2c824f6d42a22114448f92ca178ddba2b5d0a5ee7f14c2a2b8e735f",
            [7, 14, 13],
        ),
        158: (
            "20c0b77d08fb88efbe47ba5e96c7450f6c709355ac8ccf6a9cbdd6fe5813907d",
            "46b84d32279a0843d6a64bd73ae49d005f776f8f913fc9f76ab5c5254deb7445",
            [8, 15, 14],
        ),
        159: (
            "fcddeb379d70e01d61b5a028ed8073a48abfbb04a7c1fc5282da01465e920253",
            "55a935664362fa036ea6ab84853661a3437cb8e9571626706bb97c44e9517b0a",
            [13, 3, 11],
        ),
    }
    assert manifest["qualified_task_ids"] == [154, 158, 159]
    for row in manifest["tasks"]:
        task = row["task_id"]
        assert row["evidence_n"] == 16 and row["selection_seed"] == task
        assert len(row["all_original_episode_ids"]) == len(row["all_original_trace_sha256"]) == 16
        assert (
            row["original_zero_evidence_sha256"],
            row["evidence_sha256"],
            row["selected_valid_indices"],
        ) == expected[task]
        traces = []
        for index, episode in enumerate(row["all_original_episode_ids"]):
            trace = _trace(False)
            trace.episode_id = episode
            trace.rollout_seed = task
            traces.append(trace)
            assert len(row["all_original_trace_sha256"][index]) == 64
        selected = seeded_failures(traces, 3, seed=task)
        assert [t.episode_id for t in selected] == row["evidence_ids"]
        assert [
            row["all_original_trace_sha256"][i - 1] for i in row["selected_valid_indices"]
        ] == row["selected_trace_sha256"]


def test_one_new_zero_stops_without_inspecting_another_id(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _screen(viability, monkeypatch, [{"retry": True} for _ in range(16)])
    screen = _json(viability, "screening.json")
    assert screen["status"] == "qualified" and screen["qualified"] == [163]
    assert counts == {163: 16}
    assert screen["tasks"]["163"]["status"] == "CONFIRMED_ZERO"
    assert screen["tasks"]["163"]["valid_episodes"] == 16
    assert len(screen["tasks"]["163"]["recoveries"]) == 16


def test_first_valid_success_rejects_then_exactly_one_zero_ends_topup(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _screen(viability, monkeypatch, [{}] * 5 + [{"success": True, "retry": True}])
    screen = _json(viability, "screening.json")
    assert counts == {163: 6, 164: 16} and screen["qualified"] == [164]
    assert screen["tasks"]["163"]["status"] == "NON_ZERO"
    assert screen["tasks"]["163"]["valid_successes"] == 1
    assert screen["tasks"]["163"]["valid_episodes"] == 6


@pytest.mark.parametrize("valid_failures", [3, 15])
def test_missing_infrastructure_outcomes_never_count_as_completed_zero(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    valid_failures: int,
) -> None:
    counts = _screen(
        viability, monkeypatch, [{}] * valid_failures + [{"error": "timeout", "success": True}] * 3
    )
    screen = _json(viability, "screening.json")
    assert counts == {163: valid_failures + 3, 164: 16}
    row = screen["tasks"]["163"]
    assert row["status"] == "INFRA_INCONCLUSIVE"
    assert row["valid_episodes"] == valid_failures and row["valid_successes"] == 0
    assert all(e["behavioral_success"] is None for e in row["episodes"][-3:])
    assert screen["qualified"] == [164]


def test_ten_new_nonzero_tasks_end_topup_inconclusive(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _screen(viability, monkeypatch, [], other_success=True)
    screen = _json(viability, "screening.json")
    assert screen["status"] == "TOPUP_INCONCLUSIVE" and screen["qualified"] == []
    assert counts == dict.fromkeys(range(163, 173), 1)
    assert 162 not in counts and not ({154, 158, 159} & counts.keys())


def test_four_dollar_topup_stop_is_global_and_reservations_are_not_refunded(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    physical: list[Any] = []
    invoked: list[int] = []

    def callback(task: int, execution: int, attribution: Any) -> None:
        invoked.append(task)
        _cap_update(viability, actual_usd=3.5, uncertain_usd=0.49999)
        transport = viability.CappedTransport(
            lambda **wire: physical.append(wire), viability.RUN / "cap.json"
        )
        with pytest.raises(InfraError, match="screening_cost_cap"):
            transport(**_wire())

    _screen(viability, monkeypatch, [{"error": "smoke_cost_cap: topup denied"}], callback=callback)
    screen = _json(viability, "screening.json")
    assert screen["status"] == "TOPUP_INCONCLUSIVE" and screen["qualified"] == []
    assert invoked == [163] and physical == []
    cap = _json(viability, "cap.json")
    assert cap["uncertain_usd"] == 0.49999 and cap["attempts"] == 0


def _results(
    *, confirmed: int = 0, viable: int = 0, misses: int = 0, referenced: int = 4
) -> dict[str, Any]:
    tasks = {}
    for index in range(4):
        own: dict[str, Any] = {
            "first_viable_family_index": 1 if index < viable else None,
            "search_accepted": index < confirmed + misses,
        }
        if index < confirmed + misses:
            own["confirmation"] = {
                "n": 16,
                "successes": 8 if index < confirmed else 0,
                "in_band_l": index < confirmed,
                "in_band_t": index < confirmed,
            }
        tasks[str(index)] = {
            "original": {"reference_ok": index < referenced},
            "status": "completed" if index < referenced else "reference_unavailable",
            "summary": own,
        }
    return {"tasks": tasks, "interruption": None}


def test_v3_partial_signal_requires_actual_k16_misses_not_unperformed_confirmations(
    viability: Any,
) -> None:
    assert viability.decision_for(_results(viable=2), {})["decision"] == "LOW_NOT_WORKING"
    assert (
        viability.decision_for(_results(viable=2, misses=2), {})["decision"] == "LOW_PARTIAL_SIGNAL"
    )
    assert viability.decision_for(_results(viable=2, misses=1), {})["decision"] == "LOW_NOT_WORKING"
    assert (
        viability.decision_for(_results(confirmed=1, viable=1), {})["decision"]
        == "LOW_PARTIAL_SIGNAL"
    )
    assert viability.decision_for(_results(confirmed=2, viable=2), {})["decision"] == "LOW_VIABLE"
    assert viability.decision_for(_results(referenced=2), {})["decision"] == "INCONCLUSIVE"
    limited = _results(viable=2, misses=2)
    limited["interruption"] = {"kind": "smoke_cost_cap", "reason": "cap"}
    assert viability.decision_for(limited, {})["decision"] == "INCONCLUSIVE"
    enough = _results(confirmed=2, viable=2)
    enough["interruption"] = {"kind": "smoke_cost_cap", "reason": "later cap"}
    assert viability.decision_for(enough, {})["decision"] == "LOW_VIABLE"
    enough["correctness_audit"] = {"decision": "IMPLEMENTATION_FAILURE"}
    assert viability.decision_for(enough, {})["decision"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize(
    "name",
    [
        "config",
        "scoped_three_call_budget",
        "require_pass",
        "make_screen",
        "run_task",
        "assert_fresh_episode_ids",
        "confirm",
        "adapt",
    ],
)
def test_execution_method_remains_exactly_frozen(name: str) -> None:
    previous = importlib.import_module("scripts.e6_iterative_low_viability_v2")
    continuation = importlib.import_module("scripts.e6_iterative_low_viability_v3")

    def source(module: Any) -> str:
        text = Path(module.__file__).read_text()
        node = next(
            n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        return "\n".join(text.splitlines()[start - 1 : node.end_lineno])

    assert source(continuation) == source(previous)


def _core_fixture(module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path / "fixture-repository"
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "PRIOR_RUN", root / "runs/e6-iterative-low-viability-v2")
    monkeypatch.setattr(module, "PRIOR_EVIDENCE", root / "experiments/prior_evidence.json")
    module.write_json(root / "src/aea/semantic_privilege.py", {"offline": True})
    tasks = {}
    evidence = []
    raw_hashes = {}
    for task in (154, 158, 159):
        originals = []
        episodes = []
        artifacts = []
        aliases = []
        for index in range(1, 17):
            trace = _trace(False)
            trace.episode_id = f"core-{task}-{index}"
            trace.rollout_seed = task
            originals.append(trace)
            raw = [trace.model_dump(mode="json")]
            path = module.PRIOR_RUN / f"task-{task}/original-execution-{index:02}.json"
            alias = module.PRIOR_RUN / f"task-{task}/original-{index:02}.json"
            module.write_json(path, raw)
            module.write_json(alias, raw)
            file_hash = module.digest(path.read_text())
            artifacts.append(
                {"path": str(path.relative_to(module.PRIOR_RUN)), "file_sha256": file_hash}
            )
            aliases.append(
                {"path": str(alias.relative_to(module.PRIOR_RUN)), "file_sha256": file_hash}
            )
            raw_hashes[str(path.relative_to(root))] = file_hash
            raw_hashes[str(alias.relative_to(root))] = file_hash
            episodes.append(
                {
                    "execution_index": index,
                    "trace_file": str(path.relative_to(module.PRIOR_RUN)),
                    "file_sha256": file_hash,
                    "trace_sha256": module.digest(raw),
                    "episode_ids": [trace.episode_id],
                    "terminal_errors": 0,
                    "target_valid_index": index,
                    "slot_attempt": 1,
                    "is_valid": True,
                    "behavioral_success": False,
                    "successes": 0,
                }
            )
        tasks[str(task)] = {
            "status": "CONFIRMED_ZERO",
            "valid_episodes": 16,
            "valid_successes": 0,
            "valid_episode_indices": list(range(1, 17)),
            "executions": 16,
            "episodes": episodes,
        }
        selected = seeded_failures(originals, 3, seed=task)
        all_raw = [t.model_dump(mode="json") for t in originals]
        chosen = [t.model_dump(mode="json") for t in selected]
        evidence.append(
            {
                "task_id": task,
                "selection_seed": task,
                "selection_n": 3,
                "evidence_n": 16,
                "all_original_episode_ids": [t.episode_id for t in originals],
                "all_original_trace_sha256": [module.digest(t) for t in all_raw],
                "original_zero_evidence_sha256": module.digest(all_raw),
                "evidence_ids": [t.episode_id for t in selected],
                "selected_trace_sha256": [module.digest(t) for t in chosen],
                "evidence_sha256": module.digest(chosen),
                "selected_valid_indices": [originals.index(t) + 1 for t in selected],
                "all_execution_artifacts": artifacts,
                "valid_original_artifacts": aliases,
            }
        )
    module.write_json(
        module.PRIOR_RUN / "screening.json",
        {"status": "SCREENING_COST_LIMIT", "qualified": [154, 158, 159], "tasks": tasks},
    )
    previous = {
        "qualified_task_ids": [154, 158, 159],
        "tasks": evidence,
        "screening_sha256": module.digest((module.PRIOR_RUN / "screening.json").read_text()),
    }
    module.write_json(module.PRIOR_EVIDENCE, previous)
    committed: str = module.PRIOR_EVIDENCE.read_text()

    def git(*args: str) -> str:
        assert args == ("show", "fixture-prior:" + str(module.PRIOR_EVIDENCE.relative_to(root)))
        return committed.rstrip("\n")

    monkeypatch.setattr(module, "git", git)
    manifest = {
        "prior_commit": "fixture-prior",
        "prior_screening_path": str((module.PRIOR_RUN / "screening.json").relative_to(root)),
        "prior_screening_sha256": previous["screening_sha256"],
        "prior_qualified_evidence_path": str(module.PRIOR_EVIDENCE.relative_to(root)),
        "prior_qualified_evidence_sha256": module.digest(committed),
        "tasks": evidence,
        "raw_file_hashes": raw_hashes,
    }
    module.write_json(module.FROZEN / "core_manifest.json", manifest)
    return manifest


def test_verified_core_import_copies_bytes_and_fixed_selected_order_without_rollouts(
    viability: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _core_fixture(viability, tmp_path, monkeypatch)
    assert viability.verify_core() == manifest
    imported = viability.import_core()
    assert list(imported["tasks"]) == ["154", "158", "159"]
    assert len(imported["all_episode_ids"]) == 48
    for name in manifest["raw_file_hashes"]:
        source = viability.ROOT / name
        target = viability.RUN / source.relative_to(viability.PRIOR_RUN)
        assert target.read_bytes() == source.read_bytes()
    monkeypatch.setattr(
        viability,
        "seeded_failures",
        lambda *args, **kwargs: pytest.fail("core cannot be resampled"),
    )
    for row in manifest["tasks"]:
        task = row["task_id"]
        traces = viability.frozen_valid_traces(task, imported["tasks"][str(task)])
        assert [t.episode_id for t in viability.selected_failures(task, traces)] == row[
            "evidence_ids"
        ]
    with pytest.raises(ConfigError, match="already imported"):
        viability.import_core()


@pytest.mark.parametrize("artifact", ["raw_trace", "selected_indices", "committed_evidence"])
def test_changed_frozen_core_is_rejected_before_import(
    viability: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact: str,
) -> None:
    manifest = _core_fixture(viability, tmp_path, monkeypatch)
    if artifact == "raw_trace":
        (viability.PRIOR_RUN / "task-154/original-01.json").write_text("[]")
    elif artifact == "selected_indices":
        manifest["tasks"][0]["selected_valid_indices"].reverse()
        viability.write_json(viability.FROZEN / "core_manifest.json", manifest)
    else:
        prior = json.loads(viability.PRIOR_EVIDENCE.read_text())
        prior["unexpected_rewrite"] = True
        viability.write_json(viability.PRIOR_EVIDENCE, prior)
    with pytest.raises(ConfigError):
        viability.import_core()
    assert not (viability.RUN / "core_import.json").exists()
    assert not (viability.RUN / "task-154/original-01.json").exists()


def test_consumed_task_162_is_refused_before_any_dispatch(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viability.write_json(
        viability.FROZEN / "used_task_audit.json",
        {"never_used_ids": list(range(162, 172)), "smallest_never_used": 162},
    )
    monkeypatch.setattr(
        viability, "build", lambda **kwargs: pytest.fail("consumed ID cannot dispatch")
    )
    with pytest.raises(ConfigError, match="consumed"):
        viability.screen()
    assert not (viability.RUN / "cap.json").exists()


def test_joint_freeze_preserves_core_and_new_zero_then_generates_references_once(
    viability: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aea.designer import Reference
    from tests.unit.test_iterative_low import REF

    manifest = _core_fixture(viability, tmp_path, monkeypatch)
    calls: list[int] = []
    reference_calls: list[int] = []

    def rollouts(task: Any, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        number = int(task.task_id)
        assert number == 163 and n == 1
        calls.append(number)
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = number
        trace.episode_id = f"new-{number}-{len(calls)}"
        return [trace]

    def provider(task: Any) -> Any:
        number = int(task.task_id)
        reference_calls.append(number)
        return Reference(False, "fixture unavailable") if number == 158 else REF

    sub = SimpleNamespace(
        rollouts=rollouts,
        reference_provider=lambda cfg: provider,
        env_import="offline.fixture",
        reset_options={},
        max_steps=50,
        task_prompt="fixture",
        policy_spec_kwargs={"action_format": "think_action", "max_history": 50},
    )
    monkeypatch.setattr(viability, "build", lambda **kwargs: sub)
    viability.screen()
    assert calls == [163] * 16
    viability.freeze_inputs()
    assert reference_calls == [154, 158, 159, 163]
    prepared = _json(viability, "prepared.json")
    assert [r["task_id"] for r in prepared] == [154, 158, 159, 163]
    assert prepared[1]["reference_status"] == "REFERENCE_UNAVAILABLE"
    for frozen, old in zip(prepared[:3], manifest["tasks"], strict=True):
        for key in (
            "all_original_episode_ids",
            "all_original_trace_sha256",
            "original_zero_evidence_sha256",
            "evidence_ids",
            "selected_trace_sha256",
            "evidence_sha256",
        ):
            assert frozen[key] == old[key]
    new_manifest = _json(viability, "input_manifest.json")
    assert new_manifest["core_manifest_sha256"] == viability.digest(
        (viability.FROZEN / "core_manifest.json").read_text()
    )
    assert new_manifest["combined_screening_sha256"] == viability.digest(
        (viability.RUN / "combined_screening.json").read_text()
    )
    viability.write_json(viability.FROZEN / "input_manifest.json", new_manifest)
    assert viability.verify_input_set() == prepared
    with pytest.raises(ConfigError, match="already frozen"):
        viability.freeze_inputs()
    assert reference_calls == [154, 158, 159, 163] and calls == [163] * 16
    failures = _json(viability, "task-154/original_failures.json")
    viability.write_json(
        viability.RUN / "task-154/original_failures.json", list(reversed(failures))
    )
    with pytest.raises(ConfigError, match="exact prior/seeded"):
        viability.verify_input_set()


def _adaptation_baseline(
    module: Any, *, actual: float = 1.0, uncertain: float = 0.25, attempts: int = 2
) -> dict[str, Any]:
    baseline = {
        "actual_usd": actual,
        "uncertain_usd": uncertain,
        "screening_committed_usd": actual + uncertain,
        "physical_attempts": attempts,
        "screening_status": "qualified",
    }
    module.write_json(module.RUN / "topup_cost_baseline.json", baseline)
    _cap_update(
        module,
        phase="adaptation",
        actual_usd=actual,
        uncertain_usd=uncertain,
        attempts=attempts,
        screening_committed_usd=actual + uncertain,
        screening_baseline_sha256=module.digest(
            (module.RUN / "topup_cost_baseline.json").read_text()
        ),
    )
    return baseline


def test_incremental_adaptation_cap_preserves_topup_reservations_excludes_sunk_and_unused_headroom(
    viability: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        viability.SCREENING_CAP_USD == 4
        and viability.ADAPTATION_CONFIRMATION_CAP_USD == 25
        and viability.CAP_USD == 29
    )
    monkeypatch.setattr(viability, "PRIOR_RUN", tmp_path / "old-run")
    viability.write_json(
        viability.PRIOR_RUN / "cap.json",
        {"actual_usd": 500, "uncertain_usd": 500, "stopped": "historical"},
    )
    viability.initialize_cap()
    assert _json(viability, "cap.json")["actual_usd"] == 0
    baseline = _adaptation_baseline(viability)
    assert viability.phase_limit(_json(viability, "cap.json")) == 26.25
    calls = 0

    def transport(**wire: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("unknown billed result")
        return _returned(**wire)

    capped = viability.CappedTransport(transport, viability.RUN / "cap.json")
    with pytest.raises(TimeoutError):
        capped(**_wire())
    after_failure = _json(viability, "cap.json")
    capped(**_wire())
    after = _json(viability, "cap.json")
    assert after["uncertain_usd"] == after_failure["uncertain_usd"] > baseline["uncertain_usd"]
    assert after["screening_committed_usd"] == 1.25 and after["attempts"] == 4
    # The 2.75 unused top-up dollars cannot enlarge the separate $25 allocation.
    _cap_update(viability, actual_usd=26.24999 - after["uncertain_usd"])
    with pytest.raises(InfraError, match="cost_cap"):
        capped(**_wire())
    assert calls == 2
    assert _json(viability, "cap.json")["stopped"] == "cost_cap"


@pytest.mark.parametrize("tamper", ["refund", "baseline"])
def test_adaptation_baseline_cannot_be_refunded_or_rewritten(viability: Any, tamper: str) -> None:
    viability.initialize_cap()
    _adaptation_baseline(viability)
    if tamper == "refund":
        _cap_update(viability, uncertain_usd=0)
    else:
        baseline = _json(viability, "topup_cost_baseline.json")
        baseline["screening_committed_usd"] = 0
        viability.write_json(viability.RUN / "topup_cost_baseline.json", baseline)
    calls: list[Any] = []
    with pytest.raises(ConfigError):
        viability.CappedTransport(lambda **wire: calls.append(wire), viability.RUN / "cap.json")(
            **_wire()
        )
    assert calls == []


@pytest.mark.parametrize(
    "case",
    [
        "test_three_calls_keep_exact_lineage_feedback_and_restore_default",
        "test_easy_endpoint_freezes_before_control_and_confirmation_has_no_feedback",
        "test_semantic_uncertain_stops_before_certification_policy_and_redesign",
        "test_thirty_rollout_cap_stops_control_without_reopening_design",
        "test_real_schema_identity_lexical_gates_precede_semantic_and_policy",
    ],
)
def test_frozen_execution_contract_on_v3_driver(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    from tests.unit import test_iterative_low_viability as existing

    original_initialize = viability.initialize_cap

    def initialize_for_method_fixture() -> None:
        original_initialize()
        _adaptation_baseline(viability, actual=0, uncertain=0, attempts=0)

    monkeypatch.setattr(viability, "initialize_cap", initialize_for_method_fixture)
    getattr(existing, case)(viability, monkeypatch)


def test_child_cap_uses_passed_run_path_and_preserves_incremental_baseline(
    viability: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viability.initialize_cap()
    _adaptation_baseline(viability)
    cap_path = viability.RUN / "cap.json"

    def fake_client_init(self: Any, **kwargs: Any) -> None:
        self._client = SimpleNamespace(_transport=_returned)

    monkeypatch.setattr(viability.AeaLLMClient, "__init__", fake_client_init)
    monkeypatch.setattr(viability, "RUN", tmp_path / "incorrect-child-global")
    client = viability.CappedPolicyClient(cap_path=str(cap_path))
    client._client._transport(**_wire())
    state = json.loads(cap_path.read_text())
    assert state["actual_usd"] > 1.0 and state["uncertain_usd"] == 0.25
    assert state["screening_committed_usd"] == 1.25 and state["attempts"] == 3
    assert not viability.RUN.exists()


def test_topup_cannot_reuse_an_original_core_episode_identity(
    viability: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _core_fixture(viability, tmp_path, monkeypatch)
    calls: list[int] = []

    def rollouts(task: Any, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        calls.append(int(task.task_id))
        trace = _trace(False, candidate=candidate)
        trace.rollout_seed = 163
        trace.episode_id = "core-154-1"
        return [trace]

    monkeypatch.setattr(viability, "build", lambda **kwargs: SimpleNamespace(rollouts=rollouts))
    viability.screen()
    screen = _json(viability, "screening.json")
    assert screen["status"] == "IMPLEMENTATION_FAILURE" and screen["qualified"] == []
    assert screen["tasks"]["163"]["valid_episodes"] == 0 and calls == [163]


@pytest.mark.parametrize("kind", ["infra", "config"])
def test_reference_stage_exception_is_preserved_and_classified_without_retry(
    viability: Any,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    _screen(viability, monkeypatch, [{}] * 16)
    invoked: list[str] = []
    reason = (
        "exact reference-provider interruption"
        if kind == "infra"
        else "exact reference manifest mismatch"
    )

    error = (
        InfraError(reason, kind="reference_transport") if kind == "infra" else ConfigError(reason)
    )

    def failed_reference_stage() -> None:
        invoked.append("freeze-inputs")
        raise error

    monkeypatch.setattr(viability, "freeze_inputs", failed_reference_stage)
    monkeypatch.setattr(viability.sys, "argv", ["driver", "--stage", "freeze-inputs"])
    assert viability.main() == 1
    saved = _json(viability, "stage_interruption.json")
    assert saved["stage"] == "freeze-inputs" and saved["error"]["reason"] == str(error)
    summary = viability.report()
    expected = "INCONCLUSIVE" if kind == "infra" else "IMPLEMENTATION_FAILURE"
    assert summary["decision"] == summary["final_viability_decision"] == expected
    assert summary["stage_interruption"] == saved and summary["screening_status"] == "qualified"
    assert invoked == ["freeze-inputs"]
    assert not (viability.RUN / "results.json").exists()
    assert not (viability.RUN / "input_manifest.json").exists()
