"""Read-only eligibility/evidence audit for the frozen semantic LOW smoke.

Original pool screening and unused reference preparation are not adaptation. Actual task
starts, designer/proposal records, charged adaptation calls, and nonidentity policy traces
are consumption evidence. The output includes the inventory and hashes needed to reproduce
this audit; no prerequisite inventory file, policy, reference generation, or API is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from envharness.core.types import Trace

from aea.designer import Reference, ReferenceStep, reference_id, serialize_low
from aea.stage import seeded_failures

EXPECTED = (114, 115, 126, 129)
EVENTS = {
    "task_start",
    "llm_assist_proposals",
    "llm_diagnosis",
    "stage_candidates",
    "stage_family",
    "dose_control",
    "oracle_actuator",
    "proposer",
}
RECORDS = {"designer_calls.jsonl", "oracle_families.jsonl", "proposals.jsonl", "candidates.json"}
TRACE_FILES = {"traces.jsonl", "confirm.jsonl"}


def sha256_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            result.update(block)
    return result.hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def rows(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix == ".jsonl":
        with path.open() as stream:
            for line in stream:
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
    else:
        value = json.loads(path.read_text())
        for row in value if isinstance(value, list) else [value]:
            if isinstance(row, dict):
                yield row


def task_usage(row: dict[str, Any], path: Path) -> tuple[Any, str] | None:
    if path.name == "events.jsonl" and row.get("kind") in EVENTS:
        return row.get("payload", {}).get("task_id"), "event:" + str(row["kind"])
    if path.name.startswith("ledger.") and (
        row.get("budget") == "designer"
        or (
            row.get("budget") == "search"
            and row.get("phase") not in {"estimate", "original", "screen", "baseline"}
        )
    ):
        return row.get("task_id"), f"ledger:{row.get('budget')}:{row.get('phase')}"
    if path.name in RECORDS:
        task = row.get("task_id")
        if task is None and row.get("candidate_id"):
            task = str(row["candidate_id"]).split(":")[0]
        match = re.search(r"/task-(\d+)/", str(path))
        if task is None and match:
            task = match[1]
        return task, "record:" + path.name
    if path.name in TRACE_FILES:
        candidate = row.get("candidate") or {}
        if candidate.get("rules_code") or candidate.get("in_env_actions"):
            return row.get("rollout_seed"), "trace:nonidentity_candidate"
    return None


def pool_inventory(root: Path) -> list[dict[str, Any]]:
    inventory = []
    frozen = root / "experiments/alfworld_e6/frozen"
    paths = sorted(frozen.glob("low_pool*_k16.jsonl"))
    paths += sorted(frozen.glob("*-shared_confirm_summary.json"))
    for path in paths:
        if path.suffix == ".jsonl":
            records = list(rows(path))
        else:
            records = [
                row for row in json.loads(path.read_text()).values() if row.get("kind") == "orig"
            ]
        zero = sorted(
            int(str(row.get("task_id", row.get("task"))))
            for row in records
            if row.get("n") == 16 and row.get("successes") == 0 and row.get("errors") == 0
        )
        inventory.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": sha256_file(path),
                "original_classifications": len(records),
                "confirmed_zero_tasks": zero,
            }
        )
    return inventory


def adaptation_inventory(root: Path, zero: set[int]) -> tuple[dict[int, Any], list[Any], list[Any]]:
    used: dict[int, Any] = defaultdict(list)
    inventory: list[Any] = []
    errors: list[Any] = []
    paths = sorted(
        path
        for base in (root / "runs", root / "experiments")
        for path in base.rglob("*")
        if path.is_file()
        and (
            path.name in RECORDS | TRACE_FILES | {"events.jsonl"}
            or re.fullmatch(r"ledger\.\d+\.jsonl", path.name)
        )
    )
    for path in paths:
        if "semantic_privilege_offline" in str(path):
            continue
        hits: dict[int, set[str]] = defaultdict(set)
        relative = str(path.relative_to(root))
        try:
            for row in rows(path):
                hit = task_usage(row, path)
                if hit is None:
                    continue
                task, kind = hit
                if task is not None and str(task).isdigit() and int(task) in zero:
                    hits[int(task)].add(kind)
            inventory.append(
                {"path": relative, "sha256": sha256_file(path), "matched_tasks": sorted(hits)}
            )
            for task, kinds in hits.items():
                used[task].append({"path": relative, "kinds": sorted(kinds)})
        except Exception as exc:
            errors.append({"path": relative, "error": f"{type(exc).__name__}: {exc}"})
    return dict(sorted(used.items())), inventory, errors


def reference_inventory(root: Path, task: int, prior: dict[str, Any] | None) -> dict[str, Any]:
    path = root / f"runs/e6-iterative-low-smoke/task-{task}/privileged_reference.json"
    if not path.exists():
        return {
            "task_id": task,
            "path": None,
            "success": None,
            "protocol": "obtain and freeze one local provider result",
        }
    ref = json.loads(path.read_text())
    rich = bool(
        ref["success"]
        and ref["steps"]
        and [step["action"] for step in ref["steps"]] == ref["actions"]
        and all(step["observation"] and step["admissible"] for step in ref["steps"])
        and reference_id(ref["actions"]) == ref["reference_id"]
    )
    return {
        "task_id": task,
        "path": str(path.relative_to(root)),
        "file_sha256": sha256_file(path),
        "canonical_sha256": digest(ref),
        "success": ref["success"],
        "reason": ref["reason"],
        "steps": ref["n_steps"],
        "reference_id": ref["reference_id"],
        "verified_rich_record_consistent": rich,
        "prior_prepared_matches": prior is not None and prior["reference_sha256"] == digest(ref),
        "protocol": "reuse exact previous provider result; successful or unavailable",
    }


def evidence_inventory(root: Path) -> tuple[list[Any], list[Any], list[str]]:
    original = root / "runs/e6-pool3-k16/confirm.jsonl"
    by_task: dict[int, list[Any]] = defaultdict(list)
    for row in rows(original):
        task = int(row["rollout_seed"])
        if task in EXPECTED:
            by_task[task].append(row)
    prepared_path = root / "runs/e6-iterative-low-smoke/prepared.json"
    prepared = {int(row["task_id"]): row for row in json.loads(prepared_path.read_text())}
    evidence, references, errors = [], [], []
    for task in EXPECTED:
        traces = [Trace.model_validate(row) for row in by_task[task]]
        selected = seeded_failures(traces[:10], 3, seed=task)
        valid = (
            len(traces) == 16
            and len(selected) == 3
            and all(
                not trace.success
                and not trace.error
                and not trace.candidate.rules_code
                and not trace.candidate.in_env_actions
                and trace.steps
                and len(trace.steps) == trace.duration_steps
                and all(
                    step.raw_action and step.raw_observation and step.raw_observation.text
                    for step in trace.steps
                )
                for trace in traces
            )
        )
        value = [trace.model_dump() for trace in selected]
        row = {
            "task_id": task,
            "stored_original_count": len(traces),
            "frozen_classification": "0/16",
            "evidence_convention": "first ten stored K16 episodes; seeded_failures(n=3, seed=task)",
            "selected_episode_ids": [trace.episode_id for trace in selected],
            "selected_lengths": [len(trace.steps) for trace in selected],
            "selected_source_indices": [
                next(i for i, trace in enumerate(traces) if trace.episode_id == item.episode_id)
                for item in selected
            ],
            "evidence_sha256": digest(value),
            "trajectory_sha256": {
                trace.episode_id: digest(trace.model_dump()) for trace in selected
            },
            "all_original_trajectories_complete_and_unmodified": bool(valid),
            "source": str(original.relative_to(root)),
            "prior_prepared_matches": None,
        }
        prior = prepared.get(task)
        if prior:
            path = root / f"runs/e6-iterative-low-smoke/task-{task}/original_failures.json"
            row["prior_prepared_matches"] = (
                prior["evidence_sha256"] == row["evidence_sha256"]
                and prior["evidence_ids"] == row["selected_episode_ids"]
                and digest(json.loads(path.read_text())) == row["evidence_sha256"]
            )
        if not valid or row["prior_prepared_matches"] is False:
            errors.append(f"invalid or mismatched original evidence for task {task}")
        refrow = reference_inventory(root, task, prior)
        if refrow.get("verified_rich_record_consistent"):
            raw = json.loads((root / str(refrow["path"])).read_text())
            reference = Reference(
                True,
                raw["reason"],
                tuple(raw["actions"]),
                tuple(
                    ReferenceStep(
                        step["step"], step["observation"], tuple(step["admissible"]), step["action"]
                    )
                    for step in raw["steps"]
                ),
            )
            row["serialized_evidence_sha256"] = serialize_low(
                selected, 0.0, 10, reference, rich=True
            ).sha256
        if refrow.get("path") and not refrow.get("prior_prepared_matches"):
            errors.append(f"reference provenance mismatch for task {task}")
        evidence.append(row)
        references.append(refrow)
    return evidence, references, errors


def audit(root: Path) -> dict[str, Any]:
    pools = pool_inventory(root)
    pool_path = "experiments/alfworld_e6/frozen/low_pool3_k16.jsonl"
    pool = next(item for item in pools if item["path"] == pool_path)
    zero = set(pool["confirmed_zero_tasks"])
    used, files, parse_errors = adaptation_inventory(root, zero)
    eligible = sorted(zero - used.keys())
    evidence, references, errors = evidence_inventory(root)
    return {
        "starting_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=root, text=True
        ).strip(),
        "pool": pool_path,
        "pool_sha256": pool["sha256"],
        "frozen_pool_inventory": pools,
        "frozen_zero_pool_overlaps": [
            {
                "left": left["path"],
                "right": right["path"],
                "tasks": sorted(
                    set(left["confirmed_zero_tasks"]) & set(right["confirmed_zero_tasks"])
                ),
            }
            for i, left in enumerate(pools)
            for right in pools[i + 1 :]
        ],
        "original_trace_file": "runs/e6-pool3-k16/confirm.jsonl",
        "original_trace_file_sha256": sha256_file(root / "runs/e6-pool3-k16/confirm.jsonl"),
        "zero": sorted(zero),
        "used": sorted(used),
        "eligible": eligible,
        "expected": list(EXPECTED),
        "eligible_matches_expected": eligible == list(EXPECTED),
        "adaptation_sources": used,
        "scanned_file_count": len(files),
        "scanned_files": files,
        "scanned_file_manifest_sha256": digest(files),
        "parse_errors": parse_errors,
        "evidence": evidence,
        "references": references,
        "errors": errors,
        "not_usage": (
            "Mere prepared.json membership and local reference preparation "
            "without adaptation are not consumption."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "eligible",
                    "eligible_matches_expected",
                    "scanned_file_count",
                    "parse_errors",
                    "errors",
                )
            }
        )
    )
    return (
        0
        if result["eligible_matches_expected"]
        and not result["errors"]
        and not result["parse_errors"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
