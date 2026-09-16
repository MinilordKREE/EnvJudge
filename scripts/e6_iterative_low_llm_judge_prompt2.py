"""Prompt-only repeat using immutable private copies and the remaining Phase A cap.

This launcher changes storage/freeze bindings and the remaining monetary ceiling.
Every validation, admission, optimizer, CONTROL and confirmation function is imported
unchanged. It never prepares inputs or resumes a previous paid stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import e6_iterative_low_llm_judge as _driver

from aea.errors import ConfigError

driver = _driver
ROOT = driver.ROOT
OLD_BASE = ROOT / "runs/e6-iterative-low-llm-judge"
OLD_FROZEN = ROOT / "experiments/alfworld_e6/frozen/iterative_low_llm_judge"
BASE = ROOT / "runs/e6-iterative-low-llm-judge-prompt2"
PRIVATE = BASE / "private"
RUN = PRIVATE / "engineering"
VALIDATION = PRIVATE / "validation"
FROZEN = ROOT / "experiments/alfworld_e6/frozen/iterative_low_llm_judge_prompt2"
VALIDATION_PREREG = (
    ROOT / "experiments/alfworld_e6/PREREG_ITERATIVE_LOW_LLM_JUDGE_PROMPT2_VALIDATION.md"
)
PREREG = ROOT / "experiments/alfworld_e6/PREREG_ITERATIVE_LOW_LLM_JUDGE_PROMPT2_ENGINEERING.md"
BASE_DRIVER_SHA256 = "945c5b4ca969b0f8440a9a11aec7ea0e16b542d781f8076562595eb0d560d3ba"
PRIOR_VALIDATION_COMMIT = "244f0f1446d3b6a4911a9514ea8bc4976f99c0da"
PRIOR_COMMITTED_USD = Decimal("0.35856656")
VALIDATION_REMAINING_USD = Decimal("2.64143344")
STAGE_LIMITS = {"validation": float(VALIDATION_REMAINING_USD), "engineering": 17.0}
STAGES = ("validate", "freeze", "replay", "adapt", "report")
EXTRA_FROZEN_INPUTS = (
    "scripts/e6_iterative_low_llm_judge_prompt2.py",
    "docs/design/AEA_LLM_PRIVILEGE_JUDGE_PROMPT2.md",
    "experiments/alfworld_e6/frozen/iterative_low_llm_judge_prompt2/carryover.json",
    "experiments/alfworld_e6/frozen/iterative_low_llm_judge_prompt2/copied_private_inputs.json",
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path) -> bytes:
    """Read an existing regular file without following any symlink component."""
    if not path.is_relative_to(ROOT) or any(p.is_symlink() for p in (path, *path.parents)):
        raise ConfigError("launcher input path escapes repository or uses a symlink")
    if not path.is_file():
        raise ConfigError("launcher immutable input is missing")
    return path.read_bytes()


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError("invalid carryover monetary value")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ConfigError("invalid carryover monetary value")
    return amount


def _hashed_read(path: Path, expected: Any) -> bytes:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ConfigError("invalid immutable input hash")
    payload = _read(path)
    if _sha(payload) != expected:
        raise ConfigError("launcher immutable input byte hash changed")
    return payload


def verify_carryover() -> dict[str, Any]:
    """Validate old paid spend using reads only; old cap_lock would rewrite it."""
    row: dict[str, Any] = json.loads(_read(FROZEN / "carryover.json"))
    old = OLD_BASE / "private/validation"
    paths = {
        "cap": old / "cap.json",
        "result": old / "result.json",
        "attempts": old / "cap.attempts.jsonl",
    }
    expected_keys = {
        "schema_version",
        "prior_commit",
        "prior_committed_usd",
        "validation_envelope_usd",
        "validation_remaining_usd",
        "engineering_cap_usd",
        "combined_cap_usd",
        *(f"prior_validation_{kind}_{suffix}" for kind in paths for suffix in ("path", "sha256")),
    }
    if (
        set(row) != expected_keys
        or type(row["schema_version"]) is not int
        or row["schema_version"] != 1
    ):
        raise ConfigError("carryover metadata schema changed")
    if row["prior_commit"] != PRIOR_VALIDATION_COMMIT:
        raise ConfigError("prior validation commit changed")
    expected_amounts = {
        "prior_committed_usd": PRIOR_COMMITTED_USD,
        "validation_envelope_usd": Decimal("3"),
        "validation_remaining_usd": VALIDATION_REMAINING_USD,
        "engineering_cap_usd": Decimal("17"),
        "combined_cap_usd": Decimal("20"),
    }
    if any(_number(row[key]) != value for key, value in expected_amounts.items()):
        raise ConfigError("frozen carryover budget changed")
    if PRIOR_COMMITTED_USD + VALIDATION_REMAINING_USD + Decimal("17") != Decimal("20"):
        raise ConfigError("combined monetary envelope mismatch")
    payloads = {}
    for kind, path in paths.items():
        if row[f"prior_validation_{kind}_path"] != str(path.relative_to(ROOT)):
            raise ConfigError("prior validation namespace changed")
        payloads[kind] = _hashed_read(path, row[f"prior_validation_{kind}_sha256"])
    cap = json.loads(payloads["cap"])
    if (
        cap.get("stage") != "validation"
        or _number(cap.get("limit_usd")) != Decimal("3")
        or _number(cap.get("actual_usd")) != PRIOR_COMMITTED_USD
        or _number(cap.get("uncertain_usd")) != 0
        or cap.get("inflight") != {}
        or type(cap.get("attempts")) is not int
        or cap["attempts"] != 21
        or cap.get("cap_path") != str(paths["cap"].resolve())
        or cap.get("stopped") is not None
        or cap.get("accounting_error")
        or cap.get("bound_violation")
    ):
        raise ConfigError("prior validation is not the frozen completed paid run")
    result = json.loads(payloads["result"])
    if (
        result.get("decision") != "JUDGE_GATE_NOT_READY"
        or result.get("cases_completed") != 21
        or result.get("cases_expected") != 21
        or result.get("interruption") is not None
        or result.get("freeze", {}).get("head") != PRIOR_VALIDATION_COMMIT
        or result.get("freeze", {}).get("prereg_commit") != PRIOR_VALIDATION_COMMIT
    ):
        raise ConfigError("prior failed validation result changed")
    attempts = [json.loads(line) for line in payloads["attempts"].splitlines() if line.strip()]
    reserved = [x for x in attempts if x.get("status") == "reserved"]
    returned = [x for x in attempts if x.get("status") == "returned"]
    if (
        len(attempts) != 42
        or len(reserved) != 21
        or len(returned) != 21
        or len({x["attempt"] for x in reserved}) != 21
        or {x["attempt"] for x in reserved} != {x["attempt"] for x in returned}
        or any(
            x.get("model") != "deepseek-v4-flash" or x.get("stage") != "validation"
            for x in attempts
        )
        or abs(
            sum((_number(x["conservative_usd"]) for x in returned), Decimal(0))
            - PRIOR_COMMITTED_USD
        )
        > Decimal("0.000000000001")
    ):
        raise ConfigError("prior physical attempt accounting does not reconcile")
    return row


def verify_copied_inputs() -> None:
    """Keep old and new payloads byte-identical without copying or regenerating here."""
    manifest = json.loads(_read(FROZEN / "copied_private_inputs.json"))
    if (
        set(manifest) != {"schema_version", "files"}
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
    ):
        raise ConfigError("copied private input inventory schema changed")
    for name in ("input_manifest.json", "validation_manifest.json", "saved_candidates.json"):
        if _read(FROZEN / name) != _read(OLD_FROZEN / name):
            raise ConfigError("published input metadata changed")
    cases = json.loads(_read(OLD_FROZEN / "validation_manifest.json"))["cases"]
    names = {row["input_file"] for row in cases}
    if (
        len(cases) != 21
        or len(names) != 17
        or any(
            not isinstance(name, str) or not re.fullmatch(r"judge_inputs/[0-9a-f]{64}\.json", name)
            for name in names
        )
    ):
        raise ConfigError("frozen private judge-input membership changed")
    names.update({"saved_candidates.json", "engineering/prepared.json"})
    names.update(
        f"engineering/task-{task}/{name}.json"
        for task in (154, 159)
        for name in ("original_failures", "privileged_reference")
    )
    expected = {
        (
            str((OLD_BASE / "private" / name).relative_to(ROOT)),
            str((PRIVATE / name).relative_to(ROOT)),
        )
        for name in names
    }
    rows = manifest["files"]
    if not isinstance(rows, list) or len(rows) != 23:
        raise ConfigError("copied private input inventory cardinality changed")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"source", "destination", "sha256", "bytes"}:
            raise ConfigError("copied private input row schema changed")
        if not isinstance(row["source"], str) or not isinstance(row["destination"], str):
            raise ConfigError("copied private input path type changed")
        pair = (row["source"], row["destination"])
        if pair not in expected or pair in seen:
            raise ConfigError("copied private input membership changed")
        seen.add(pair)
        if type(row["bytes"]) is not int or row["bytes"] < 0:
            raise ConfigError("copied private input byte length is invalid")
        for name in pair:
            if len(_hashed_read(ROOT / name, row["sha256"])) != row["bytes"]:
                raise ConfigError("copied private input byte length changed")
    if seen != expected:
        raise ConfigError("copied private input membership incomplete")


@contextmanager
def bound_driver() -> Iterator[None]:
    """Bind only operational globals; all executable phase functions remain identical."""
    bindings = {
        "BASE": BASE,
        "PRIVATE": PRIVATE,
        "RUN": RUN,
        "VALIDATION": VALIDATION,
        "FROZEN": FROZEN,
        "VALIDATION_PREREG": VALIDATION_PREREG,
        "PREREG": PREREG,
        "STAGE_LIMITS": dict(STAGE_LIMITS),
        "FROZEN_INPUTS": (*driver.FROZEN_INPUTS, *EXTRA_FROZEN_INPUTS),
    }
    saved = {key: getattr(driver, key) for key in bindings}
    try:
        for key, value in bindings.items():
            setattr(driver, key, value)
        yield
    finally:
        for key, value in saved.items():
            setattr(driver, key, value)


def run_stage(stage: str) -> Any:
    if stage not in STAGES:
        raise ConfigError("prompt revision forbids prepare or unknown stages")
    _hashed_read(ROOT / "scripts/e6_iterative_low_llm_judge.py", BASE_DRIVER_SHA256)
    verify_carryover()
    verify_copied_inputs()
    with bound_driver():
        # Report also requires immutable input/source verification. The other phase
        # functions repeat this check internally at their original boundaries.
        driver.ensure_frozen(adaptation=stage in {"replay", "adapt"})
        actions = {
            "validate": driver.validate,
            "freeze": driver.freeze_validation,
            "replay": driver.replay_saved,
            "adapt": driver.adapt,
            "report": driver.report,
        }
        return actions[stage]()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    stage = parser.parse_args().stage
    try:
        value = run_stage(stage)
        if value is not None:
            print(json.dumps(driver.public_stage_summary(value), sort_keys=True), flush=True)
        if stage == "validate":
            return 0 if value["decision"] == "JUDGE_GATE_READY" else 2
        if stage == "replay":
            return 0 if value["status"] == "completed" else 2
        if stage == "adapt":
            return 0 if value["interruption"] is None else 2
        return 0
    except Exception as exc:
        record = driver.interruption(exc)
        driver.write_json(PRIVATE / f"{stage}_interruption.json", record)
        print(json.dumps({"stage": stage, "error_sha256": driver.digest(record)}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
