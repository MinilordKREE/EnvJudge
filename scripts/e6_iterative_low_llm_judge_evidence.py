"""Run at most five frozen evidence-verification rounds within one USD 20 campaign.

Prepare copies existing bytes offline. Each paid round requires its own published
preregistration. The unchanged common driver owns validation, admission and LOW;
this launcher binds storage, witness verification and conservative monetary limits.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import e6_iterative_low_llm_judge as driver
from scripts import e6_iterative_low_llm_judge_prompt4 as previous

from aea.errors import ConfigError
from aea.llm.envharness_client import AeaLLMClient
from aea.privilege_judge import JudgeRecord, PrivilegeJudgeInput, canonical_json
from aea.privilege_witness import WitnessCheckingPrivilegeJudge, validate_witness_record

ROOT = driver.ROOT
BASE = ROOT / "runs/e6-iterative-low-llm-judge-evidence"
FROZEN_BASE = ROOT / "experiments/alfworld_e6/frozen/iterative_low_llm_judge_evidence"
OLD_BASE = ROOT / "runs/e6-iterative-low-llm-judge"
OLD_FROZEN = ROOT / "experiments/alfworld_e6/frozen/iterative_low_llm_judge"
IMPLEMENTATION = "candidate-witness-v1"
MAX_ROUNDS = 5
COMBINED_CAP = Decimal("20")
ROUND_CAP = Decimal("2.5")
ENGINEERING_MAX = Decimal("17")
TOLERANCE = Decimal("0.000000000001")
BASE_DRIVER_SHA256 = previous.BASE_DRIVER_SHA256
PRIOR_COMMITS = (*previous.PRIOR_VALIDATION_COMMITS, "1f0a0e876a9c3656b39b0b524acb16b68d15f36c")
PRIOR_AMOUNTS = (*previous.PRIOR_RUN_COMMITTED_USD, Decimal("0.35397824"))
PRIOR_LIMITS = (*previous.PRIOR_RUN_LIMITS_USD, Decimal("1.90809204"))
PRIOR_NAMES = (
    "e6-iterative-low-llm-judge",
    "e6-iterative-low-llm-judge-prompt2",
    "e6-iterative-low-llm-judge-prompt3",
    "e6-iterative-low-llm-judge-prompt4",
)
STAGES = ("prepare", "validate", "freeze", "replay", "adapt", "report")
EXTRA_FROZEN_INPUTS = (
    "scripts/e6_iterative_low_llm_judge_evidence.py",
    "scripts/e6_iterative_low_llm_judge_prompt4.py",
    "scripts/audit_llm_privilege_evidence.py",
    "docs/design/AEA_LLM_PRIVILEGE_JUDGE_EVIDENCE.md",
)
ORIGINAL_BUILD = driver.build
ORIGINAL_VALIDATION_DECISION = driver.validation_decision
RECEIPT_FILES = ("cap.json", "result.json", "cap.attempts.jsonl")
NEW_RECEIPT_FILES = (
    *RECEIPT_FILES,
    "judgments.jsonl",
    "judge_requests/requests.jsonl",
    "judge_requests/responses.jsonl",
    "ledger.judge.jsonl",
)


def paths(round_index: int) -> dict[str, Path]:
    if type(round_index) is not int or not 1 <= round_index <= MAX_ROUNDS:
        raise ConfigError("campaign round must be an integer in 1..5")
    base = BASE / f"round-{round_index}"
    exp = ROOT / "experiments/alfworld_e6"
    prefix = f"PREREG_ITERATIVE_LOW_LLM_JUDGE_EVIDENCE_R{round_index}"
    return {
        "BASE": base,
        "PRIVATE": base / "private",
        "RUN": base / "private/engineering",
        "VALIDATION": base / "private/validation",
        "FROZEN": FROZEN_BASE / f"round-{round_index}",
        "VALIDATION_PREREG": exp / f"{prefix}_VALIDATION.md",
        "PREREG": exp / f"{prefix}_ENGINEERING.md",
    }


def _read(path: Path) -> bytes:
    if not path.is_relative_to(ROOT) or any(p.is_symlink() for p in (path, *path.parents)):
        raise ConfigError("campaign input path escapes repository or uses a symlink")
    if not path.is_file():
        raise ConfigError("campaign immutable input is missing")
    return path.read_bytes()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError("invalid campaign monetary value")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ConfigError("invalid campaign monetary value")
    return amount


def _hashed(path: Path, expected: Any) -> bytes:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ConfigError("invalid campaign immutable hash")
    payload = _read(path)
    if _sha(payload) != expected:
        raise ConfigError("campaign immutable bytes changed")
    return payload


def _json(path: Path) -> Any:
    return json.loads(_read(path))


def _rows(payload: bytes) -> list[dict[str, Any]]:
    values = [json.loads(line) for line in payload.splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in values):
        raise ConfigError("invalid physical or logical journal row")
    return values


def _receipt(base: Path, *, campaign_round: int | None = None) -> dict[str, Any]:
    directory = base / "private/validation"
    result = _json(directory / "result.json")
    cap = _json(directory / "cap.json")
    names = NEW_RECEIPT_FILES if campaign_round is not None else RECEIPT_FILES
    receipt = {
        "namespace": str(base.relative_to(ROOT)),
        "validation_limit_usd": cap["limit_usd"],
        "committed_usd": float(_number(cap["actual_usd"]) + _number(cap["uncertain_usd"])),
        "prereg_commit": result["freeze"]["prereg_commit"],
        "files": {
            name: {
                "path": str((directory / name).relative_to(ROOT)),
                "sha256": _sha(_read(directory / name)),
            }
            for name in names
        },
    }
    if campaign_round is not None:
        audit = paths(campaign_round)["FROZEN"] / "independent_audit.json"
        receipt["independent_audit"] = {
            "path": str(audit.relative_to(ROOT)),
            "sha256": _sha(_read(audit)),
        }
    return receipt


def _receipt_payloads(row: Any, base: Path, *, new: bool) -> dict[str, bytes]:
    expected = {"namespace", "validation_limit_usd", "committed_usd", "prereg_commit", "files"}
    if new:
        expected.add("independent_audit")
    if not isinstance(row, dict) or set(row) != expected:
        raise ConfigError("campaign receipt schema changed")
    if row["namespace"] != str(base.relative_to(ROOT)):
        raise ConfigError("campaign receipt namespace changed")
    if not isinstance(row["prereg_commit"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", row["prereg_commit"]
    ):
        raise ConfigError("invalid prior preregistration commit")
    names = NEW_RECEIPT_FILES if new else RECEIPT_FILES
    if not isinstance(row["files"], dict) or set(row["files"]) != set(names):
        raise ConfigError("campaign receipt file membership changed")
    payloads = {}
    for name in names:
        entry = row["files"][name]
        path = base / "private/validation" / name
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "sha256"}
            or entry["path"] != str(path.relative_to(ROOT))
        ):
            raise ConfigError("campaign receipt file path changed")
        payloads[name] = _hashed(path, entry["sha256"])
    return payloads


def _verify_old(row: dict[str, Any], index: int) -> None:
    base = ROOT / "runs" / PRIOR_NAMES[index]
    _receipt_payloads(row, base, new=False)
    if _number(row["validation_limit_usd"]) != PRIOR_LIMITS[index]:
        raise ConfigError("historical validation limit changed")
    legacy = {"prior_commit": row["prereg_commit"], "prior_committed_usd": row["committed_usd"]}
    for kind, filename in zip(("cap", "result", "attempts"), RECEIPT_FILES, strict=True):
        legacy[f"prior_validation_{kind}_path"] = row["files"][filename]["path"]
        legacy[f"prior_validation_{kind}_sha256"] = row["files"][filename]["sha256"]
    with _bindings(previous, {"ROOT": ROOT}):
        previous._verify_prior_run(
            legacy, base, PRIOR_COMMITS[index], PRIOR_AMOUNTS[index], PRIOR_LIMITS[index]
        )


def physical_accounting(
    directory: Path, limit: Decimal, *, expected_stop: str | None = None
) -> dict[str, Any]:
    """Read-only reconciliation: every failed request retains its full reservation."""
    if expected_stop is not None and (
        expected_stop != "implementation"
        or directory != paths(1)["VALIDATION"]
        or _sha(_read(directory / "cap.json")) != R1_ARCHIVE_SHA256["cap.json"]
    ):
        raise ConfigError("stopped-cap exception is limited to the exact archived Round 1 cap")
    cap = _json(directory / "cap.json")
    if (
        cap.get("stage") != "validation"
        or _number(cap.get("limit_usd")) != limit
        or cap.get("cap_path") != str((directory / "cap.json").resolve())
    ):
        raise ConfigError("validation monetary namespace/limit changed")
    if (
        cap.get("inflight") != {}
        or cap.get("stopped") != expected_stop
        or cap.get("accounting_error")
        or cap.get("bound_violation")
    ):
        raise ConfigError("interrupted or unresolved round cannot advance")
    journal = _rows(_read(directory / "cap.attempts.jsonl"))
    reserved: dict[str, dict[str, Any]] = {}
    terminals: set[str] = set()
    actual, uncertain = Decimal(0), Decimal(0)
    for row in journal:
        key = row.get("attempt")
        if not isinstance(key, str) or not key:
            raise ConfigError("invalid physical attempt identity")
        if (
            row.get("model") != "deepseek-v4-flash"
            or row.get("stage") != "validation"
            or row.get("attribution", {}).get("arm") != driver.ARM
            or row.get("attribution", {}).get("phase") != "judge_validation"
        ):
            raise ConfigError("unauthorized physical validation request")
        status = row.get("status")
        if status == "reserved":
            if key in reserved:
                raise ConfigError("duplicate physical reservation")
            _number(row.get("reserved_usd"))
            reserved[key] = row
        elif status in {"returned", "ambiguous_failure"}:
            if key not in reserved or key in terminals:
                raise ConfigError("orphan or duplicate physical outcome")
            start = reserved[key]
            if any(
                row.get(k) != start.get(k)
                for k in ("model", "stage", "attribution", "seed", "reserved_usd")
            ):
                raise ConfigError("physical outcome attribution/reservation changed")
            terminals.add(key)
            if status == "returned":
                amount = _number(row.get("conservative_usd"))
                if amount > _number(start["reserved_usd"]) + TOLERANCE:
                    raise ConfigError("returned cost exceeded reservation")
                actual += amount
            else:
                uncertain += _number(start["reserved_usd"])
        else:
            raise ConfigError("invalid or failed accounting outcome")
    if (
        terminals != set(reserved)
        or type(cap.get("attempts")) is not int
        or cap["attempts"] != len(reserved)
    ):
        raise ConfigError("unresolved physical attempt journal")
    if (
        abs(_number(cap.get("actual_usd")) - actual) > TOLERANCE
        or abs(_number(cap.get("uncertain_usd")) - uncertain) > TOLERANCE
        or actual + uncertain >= limit
    ):
        raise ConfigError("physical conservative totals do not reconcile")
    return {"committed_usd": float(actual + uncertain), "physical_attempts": len(reserved)}


# This exception identifies one immutable archived failure, not an error class.
R1_PREREG_COMMIT = "17f420c2fdd3a9ecb8dfb15481054813937ea3b8"
R1_AUDIT_SHA256 = "8aefaa00dc879d385db9600f8c4e7a772b49cb2c56d6c36ae7f76d54df26edc4"
R1_ARCHIVE_SHA256 = {
    "cap.json": "a583a603aaf0c506c1d5e8dfc632d35b360c1e0106c1c3605f516c1507d47524",
    "result.json": "19cdc1e0f7fef5e23e08fec2ae8b52fd8dea4394fb3130e00c10e5ea2a876d37",
    "cap.attempts.jsonl": "f577f136bb2cad1ef13641b4433e80b57f3429a29dd2597c8b005ba9af74c59d",
    "judgments.jsonl": "d80b24b560798c708029c6d060746f10a4e8982b0e93e2faf03029f95ffccc32",
    "judge_requests/requests.jsonl": (
        "7889120e4977ca75581b9832ea76aa6f260df3165d2ab8fe56eb10833a743e41"
    ),
    "judge_requests/responses.jsonl": (
        "42759d524bac15edf754cedf912ec92d38ddf200e93f7bee3ee2be712c6844e3"
    ),
    "ledger.judge.jsonl": "99ca38813de6d102b24c12d623f6def860da2f7eece5698348899de9f98aba8b",
}
R1_EXPECTED_AUDIT_FAILURES = {
    "21_final_cases",
    "no_interruption",
    "case_19_exact_final_replay",
    "acceptance_recomputed",
}
R1_DIAGNOSTIC_PATHS = [
    ["decision", "revision_reason"],
    ["evidence_verification", "stages", 1, "record", "generated_uncertainty"],
    ["generated_uncertainty"],
]
CONTINUATION_POLICY = "archived-r1-diagnostic-serialization-continuation-v1"
REPAIR_SOURCE_PATHS = ("src/aea/privilege_judge.py", "src/aea/privilege_witness.py")


def continuation_inputs() -> tuple[Path, Path]:
    return (
        FROZEN_BASE / "round-2-continuation.json",
        FROZEN_BASE / "round-2-repair-tests.json",
    )


def _published_bytes(path: Path, payload: bytes, *, prereg: Path | None = None) -> None:
    relative = str((prereg or path).relative_to(ROOT))
    commit = driver.git("log", "-1", "--format=%H", "--", relative)
    driver.git("merge-base", "--is-ancestor", commit, "origin/aea-llm-vnext")
    if driver.git("show", f"{commit}:{path.relative_to(ROOT)}").strip() != payload.decode().strip():
        raise ConfigError("continuation evidence is not the published artifact")


def _verify_continuation_manifest(audit_entry: dict[str, Any]) -> None:
    manifest_path, repair_path = continuation_inputs()
    manifest = _json(manifest_path)
    expected = {
        "schema_version",
        "policy",
        "from_round",
        "next_round",
        "archived_prereg_commit",
        "archived_result",
        "interruption_class",
        "archive_files",
        "interruption_audit",
        "repair_test_report",
        "preserve_operational_failure",
        "resume_old_namespace",
        "prior_committed_usd",
        "round_limit_usd",
        "combined_cap_usd",
        "maximum_round",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected:
        raise ConfigError("scoped continuation manifest schema changed")
    required = {
        "schema_version": 1,
        "policy": CONTINUATION_POLICY,
        "from_round": 1,
        "next_round": 2,
        "archived_prereg_commit": R1_PREREG_COMMIT,
        "archived_result": "IMPLEMENTATION_FAILURE",
        "interruption_class": "NONDETERMINISTIC_VALIDATION_ERROR_TEXT",
        "preserve_operational_failure": True,
        "resume_old_namespace": False,
        "maximum_round": 5,
    }
    if any(
        type(manifest[key]) is not type(value) or manifest[key] != value
        for key, value in required.items()
    ):
        raise ConfigError("continuation authorizes only the archived Round 1 failure")
    amounts = {
        "prior_committed_usd": Decimal("2.50181228"),
        "round_limit_usd": ROUND_CAP,
        "combined_cap_usd": COMBINED_CAP,
    }
    if any(abs(_number(manifest[key]) - value) > TOLERANCE for key, value in amounts.items()):
        raise ConfigError("continuation cannot refund costs or change campaign limits")
    expected_archive = {
        str((paths(1)["VALIDATION"] / name).relative_to(ROOT)): sha
        for name, sha in R1_ARCHIVE_SHA256.items()
    }
    if (
        manifest["archive_files"] != expected_archive
        or manifest["interruption_audit"] != audit_entry
    ):
        raise ConfigError("continuation archive/audit binding changed")
    entry = manifest["repair_test_report"]
    if (
        not isinstance(entry, dict)
        or set(entry) != {"path", "sha256"}
        or entry["path"] != str(repair_path.relative_to(ROOT))
    ):
        raise ConfigError("continuation repair report path changed")
    repair_payload = _hashed(repair_path, entry["sha256"])
    repair = json.loads(repair_payload)
    if not isinstance(repair, dict) or set(repair) != {
        "schema_version",
        "status",
        "regression",
        "tests_passed",
        "requests_responses_verdicts_unchanged",
        "malformed_outputs_remain_uncertain",
        "source_hashes",
    }:
        raise ConfigError("continuation repair report schema changed")
    if (
        type(repair["schema_version"]) is not int
        or repair["schema_version"] != 1
        or repair["status"] != "PASS"
        or repair["regression"] != "stable-validation-error-serialization"
        or type(repair["tests_passed"]) is not int
        or repair["tests_passed"] <= 0
        or repair["requests_responses_verdicts_unchanged"] is not True
        or repair["malformed_outputs_remain_uncertain"] is not True
    ):
        raise ConfigError("continuation requires the completed offline serialization repair")
    hashes = repair["source_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != set(REPAIR_SOURCE_PATHS):
        raise ConfigError("repair report source membership changed")
    source_manifest = paths(2)["FROZEN"] / "source_manifest.json"
    for name, sha in hashes.items():
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ConfigError("invalid repair source hash")
        if source_manifest.exists():
            if _json(source_manifest)["source_hashes"].get(name) != sha:
                raise ConfigError("repair report differs from the Round 2 source freeze")
        else:
            _hashed(ROOT / name, sha)
    # Round 2 preparation is offline. Before it is dispatched, the common freeze
    # guard binds both metadata files in its pushed source manifest. Thereafter
    # later rounds verify the exact published Round 2 artifacts read-only.
    if (paths(2)["VALIDATION"] / "cap.json").exists():
        prereg = paths(2)["VALIDATION_PREREG"]
        for path in (manifest_path, repair_path, source_manifest):
            _published_bytes(path, _read(path), prereg=prereg)


def _verify_archived_r1_interruption(row: dict[str, Any], total_before: Decimal) -> None:
    p = paths(1)
    payloads = _receipt_payloads(row, p["BASE"], new=True)
    if any(_sha(payloads[name]) != sha for name, sha in R1_ARCHIVE_SHA256.items()):
        raise ConfigError("interruption is not the exact authorized Round 1 archive")
    if (
        row["prereg_commit"] != R1_PREREG_COMMIT
        or abs(total_before - Decimal("1.44588620")) > TOLERANCE
        or _number(row["validation_limit_usd"]) != ROUND_CAP
    ):
        raise ConfigError("archived interruption predecessor identity/budget changed")
    accounting = physical_accounting(p["VALIDATION"], ROUND_CAP, expected_stop="implementation")
    if (
        accounting["physical_attempts"] != 43
        or abs(_number(accounting["committed_usd"]) - Decimal("1.05592608")) > TOLERANCE
        or abs(_number(row["committed_usd"]) - Decimal("1.05592608")) > TOLERANCE
    ):
        raise ConfigError("archived interruption accounting changed")
    result = json.loads(payloads["result.json"])
    if (
        result.get("decision") != "IMPLEMENTATION_FAILURE"
        or result.get("cases_completed") != 19
        or result.get("cases_expected") != 21
        or result.get("interruption", {}).get("kind") != "implementation"
        or result.get("freeze", {}).get("prereg_commit") != R1_PREREG_COMMIT
    ):
        raise ConfigError("archived operational failure must remain unchanged")
    requests, responses = (
        _rows(payloads[f"judge_requests/{name}.jsonl"]) for name in ("requests", "responses")
    )
    full = _rows(payloads["judgments.jsonl"])
    if (
        len(requests) != 42
        or len(responses) != 42
        or len(full) != 19
        or len(result.get("outcomes", [])) != 19
        or sum(x.get("event") == "call" for x in _rows(payloads["ledger.judge.jsonl"])) != 42
    ):
        raise ConfigError("archived interruption logical accounting changed")
    cursor = 0
    for compact, stored in zip(result["outcomes"], full, strict=True):
        record = stored["result"]
        if (
            compact
            != {
                **stored,
                "result": {
                    key: value
                    for key, value in record.items()
                    if key not in ("request", "response")
                },
            }
            or driver.digest(record) != compact["full_judge_record_sha256"]
        ):
            raise ConfigError("archived interrupted full/compact records differ")
        audit = record.get("evidence_verification") or {}
        logical = [
            stage["record"]
            for stage in audit.get("stages", [])
            if stage["record"].get("request") is not None
        ]
        if not 1 <= len(logical) <= 4 or audit.get("logical_calls") != len(logical):
            raise ConfigError("archived interrupted logical call bound changed")
        for call in logical:
            if (
                cursor >= len(requests)
                or call["request"] != requests[cursor]
                or call["response"] != responses[cursor]
            ):
                raise ConfigError("archived interruption request/response changed")
            cursor += 1
    if cursor != 42:
        raise ConfigError("archived interruption has unattributed logical calls")
    entry = row["independent_audit"]
    audit_path = p["FROZEN"] / "independent_audit.json"
    if (
        not isinstance(entry, dict)
        or set(entry) != {"path", "sha256"}
        or entry["path"] != str(audit_path.relative_to(ROOT))
    ):
        raise ConfigError("archived interruption audit path changed")
    if entry["sha256"] != R1_AUDIT_SHA256:
        raise ConfigError("interruption audit is not the exact published Round 1 audit")
    payload = _hashed(audit_path, entry["sha256"])
    audit = json.loads(payload)
    required = {
        "integrity": "FAIL",
        "judge_ready": False,
        "accounting_integrity": "PASS",
        "interruption_class": "NONDETERMINISTIC_VALIDATION_ERROR_TEXT",
        "round": 1,
        "cases_completed": 19,
        "cases_expected": 21,
        "recorded_decision": "IMPLEMENTATION_FAILURE",
        "exact_final_records": 18,
        "logical_calls": 42,
        "physical_attempts": 43,
        "all_recorded_requests_exact": True,
        "all_recorded_responses_unchanged": True,
        "all_recorded_verdicts_unchanged": True,
        "private_result_sha256": R1_ARCHIVE_SHA256["result.json"],
    }
    if (
        any(
            type(audit.get(key)) is not type(value) or audit.get(key) != value
            for key, value in required.items()
        )
        or audit.get("diagnostic_only_case_ids") != ["saved_159_C1"]
        or audit.get("diagnostic_only_paths") != R1_DIAGNOSTIC_PATHS
    ):
        raise ConfigError("interruption audit does not establish the scoped diagnostic defect")
    checks, failed = audit.get("checks"), audit.get("failed_checks")
    if (
        not isinstance(checks, dict)
        or not isinstance(failed, list)
        or set(failed) != R1_EXPECTED_AUDIT_FAILURES
        or len(failed) != 4
        or type(audit.get("check_count")) is not int
        or audit["check_count"] != len(checks)
        or checks.get("operational_decision_precedence") is not True
        or any(
            type(value) is not bool or value is not (key not in R1_EXPECTED_AUDIT_FAILURES)
            for key, value in checks.items()
        )
        or not checks.keys() >= R1_EXPECTED_AUDIT_FAILURES
    ):
        raise ConfigError("interruption audit contains additional/unexplained failures")
    for key, value in {
        "conservative_actual_usd": Decimal("0.58990976"),
        "uncertain_usd": Decimal("0.46601632"),
        "stage_limit_usd": ROUND_CAP,
    }.items():
        if abs(_number(audit.get(key)) - value) > TOLERANCE:
            raise ConfigError("interruption audit cost changed")
    _published_bytes(audit_path, payload)
    _verify_continuation_manifest(entry)
    if (p["RUN"] / "cap.json").exists():
        raise ConfigError("the archived failed round cannot have an engineering stage")


def _verify_predecessor(row: dict[str, Any], index: int, total_before: Decimal) -> None:
    if (
        index == 1
        and _json(paths(index)["VALIDATION"] / "result.json").get("decision")
        == "IMPLEMENTATION_FAILURE"
    ):
        _verify_archived_r1_interruption(row, total_before)
        return
    p = paths(index)
    payloads = _receipt_payloads(row, p["BASE"], new=True)
    limit = min(ROUND_CAP, COMBINED_CAP - total_before)
    if abs(_number(row["validation_limit_usd"]) - limit) > TOLERANCE:
        raise ConfigError("prior campaign round limit changed")
    accounting = physical_accounting(p["VALIDATION"], limit)
    if abs(_number(accounting["committed_usd"]) - _number(row["committed_usd"])) > TOLERANCE:
        raise ConfigError("prior campaign committed amount changed")
    result = json.loads(payloads["result.json"])
    if (
        result.get("decision") != "JUDGE_GATE_NOT_READY"
        or result.get("interruption") is not None
        or result.get("cases_completed") != 21
        or result.get("cases_expected") != 21
    ):
        raise ConfigError("only a complete failed validation permits the next round")
    if result.get("freeze", {}).get("prereg_commit") != row["prereg_commit"]:
        raise ConfigError("prior validation preregistration changed")
    requests, responses = (
        _rows(payloads[f"judge_requests/{name}.jsonl"]) for name in ("requests", "responses")
    )
    full = _rows(payloads["judgments.jsonl"])
    if (
        not 21 <= len(requests) == len(responses) <= 84
        or len(full) != 21
        or accounting["physical_attempts"] > 5 * len(requests)
    ):
        raise ConfigError("prior logical/physical call bounds or completeness changed")
    if sum(x.get("event") == "call" for x in _rows(payloads["ledger.judge.jsonl"])) != len(
        requests
    ):
        raise ConfigError("prior logical ledger does not reconcile")
    if len(result.get("outcomes", [])) != 21:
        raise ConfigError("prior validation outcome count changed")
    cursor = 0
    for compact, full_row in zip(result["outcomes"], full, strict=True):
        record = full_row["result"]
        if (
            compact
            != {
                **full_row,
                "result": {k: v for k, v in record.items() if k not in ("request", "response")},
            }
            or driver.digest(record) != compact["full_judge_record_sha256"]
        ):
            raise ConfigError("prior compact/full witness records differ")
        audit = record.get("evidence_verification") or {}
        stages = audit.get("stages", [])
        logical = [
            stage["record"] for stage in stages if stage["record"].get("request") is not None
        ]
        if not 1 <= len(logical) <= 4 or audit.get("logical_calls") != len(logical):
            raise ConfigError("prior witness logical call bound changed")
        for call in logical:
            if (
                cursor >= len(requests)
                or call["request"] != requests[cursor]
                or call["response"] != responses[cursor]
            ):
                raise ConfigError("prior serialized logical call changed")
            cursor += 1
    if cursor != len(requests):
        raise ConfigError("unattributed prior logical requests")
    audit_entry = row["independent_audit"]
    audit_path = p["FROZEN"] / "independent_audit.json"
    if (
        not isinstance(audit_entry, dict)
        or set(audit_entry) != {"path", "sha256"}
        or audit_entry["path"] != str(audit_path.relative_to(ROOT))
    ):
        raise ConfigError("prior independent audit path changed")
    audit_payload = _hashed(audit_path, audit_entry["sha256"])
    audit_result = json.loads(audit_payload)
    if (
        audit_result.get("integrity") != "PASS"
        or audit_result.get("judge_ready") is not False
        or audit_result.get("round") != index
        or audit_result.get("private_result_sha256") != _sha(payloads["result.json"])
    ):
        raise ConfigError("prior independent audit did not establish a completed failed round")
    relative = str(audit_path.relative_to(ROOT))
    commit = driver.git("log", "-1", "--format=%H", "--", relative)
    driver.git("merge-base", "--is-ancestor", commit, "origin/aea-llm-vnext")
    if driver.git("show", f"{commit}:{relative}").strip() != audit_payload.decode().strip():
        raise ConfigError("prior independent audit is not the published artifact")
    if (p["RUN"] / "cap.json").exists():
        raise ConfigError("a prior engineering stage prohibits another validation round")


def verify_carryover(round_index: int) -> dict[str, Any]:
    p = paths(round_index)
    row = _json(p["FROZEN"] / "carryover.json")
    expected = {
        "schema_version",
        "implementation",
        "round_index",
        "max_rounds",
        "combined_cap_usd",
        "validation_round_cap_usd",
        "engineering_max_usd",
        "prior_committed_usd",
        "prior_runs",
    }
    if (
        not isinstance(row, dict)
        or set(row) != expected
        or type(row["schema_version"]) is not int
        or row["schema_version"] != 1
        or row["implementation"] != IMPLEMENTATION
        or type(row["round_index"]) is not int
        or row["round_index"] != round_index
        or type(row["max_rounds"]) is not int
        or row["max_rounds"] != MAX_ROUNDS
    ):
        raise ConfigError("campaign carryover schema or round changed")
    if (
        _number(row["combined_cap_usd"]) != COMBINED_CAP
        or _number(row["engineering_max_usd"]) != ENGINEERING_MAX
    ):
        raise ConfigError("campaign monetary ceiling changed")
    prior = row["prior_runs"]
    if not isinstance(prior, list) or len(prior) != 4 + round_index - 1:
        raise ConfigError("campaign must include every prior paid validation exactly once")
    total = Decimal(0)
    for index, receipt in enumerate(prior):
        if index < 4:
            _verify_old(receipt, index)
        else:
            _verify_predecessor(receipt, index - 3, total)
        total += _number(receipt["committed_usd"])
    if (
        abs(_number(row["prior_committed_usd"]) - total) > TOLERANCE
        or total >= COMBINED_CAP
        or abs(_number(row["validation_round_cap_usd"]) - min(ROUND_CAP, COMBINED_CAP - total))
        > TOLERANCE
    ):
        raise ConfigError("campaign cumulative budget does not reconcile")
    for later in range(round_index + 1, MAX_ROUNDS + 1):
        if any(paths(later)[key].exists() for key in ("BASE", "FROZEN")):
            raise ConfigError("later round already exists; previous rounds cannot be resumed")
    return row


def verify_copied_inputs(round_index: int) -> None:
    p = paths(round_index)
    with _bindings(
        previous,
        {
            "ROOT": ROOT,
            "OLD_BASE": OLD_BASE,
            "OLD_FROZEN": OLD_FROZEN,
            "FROZEN": p["FROZEN"],
            "PRIVATE": p["PRIVATE"],
        },
    ):
        previous.verify_copied_inputs()


@contextmanager
def _bindings(module: Any, values: dict[str, Any]) -> Iterator[None]:
    saved = {key: getattr(module, key) for key in values}
    try:
        for key, value in values.items():
            setattr(module, key, value)
        yield
    finally:
        for key, value in saved.items():
            setattr(module, key, value)


@contextmanager
def campaign_lock() -> Iterator[None]:
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE / ".active.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigError("another campaign stage is active") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def prepare_round(round_index: int) -> dict[str, Any]:
    """Copy exactly the existing 23 inputs; never recapture, sample, or call a model."""
    p = paths(round_index)
    if p["BASE"].exists() or p["FROZEN"].exists():
        raise ConfigError("round already prepared or interrupted; no implicit overwrite")
    prior = [_receipt(ROOT / "runs" / name) for name in PRIOR_NAMES]
    for receipt, amount in zip(prior, PRIOR_AMOUNTS, strict=True):
        receipt["committed_usd"] = float(amount)
    prior.extend(
        _receipt(paths(index)["BASE"], campaign_round=index) for index in range(1, round_index)
    )
    total = sum((_number(row["committed_usd"]) for row in prior), Decimal(0))
    carry = {
        "schema_version": 1,
        "implementation": IMPLEMENTATION,
        "round_index": round_index,
        "max_rounds": MAX_ROUNDS,
        "combined_cap_usd": float(COMBINED_CAP),
        "validation_round_cap_usd": float(min(ROUND_CAP, COMBINED_CAP - total)),
        "engineering_max_usd": float(ENGINEERING_MAX),
        "prior_committed_usd": float(total),
        "prior_runs": prior,
    }
    # Verify every predecessor before creating any current namespace.
    for index, receipt in enumerate(prior):
        if index < 4:
            _verify_old(receipt, index)
        else:
            before = sum((_number(x["committed_usd"]) for x in prior[:index]), Decimal(0))
            _verify_predecessor(receipt, index - 3, before)
    if total >= COMBINED_CAP or any(
        paths(index)["BASE"].exists() or paths(index)["FROZEN"].exists()
        for index in range(round_index + 1, MAX_ROUNDS + 1)
    ):
        raise ConfigError("campaign spent or later round already exists")
    cases = _json(OLD_FROZEN / "validation_manifest.json")["cases"]
    names = {row["input_file"] for row in cases}
    if (
        len(cases) != 21
        or len(names) != 17
        or any(
            not isinstance(name, str) or not re.fullmatch(r"judge_inputs/[0-9a-f]{64}\.json", name)
            for name in names
        )
    ):
        raise ConfigError("original fixed validation membership changed")
    names.update({"saved_candidates.json", "engineering/prepared.json"})
    names.update(
        f"engineering/task-{task}/{name}.json"
        for task in (154, 159)
        for name in ("original_failures", "privileged_reference")
    )
    inventory = []
    for name in sorted(names):
        source, destination = OLD_BASE / "private" / name, p["PRIVATE"] / name
        payload = _read(source)
        driver.write_exact(destination, payload)
        inventory.append(
            {
                "source": str(source.relative_to(ROOT)),
                "destination": str(destination.relative_to(ROOT)),
                "sha256": _sha(payload),
                "bytes": len(payload),
            }
        )
    for name in ("input_manifest.json", "validation_manifest.json", "saved_candidates.json"):
        driver.write_exact(p["FROZEN"] / name, _read(OLD_FROZEN / name))
    driver.write_exact(
        p["FROZEN"] / "copied_private_inputs.json",
        (canonical_json({"schema_version": 1, "files": inventory}) + "\n").encode(),
    )
    driver.write_exact(p["FROZEN"] / "carryover.json", (canonical_json(carry) + "\n").encode())
    verify_carryover(round_index)
    verify_copied_inputs(round_index)
    return {
        "status": "prepared",
        "round": round_index,
        "private_files": len(inventory),
        "carryover_sha256": _sha(_read(p["FROZEN"] / "carryover.json")),
    }


def strict_validation_decision(
    cases: list[dict[str, Any]], outcomes: list[dict[str, Any]], error: dict[str, Any] | None = None
) -> dict[str, Any]:
    result = ORIGINAL_VALIDATION_DECISION(cases, outcomes, error)
    if not outcomes or error is not None:
        return result
    full = _rows(_read(driver.VALIDATION / "judgments.jsonl"))
    if len(full) != len(outcomes):
        raise ConfigError("witness full/compact count changed")
    by_id = {case["case_id"]: case for case in cases}
    schema_ready = True
    for compact, stored in zip(outcomes, full, strict=True):
        raw = stored["result"]
        expected = {
            **stored,
            "result": {k: v for k, v in raw.items() if k not in ("request", "response")},
        }
        if compact != expected or compact["full_judge_record_sha256"] != driver.digest(raw):
            raise ConfigError("witness full/compact hash changed")
        record = JudgeRecord.model_validate(raw)
        evidence = PrivilegeJudgeInput.model_validate_json(
            _read(driver.private_input_path(by_id[compact["case_id"]]))
        )
        validate_witness_record(record, evidence)
        schema_ready &= record.generated_uncertainty is None
    if not schema_ready:
        result["decision"] = "JUDGE_GATE_NOT_READY"
    return result


def engineering_budget(round_index: int, *, published: bool = False) -> dict[str, Any]:
    p = paths(round_index)
    path = p["FROZEN"] / "engineering_budget.json"
    row = _json(path)
    expected = {
        "schema_version",
        "round_index",
        "prior_committed_usd",
        "validation_committed_usd",
        "engineering_cap_usd",
        "combined_cap_usd",
        "validation_cap_sha256",
        "validation_result_sha256",
        "carryover_sha256",
    }
    if (
        not isinstance(row, dict)
        or set(row) != expected
        or type(row["schema_version"]) is not int
        or row["schema_version"] != 1
        or type(row["round_index"]) is not int
        or row["round_index"] != round_index
    ):
        raise ConfigError("engineering budget schema changed")
    carry = verify_carryover(round_index)
    accounting = physical_accounting(p["VALIDATION"], _number(carry["validation_round_cap_usd"]))
    prior, current = _number(carry["prior_committed_usd"]), _number(accounting["committed_usd"])
    limit = min(ENGINEERING_MAX, COMBINED_CAP - prior - current)
    if (
        _number(row["prior_committed_usd"]) != prior
        or abs(_number(row["validation_committed_usd"]) - current) > TOLERANCE
        or abs(_number(row["engineering_cap_usd"]) - limit) > TOLERANCE
        or _number(row["combined_cap_usd"]) != COMBINED_CAP
        or limit <= 0
    ):
        raise ConfigError("engineering cumulative budget changed")
    for key, source in (
        ("validation_cap_sha256", p["VALIDATION"] / "cap.json"),
        ("validation_result_sha256", p["VALIDATION"] / "result.json"),
        ("carryover_sha256", p["FROZEN"] / "carryover.json"),
    ):
        _hashed(source, row[key])
    if _json(p["VALIDATION"] / "result.json").get("decision") != "JUDGE_GATE_READY":
        raise ConfigError("engineering requires a passing validation")
    if published:
        relative = str(p["PREREG"].relative_to(ROOT))
        commit = driver.git("log", "-1", "--format=%H", "--", relative)
        driver.git("merge-base", "--is-ancestor", commit, "origin/aea-llm-vnext")
        if (
            _sha(_read(path)) not in _read(p["PREREG"]).decode()
            or driver.git("show", f"{commit}:{path.relative_to(ROOT)}").strip()
            != _read(path).decode().strip()
        ):
            raise ConfigError("engineering budget lacks published preregistration binding")
    return row


def freeze_round(round_index: int) -> None:
    p = paths(round_index)
    budget_path = p["FROZEN"] / "engineering_budget.json"
    if budget_path.exists() or (p["RUN"] / "cap.json").exists():
        raise ConfigError("engineering budget already frozen; no regeneration")
    carry = verify_carryover(round_index)
    accounting = physical_accounting(p["VALIDATION"], _number(carry["validation_round_cap_usd"]))
    audit_path = p["FROZEN"] / "independent_audit.json"
    audit = _json(audit_path)
    if (
        audit.get("integrity") != "PASS"
        or audit.get("judge_ready") is not True
        or audit.get("round") != round_index
        or audit.get("private_result_sha256") != _sha(_read(p["VALIDATION"] / "result.json"))
        or not isinstance(audit.get("checks"), dict)
        or not audit["checks"]
        or any(value is not True for value in audit["checks"].values())
    ):
        raise ConfigError("engineering freeze requires independent passing validation audit")
    # The original freeze checks the complete witness-audited acceptance predicate.
    driver.freeze_validation()
    prior, current = _number(carry["prior_committed_usd"]), _number(accounting["committed_usd"])
    row = {
        "schema_version": 1,
        "round_index": round_index,
        "prior_committed_usd": float(prior),
        "validation_committed_usd": float(current),
        "engineering_cap_usd": float(min(ENGINEERING_MAX, COMBINED_CAP - prior - current)),
        "combined_cap_usd": float(COMBINED_CAP),
        "validation_cap_sha256": _sha(_read(p["VALIDATION"] / "cap.json")),
        "validation_result_sha256": _sha(_read(p["VALIDATION"] / "result.json")),
        "carryover_sha256": _sha(_read(p["FROZEN"] / "carryover.json")),
    }
    driver.write_exact(budget_path, (canonical_json(row) + "\n").encode())
    engineering_budget(round_index)
    # Replace only the freshly generated, uncommitted common template with this
    # campaign's actual budget and design bindings. Root completes it before push.
    template = p["PREREG"].read_text()
    template = template.replace(
        "docs/design/AEA_LLM_PRIVILEGE_JUDGE.md",
        "docs/design/AEA_LLM_PRIVILEGE_JUDGE_EVIDENCE.md",
    ).replace("Hard physical cap: USD 17.", f"Hard physical cap: USD {row['engineering_cap_usd']}.")
    template += (
        "\nEngineering budget SHA256: "
        + _sha(_read(budget_path))
        + "\nIndependent audit SHA256: "
        + _sha(_read(audit_path))
        + "\nCampaign cumulative cap USD 20 includes every prior validation and this stage.\n"
    )
    p["PREREG"].write_text(template)


def _build(*, designer: bool) -> Any:
    substrate = ORIGINAL_BUILD(designer=designer)
    substrate.policy_spec_kwargs["client_factory"] = (
        "scripts.e6_iterative_low_llm_judge_evidence:CappedPolicyClient"
    )
    return substrate


class _PolicyTransport:
    def __init__(self, transport: Callable[..., Any], cap_path: Path, limit: float) -> None:
        self.delegate = driver.CappedTransport(transport, cap_path)
        self.limit = limit

    def __call__(self, **wire: Any) -> Any:
        with _bindings(
            driver, {"STAGE_LIMITS": {**driver.STAGE_LIMITS, "engineering": self.limit}}
        ):
            return self.delegate(**wire)


class CappedPolicyClient(AeaLLMClient):
    """Child process binding for the same physical guard at the derived engineering cap."""

    def __init__(self, *, cap_path: str, **kwargs: Any) -> None:
        target = Path(cap_path)
        matches = [i for i in range(1, MAX_ROUNDS + 1) if target == paths(i)["RUN"] / "cap.json"]
        if len(matches) != 1:
            raise ConfigError("policy cap is outside the frozen campaign namespace")
        budget = engineering_budget(matches[0], published=True)
        super().__init__(**kwargs)
        self._client._transport = _PolicyTransport(
            self._client._transport, target, budget["engineering_cap_usd"]
        )


@contextmanager
def bound_driver(round_index: int) -> Iterator[None]:
    """No writes or dispatch. Preserve all phase functions and restore every binding."""
    p = paths(round_index)
    carry = verify_carryover(round_index)
    limits = {
        "validation": float(carry["validation_round_cap_usd"]),
        "engineering": float(ENGINEERING_MAX),
    }
    if (p["FROZEN"] / "engineering_budget.json").exists():
        limits["engineering"] = float(engineering_budget(round_index)["engineering_cap_usd"])
    extras = (
        *EXTRA_FROZEN_INPUTS,
        *(
            str((p["FROZEN"] / name).relative_to(ROOT))
            for name in ("carryover.json", "copied_private_inputs.json")
        ),
    )
    if (
        round_index >= 2
        and _json(paths(1)["VALIDATION"] / "result.json").get("decision")
        == "IMPLEMENTATION_FAILURE"
    ):
        extras = (*extras, *(str(path.relative_to(ROOT)) for path in continuation_inputs()))
    with _bindings(
        driver,
        {
            **p,
            "STAGE_LIMITS": limits,
            "FROZEN_INPUTS": (*driver.FROZEN_INPUTS, *extras),
            "LLMPrivilegeJudge": WitnessCheckingPrivilegeJudge,
            "validation_decision": strict_validation_decision,
            "build": _build,
        },
    ):
        yield


def run_stage(round_index: int, stage: str) -> Any:
    if stage not in STAGES:
        raise ConfigError("unknown campaign stage")
    paths(round_index)
    _hashed(ROOT / "scripts/e6_iterative_low_llm_judge.py", BASE_DRIVER_SHA256)
    with campaign_lock():
        if stage == "prepare":
            return prepare_round(round_index)
        verify_carryover(round_index)
        verify_copied_inputs(round_index)
        with bound_driver(round_index):
            driver.ensure_frozen(adaptation=stage in {"replay", "adapt"})
            if stage in {"replay", "adapt"}:
                engineering_budget(round_index, published=True)
            actions = {
                "validate": driver.validate,
                "freeze": lambda: freeze_round(round_index),
                "replay": driver.replay_saved,
                "adapt": driver.adapt,
                "report": driver.report,
            }
            return actions[stage]()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, choices=range(1, MAX_ROUNDS + 1), required=True)
    parser.add_argument("--stage", choices=STAGES, required=True)
    args = parser.parse_args()
    try:
        value = run_stage(args.round, args.stage)
        if value is not None:
            public = value if args.stage == "prepare" else driver.public_stage_summary(value)
            print(json.dumps(public, sort_keys=True), flush=True)
        if args.stage == "validate":
            return 0 if value["decision"] == "JUDGE_GATE_READY" else 2
        if args.stage == "replay":
            return 0 if value["status"] == "completed" else 2
        if args.stage == "adapt":
            return 0 if value["interruption"] is None else 2
        return 0
    except Exception as exc:
        # Do not overwrite an old interruption or write inside another process's stage.
        record = driver.interruption(exc)
        print(
            json.dumps(
                {"round": args.round, "stage": args.stage, "error_sha256": driver.digest(record)}
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
