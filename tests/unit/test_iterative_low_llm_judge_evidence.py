"""Offline campaign budget, immutable-copy and inherited-execution boundary checks."""

from __future__ import annotations

import hashlib
import importlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aea.errors import ConfigError, InfraError
from aea.llm.attribution import attributed
from aea.llm.types import Attribution


def put(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journal(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.fixture
def campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module: Any = importlib.import_module("scripts.e6_iterative_low_llm_judge_evidence")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.driver, "ROOT", tmp_path)
    for key, name in {
        "BASE": "runs/e6-iterative-low-llm-judge-evidence",
        "FROZEN_BASE": "experiments/alfworld_e6/frozen/iterative_low_llm_judge_evidence",
        "OLD_BASE": "runs/e6-iterative-low-llm-judge",
        "OLD_FROZEN": "experiments/alfworld_e6/frozen/iterative_low_llm_judge",
    }.items():
        monkeypatch.setattr(module, key, tmp_path / name)
    source = tmp_path / "scripts/e6_iterative_low_llm_judge.py"
    source.parent.mkdir()
    source.write_text("immutable synthetic common driver\n")
    monkeypatch.setattr(
        module, "BASE_DRIVER_SHA256", hashlib.sha256(source.read_bytes()).hexdigest()
    )
    for index, name in enumerate(module.PRIOR_NAMES):
        directory = tmp_path / "runs" / name / "private/validation"
        amount = float(module.PRIOR_AMOUNTS[index])
        if index:
            amount += 5e-17  # The real journals contain harmless floating summation noise.
        cap = {
            "stage": "validation",
            "limit_usd": float(module.PRIOR_LIMITS[index]),
            "cap_path": str(directory / "cap.json"),
            "actual_usd": amount,
            "uncertain_usd": 0.0,
            "inflight": {},
            "attempts": 21,
        }
        put(directory / "cap.json", cap)
        put(
            directory / "result.json",
            {
                "decision": "JUDGE_GATE_NOT_READY",
                "cases_completed": 21,
                "cases_expected": 21,
                "freeze": {
                    "head": module.PRIOR_COMMITS[index],
                    "prereg_commit": module.PRIOR_COMMITS[index],
                },
            },
        )
        rows: list[dict[str, Any]] = []
        for call in range(21):
            fields = {"attempt": str(call), "model": "deepseek-v4-flash", "stage": "validation"}
            rows.extend(
                [
                    {**fields, "status": "reserved"},
                    {
                        **fields,
                        "status": "returned",
                        "conservative_usd": amount if call == 0 else 0.0,
                    },
                ]
            )
        journal(directory / "cap.attempts.jsonl", rows)
    names = []
    for index in range(17):
        name = f"judge_inputs/{index:064x}.json"
        names.append(name)
        put(module.OLD_BASE / "private" / name, {"synthetic": index})
    put(
        module.OLD_FROZEN / "validation_manifest.json",
        {"cases": [{"input_file": name} for name in names + names[:4]]},
    )
    put(module.OLD_FROZEN / "input_manifest.json", {"synthetic": "same selected failures"})
    put(module.OLD_FROZEN / "saved_candidates.json", [{"source_sha256": "a" * 64}])
    put(module.OLD_BASE / "private/saved_candidates.json", [{"private": "synthetic source"}])
    put(module.OLD_BASE / "private/engineering/prepared.json", [{"task_id": 154}, {"task_id": 159}])
    for task in (154, 159):
        for name in ("original_failures", "privileged_reference"):
            put(
                module.OLD_BASE / f"private/engineering/task-{task}/{name}.json",
                {"synthetic": name},
            )
    return module


def prepared(campaign: Any) -> dict[str, Path]:
    campaign.prepare_round(1)
    return campaign.paths(1)  # type: ignore[no-any-return]


def completed_round(
    campaign: Any,
    index: int = 1,
    *,
    ready: bool = False,
    actual: float = 0.2,
    uncertain: float = 0.05,
) -> dict[str, Path]:
    p: dict[str, Path] = campaign.paths(index)
    carry = json.loads((p["FROZEN"] / "carryover.json").read_bytes())
    directory = p["VALIDATION"]
    cap = {
        "stage": "validation",
        "limit_usd": carry["validation_round_cap_usd"],
        "cap_path": str(directory / "cap.json"),
        "actual_usd": actual,
        "uncertain_usd": uncertain,
        "inflight": {},
        "attempts": 22 if uncertain else 21,
    }
    put(directory / "cap.json", cap)
    rows, requests, responses, full, compact = [], [], [], [], []
    attribution = {
        "phase": "judge_validation",
        "arm": campaign.driver.ARM,
        "budget": "none",
        "task_id": "154",
    }
    if uncertain:
        fields = {
            "attempt": "retry",
            "model": "deepseek-v4-flash",
            "stage": "validation",
            "attribution": attribution,
            "seed": 0,
            "reserved_usd": uncertain,
        }
        rows.extend([{**fields, "status": "reserved"}, {**fields, "status": "ambiguous_failure"}])
    for i in range(21):
        fields = {
            "attempt": f"ok-{i}",
            "model": "deepseek-v4-flash",
            "stage": "validation",
            "attribution": attribution,
            "seed": 0,
            "reserved_usd": max(actual, 0.1),
        }
        rows.extend(
            [
                {**fields, "status": "reserved"},
                {**fields, "status": "returned", "conservative_usd": actual if i == 0 else 0},
            ]
        )
        request, response = {"synthetic_request": i}, {"synthetic_response": i}
        record = {
            "request": request,
            "response": response,
            "evidence_verification": {
                "logical_calls": 1,
                "stages": [{"kind": "draft", "record": {"request": request, "response": response}}],
            },
        }
        entry = {
            "case_id": f"synthetic-{i}",
            "result": record,
            "full_judge_record_sha256": campaign.driver.digest(record),
        }
        full.append(entry)
        compact.append(
            {
                **entry,
                "result": {k: v for k, v in record.items() if k not in ("request", "response")},
            }
        )
        requests.append(request)
        responses.append(response)
    journal(directory / "cap.attempts.jsonl", rows)
    journal(directory / "judge_requests/requests.jsonl", requests)
    journal(directory / "judge_requests/responses.jsonl", responses)
    journal(directory / "judgments.jsonl", full)
    journal(directory / "ledger.judge.jsonl", [{"event": "call"} for _ in requests])
    result = {
        "decision": "JUDGE_GATE_READY" if ready else "JUDGE_GATE_NOT_READY",
        "cases_completed": 21,
        "cases_expected": 21,
        "interruption": None,
        "outcomes": compact,
        "freeze": {"prereg_commit": "a" * 40},
    }
    sha = put(directory / "result.json", result)
    put(
        p["FROZEN"] / "independent_audit.json",
        {
            "round": index,
            "integrity": "PASS",
            "judge_ready": ready,
            "private_result_sha256": sha,
            "checks": {"synthetic_independent_check": True},
        },
    )
    return p


def fake_git(campaign: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def git(*args: str) -> str:
        if args[0] == "show":
            return str((campaign.ROOT / args[1].split(":", 1)[1]).read_text())
        return "a" * 40 if args[0] == "log" else ""

    monkeypatch.setattr(campaign.driver, "git", git)


def test_prepare_copies_exact23_preserves_four_old_caps_and_never_creates_paid_state(
    campaign: Any,
) -> None:
    old = {p: p.read_bytes() for p in campaign.ROOT.rglob("*") if p.is_file()}
    p = prepared(campaign)
    carry = campaign.verify_carryover(1)
    assert carry["prior_committed_usd"] == pytest.approx(1.44588620)
    assert carry["validation_round_cap_usd"] == 2.5
    assert len(carry["prior_runs"]) == 4
    assert campaign.verify_copied_inputs(1) is None
    inventory = json.loads((p["FROZEN"] / "copied_private_inputs.json").read_bytes())
    assert len(inventory["files"]) == 23
    assert {p: p.read_bytes() for p in old} == old
    assert not (p["VALIDATION"] / "cap.json").exists()
    assert not (p["FROZEN"] / "source_manifest.json").exists()
    assert not p["VALIDATION_PREREG"].exists()
    assert not list(campaign.OLD_BASE.rglob("*.lock"))
    with pytest.raises(ConfigError, match="already prepared"):
        campaign.prepare_round(1)


@pytest.mark.parametrize("index", [0, 1, 2, 3])
@pytest.mark.parametrize("kind", ["cap.json", "result.json", "cap.attempts.jsonl"])
def test_all_four_prior_bytes_bound(campaign: Any, index: int, kind: str) -> None:
    prepared(campaign)
    path = campaign.ROOT / "runs" / campaign.PRIOR_NAMES[index] / "private/validation" / kind
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ConfigError, match="bytes changed"):
        campaign.verify_carryover(1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("combined_cap_usd", 21),
        ("max_rounds", 6),
        ("validation_round_cap_usd", 3),
        ("prior_committed_usd", 0),
        ("engineering_max_usd", 18),
    ],
)
def test_campaign_caps_cannot_reset_or_expand(campaign: Any, field: str, value: Any) -> None:
    p = prepared(campaign)
    path = p["FROZEN"] / "carryover.json"
    carry = json.loads(path.read_bytes())
    carry[field] = value
    put(path, carry)
    with pytest.raises(ConfigError):
        campaign.verify_carryover(1)


@pytest.mark.parametrize("index", [0, 6, True, 1.0])
def test_at_most_five_integer_rounds(campaign: Any, index: Any) -> None:
    with pytest.raises(ConfigError):
        campaign.paths(index)


def test_predecessor_failed_retry_reservation_is_carried_without_refund(
    campaign: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared(campaign)
    completed_round(campaign, actual=0.2, uncertain=0.05)
    fake_git(campaign, monkeypatch)
    before = {p: p.read_bytes() for p in campaign.paths(1)["BASE"].rglob("*") if p.is_file()}
    campaign.prepare_round(2)
    carry = campaign.verify_carryover(2)
    assert carry["prior_committed_usd"] == pytest.approx(1.44588620 + 0.25)
    assert carry["validation_round_cap_usd"] == 2.5
    assert {p: p.read_bytes() for p in before} == before
    with pytest.raises(ConfigError, match="later round"):
        campaign.verify_carryover(1)


@pytest.mark.parametrize(
    "mutation",
    [
        "ready",
        "interruption",
        "missing_outcome",
        "inflight",
        "stopped",
        "audit_failed",
        "audit_unready_mismatch",
        "unreconciled_cost",
        "orphan",
        "too_many_logical",
        "engineering_started",
    ],
)
def test_bad_or_successful_predecessor_blocks_next_round_before_copy(
    campaign: Any, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    prepared(campaign)
    p = completed_round(campaign)
    fake_git(campaign, monkeypatch)
    result = json.loads((p["VALIDATION"] / "result.json").read_bytes())
    cap = json.loads((p["VALIDATION"] / "cap.json").read_bytes())
    audit = json.loads((p["FROZEN"] / "independent_audit.json").read_bytes())
    if mutation == "ready":
        result["decision"] = "JUDGE_GATE_READY"
    elif mutation == "interruption":
        result["interruption"] = {"kind": "infra"}
    elif mutation == "missing_outcome":
        result["cases_completed"] = 20
    elif mutation == "inflight":
        cap["inflight"] = {"unknown": 0.03}
    elif mutation == "stopped":
        cap["stopped"] = "cost_cap"
    elif mutation == "unreconciled_cost":
        cap["uncertain_usd"] = 0
    elif mutation == "audit_failed":
        audit["integrity"] = "FAIL"
    elif mutation == "audit_unready_mismatch":
        audit["judge_ready"] = True
    elif mutation == "engineering_started":
        put(p["RUN"] / "cap.json", {})
    elif mutation == "orphan":
        path = p["VALIDATION"] / "cap.attempts.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        rows.pop()
        journal(path, rows)
    else:
        path = p["VALIDATION"] / "judge_requests/requests.jsonl"
        journal(path, [{"extra": i} for i in range(85)])
    put(p["VALIDATION"] / "result.json", result)
    put(p["VALIDATION"] / "cap.json", cap)
    put(p["FROZEN"] / "independent_audit.json", audit)
    with pytest.raises(ConfigError):
        campaign.prepare_round(2)
    assert not campaign.paths(2)["BASE"].exists()
    assert not campaign.paths(2)["FROZEN"].exists()


def test_campaign_lock_rejects_concurrent_stage(campaign: Any) -> None:
    with (
        campaign.campaign_lock(),
        pytest.raises(ConfigError, match="another campaign"),
        campaign.campaign_lock(),
    ):
        pytest.fail("second process lock admitted")


def test_all_low_and_phase_functions_remain_identical_and_bindings_restore(campaign: Any) -> None:
    prepared(campaign)
    names = (
        "validate",
        "freeze_validation",
        "replay_saved",
        "adapt",
        "report",
        "run_task",
        "confirm",
        "scoped_three_call_budget",
        "require_pass",
        "make_screen",
        "make_judge",
        "config",
        "decision_for",
    )
    original = {name: getattr(campaign.driver, name) for name in names}
    old_limits = campaign.driver.STAGE_LIMITS
    old_judge = campaign.driver.LLMPrivilegeJudge
    old_method = campaign.driver.METHOD
    with pytest.raises(RuntimeError, match="synthetic"), campaign.bound_driver(1):
        assert {name: getattr(campaign.driver, name) for name in names} == original
        assert campaign.driver.STAGE_LIMITS == {"validation": 2.5, "engineering": 17.0}
        assert old_method == campaign.driver.METHOD
        assert campaign.driver.LLMPrivilegeJudge is campaign.WitnessCheckingPrivilegeJudge
        assert "scripts/audit_llm_privilege_evidence.py" in campaign.driver.FROZEN_INPUTS
        raise RuntimeError("synthetic")
    assert campaign.driver.STAGE_LIMITS is old_limits
    assert campaign.driver.LLMPrivilegeJudge is old_judge


def write_budget(campaign: Any, p: dict[str, Path]) -> None:
    carry_path = p["FROZEN"] / "carryover.json"
    carry = json.loads(carry_path.read_bytes())
    cap_path = p["VALIDATION"] / "cap.json"
    cap = json.loads(cap_path.read_bytes())
    current = Decimal(str(cap["actual_usd"])) + Decimal(str(cap["uncertain_usd"]))
    prior = Decimal(str(carry["prior_committed_usd"]))
    put(
        p["FROZEN"] / "engineering_budget.json",
        {
            "schema_version": 1,
            "round_index": 1,
            "prior_committed_usd": float(prior),
            "validation_committed_usd": float(current),
            "engineering_cap_usd": float(min(Decimal(17), Decimal(20) - prior - current)),
            "combined_cap_usd": 20.0,
            "validation_cap_sha256": hashlib.sha256(cap_path.read_bytes()).hexdigest(),
            "validation_result_sha256": hashlib.sha256(
                (p["VALIDATION"] / "result.json").read_bytes()
            ).hexdigest(),
            "carryover_sha256": hashlib.sha256(carry_path.read_bytes()).hexdigest(),
        },
    )


def test_engineering_cap_uses_remaining_total_preserves_validation_limit(campaign: Any) -> None:
    prepared(campaign)
    p = completed_round(campaign, ready=True, actual=2.0, uncertain=0.1)
    write_budget(campaign, p)
    budget = campaign.engineering_budget(1)
    assert budget["engineering_cap_usd"] == pytest.approx(20 - 1.44588620 - 2.1)
    with campaign.bound_driver(1):
        assert campaign.driver.STAGE_LIMITS["validation"] == 2.5
        assert campaign.driver.STAGE_LIMITS["engineering"] < 17
    path = p["FROZEN"] / "engineering_budget.json"
    budget["engineering_cap_usd"] = 17
    put(path, budget)
    with pytest.raises(ConfigError, match="cumulative budget"):
        campaign.engineering_budget(1)


def test_child_policy_uses_derived_cap_and_denies_before_transport(
    campaign: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = prepared(campaign)
    cap_path = p["RUN"] / "cap.json"
    limit = 16.4541138
    put(
        cap_path,
        {
            "stage": "engineering",
            "limit_usd": limit,
            "cap_path": str(cap_path),
            "actual_usd": limit - 0.000001,
            "uncertain_usd": 0,
            "inflight": {},
            "attempts": 0,
        },
    )
    invoked: list[Any] = []
    monkeypatch.setattr(
        campaign, "engineering_budget", lambda *a, **kw: {"engineering_cap_usd": limit}
    )

    def initialize(self: Any, **kwargs: Any) -> None:
        invoked.append(kwargs)
        self._client = SimpleNamespace(
            _transport=lambda **wire: pytest.fail("cap denied before API")
        )

    monkeypatch.setattr(campaign.AeaLLMClient, "__init__", initialize)
    client = campaign.CappedPolicyClient(cap_path=str(cap_path), frozen_policy="same")
    assert invoked == [{"frozen_policy": "same"}]
    old_limits = campaign.driver.STAGE_LIMITS
    attribution = Attribution(
        phase="adapt", budget="search", arm=campaign.driver.ARM, task_id="154"
    )
    with attributed(attribution, seed=0), pytest.raises(InfraError):
        client._client._transport(model="deepseek-v4-flash", messages=[], max_tokens=1)
    assert campaign.driver.STAGE_LIMITS is old_limits
    cap = json.loads(cap_path.read_bytes())
    assert cap["attempts"] == 0 and cap["stopped"] == "cost_cap"


def test_build_changes_only_factory_path(campaign: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    sub = SimpleNamespace(
        policy_spec_kwargs={
            "client_factory": "old",
            "client_kwargs": {"cap_path": "unchanged"},
            "model": "frozen",
        }
    )
    seen = []

    def original_build(**kwargs: Any) -> Any:
        seen.append(kwargs)
        return sub

    monkeypatch.setattr(campaign, "ORIGINAL_BUILD", original_build)
    assert campaign._build(designer=True) is sub
    assert seen == [{"designer": True}]
    assert sub.policy_spec_kwargs == {
        "client_factory": "scripts.e6_iterative_low_llm_judge_evidence:CappedPolicyClient",
        "client_kwargs": {"cap_path": "unchanged"},
        "model": "frozen",
    }


@pytest.mark.parametrize("ready", [False, True])
def test_freeze_requires_independent_ready_audit_and_budget_is_write_once(
    campaign: Any, monkeypatch: pytest.MonkeyPatch, ready: bool
) -> None:
    prepared(campaign)
    p = completed_round(campaign, ready=True, actual=2.0, uncertain=0)
    audit_path = p["FROZEN"] / "independent_audit.json"
    audit = json.loads(audit_path.read_bytes())
    audit["judge_ready"] = ready
    put(audit_path, audit)
    calls = []

    def freeze() -> None:
        calls.append("freeze")
        p["PREREG"].parent.mkdir(parents=True, exist_ok=True)
        p["PREREG"].write_text(
            "Hard physical cap: USD 17. docs/design/AEA_LLM_PRIVILEGE_JUDGE.md\n"
        )

    monkeypatch.setattr(campaign.driver, "freeze_validation", freeze)
    if not ready:
        with pytest.raises(ConfigError, match="independent passing"):
            campaign.freeze_round(1)
        assert calls == []
    else:
        campaign.freeze_round(1)
        assert calls == ["freeze"]
        assert "USD 17." not in p["PREREG"].read_text()
        assert "engineering_budget" not in campaign.EXTRA_FROZEN_INPUTS
        with pytest.raises(ConfigError, match="already frozen"):
            campaign.freeze_round(1)


def test_strict_acceptance_rejects_generated_uncertainty_even_in_unlabeled_case(
    campaign: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.test_privilege_witness import CompletionQueue, Reply, decision, evidence

    prepared(campaign)
    p = campaign.paths(1)
    cases, outcomes, full = [], [], []
    for i in range(21):
        item = evidence()
        payload = (json.dumps(item.model_dump(mode="json"), sort_keys=True) + "\n").encode()
        input_sha = hashlib.sha256(payload).hexdigest()
        name = f"judge_inputs/{input_sha}.json"
        (p["PRIVATE"] / name).write_bytes(payload)
        repeat = f"case-{i - 4}" if 17 <= i <= 20 else None
        case = {
            "case_id": f"case-{i}",
            "expected_verdict": None if i == 0 else "PASS",
            "repeat_of": repeat,
            "input_file": name,
            "input_file_sha256": input_sha,
        }
        queue = CompletionQueue(Reply("judge", {} if i == 0 else decision("PASS")))
        record = (
            campaign.WitnessCheckingPrivilegeJudge(
                queue,
                attribution=Attribution(
                    phase="judge_validation", budget="none", arm=campaign.driver.ARM, task_id="154"
                ),
            )
            .judge(item)
            .as_record()
        )
        row = {
            "case_id": case["case_id"],
            "result": record,
            "full_judge_record_sha256": campaign.driver.digest(record),
        }
        full.append(row)
        outcomes.append(
            {**row, "result": {k: v for k, v in record.items() if k not in ("request", "response")}}
        )
        cases.append(case)
    journal(p["VALIDATION"] / "judgments.jsonl", full)
    assert campaign.ORIGINAL_VALIDATION_DECISION(cases, outcomes)["decision"] == "JUDGE_GATE_READY"
    with campaign.bound_driver(1):
        assert (
            campaign.strict_validation_decision(cases, outcomes)["decision"]
            == "JUDGE_GATE_NOT_READY"
        )
    full[1]["result"]["evidence_verification"]["logical_calls"] = 5
    outcomes[1]["result"]["evidence_verification"]["logical_calls"] = 5
    sha = campaign.driver.digest(full[1]["result"])
    full[1]["full_judge_record_sha256"] = outcomes[1]["full_judge_record_sha256"] = sha
    journal(p["VALIDATION"] / "judgments.jsonl", full)
    with campaign.bound_driver(1), pytest.raises(ConfigError):
        campaign.strict_validation_decision(cases, outcomes)


def test_failed_main_exits_two_without_private_prose_or_engineering(
    campaign: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    monkeypatch.setattr(
        campaign,
        "run_stage",
        lambda *args: {"decision": "JUDGE_GATE_NOT_READY", "private": "PRIVATE_CANARY"},
    )
    monkeypatch.setattr(sys, "argv", ["evidence", "--round", "1", "--stage", "validate"])
    assert campaign.main() == 2
    assert "PRIVATE_CANARY" not in capsys.readouterr().out
    assert not campaign.paths(1)["RUN"].exists()


@pytest.fixture
def interrupted_r1(campaign: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    prepared(campaign)
    p = completed_round(campaign, actual=0.58990976, uncertain=0.46601632)
    fake_git(campaign, monkeypatch)
    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    full: list[dict[str, Any]] = []
    compact: list[dict[str, Any]] = []
    for index in range(19):
        calls: list[dict[str, Any]] = []
        for _ in range(3 if index < 4 else 2):
            request = {"synthetic_request": len(requests)}
            response = {"synthetic_response": len(responses)}
            requests.append(request)
            responses.append(response)
            calls.append({"kind": "draft", "record": {"request": request, "response": response}})
        record = {
            "request": calls[-1]["record"]["request"],
            "response": calls[-1]["record"]["response"],
            "decision": {"verdict": "UNCERTAIN"},
            "evidence_verification": {"logical_calls": len(calls), "stages": calls},
        }
        row = {
            "case_id": "saved_159_C1" if index == 18 else f"case-{index}",
            "result": record,
            "full_judge_record_sha256": campaign.driver.digest(record),
        }
        full.append(row)
        compact.append(
            {
                **row,
                "result": {
                    key: value
                    for key, value in record.items()
                    if key not in ("request", "response")
                },
            }
        )
    assert len(requests) == 42
    directory = p["VALIDATION"]
    journal(directory / "judge_requests/requests.jsonl", requests)
    journal(directory / "judge_requests/responses.jsonl", responses)
    journal(directory / "judgments.jsonl", full)
    journal(
        directory / "ledger.judge.jsonl",
        [{"event": "call"} for _ in requests] + [{"event": "infra_retry"}],
    )
    attribution = {
        "phase": "judge_validation",
        "arm": campaign.driver.ARM,
        "budget": "none",
        "task_id": "154",
    }
    rows: list[dict[str, Any]] = []
    for index in range(43):
        fields = {
            "attempt": str(index),
            "model": "deepseek-v4-flash",
            "stage": "validation",
            "attribution": attribution,
            "seed": 0,
            "reserved_usd": 0.46601632 if index == 0 else 0.6,
        }
        terminal = (
            {**fields, "status": "ambiguous_failure"}
            if index == 0
            else {
                **fields,
                "status": "returned",
                "conservative_usd": 0.58990976 if index == 1 else 0.0,
            }
        )
        rows.extend([{**fields, "status": "reserved"}, terminal])
    journal(directory / "cap.attempts.jsonl", rows)
    put(
        directory / "cap.json",
        {
            "stage": "validation",
            "limit_usd": 2.5,
            "cap_path": str(directory / "cap.json"),
            "actual_usd": 0.58990976,
            "uncertain_usd": 0.46601632,
            "inflight": {},
            "attempts": 43,
            "stopped": "implementation",
        },
    )
    result = {
        "decision": "IMPLEMENTATION_FAILURE",
        "cases_completed": 19,
        "cases_expected": 21,
        "interruption": {
            "kind": "implementation",
            "reason": "synthetic diagnostic order",
            "type": "ConfigError",
        },
        "outcomes": compact,
        "freeze": {"prereg_commit": campaign.R1_PREREG_COMMIT},
    }
    result_sha = put(directory / "result.json", result)
    checks = dict.fromkeys(campaign.R1_EXPECTED_AUDIT_FAILURES, False)
    checks["operational_decision_precedence"] = True
    audit = {
        "schema_version": 1,
        "round": 1,
        "integrity": "FAIL",
        "judge_ready": False,
        "accounting_integrity": "PASS",
        "interruption_class": "NONDETERMINISTIC_VALIDATION_ERROR_TEXT",
        "recorded_decision": "IMPLEMENTATION_FAILURE",
        "cases_completed": 19,
        "cases_expected": 21,
        "exact_final_records": 18,
        "logical_calls": 42,
        "physical_attempts": 43,
        "all_recorded_requests_exact": True,
        "all_recorded_responses_unchanged": True,
        "all_recorded_verdicts_unchanged": True,
        "private_result_sha256": result_sha,
        "diagnostic_only_case_ids": ["saved_159_C1"],
        "diagnostic_only_paths": campaign.R1_DIAGNOSTIC_PATHS,
        "checks": checks,
        "check_count": len(checks),
        "failed_checks": sorted(campaign.R1_EXPECTED_AUDIT_FAILURES),
        "conservative_actual_usd": 0.58990976,
        "uncertain_usd": 0.46601632,
        "stage_limit_usd": 2.5,
    }
    audit_path = p["FROZEN"] / "independent_audit.json"
    audit_sha = put(audit_path, audit)
    hashes = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in campaign.NEW_RECEIPT_FILES
    }
    monkeypatch.setattr(campaign, "R1_ARCHIVE_SHA256", hashes)
    monkeypatch.setattr(campaign, "R1_AUDIT_SHA256", audit_sha)
    source_hashes = {}
    for name in campaign.REPAIR_SOURCE_PATHS:
        source_hashes[name] = put(
            campaign.ROOT / name, {"synthetic": "fixed deterministic error serialization"}
        )
    manifest_path, repair_path = campaign.continuation_inputs()
    repair_sha = put(
        repair_path,
        {
            "schema_version": 1,
            "status": "PASS",
            "regression": "stable-validation-error-serialization",
            "tests_passed": 4,
            "requests_responses_verdicts_unchanged": True,
            "malformed_outputs_remain_uncertain": True,
            "source_hashes": source_hashes,
        },
    )
    put(
        manifest_path,
        {
            "schema_version": 1,
            "policy": campaign.CONTINUATION_POLICY,
            "from_round": 1,
            "next_round": 2,
            "archived_prereg_commit": campaign.R1_PREREG_COMMIT,
            "archived_result": "IMPLEMENTATION_FAILURE",
            "interruption_class": "NONDETERMINISTIC_VALIDATION_ERROR_TEXT",
            "archive_files": {
                str((directory / name).relative_to(campaign.ROOT)): sha
                for name, sha in hashes.items()
            },
            "interruption_audit": {
                "path": str(audit_path.relative_to(campaign.ROOT)),
                "sha256": audit_sha,
            },
            "repair_test_report": {
                "path": str(repair_path.relative_to(campaign.ROOT)),
                "sha256": repair_sha,
            },
            "preserve_operational_failure": True,
            "resume_old_namespace": False,
            "prior_committed_usd": 2.50181228,
            "round_limit_usd": 2.5,
            "combined_cap_usd": 20.0,
            "maximum_round": 5,
        },
    )
    return campaign


def test_exact_archived_interruption_continues_only_new_round_with_all_costs(
    interrupted_r1: Any,
) -> None:
    campaign = interrupted_r1
    old = {
        path: path.read_bytes()
        for key in ("BASE", "FROZEN")
        for path in campaign.paths(1)[key].rglob("*")
        if path.is_file()
    }
    campaign.prepare_round(2)
    carry = campaign.verify_carryover(2)
    assert carry["prior_committed_usd"] == pytest.approx(2.50181228)
    assert carry["validation_round_cap_usd"] == 2.5
    assert {path: path.read_bytes() for path in old} == old
    with campaign.bound_driver(2):
        for path in campaign.continuation_inputs():
            assert str(path.relative_to(campaign.ROOT)) in campaign.driver.FROZEN_INPUTS
    assert not (campaign.paths(2)["VALIDATION"] / "cap.json").exists()
    with pytest.raises(ConfigError, match="already prepared"):
        campaign.prepare_round(2)


@pytest.mark.parametrize(
    "field,value",
    [
        ("from_round", 2),
        ("next_round", 3),
        ("resume_old_namespace", True),
        ("preserve_operational_failure", False),
        ("archived_result", "JUDGE_GATE_NOT_READY"),
        ("interruption_class", "PROVIDER_TIMEOUT"),
        ("prior_committed_usd", 1.4458862),
        ("round_limit_usd", 3.0),
        ("maximum_round", 6),
    ],
)
def test_narrow_continuation_manifest_cannot_expand_scope(
    interrupted_r1: Any, field: str, value: Any
) -> None:
    campaign = interrupted_r1
    path, _ = campaign.continuation_inputs()
    manifest = json.loads(path.read_bytes())
    manifest[field] = value
    put(path, manifest)
    with pytest.raises(ConfigError):
        campaign.prepare_round(2)
    assert not campaign.paths(2)["BASE"].exists()


@pytest.mark.parametrize("kind", ["manifest", "repair", "audit", "unpublished"])
def test_missing_or_unpublished_continuation_proof_stops(
    interrupted_r1: Any, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    campaign = interrupted_r1
    manifest, repair = campaign.continuation_inputs()
    if kind == "manifest":
        manifest.unlink()
    elif kind == "repair":
        repair.unlink()
    elif kind == "audit":
        (campaign.paths(1)["FROZEN"] / "independent_audit.json").unlink()
    else:

        def unpublished(*args: Any) -> str:
            raise ConfigError("unpublished audit")

        monkeypatch.setattr(campaign.driver, "git", unpublished)
    with pytest.raises(ConfigError):
        campaign.prepare_round(2)
    assert not campaign.paths(2)["BASE"].exists()


@pytest.mark.parametrize(
    "name",
    [
        "cap.json",
        "result.json",
        "cap.attempts.jsonl",
        "judgments.jsonl",
        "judge_requests/requests.jsonl",
        "judge_requests/responses.jsonl",
        "ledger.judge.jsonl",
    ],
)
def test_even_rehashed_different_interruption_archive_stops(interrupted_r1: Any, name: str) -> None:
    campaign = interrupted_r1
    path = campaign.paths(1)["VALIDATION"] / name
    path.write_bytes(path.read_bytes() + b" ")
    # prepare constructs new receipt hashes itself; immutable approved hashes still win.
    with pytest.raises(ConfigError, match="exact authorized"):
        campaign.prepare_round(2)


@pytest.mark.parametrize(
    "change",
    [
        "promote_integrity",
        "ready",
        "new_failure",
        "relabel_failure",
        "wrong_case",
        "changed_requests",
        "missing_precedence",
    ],
)
def test_truthful_failure_audit_cannot_be_promoted_or_broadened(
    interrupted_r1: Any, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    campaign = interrupted_r1
    path = campaign.paths(1)["FROZEN"] / "independent_audit.json"
    audit = json.loads(path.read_bytes())
    if change == "promote_integrity":
        audit["integrity"] = "PASS"
    elif change == "ready":
        audit["judge_ready"] = True
    elif change == "new_failure":
        audit["checks"]["unexplained"] = False
        audit["failed_checks"].append("unexplained")
        audit["check_count"] += 1
    elif change == "relabel_failure":
        audit["recorded_decision"] = "JUDGE_GATE_NOT_READY"
    elif change == "wrong_case":
        audit["diagnostic_only_case_ids"] = ["saved_154_C1"]
    elif change == "changed_requests":
        audit["all_recorded_requests_exact"] = False
    else:
        audit["checks"]["operational_decision_precedence"] = False
    sha = put(path, audit)
    monkeypatch.setattr(campaign, "R1_AUDIT_SHA256", sha)
    manifest, _ = campaign.continuation_inputs()
    row = json.loads(manifest.read_bytes())
    row["interruption_audit"]["sha256"] = sha
    put(manifest, row)
    with pytest.raises(ConfigError):
        campaign.prepare_round(2)


@pytest.mark.parametrize(
    "change", ["failed", "zero_tests", "unsafe_pass", "changed_verdict", "wrong_source"]
)
def test_repair_report_requires_pass_with_exact_source_binding(
    interrupted_r1: Any, change: str
) -> None:
    campaign = interrupted_r1
    manifest, repair = campaign.continuation_inputs()
    report = json.loads(repair.read_bytes())
    if change == "failed":
        report["status"] = "FAIL"
    elif change == "zero_tests":
        report["tests_passed"] = 0
    elif change == "unsafe_pass":
        report["malformed_outputs_remain_uncertain"] = False
    elif change == "changed_verdict":
        report["requests_responses_verdicts_unchanged"] = False
    else:
        report["source_hashes"][campaign.REPAIR_SOURCE_PATHS[0]] = "f" * 64
    sha = put(repair, report)
    row = json.loads(manifest.read_bytes())
    row["repair_test_report"]["sha256"] = sha
    put(manifest, row)
    with pytest.raises(ConfigError):
        campaign.prepare_round(2)


def test_stopped_cap_exception_cannot_apply_to_any_other_cap(interrupted_r1: Any) -> None:
    campaign = interrupted_r1
    path = campaign.paths(1)["VALIDATION"]
    with pytest.raises(ConfigError):
        campaign.physical_accounting(path, Decimal("2.5"))
    assert (
        campaign.physical_accounting(path, Decimal("2.5"), expected_stop="implementation")[
            "physical_attempts"
        ]
        == 43
    )
    with pytest.raises(ConfigError):
        campaign.physical_accounting(path, Decimal("2.5"), expected_stop="cost_cap")
    with pytest.raises(ConfigError):
        campaign.physical_accounting(
            campaign.paths(2)["VALIDATION"], Decimal("2.5"), expected_stop="implementation"
        )


def test_next_interruption_does_not_inherit_r1_exception(interrupted_r1: Any) -> None:
    campaign = interrupted_r1
    campaign.prepare_round(2)
    p = completed_round(campaign, index=2)
    result_path = p["VALIDATION"] / "result.json"
    row = json.loads(result_path.read_bytes())
    row["decision"] = "IMPLEMENTATION_FAILURE"
    row["interruption"] = {"kind": "implementation"}
    put(result_path, row)
    # Bind the prior repair source manifest now that Round 2 has a paid-cap marker.
    _, repair_path = campaign.continuation_inputs()
    put(
        p["FROZEN"] / "source_manifest.json",
        {"source_hashes": json.loads(repair_path.read_bytes())["source_hashes"]},
    )
    p["VALIDATION_PREREG"].write_text("synthetic published preregistration")
    with pytest.raises(ConfigError):
        campaign.prepare_round(3)
    assert not campaign.paths(3)["BASE"].exists()
