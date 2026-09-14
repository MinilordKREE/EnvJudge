"""Phase 3.3a part A (experiments/alfworld_e6/PREREG_LOW_POOL2.md): K = 16 original-environment
classification of the 50 fresh tasks 30..79 with the current policy. No designer, no reference,
no Stage. Output: runs/e6-pool2-k16 (traces, summary, ledger) frozen to
experiments/alfworld_e6/frozen/low_pool2_k16.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate

from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.errors import ConfigError
from aea.io import TraceWriter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_refalign as er
import e6_smoke as e6

RUNS = e6.RUNS
FROZEN = e6.FROZEN
RUN_ID = "e6-pool2-k16"
USED: frozenset[int] = frozenset(range(30))  # USED_TASKS_AUDIT.md
TASKS: tuple[int, ...] = tuple(t for t in range(30, 80) if t not in USED)
PREREG_SHA: str | None = None  # PREREG_LOW_POOL2.md commit, recorded before the first paid call
CAP_USD = 60.0
K = 16
INFLIGHT = 16

e3.SPEND_GLOB = "e6-pool2-*"
e3.CAP_USD = CAP_USD
e3.EXPERIMENT = "E6 pool 2 (fresh K16 behavioural classification, PREREG_LOW_POOL2)"


def classify(rec: dict[str, Any]) -> str:
    if rec["errors"]:
        return "invalid"
    if rec["successes"] == 0:
        return "zero"
    if rec["successes"] == rec["n"] == K:
        return "saturated"
    return "middle"


def stage_k16() -> None:
    if PREREG_SHA is None:
        raise ConfigError("PREREG_SHA not recorded: commit PREREG_LOW_POOL2.md first")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    e3.guard("pool2")
    d = RUNS / RUN_ID
    cfg = AEAConfig()  # v0.4 defaults: only the substrate and the K16 helper are used
    er._manifest(
        d,
        RUN_ID,
        cfg,
        {
            "stage": "pool2 k16",
            "prereg": "experiments/alfworld_e6/PREREG_LOW_POOL2.md",
            "prereg_sha_pool2": PREREG_SHA,
            "pool_tasks": list(TASKS),
            "k": K,
            "inflight": INFLIGHT,
        },
    )
    sub = e3.substrate(d, RUN_ID, with_designer=False, concurrency=INFLIGHT)
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "confirm.jsonl")
    n_run = 0
    for t in TASKS:
        key = f"{t}:orig"
        if key in summary:
            continue
        task = TaskRef(str(t), t)
        rec = e3._k16(sub, writer, key, task, Candidate(), arm="pool2", n=K)
        rec["class"] = classify(rec)
        summary[key] = rec
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps(rec), flush=True)
        n_run += 1
        if n_run % 5 == 0:
            e3.merge(d)
            e3.guard(f"pool2 after {n_run} tasks")
    e3.merge(d)
    freeze(summary)
    print(json.dumps({"stage": "pool2", "tasks": len(summary), "usd": round(e3.dir_spend(d), 2)}))


def freeze(summary: dict[str, Any]) -> Path:
    FROZEN.mkdir(parents=True, exist_ok=True)
    out = FROZEN / "low_pool2_k16.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for t in TASKS:
            r = summary.get(f"{t}:orig")
            if r is None:
                continue
            fh.write(
                json.dumps(
                    {
                        "task_id": str(t),
                        "successes": r["successes"],
                        "n": r["n"],
                        "errors": r["errors"],
                        "p16": r["p16"],
                        "class": r["class"],
                    }
                )
                + "\n"
            )
    return out


def low_pool2() -> list[int]:
    rows = e3.jsonl(FROZEN / "low_pool2_k16.jsonl")
    return sorted(int(r["task_id"]) for r in rows if r["class"] == "zero")


def distribution() -> dict[str, int]:
    rows = e3.jsonl(FROZEN / "low_pool2_k16.jsonl")
    out: dict[str, int] = {"zero": 0, "middle": 0, "saturated": 0, "invalid": 0}
    for r in rows:
        out[str(r["class"])] = out.get(str(r["class"]), 0) + 1
    out["measured"] = len(rows)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["probe", "k16", "summary", "spend"])
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe":
            return e3.stage_probe()
        if args.stage == "k16":
            stage_k16()
        elif args.stage == "summary":
            print(json.dumps({"distribution": distribution(), "low_pool2": low_pool2()}))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "ts": time.strftime("%FT%TZ", time.gmtime()),
                    }
                )
            )
    except ConfigError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
