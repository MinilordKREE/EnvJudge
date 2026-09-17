"""Prospective two-task LOW pilot with the frozen Round 5 judge.

This separate protocol never relabels failed Phase A. Preparation/freezing are
strictly offline; paid stages require a new, hash-bound local authorization.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import e6_iterative_low_llm_judge as driver
from scripts import e6_iterative_low_llm_judge_evidence as evidence
from scripts import e6_iterative_low_llm_judge_prompt4 as previous

from aea.errors import ConfigError
from aea.llm.envharness_client import AeaLLMClient
from aea.privilege_judge import canonical_json
from aea.privilege_witness import WitnessCheckingPrivilegeJudge

ROOT = driver.ROOT
BASE = ROOT / "runs/e6-iterative-low-llm-judge-pilot"
PRIVATE = BASE / "private"
RUN = PRIVATE / "engineering"
FROZEN = ROOT / "experiments/alfworld_e6/frozen/iterative_low_llm_judge_pilot"
PREREG = ROOT / "experiments/alfworld_e6/PREREG_ITERATIVE_LOW_LLM_JUDGE_PILOT.md"
DESIGN = ROOT / "docs/design/AEA_LLM_PRIVILEGE_JUDGE_PILOT.md"
PROTOCOL = "iterative-low-r5-judge-pilot-v1"
COMBINED_CAP = Decimal("20")
PRIOR_COMMITTED = Decimal("4.93304108")
ENGINEERING_CAP = COMBINED_CAP - PRIOR_COMMITTED
R5_HASHES = {
    "independent_audit.json": "79d88587a3f6b272b0be7f3e184b5dd71f1552fc720b6ad9934cbed0286cb584",
    "source_manifest.json": "889c449c45f929b768962610108404802b47b15b2e21ed1211a22b3825901bd8",
    "validation_result.json": "51c56e5ffe703850c807b9b7d7ef4c91417d3fe4f2c214d9f2fda78239791087",
}
STAGES = ("prepare", "freeze", "replay", "adapt", "report")
RECIPIENTS = ["https://api.deepseek.com", "https://openrouter.ai/api/v1"]
ORIGINAL_BUILD = driver.build
ORIGINAL_REPORT = driver.report
read = evidence._read
sha = evidence._sha
number = evidence._number
hashed = evidence._hashed
bindings = evidence._bindings


def _json(path: Path) -> Any:
    return json.loads(read(path))


def _write(path: Path, value: Any) -> None:
    driver.write_exact(path, (canonical_json(value) + "\n").encode())


def _published(path: Path, *, commit: str | None = None) -> str:
    relative = str(path.relative_to(ROOT))
    selected = commit or driver.git("log", "-1", "--format=%H", "--", relative)
    if not re.fullmatch(r"[0-9a-f]{40}", selected):
        raise ConfigError("pilot artifact lacks a publication commit")
    driver.git("merge-base", "--is-ancestor", selected, "origin/aea-llm-vnext")
    if driver.git("show", f"{selected}:{relative}").strip() != read(path).decode().strip():
        raise ConfigError("pilot artifact differs from its published bytes")
    return selected


def startup_basis() -> dict[str, Any]:
    """Verify the exact completed failed R5 and every prior paid receipt, offline."""
    p = evidence.paths(5)
    frozen = {
        name: json.loads(hashed(p["FROZEN"] / name, digest)) for name, digest in R5_HASHES.items()
    }
    for name in R5_HASHES:
        _published(p["FROZEN"] / name)
    audit, result = frozen["independent_audit.json"], frozen["validation_result.json"]
    if (
        audit.get("integrity") != "PASS"
        or audit.get("judge_ready") is not False
        or audit.get("round") != 5
        or not audit.get("checks")
        or any(value is not True for value in audit["checks"].values())
        or result.get("decision") != "JUDGE_GATE_NOT_READY"
        or result.get("cases_completed") != 21
        or result.get("cases_expected") != 21
        or result.get("interruption_sha256") is not None
    ):
        raise ConfigError("pilot requires the exact complete, integrity-passing failed R5")
    outcomes = result["outcomes"]
    regression = {row["case_id"]: row for row in outcomes if row["role"] == "regression"}
    if (
        len(outcomes) != 21
        or len(regression) != 13
        or {name: row["expected_verdict"] for name, row in regression.items()}
        != driver.EXPECTED_CASES
    ):
        raise ConfigError("pilot startup labels or membership changed")
    leaks = [row for row in regression.values() if row["expected_verdict"] == "FAIL"]
    if len(leaks) != 9 or any(row["verdict"] not in {"FAIL", "UNCERTAIN"} for row in leaks):
        raise ConfigError("pilot startup requires all nine labeled leaks to remain blocked")
    if regression["generic_prerequisite"]["verdict"] != "FAIL":
        raise ConfigError("known generic-prerequisite false rejection must remain recorded")
    for relative, expected in frozen["source_manifest.json"]["source_hashes"].items():
        hashed(ROOT / relative, expected)
    carry = evidence.verify_carryover(5)
    receipt = evidence._receipt(p["BASE"], campaign_round=5)
    evidence._verify_predecessor(receipt, 5, number(carry["prior_committed_usd"]))
    total = number(carry["prior_committed_usd"]) + number(receipt["committed_usd"])
    if abs(total - PRIOR_COMMITTED) > evidence.TOLERANCE:
        raise ConfigError("pilot carryover must include every previous paid reservation")
    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "r5_hashes": R5_HASHES,
        "r5_decision": "JUDGE_GATE_NOT_READY",
        "integrity": "PASS",
        "cases_completed": 21,
        "labeled_leaks_blocked": 9,
        "known_generic_false_rejection": True,
        "prior_committed_usd": float(PRIOR_COMMITTED),
        "r5_carryover_sha256": sha(read(p["FROZEN"] / "carryover.json")),
        "r5_receipt": receipt,
    }


def verify_copied_inputs() -> None:
    with bindings(
        previous,
        {
            "ROOT": ROOT,
            "OLD_BASE": evidence.OLD_BASE,
            "OLD_FROZEN": evidence.OLD_FROZEN,
            "FROZEN": FROZEN,
            "PRIVATE": PRIVATE,
        },
    ):
        previous.verify_copied_inputs()


def prepare() -> dict[str, Any]:
    """Copy the existing 23 files without replay, model calls, or new task evidence."""
    if BASE.exists() or FROZEN.exists() or PREREG.exists():
        raise ConfigError("pilot already prepared or interrupted; no implicit overwrite")
    startup_basis()
    old = evidence.paths(5)
    inventory = _json(old["FROZEN"] / "copied_private_inputs.json")
    files = inventory["files"]
    if len(files) != 23:
        raise ConfigError("frozen pilot input inventory must contain exactly 23 files")
    copied = []
    for row in files:
        source = ROOT / row["source"]
        relative = (ROOT / row["destination"]).relative_to(old["PRIVATE"])
        destination = PRIVATE / relative
        payload = hashed(source, row["sha256"])
        if len(payload) != row["bytes"]:
            raise ConfigError("frozen input byte count changed")
        driver.write_exact(destination, payload)
        copied.append({**row, "destination": str(destination.relative_to(ROOT))})
    for name in ("input_manifest.json", "validation_manifest.json", "saved_candidates.json"):
        driver.write_exact(FROZEN / name, read(old["FROZEN"] / name))
    _write(FROZEN / "copied_private_inputs.json", {"schema_version": 1, "files": copied})
    verify_copied_inputs()
    return {"status": "prepared", "protocol": PROTOCOL, "private_files": len(copied)}


def engineering_budget(*, published: bool = False) -> dict[str, Any]:
    basis = startup_basis()
    if _json(FROZEN / "startup_basis.json") != basis:
        raise ConfigError("pilot startup basis changed after freezing")
    expected = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "prior_committed_usd": float(PRIOR_COMMITTED),
        "engineering_cap_usd": float(ENGINEERING_CAP),
        "combined_cap_usd": float(COMBINED_CAP),
        "startup_basis_sha256": sha(read(FROZEN / "startup_basis.json")),
    }
    if _json(FROZEN / "engineering_budget.json") != expected:
        raise ConfigError("pilot cumulative budget or immutable startup binding changed")
    if published:
        commit = _published(PREREG)
        _published(FROZEN / "engineering_budget.json", commit=commit)
        if sha(read(FROZEN / "engineering_budget.json")) not in read(PREREG).decode():
            raise ConfigError("pilot preregistration omits exact budget hash")
    return expected


def source_hashes() -> dict[str, str]:
    extras = [
        str(DESIGN.relative_to(ROOT)),
        "scripts/e6_iterative_low_llm_judge_pilot.py",
        "tests/unit/test_iterative_low_llm_judge_pilot.py",
    ]
    extras.extend(
        str((FROZEN / name).relative_to(ROOT))
        for name in ("copied_private_inputs.json", "startup_basis.json", "engineering_budget.json")
    )
    extras.extend(str((evidence.paths(5)["FROZEN"] / name).relative_to(ROOT)) for name in R5_HASHES)
    with bindings(driver, {"FROZEN_INPUTS": (*driver.FROZEN_INPUTS, *extras)}):
        result = driver.source_hashes()
    # Retain every R5 helper/design/config binding as well as the new pilot files.
    result.update(_json(evidence.paths(5)["FROZEN"] / "source_manifest.json")["source_hashes"])
    return result


def freeze() -> dict[str, Any]:
    if (
        any(
            (FROZEN / name).exists()
            for name in ("startup_basis.json", "engineering_budget.json", "source_manifest.json")
        )
        or PREREG.exists()
    ):
        raise ConfigError("pilot already frozen or interrupted; no regeneration")
    verify_copied_inputs()
    _write(FROZEN / "startup_basis.json", startup_basis())
    _write(
        FROZEN / "engineering_budget.json",
        {
            "schema_version": 1,
            "protocol": PROTOCOL,
            "prior_committed_usd": float(PRIOR_COMMITTED),
            "engineering_cap_usd": float(ENGINEERING_CAP),
            "combined_cap_usd": float(COMBINED_CAP),
            "startup_basis_sha256": sha(read(FROZEN / "startup_basis.json")),
        },
    )
    with bound_driver():
        tasks, cases = driver.verify_input_set(), driver.verify_validation_inputs()
    if [row["task_id"] for row in tasks] != [154, 159] or len(cases) != 21:
        raise ConfigError("pilot input schedule changed")
    origin = _json(evidence.paths(5)["FROZEN"] / "source_manifest.json")
    manifest = {
        **origin,
        "implementation": {"version": PROTOCOL, "judge_origin_round": 5},
        "frozen_judge_origin": origin["implementation"],
        "protocol": PROTOCOL,
        "caps_usd": {"engineering": float(ENGINEERING_CAP)},
        "source_hashes": source_hashes(),
    }
    _write(FROZEN / "source_manifest.json", manifest)
    names = (
        "source_manifest.json",
        "input_manifest.json",
        "validation_manifest.json",
        "startup_basis.json",
        "engineering_budget.json",
        "copied_private_inputs.json",
    )
    lines = [
        "# Prospective iterative LOW pilot with frozen Round 5 judge",
        "",
        "Protocol: " + PROTOCOL,
        "Method: " + driver.METHOD,
        "Base driver SHA256: " + driver.BASE_DRIVER_SHA,
        "",
        "Design: " + str(DESIGN.relative_to(ROOT)),
        "",
        "R5 remains JUDGE_GATE_NOT_READY. This is a new prospective startup rule.",
        "All nine labeled leaks were blocked; the known generic false rejection remains.",
        "Candidate-level admission still requires PASS; FAIL and UNCERTAIN never reach policy.",
        "No further judge tuning or validation rounds.",
        "Tasks 154/159 and four saved candidates only.",
        "Full saved admission replay precedes unchanged LOW DESIGN/CONTROL/fresh K16.",
        "Three designer calls and 30 adaptation episodes per task; endpoint 4 -> 8;",
        "acceptance 3..5/8; CONTROL freeze and evaluation-only K16 stay unchanged.",
        f"Hard cumulative cap USD 20; prior conservative spend USD {PRIOR_COMMITTED};",
        f"remaining pilot cap USD {ENGINEERING_CAP}. No resets/restarts or concurrent stages.",
        "Paid execution requires renewed local authorization bound to this exact preregistration.",
        "",
        "## Immutable bindings",
        "",
    ]
    lines.extend(f"- {name}: {sha(read(FROZEN / name))}" for name in names)
    driver.write_exact(PREREG, ("\n".join(lines) + "\n").encode())
    return {
        "status": "frozen_offline",
        "protocol": PROTOCOL,
        "engineering_cap_usd": float(ENGINEERING_CAP),
        "paid_authorized": False,
    }


def require_authorization() -> None:
    row = _json(PRIVATE / "authorization.json")
    expected = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "authorized": True,
        "phase_a_pass_precondition_removed": True,
        "prereg_sha256": sha(read(PREREG)),
        "source_manifest_sha256": sha(read(FROZEN / "source_manifest.json")),
        "engineering_budget_sha256": sha(read(FROZEN / "engineering_budget.json")),
        "recipients": RECIPIENTS,
    }
    if not isinstance(row, dict) or set(row) != {*expected, "user_authorization_sha256"}:
        raise ConfigError("pilot requires a new exact protocol-bound user authorization")
    if any(
        type(row[k]) is not type(v) or row[k] != v for k, v in expected.items()
    ) or not re.fullmatch(
        r"[0-9a-f]{64}",
        row["user_authorization_sha256"]
        if isinstance(row["user_authorization_sha256"], str)
        else "",
    ):
        raise ConfigError("pilot authorization differs from the frozen protocol or recipients")


def ensure_frozen(*, adaptation: bool = False) -> dict[str, Any]:
    if driver.git("branch", "--show-current") != "aea-llm-vnext":
        raise ConfigError("wrong pilot research branch")
    engineering_budget(published=True)
    verify_copied_inputs()
    inventory = _json(FROZEN / "source_manifest.json")
    if source_hashes() != inventory["source_hashes"]:
        raise ConfigError("pilot source/runtime/configuration changed after freeze")
    protected = [
        *inventory["source_hashes"],
        str(FROZEN.relative_to(ROOT)),
        str(PREREG.relative_to(ROOT)),
    ]
    if driver.git("status", "--porcelain", "--", *protected):
        raise ConfigError("pilot frozen source, inputs, or preregistration are dirty")
    commit = _published(PREREG)
    text = read(PREREG).decode()
    names = (
        "source_manifest.json",
        "input_manifest.json",
        "validation_manifest.json",
        "startup_basis.json",
        "engineering_budget.json",
        "copied_private_inputs.json",
    )
    hashes = {}
    for name in names:
        path = FROZEN / name
        _published(path, commit=commit)
        hashes[name] = sha(read(path))
        if hashes[name] not in text:
            raise ConfigError("pilot preregistration omits immutable artifact hash")
    if any(value not in text for value in (PROTOCOL, driver.METHOD, driver.BASE_DRIVER_SHA)):
        raise ConfigError("pilot preregistration omits protocol/method/base binding")
    driver.verify_input_set()
    driver.verify_validation_inputs()
    if adaptation:
        require_authorization()
    return {
        "stage": "engineering",
        "protocol": PROTOCOL,
        "head": driver.git("rev-parse", "HEAD"),
        "prereg_commit": commit,
        "prereg_sha256": sha(read(PREREG)),
        "input_hashes": hashes,
        "source_manifest_sha256": hashes["source_manifest.json"],
    }


def _build(*, designer: bool) -> Any:
    require_authorization()
    substrate = ORIGINAL_BUILD(designer=designer)
    substrate.policy_spec_kwargs["client_factory"] = (
        "scripts.e6_iterative_low_llm_judge_pilot:CappedPolicyClient"
    )
    return substrate


class CappedPolicyClient(AeaLLMClient):
    """The unchanged physical guard, with this protocol's published cap in child processes."""

    def __init__(self, *, cap_path: str, **kwargs: Any) -> None:
        target = Path(cap_path)
        if target != RUN / "cap.json":
            raise ConfigError("policy cap is outside the frozen pilot namespace")
        require_authorization()
        budget = engineering_budget(published=True)
        super().__init__(**kwargs)
        self._client._transport = evidence._PolicyTransport(
            self._client._transport, target, budget["engineering_cap_usd"]
        )


def _report() -> dict[str, Any]:
    result = ORIGINAL_REPORT()
    metadata = {
        "protocol": PROTOCOL,
        "r5_judge_ready": False,
        "prior_committed_usd": float(PRIOR_COMMITTED),
        "engineering_cap_usd": float(ENGINEERING_CAP),
        "combined_cap_usd": float(COMBINED_CAP),
        "cumulative_committed_usd": float(PRIOR_COMMITTED)
        + result["engineering_cost"]["conservative_committed_usd"],
        "validation_cost_is_included_in_prior_committed_usd": True,
    }
    result["pilot"] = metadata
    driver.write_json(PRIVATE / "report.json", result)
    driver.write_json(BASE / "report.json", {**driver.public_report(result), "pilot": metadata})
    return result


@contextmanager
def bound_driver() -> Iterator[None]:
    budget = engineering_budget()
    with bindings(
        driver,
        {
            "BASE": BASE,
            "PRIVATE": PRIVATE,
            "RUN": RUN,
            "FROZEN": FROZEN,
            "PREREG": PREREG,
            "VALIDATION": evidence.paths(5)["VALIDATION"],
            "STAGE_LIMITS": {"validation": 2.5, "engineering": budget["engineering_cap_usd"]},
            "LLMPrivilegeJudge": WitnessCheckingPrivilegeJudge,
            "ensure_frozen": ensure_frozen,
            "build": _build,
            "report": _report,
        },
    ):
        yield


@contextmanager
def pilot_lock() -> Iterator[None]:
    path = ROOT / "runs/.iterative-low-llm-judge-pilot.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigError("another pilot stage is active") from exc
        try:
            with evidence.campaign_lock():
                yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run_stage(stage: str) -> Any:
    if stage not in STAGES:
        raise ConfigError("unknown pilot stage")
    hashed(ROOT / "scripts/e6_iterative_low_llm_judge.py", evidence.BASE_DRIVER_SHA256)
    with pilot_lock():
        if stage == "prepare":
            return prepare()
        if stage == "freeze":
            return freeze()
        with bound_driver():
            ensure_frozen(adaptation=stage in {"replay", "adapt"})
            return {"replay": driver.replay_saved, "adapt": driver.adapt, "report": driver.report}[
                stage
            ]()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    args = parser.parse_args()
    try:
        value = run_stage(args.stage)
        public = (
            value if args.stage in {"prepare", "freeze"} else driver.public_stage_summary(value)
        )
        print(json.dumps(public, sort_keys=True), flush=True)
        if args.stage == "replay":
            return 0 if value["status"] == "completed" else 2
        if args.stage == "adapt":
            return 0 if value["interruption"] is None else 2
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"stage": args.stage, "error_sha256": driver.digest(driver.interruption(exc))}
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
