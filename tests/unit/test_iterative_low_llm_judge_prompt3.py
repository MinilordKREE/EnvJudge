"""Offline tests for prompt-only launch bindings and cumulative monetary admission."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aea.errors import ConfigError, InfraError
from aea.llm.attribution import attributed
from aea.llm.types import Attribution


def _put(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module: Any = importlib.import_module("scripts.e6_iterative_low_llm_judge_prompt3")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.driver, "ROOT", tmp_path)
    names = {
        "OLD_BASE": "runs/old",
        "PROMPT2_BASE": "runs/prompt2",
        "OLD_FROZEN": "frozen/old",
        "BASE": "runs/new",
        "PRIVATE": "runs/new/private",
        "RUN": "runs/new/private/engineering",
        "VALIDATION": "runs/new/private/validation",
        "FROZEN": "frozen/new",
        "VALIDATION_PREREG": "prereg/validation.md",
        "PREREG": "prereg/engineering.md",
    }
    for key, name in names.items():
        monkeypatch.setattr(module, key, tmp_path / name)
    original_driver = tmp_path / "scripts/e6_iterative_low_llm_judge.py"
    original_driver.parent.mkdir()
    original_driver.write_bytes(b"immutable base driver\n")
    monkeypatch.setattr(
        module, "BASE_DRIVER_SHA256", hashlib.sha256(original_driver.read_bytes()).hexdigest()
    )
    prior_rows = []
    for run_index, (base, commit, committed, limit) in enumerate(
        zip(
            (module.OLD_BASE, module.PROMPT2_BASE),
            module.PRIOR_VALIDATION_COMMITS,
            module.PRIOR_RUN_COMMITTED_USD,
            module.PRIOR_RUN_LIMITS_USD,
            strict=True,
        )
    ):
        old = base / "private/validation"
        cap = {
            "stage": "validation",
            "limit_usd": float(limit),
            "actual_usd": float(committed) if run_index == 0 else 0.36499232000000004,
            "uncertain_usd": 0.0,
            "inflight": {},
            "attempts": 21,
            "cap_path": str((old / "cap.json").resolve()),
        }
        result = {
            "decision": "JUDGE_GATE_NOT_READY",
            "cases_completed": 21,
            "cases_expected": 21,
            "freeze": {"head": commit, "prereg_commit": commit},
        }
        cap_sha = _put(old / "cap.json", cap)
        result_sha = _put(old / "result.json", result)
        attempts = []
        for i in range(21):
            fields = {"attempt": str(i), "model": "deepseek-v4-flash", "stage": "validation"}
            attempts.extend(
                [
                    {**fields, "status": "reserved"},
                    {
                        **fields,
                        "status": "returned",
                        "conservative_usd": float(committed) if i == 0 else 0,
                    },
                ]
            )
        attempt_file = old / "cap.attempts.jsonl"
        attempt_file.write_text("".join(json.dumps(row) + "\n" for row in attempts))
        prior = {"prior_commit": commit, "prior_committed_usd": float(committed)}
        for kind, path, sha in [
            ("cap", old / "cap.json", cap_sha),
            ("result", old / "result.json", result_sha),
            ("attempts", attempt_file, hashlib.sha256(attempt_file.read_bytes()).hexdigest()),
        ]:
            prior[f"prior_validation_{kind}_path"] = str(path.relative_to(tmp_path))
            prior[f"prior_validation_{kind}_sha256"] = sha
        prior_rows.append(prior)
    carry = {
        "schema_version": 2,
        "prior_runs": prior_rows,
        "prior_committed_usd": 0.72355888,
        "validation_envelope_usd": 3.0,
        "validation_remaining_usd": 2.27644112,
        "engineering_cap_usd": 17.0,
        "combined_cap_usd": 20.0,
    }
    _put(module.FROZEN / "carryover.json", carry)
    input_names = []
    private_values: dict[str, Any] = {}
    for i in range(17):
        payload = {"synthetic_input": i}
        sha = hashlib.sha256((json.dumps(payload, sort_keys=True) + "\n").encode()).hexdigest()
        name = f"judge_inputs/{sha}.json"
        input_names.append(name)
        private_values[name] = payload
    private_values["saved_candidates.json"] = {"synthetic": "saved sources"}
    private_values["engineering/prepared.json"] = [{"task_id": 154}, {"task_id": 159}]
    for task in (154, 159):
        for name in ("original_failures", "privileged_reference"):
            private_values[f"engineering/task-{task}/{name}.json"] = {
                "task_id": task,
                "synthetic": name,
            }
    rows = []
    for name, value in private_values.items():
        source, destination = module.OLD_BASE / "private" / name, module.PRIVATE / name
        sha = _put(source, value)
        _put(destination, value)
        rows.append(
            {
                "source": str(source.relative_to(tmp_path)),
                "destination": str(destination.relative_to(tmp_path)),
                "sha256": sha,
                "bytes": source.stat().st_size,
            }
        )
    _put(module.FROZEN / "copied_private_inputs.json", {"schema_version": 1, "files": rows})
    for name, value in {
        "input_manifest.json": {"synthetic": "same evidence manifest"},
        "validation_manifest.json": {
            "cases": [{"input_file": n} for n in input_names + input_names[:4]]
        },
        "saved_candidates.json": {"synthetic": "same metadata"},
    }.items():
        _put(module.OLD_FROZEN / name, value)
        _put(module.FROZEN / name, value)
    return module


def test_exact_immutable_inputs_and_paid_spend_verified_without_old_writes(prepared: Any) -> None:
    before = {
        p: p.read_bytes()
        for root in (prepared.OLD_BASE, prepared.PROMPT2_BASE, prepared.OLD_FROZEN)
        for p in root.rglob("*")
        if p.is_file()
    }
    assert prepared.verify_carryover()["prior_committed_usd"] == 0.72355888
    prepared.verify_copied_inputs()
    assert {p: p.read_bytes() for p in before} == before
    assert not list(prepared.OLD_BASE.rglob("*.lock"))
    assert not list(prepared.PROMPT2_BASE.rglob("*.lock"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("prior_committed_usd", 0),
        ("validation_remaining_usd", 3),
        ("engineering_cap_usd", 18),
        ("combined_cap_usd", 21),
        ("prior_committed_usd", float("nan")),
        ("validation_remaining_usd", True),
    ],
)
def test_invalid_carryover_refused(prepared: Any, field: str, value: Any) -> None:
    path = prepared.FROZEN / "carryover.json"
    row = json.loads(path.read_text())
    row[field] = value
    _put(path, row)
    with pytest.raises(ConfigError):
        prepared.verify_carryover()


@pytest.mark.parametrize(
    "field,value",
    [
        ("inflight", {"orphan": 0.1}),
        ("uncertain_usd", 0.01),
        ("attempts", 22),
        ("stopped", "cost_cap"),
    ],
)
@pytest.mark.parametrize("run_index", [0, 1])
def test_old_unresolved_or_different_run_refused_even_if_manifest_rehashed(
    prepared: Any, field: str, value: Any, run_index: int
) -> None:
    base = (prepared.OLD_BASE, prepared.PROMPT2_BASE)[run_index]
    path = base / "private/validation/cap.json"
    row = json.loads(path.read_text())
    row[field] = value
    sha = _put(path, row)
    carry_path = prepared.FROZEN / "carryover.json"
    carry = json.loads(carry_path.read_text())
    carry["prior_runs"][run_index]["prior_validation_cap_sha256"] = sha
    _put(carry_path, carry)
    with pytest.raises(ConfigError):
        prepared.verify_carryover()


@pytest.mark.parametrize("side", ["source", "destination"])
def test_private_copy_tampering_refused(prepared: Any, side: str) -> None:
    row = json.loads((prepared.FROZEN / "copied_private_inputs.json").read_text())["files"][0]
    (prepared.ROOT / row[side]).write_bytes(b"changed confidential payload")
    with pytest.raises(ConfigError):
        prepared.verify_copied_inputs()


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "escape", "length", "hash", "symlink"]
)
def test_copy_inventory_boundaries(prepared: Any, mutation: str) -> None:
    path = prepared.FROZEN / "copied_private_inputs.json"
    inventory = json.loads(path.read_text())
    first = inventory["files"][0]
    if mutation == "missing":
        inventory["files"].pop()
    elif mutation == "duplicate":
        inventory["files"][-1] = first
    elif mutation == "escape":
        first["destination"] = "../secret"
    elif mutation == "length":
        first["bytes"] = True
    elif mutation == "hash":
        first["sha256"] = "private prose"
    elif mutation == "symlink":
        destination = prepared.ROOT / first["destination"]
        destination.unlink()
        destination.symlink_to(prepared.ROOT / first["source"])
    _put(path, inventory)
    with pytest.raises(ConfigError):
        prepared.verify_copied_inputs()


def test_binding_preserves_all_functions_and_restores_globals(prepared: Any) -> None:
    d = prepared.driver
    functions = {
        name: getattr(d, name)
        for name in (
            "validate",
            "freeze_validation",
            "replay_saved",
            "adapt",
            "report",
            "run_task",
            "confirm",
            "decision_for",
            "make_judge",
            "CappedTransport",
            "CappedPolicyClient",
            "make_screen",
        )
    }
    old_paths = {
        name: getattr(d, name)
        for name in (
            "BASE",
            "PRIVATE",
            "RUN",
            "VALIDATION",
            "FROZEN",
            "STAGE_LIMITS",
            "FROZEN_INPUTS",
        )
    }
    with pytest.raises(RuntimeError, match="offline"), prepared.bound_driver():
        assert all(getattr(d, k) is v for k, v in functions.items())
        assert d.RUN == prepared.RUN and d.PRIVATE == prepared.PRIVATE
        assert d.STAGE_LIMITS == {"validation": 2.27644112, "engineering": 17.0}
        assert set(prepared.EXTRA_FROZEN_INPUTS).issubset(d.FROZEN_INPUTS)
        raise RuntimeError("offline")
    assert all(getattr(d, k) is v for k, v in old_paths.items())


def test_remaining_validation_ceiling_applies_before_every_physical_dispatch(prepared: Any) -> None:
    calls = []
    d = prepared.driver
    wire = {"model": "deepseek-v4-flash", "messages": [], "max_tokens": 2048}
    with prepared.bound_driver():
        path = d.VALIDATION / "cap.json"
        d.initialize_cap(path, "validation")
        with d.cap_lock(path) as state:
            state["actual_usd"] = 2.275
        transport = d.CappedTransport(lambda **kw: calls.append(kw), path)
        with attributed(Attribution(phase="judge_validation", arm=d.ARM, task_id="154"), 0):
            for _ in range(2):
                with pytest.raises(InfraError, match="cost_cap"):
                    transport(**wire)
        assert not calls
        state = json.loads(path.read_text())
        assert state["attempts"] == 0 and state["stopped"] == "cost_cap"
        assert state["limit_usd"] == 2.27644112


def test_failed_physical_reservation_retained_and_no_validation_restart(prepared: Any) -> None:
    d = prepared.driver
    calls = []

    def fail(**kw: Any) -> Any:
        calls.append(kw)
        raise RuntimeError("physical timeout")

    with prepared.bound_driver():
        path = d.VALIDATION / "cap.json"
        d.initialize_cap(path, "validation")
        with (
            attributed(Attribution(phase="judge_validation", arm=d.ARM, task_id="154"), 0),
            pytest.raises(RuntimeError, match="physical timeout"),
        ):
            d.CappedTransport(fail, path)(model="deepseek-v4-flash", messages=[], max_tokens=2048)
        state = json.loads(path.read_text())
        assert state["uncertain_usd"] > 0 and state["inflight"] == {} and len(calls) == 1
        with pytest.raises(ConfigError, match="no implicit restart"):
            d.initialize_cap(path, "validation")


def test_engineering_cap_compatible_after_fresh_child_default_binding(prepared: Any) -> None:
    d = prepared.driver
    original_engineering = d.STAGE_LIMITS["engineering"]
    assert original_engineering == 17.0
    with prepared.bound_driver():
        path = d.RUN / "cap.json"
        d.initialize_cap(path, "engineering")
        with d.cap_lock(path) as state:
            state["actual_usd"] = 16.0
    # Fresh policy workers import the original module's 3/17 limits, not the launcher.
    calls = []

    def returned(**kw: Any) -> Any:
        calls.append(kw)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, cost=None)
        )

    with attributed(Attribution(phase="C1:endpoint", arm=d.ARM, task_id="154"), 154):
        d.CappedTransport(returned, path)(model="deepseek-v4-flash", messages=[], max_tokens=2048)
    assert len(calls) == 1
    assert json.loads(path.read_text())["actual_usd"] > 16.0


@pytest.mark.parametrize(
    "stage,name",
    [
        ("validate", "validate"),
        ("freeze", "freeze_validation"),
        ("replay", "replay_saved"),
        ("adapt", "adapt"),
        ("report", "report"),
    ],
)
def test_dispatches_identical_phase_function_only_after_guards(
    prepared: Any, monkeypatch: pytest.MonkeyPatch, stage: str, name: str
) -> None:
    calls = []
    monkeypatch.setattr(
        prepared.driver, "ensure_frozen", lambda **kwargs: calls.append(("freeze", kwargs))
    )

    def phase() -> dict[str, Any]:
        calls.append((name, prepared.driver.BASE))
        return {"same_function": name}

    monkeypatch.setattr(prepared.driver, name, phase)
    assert prepared.run_stage(stage) == {"same_function": name}
    assert calls == [
        ("freeze", {"adaptation": stage in {"replay", "adapt"}}),
        (name, prepared.BASE),
    ]
    bad = prepared.PRIVATE / "saved_candidates.json"
    bad.write_bytes(b"tampered")
    calls.clear()
    with pytest.raises(ConfigError):
        prepared.run_stage(stage)
    assert calls == []


def test_prepare_forbidden_without_any_write(prepared: Any) -> None:
    before = {p: p.read_bytes() for p in prepared.ROOT.rglob("*") if p.is_file()}
    with pytest.raises(ConfigError, match="forbids prepare"):
        prepared.run_stage("prepare")
    assert {p: p.read_bytes() for p in prepared.ROOT.rglob("*") if p.is_file()} == before


def test_failed_validation_main_exits_two_without_engineering(
    prepared: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    calls = []

    def failed(stage: str) -> dict[str, Any]:
        calls.append(stage)
        return {"decision": "JUDGE_GATE_NOT_READY", "private_reason": "PRIVATE_CANARY"}

    monkeypatch.setattr(prepared, "run_stage", failed)
    monkeypatch.setattr(sys, "argv", ["prompt3", "validate"])
    assert prepared.main() == 2
    assert calls == ["validate"]
    assert "PRIVATE_CANARY" not in capsys.readouterr().out
    assert not (prepared.RUN / "cap.json").exists()


def test_main_error_writes_only_new_private_namespace(
    prepared: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    before = {p: p.read_bytes() for p in prepared.OLD_BASE.rglob("*") if p.is_file()}

    def failed(stage: str) -> Any:
        raise ConfigError("PRIVATE_CANARY")

    monkeypatch.setattr(prepared, "run_stage", failed)
    monkeypatch.setattr(sys, "argv", ["prompt3", "validate"])
    assert prepared.main() == 2
    assert "PRIVATE_CANARY" not in capsys.readouterr().out
    assert (prepared.PRIVATE / "validate_interruption.json").exists()
    assert {p: p.read_bytes() for p in prepared.OLD_BASE.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("run_index", [0, 1])
@pytest.mark.parametrize(
    "field,value",
    [
        ("prior_commit", "0" * 40),
        ("prior_committed_usd", 0),
        ("prior_validation_cap_sha256", "0" * 64),
        ("prior_validation_result_sha256", "0" * 64),
        ("prior_validation_attempts_sha256", "0" * 64),
    ],
)
def test_each_prior_run_has_independent_hash_and_amount_binding(
    prepared: Any, run_index: int, field: str, value: Any
) -> None:
    path = prepared.FROZEN / "carryover.json"
    row = json.loads(path.read_text())
    row["prior_runs"][run_index][field] = value
    _put(path, row)
    with pytest.raises(ConfigError):
        prepared.verify_carryover()


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "extra"])
def test_cannot_omit_repeat_or_reorder_previous_paid_run(prepared: Any, mutation: str) -> None:
    path = prepared.FROZEN / "carryover.json"
    row = json.loads(path.read_text())
    if mutation == "missing":
        row["prior_runs"].pop()
    elif mutation == "duplicate":
        row["prior_runs"][1] = row["prior_runs"][0]
    elif mutation == "reordered":
        row["prior_runs"].reverse()
    else:
        row["prior_runs"].append(row["prior_runs"][0])
    _put(path, row)
    with pytest.raises(ConfigError):
        prepared.verify_carryover()


@pytest.mark.parametrize("run_index", [0, 1])
@pytest.mark.parametrize("kind", ["result", "attempts"])
def test_prior_result_or_physical_journal_tampering_rejected_even_if_rehashed(
    prepared: Any, run_index: int, kind: str
) -> None:
    base = (prepared.OLD_BASE, prepared.PROMPT2_BASE)[run_index] / "private/validation"
    if kind == "result":
        path = base / "result.json"
        result = json.loads(path.read_text())
        result["cases_completed"] = 20
        sha = _put(path, result)
    else:
        path = base / "cap.attempts.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]["conservative_usd"] = 0.01
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    carry_path = prepared.FROZEN / "carryover.json"
    carry = json.loads(carry_path.read_text())
    carry["prior_runs"][run_index][f"prior_validation_{kind}_sha256"] = sha
    _put(carry_path, carry)
    with pytest.raises(ConfigError):
        prepared.verify_carryover()
