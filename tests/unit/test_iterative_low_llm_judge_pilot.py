"""Offline prospective startup, authorization, carryover, and inherited LOW boundaries."""

from __future__ import annotations

import importlib
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aea.errors import ConfigError, InfraError
from aea.llm.attribution import attributed
from aea.llm.types import Attribution


def put(path: Path, value: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return payload


@pytest.fixture
def pilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module: Any = importlib.import_module("scripts.e6_iterative_low_llm_judge_pilot")
    for owner in (module, module.evidence, module.driver):
        monkeypatch.setattr(owner, "ROOT", tmp_path)
    base = tmp_path / "runs/pilot"
    for key, path in {
        "BASE": base,
        "PRIVATE": base / "private",
        "RUN": base / "private/engineering",
        "FROZEN": tmp_path / "frozen/pilot",
        "PREREG": tmp_path / "prereg/pilot.md",
        "DESIGN": tmp_path / "design/pilot.md",
    }.items():
        monkeypatch.setattr(module, key, path)
    old = {
        "BASE": tmp_path / "runs/r5",
        "PRIVATE": tmp_path / "runs/r5/private",
        "VALIDATION": tmp_path / "runs/r5/private/validation",
        "FROZEN": tmp_path / "frozen/r5",
    }
    monkeypatch.setattr(module.evidence, "paths", lambda index: old)
    monkeypatch.setattr(module, "_published", lambda *a, **kw: "c" * 40)
    monkeypatch.setattr(
        module.evidence,
        "verify_carryover",
        lambda index: {"prior_committed_usd": float(module.PRIOR_COMMITTED - module.number(0.5))},
    )
    monkeypatch.setattr(module.evidence, "_receipt", lambda *a, **kw: {"committed_usd": 0.5})
    monkeypatch.setattr(module.evidence, "_verify_predecessor", lambda *a, **kw: None)
    put(old["FROZEN"] / "carryover.json", {"synthetic": "previous eight paid runs"})
    source = tmp_path / "src/frozen.py"
    source.parent.mkdir()
    source.write_text("frozen judge implementation\n")
    outcomes = [
        {
            "case_id": name,
            "role": "regression",
            "expected_verdict": label,
            "verdict": "UNCERTAIN"
            if name == "archived_task110"
            else "FAIL"
            if name == "generic_prerequisite"
            else label,
        }
        for name, label in module.driver.EXPECTED_CASES.items()
    ]
    outcomes.extend({"role": "inspection", "case_id": f"extra-{i}"} for i in range(8))
    values = {
        "independent_audit.json": {
            "integrity": "PASS",
            "judge_ready": False,
            "round": 5,
            "checks": {"synthetic_accounting": True},
        },
        "validation_result.json": {
            "decision": "JUDGE_GATE_NOT_READY",
            "cases_completed": 21,
            "cases_expected": 21,
            "interruption_sha256": None,
            "outcomes": outcomes,
        },
        "source_manifest.json": {
            "implementation": {"campaign_round": 5, "version": "synthetic witness"},
            "source_hashes": {"src/frozen.py": module.sha(source.read_bytes())},
        },
    }
    hashes = {name: module.sha(put(old["FROZEN"] / name, value)) for name, value in values.items()}
    monkeypatch.setattr(module, "R5_HASHES", hashes)
    return module


def alter_r5(pilot: Any, name: str, mutate: Any, *, repin: bool = True) -> None:
    path = pilot.evidence.paths(5)["FROZEN"] / name
    value = json.loads(path.read_bytes())
    mutate(value)
    payload = put(path, value)
    if repin:
        pilot.R5_HASHES[name] = pilot.sha(payload)


def budget(pilot: Any) -> dict[str, Any]:
    basis = pilot.startup_basis()
    put(pilot.FROZEN / "startup_basis.json", basis)
    result = {
        "schema_version": 1,
        "protocol": pilot.PROTOCOL,
        "prior_committed_usd": float(pilot.PRIOR_COMMITTED),
        "engineering_cap_usd": float(pilot.ENGINEERING_CAP),
        "combined_cap_usd": 20.0,
        "startup_basis_sha256": pilot.sha((pilot.FROZEN / "startup_basis.json").read_bytes()),
    }
    put(pilot.FROZEN / "engineering_budget.json", result)
    return result


def authorization(pilot: Any) -> dict[str, Any]:
    budget(pilot)
    put(pilot.FROZEN / "source_manifest.json", {"synthetic": "prospective source"})
    put(pilot.PREREG, {"synthetic": "new prospective authorization conditions"})
    value = {
        "schema_version": 1,
        "protocol": pilot.PROTOCOL,
        "authorized": True,
        "phase_a_pass_precondition_removed": True,
        "prereg_sha256": pilot.sha(pilot.PREREG.read_bytes()),
        "source_manifest_sha256": pilot.sha((pilot.FROZEN / "source_manifest.json").read_bytes()),
        "engineering_budget_sha256": pilot.sha(
            (pilot.FROZEN / "engineering_budget.json").read_bytes()
        ),
        "user_authorization_sha256": "d" * 64,
        "recipients": pilot.RECIPIENTS,
    }
    put(pilot.PRIVATE / "authorization.json", value)
    return value


def test_startup_preserves_failed_r5_and_blocked_uncertainty(pilot: Any) -> None:
    before = (pilot.evidence.paths(5)["FROZEN"] / "validation_result.json").read_bytes()
    result = pilot.startup_basis()
    assert result["r5_decision"] == "JUDGE_GATE_NOT_READY"
    assert result["labeled_leaks_blocked"] == 9
    assert result["known_generic_false_rejection"] is True
    assert result["prior_committed_usd"] == 4.93304108
    assert (pilot.evidence.paths(5)["FROZEN"] / "validation_result.json").read_bytes() == before


@pytest.mark.parametrize(
    "name,changes",
    [
        ("independent_audit.json", {"integrity": "FAIL"}),
        ("independent_audit.json", {"judge_ready": True}),
        ("independent_audit.json", {"checks": {"failed": False}}),
        ("validation_result.json", {"cases_completed": 20}),
        ("validation_result.json", {"decision": "JUDGE_GATE_READY"}),
        ("validation_result.json", {"interruption_sha256": "a" * 64}),
    ],
)
def test_startup_refuses_unverified_or_relabelled_history(
    pilot: Any, name: str, changes: Any
) -> None:
    alter_r5(pilot, name, lambda value: value.update(changes))
    with pytest.raises(ConfigError):
        pilot.startup_basis()


@pytest.mark.parametrize("case", ["archived_task110", "hidden_location_ranking"])
def test_known_leak_pass_blocks_the_entire_new_pilot(pilot: Any, case: str) -> None:
    def change(value: Any) -> None:
        next(row for row in value["outcomes"] if row["case_id"] == case)["verdict"] = "PASS"

    alter_r5(pilot, "validation_result.json", change)
    with pytest.raises(ConfigError, match="nine labeled leaks"):
        pilot.startup_basis()


def test_r5_artifact_or_judge_bytes_cannot_change(pilot: Any) -> None:
    alter_r5(pilot, "validation_result.json", lambda value: value.update(extra=True), repin=False)
    with pytest.raises(ConfigError, match="immutable bytes"):
        pilot.startup_basis()


def test_r5_frozen_source_is_checked_independently_of_new_manifest(pilot: Any) -> None:
    (pilot.ROOT / "src/frozen.py").write_text("changed judge prompt\n")
    with pytest.raises(ConfigError, match="immutable bytes"):
        pilot.startup_basis()


def test_ambiguous_reservation_cannot_be_refunded(
    pilot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pilot.evidence, "_receipt", lambda *a, **kw: {"committed_usd": 0.4})
    with pytest.raises(ConfigError, match="every previous paid reservation"):
        pilot.startup_basis()


def test_all_previous_receipts_are_verified_before_startup(
    pilot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = []
    monkeypatch.setattr(pilot.evidence, "_verify_predecessor", lambda *args: called.append(args))
    pilot.startup_basis()
    assert len(called) == 1 and called[0][1] == 5
    assert float(called[0][2]) == 4.43304108


def test_budget_uses_total_remainder_and_rejects_old_seventeen_dollar_cap(pilot: Any) -> None:
    expected = budget(pilot)
    assert pilot.engineering_budget() == expected
    assert expected["engineering_cap_usd"] == 15.06695892
    put(pilot.FROZEN / "engineering_budget.json", {**expected, "engineering_cap_usd": 17.0})
    with pytest.raises(ConfigError, match="cumulative budget"):
        pilot.engineering_budget()


def test_budget_rechecks_startup_and_binds_basis_hash(pilot: Any) -> None:
    budget(pilot)
    basis = pilot._json(pilot.FROZEN / "startup_basis.json")
    put(pilot.FROZEN / "startup_basis.json", {**basis, "prior_committed_usd": 0.0})
    with pytest.raises(ConfigError, match="startup basis changed"):
        pilot.engineering_budget()


def test_missing_new_consent_blocks_before_model_client_construction(
    pilot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pilot.AeaLLMClient, "__init__", lambda *a, **kw: pytest.fail("constructed API client")
    )
    with pytest.raises(ConfigError):
        pilot.CappedPolicyClient(cap_path=str(pilot.RUN / "cap.json"))
    monkeypatch.setattr(
        pilot, "ORIGINAL_BUILD", lambda **kw: pytest.fail("constructed environment/API substrate")
    )
    with pytest.raises(ConfigError):
        pilot._build(designer=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"authorized": False},
        {"authorized": 1},
        {"phase_a_pass_precondition_removed": False},
        {"recipients": ["https://another-provider.example"]},
        {"prereg_sha256": "a" * 64},
        {"extra_bypass": True},
        {"user_authorization_sha256": "not-a-hash"},
    ],
)
def test_authorization_must_explicitly_bind_new_protocol(pilot: Any, changes: Any) -> None:
    value = authorization(pilot)
    put(pilot.PRIVATE / "authorization.json", {**value, **changes})
    with pytest.raises(ConfigError):
        pilot.require_authorization()


def test_consent_becomes_invalid_if_preregistration_changes(pilot: Any) -> None:
    authorization(pilot)
    pilot.require_authorization()
    pilot.PREREG.write_text("different prospective procedure\n")
    with pytest.raises(ConfigError):
        pilot.require_authorization()


def test_child_policy_rejects_any_other_cap_namespace(pilot: Any) -> None:
    with pytest.raises(ConfigError, match="namespace"):
        pilot.CappedPolicyClient(cap_path=str(pilot.ROOT / "other/cap.json"))


def test_child_policy_uses_new_cap_and_denies_before_transport(
    pilot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    authorization(pilot)
    limit = float(pilot.ENGINEERING_CAP)
    path = pilot.RUN / "cap.json"
    put(
        path,
        {
            "stage": "engineering",
            "limit_usd": limit,
            "cap_path": str(path),
            "actual_usd": limit - 0.000001,
            "uncertain_usd": 0.0,
            "inflight": {},
            "attempts": 0,
        },
    )
    monkeypatch.setattr(pilot, "engineering_budget", lambda **kw: {"engineering_cap_usd": limit})
    initialized = []

    def init(self: Any, **kwargs: Any) -> None:
        initialized.append(kwargs)
        self._client = SimpleNamespace(_transport=lambda **wire: pytest.fail("paid API reached"))

    monkeypatch.setattr(pilot.AeaLLMClient, "__init__", init)
    client = pilot.CappedPolicyClient(cap_path=str(path), frozen_policy="unchanged")
    assert initialized == [{"frozen_policy": "unchanged"}]
    limits = pilot.driver.STAGE_LIMITS
    with (
        attributed(
            Attribution(phase="adapt", budget="search", arm=pilot.driver.ARM, task_id="154"), seed=0
        ),
        pytest.raises(InfraError),
    ):
        client._client._transport(model="deepseek-v4-flash", messages=[], max_tokens=1)
    assert pilot.driver.STAGE_LIMITS is limits
    assert json.loads(path.read_bytes())["attempts"] == 0


def test_context_preserves_original_phase_functions_and_candidate_judge(pilot: Any) -> None:
    budget(pilot)
    originals = {
        name: getattr(pilot.driver, name)
        for name in (
            "replay_saved",
            "adapt",
            "run_task",
            "confirm",
            "validation_decision",
            "freeze_validation",
        )
    }
    old_judge, old_ensure = pilot.driver.LLMPrivilegeJudge, pilot.driver.ensure_frozen
    with pytest.raises(RuntimeError), pilot.bound_driver():
        assert pilot.driver.LLMPrivilegeJudge is pilot.WitnessCheckingPrivilegeJudge
        assert pilot.driver.ensure_frozen is pilot.ensure_frozen
        assert pilot.driver.STAGE_LIMITS["engineering"] == 15.06695892
        assert all(getattr(pilot.driver, name) is value for name, value in originals.items())
        raise RuntimeError("synthetic interrupt")
    assert pilot.driver.LLMPrivilegeJudge is old_judge
    assert pilot.driver.ensure_frozen is old_ensure


def test_existing_cap_or_replay_journal_cannot_restart(pilot: Any) -> None:
    budget(pilot)
    path = pilot.RUN / "cap.json"
    with pilot.bound_driver():
        pilot.driver.initialize_cap(path, "engineering")
        assert pilot._json(path)["limit_usd"] == 15.06695892
        with pytest.raises(ConfigError, match="no implicit restart"):
            pilot.driver.initialize_cap(path, "engineering")
    path.unlink()
    put(pilot.RUN / "saved_replay.json", {"status": "interrupted"})
    with pilot.bound_driver(), pytest.raises(ConfigError, match="no implicit restart"):
        pilot.driver.initialize_cap(path, "engineering")


def test_stage_lock_refuses_concurrency(pilot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pilot.evidence, "campaign_lock", nullcontext)
    with (
        pilot.pilot_lock(),
        pytest.raises(ConfigError, match="another pilot stage"),
        pilot.pilot_lock(),
    ):
        pytest.fail("concurrent stage admitted")


def test_prepare_copies_exactly_existing_inputs_and_freeze_is_offline(
    pilot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = pilot.evidence.paths(5)
    rows = []
    for index in range(23):
        source = pilot.ROOT / f"original/private/synthetic-{index}.json"
        payload = put(source, {"synthetic": index})
        rows.append(
            {
                "source": str(source.relative_to(pilot.ROOT)),
                "destination": str((old["PRIVATE"] / source.name).relative_to(pilot.ROOT)),
                "sha256": pilot.sha(payload),
                "bytes": len(payload),
            }
        )
    put(old["FROZEN"] / "copied_private_inputs.json", {"schema_version": 1, "files": rows})
    for name in ("input_manifest.json", "validation_manifest.json", "saved_candidates.json"):
        put(old["FROZEN"] / name, {"synthetic": name})
    original = {path: path.read_bytes() for path in old["FROZEN"].iterdir()}
    monkeypatch.setattr(pilot, "verify_copied_inputs", lambda: None)
    monkeypatch.setattr(pilot, "source_hashes", lambda: {"synthetic": "e" * 64})
    monkeypatch.setattr(
        pilot.driver, "verify_input_set", lambda: [{"task_id": 154}, {"task_id": 159}]
    )
    monkeypatch.setattr(pilot.driver, "verify_validation_inputs", lambda: [{}] * 21)
    monkeypatch.setattr(
        pilot, "ORIGINAL_BUILD", lambda **kw: pytest.fail("offline prepare built substrate")
    )
    monkeypatch.setattr(
        pilot.AeaLLMClient, "__init__", lambda *a, **kw: pytest.fail("offline prepare built client")
    )
    assert pilot.prepare()["private_files"] == 23
    for row in pilot._json(pilot.FROZEN / "copied_private_inputs.json")["files"]:
        assert (pilot.ROOT / row["source"]).read_bytes() == (
            pilot.ROOT / row["destination"]
        ).read_bytes()
    result = pilot.freeze()
    assert result["status"] == "frozen_offline" and result["paid_authorized"] is False
    manifest = pilot._json(pilot.FROZEN / "source_manifest.json")
    assert manifest["implementation"] == {"version": pilot.PROTOCOL, "judge_origin_round": 5}
    assert manifest["frozen_judge_origin"]["campaign_round"] == 5
    assert not (pilot.PRIVATE / "authorization.json").exists()
    assert not (pilot.RUN / "cap.json").exists()
    assert all(path.read_bytes() == payload for path, payload in original.items())
    with pytest.raises(ConfigError, match="no implicit overwrite"):
        pilot.prepare()
    with pytest.raises(ConfigError, match="no regeneration"):
        pilot.freeze()


@pytest.mark.parametrize("stage", ["replay", "adapt"])
def test_top_level_paid_stage_denies_missing_renewed_consent_before_action(
    pilot: Any, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    budget(pilot)
    source = pilot.ROOT / "scripts/e6_iterative_low_llm_judge.py"
    source.parent.mkdir()
    source.write_text("synthetic immutable base driver\n")
    monkeypatch.setattr(pilot.evidence, "BASE_DRIVER_SHA256", pilot.sha(source.read_bytes()))
    for name in ("input_manifest.json", "validation_manifest.json", "copied_private_inputs.json"):
        put(pilot.FROZEN / name, {"synthetic": name})
    sources = {str(source.relative_to(pilot.ROOT)): pilot.sha(source.read_bytes())}
    put(pilot.FROZEN / "source_manifest.json", {"source_hashes": sources})
    monkeypatch.setattr(pilot, "source_hashes", lambda: sources)
    monkeypatch.setattr(pilot, "verify_copied_inputs", lambda: None)
    monkeypatch.setattr(pilot.driver, "verify_input_set", lambda: [])
    monkeypatch.setattr(pilot.driver, "verify_validation_inputs", lambda: [])
    monkeypatch.setattr(pilot, "pilot_lock", nullcontext)
    monkeypatch.setattr(
        pilot.driver,
        "git",
        lambda *args: (
            "aea-llm-vnext" if args[0] == "branch" else "" if args[0] == "status" else "f" * 40
        ),
    )
    pilot.PREREG.parent.mkdir(parents=True)
    pilot.PREREG.write_text(
        "\n".join(
            [
                pilot.PROTOCOL,
                pilot.driver.METHOD,
                pilot.driver.BASE_DRIVER_SHA,
                *(pilot.sha(path.read_bytes()) for path in pilot.FROZEN.glob("*.json")),
            ]
        )
    )
    monkeypatch.setattr(
        pilot.driver,
        "replay_saved" if stage == "replay" else "adapt",
        lambda: pytest.fail("paid stage action reached without prospective user consent"),
    )
    with pytest.raises(ConfigError, match="immutable input is missing"):
        pilot.run_stage(stage)
    assert not (pilot.RUN / "cap.json").exists()


def test_report_counts_prior_validation_once_without_requiring_paid_consent(
    pilot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pilot,
        "ORIGINAL_REPORT",
        lambda: {
            "decision": "PREPARED",
            "engineering_cost": {"conservative_committed_usd": 1.25},
            "validation_cost": {"conservative_committed_usd": 0.5},
        },
    )
    monkeypatch.setattr(
        pilot.driver, "public_report", lambda result: {"decision": result["decision"]}
    )
    result = pilot._report()
    assert result["pilot"]["cumulative_committed_usd"] == pytest.approx(6.18304108)
    assert result["pilot"]["validation_cost_is_included_in_prior_committed_usd"] is True
    assert result["pilot"]["r5_judge_ready"] is False
    assert not (pilot.PRIVATE / "authorization.json").exists()
    assert not (pilot.RUN / "cap.json").exists()
