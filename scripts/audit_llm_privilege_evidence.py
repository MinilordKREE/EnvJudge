"""Read-only replay and accounting audit of a frozen evidence-verification round.

Stored responses are replayed locally; this module cannot construct an API client.
The report exposes only booleans, counts, hashes, and frozen categorical labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from scripts import e6_iterative_low_llm_judge as common_driver
from scripts import e6_iterative_low_llm_judge_evidence as launch

from aea.core.hashing import sha256_of
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.privilege_judge import JudgeConfig, PrivilegeJudgeInput, canonical_json
from aea.privilege_witness import WitnessCheckingPrivilegeJudge


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def audit_round(round_index: int) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    def close(left: float, right: float) -> bool:
        return math.isfinite(left) and math.isfinite(right) and abs(left - right) < 1e-9

    with launch.bound_driver(round_index):
        driver = common_driver
        validation = driver.VALIDATION
        result = read(validation / "result.json")
        cases = driver.verify_validation_inputs()
        full = rows(validation / "judgments.jsonl")
        requests = rows(validation / "judge_requests/requests.jsonl")
        responses = rows(validation / "judge_requests/responses.jsonl")
        ledger = rows(validation / "ledger.judge.jsonl")
        attempts = rows(validation / "cap.attempts.jsonl")
        cap = read(validation / "cap.json")
        check("21_final_cases", len(cases) == len(full) == len(result["outcomes"]) == 21)
        check("logical_request_response_balance", len(requests) == len(responses))
        check("bounded_logical_calls", 21 <= len(requests) <= 84)
        check("no_interruption", result.get("interruption") is None)
        check("closed_reservations", cap.get("inflight") == {})
        check("no_accounting_error", not cap.get("accounting_error"))
        check("no_bound_violation", not cap.get("bound_violation"))
        check("cap_namespace", cap.get("cap_path") == str((validation / "cap.json").resolve()))
        check(
            "current_sources_frozen",
            driver.source_hashes() == read(driver.FROZEN / "source_manifest.json")["source_hashes"],
        )
        startup = result["freeze"]
        for name, expected in startup["input_hashes"].items():
            path = driver.FROZEN / name
            check("frozen_" + name, digest(path.read_bytes()) == expected)
            stored = driver.git(
                "show", f"{startup['prereg_commit']}:{path.relative_to(driver.ROOT)}"
            )
            check("committed_" + name, stored.strip() == path.read_text().strip())
        check(
            "prereg_hash", digest(driver.VALIDATION_PREREG.read_bytes()) == startup["prereg_sha256"]
        )
        driver.git("merge-base", "--is-ancestor", startup["prereg_commit"], "origin/aea-llm-vnext")
        check("prereg_published", True)
        cursor = 0
        per_case = []
        config = JudgeConfig()
        for index, (case, record, compact) in enumerate(
            zip(cases, full, result["outcomes"], strict=True), 1
        ):
            key = f"case_{index:02d}"
            before = cursor
            evidence_path = driver.private_input_path(case)
            evidence = PrivilegeJudgeInput.model_validate_json(evidence_path.read_bytes())

            def complete(request: ChatRequest) -> ChatResponse:
                nonlocal cursor
                if cursor >= len(requests) or cursor >= len(responses):
                    raise AssertionError("replay requires an unrecorded completion")
                check(
                    f"request_{cursor:03d}_exact_replay",
                    request.model_dump(mode="json") == requests[cursor],
                )
                response = ChatResponse.model_validate(responses[cursor])
                check(
                    f"request_{cursor:03d}_binding",
                    response.request_sha256
                    == sha256_of({"provider": "deepseek", "request": request.model_dump()}),
                )
                check(
                    f"request_{cursor:03d}_frozen_config",
                    (
                        request.model == config.model
                        and request.temperature == config.temperature
                        and request.max_tokens == config.max_tokens
                        and request.thinking == config.thinking
                        and request.seed == config.seed
                        and response.model in config.accepted_response_models
                        and response.provider in (None, "deepseek", "DeepSeek")
                    ),
                )
                cursor += 1
                return response

            replay = WitnessCheckingPrivilegeJudge(
                complete,
                config=config,
                attribution=Attribution(
                    phase="judge_validation",
                    budget="none",
                    arm=driver.ARM,
                    task_id=str(case["task_id"]),
                ),
            ).judge(evidence)
            original = record["result"]
            check(key + "_exact_final_replay", replay.as_record() == original)
            check(key + "_bounded_calls", 1 <= cursor - before <= 4)
            check(
                key + "_input_bytes",
                digest(evidence_path.read_bytes()) == case["input_file_sha256"],
            )
            check(
                key + "_source",
                replay.source_sha256
                == case["source_sha256"]
                == digest(evidence.candidate_artifact.encode()),
            )
            check(
                key + "_original_input_binding",
                replay.input_sha256
                == digest(canonical_json(evidence.model_dump(mode="json")).encode()),
            )
            check(key + "_full_hash", driver.digest(original) == record["full_judge_record_sha256"])
            check(
                key + "_compact",
                compact
                == {
                    **record,
                    "result": {
                        k: v for k, v in original.items() if k not in ("request", "response")
                    },
                },
            )
            check(
                key + "_case_order_label",
                all(record[k] == case[k] for k in ("case_id", "role", "expected_verdict")),
            )
            per_case.append(
                {
                    "case_id": case["case_id"],
                    "verdict": replay.verdict,
                    "expected": case["expected_verdict"],
                    "logical_calls": cursor - before,
                    "generated_uncertainty": replay.generated_uncertainty is not None,
                    "record_sha256": record["full_judge_record_sha256"],
                }
            )
        check("all_requests_consumed", cursor == len(requests) == len(responses))
        call_rows = [row for row in ledger if row.get("event") == "call"]
        check("ledger_logical_calls", len(call_rows) == len(requests))
        reserved = {row["attempt"]: row for row in attempts if row.get("status") == "reserved"}
        terminal = [
            row
            for row in attempts
            if row.get("status") in {"returned", "ambiguous_failure", "invalid_usage"}
        ]
        check(
            "unique_attempt_ids",
            len(reserved) == sum(row.get("status") == "reserved" for row in attempts),
        )
        check(
            "attempt_journal_complete",
            len(terminal) == len(reserved) == cap["attempts"]
            and Counter(row["attempt"] for row in terminal)
            == Counter({key: 1 for key in reserved}),
        )
        actual = sum(
            float(row["conservative_usd"]) for row in terminal if row["status"] == "returned"
        )
        uncertain = sum(
            float(reserved[row["attempt"]]["reserved_usd"])
            for row in terminal
            if row["status"] != "returned"
        )
        check("physical_actual_reconciled", close(actual, float(cap["actual_usd"])))
        check("physical_uncertainty_retained", close(uncertain, float(cap["uncertain_usd"])))
        check("within_stage_cap", actual + uncertain < float(cap["limit_usd"]))
        check("physical_attempt_bound", cap["attempts"] <= 5 * len(requests))
        check(
            "only_authorized_judge_calls",
            all(
                row.get("model") == config.model
                and row.get("stage") == "validation"
                and row.get("attribution", {}).get("arm") == driver.ARM
                and row.get("attribution", {}).get("phase") == "judge_validation"
                for row in attempts
            ),
        )
        check("no_phase_b_dispatch", not (driver.RUN / "cap.json").exists())
        computed = driver.validation_decision(cases, result["outcomes"], result.get("interruption"))
        check("acceptance_recomputed", computed["decision"] == result["decision"])
        schema_ready = all(not case["generated_uncertainty"] for case in per_case)
        ready = result["decision"] == "JUDGE_GATE_READY" and schema_ready and all(checks.values())
        return {
            "schema_version": 1,
            "round": round_index,
            "integrity": "PASS" if all(checks.values()) else "FAIL",
            "judge_ready": ready,
            "checks": checks,
            "check_count": len(checks),
            "failed_checks": [key for key, passed in checks.items() if not passed],
            "cases": per_case,
            "logical_calls": len(requests),
            "physical_attempts": cap["attempts"],
            "conservative_actual_usd": actual,
            "uncertain_usd": uncertain,
            "stage_limit_usd": cap["limit_usd"],
            "private_result_sha256": digest((validation / "result.json").read_bytes()),
            "audit_source_sha256": digest(Path(__file__).read_bytes()),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_round(args.round)
    if args.output.exists():
        raise ValueError("audit destination already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "round",
                    "integrity",
                    "judge_ready",
                    "check_count",
                    "failed_checks",
                    "logical_calls",
                    "physical_attempts",
                )
            }
        )
    )
    return int(report["integrity"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
