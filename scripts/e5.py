"""E5 (PREREG12 @ experiments/alfworld_e5/PREREG12.md): v0.2 midpoint start (arm A2) vs v0.4 soft
warm start (arm A4) on 8 saturated tasks, same code (tag aea-v0.4), same everything else; the only
difference is ``impl.warm_start_min_history`` (10^9 vs 3). Library families only, proposer off,
task concurrency 1. Runs write runs/e5-A2, runs/e5-A4, runs/e5-confirm; spend = every runs/e5-*
ledger against the cap.

Stages: A2 | A4 (the controller on the 8 tasks in the pre-registered order) -> confirm (K=16 on
every accepted environment of either arm) -> tables (scripts/make_tables_e5.py) -> spend.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from aea.config import AEAConfig, ImplConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import load_run_context, write_manifest
from aea.errors import ConfigError
from aea.io import TraceWriter, read_corpus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3

ROOT = e3.ROOT
RUNS = e3.RUNS
RESULTS = ROOT / "experiments" / "alfworld_e5" / "results"
TASKS: tuple[int, ...] = (3, 12, 13, 15, 22, 23, 24, 29)  # pre-registered order
PREREG_SHA = "TBD"
CAP_USD = 70.0
ARMS: dict[str, int] = {"A2": 10**9, "A4": 3}  # warm_start_min_history: v0.2 (never) vs v0.4
e3.SPEND_GLOB = "e5-*"  # the E3 helpers (spend guard, watchdog) now count runs/e5-*
e3.CAP_USD = CAP_USD
e3.EXPERIMENT = "E5 (v0.2 vs v0.4 saturated search, PREREG12)"


def config_for(arm: str) -> AEAConfig:
    return AEAConfig(impl=ImplConfig(warm_start_min_history=ARMS[arm]))


def stage_arm(arm: str) -> None:
    e3.guard(arm)
    cfg = config_for(arm)
    policy = e3.policy_qwen()
    run_id = f"e5-{arm}"
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=policy,  # RunConfig needs one; the proposer is OFF (manifest extra 'proposer')
        runs_root=RUNS,
    )
    d = RUNS / run_id
    if (d / "manifest.json").exists():
        ctx, _ = load_run_context(d)
    else:
        ctx = create_run_context(
            run_config,
            runs_root=RUNS,
            run_id=run_id,
            repo_dir=ROOT,
            aea_config_sha256=aea_config_sha256(cfg),
        )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=e3._git_sha(e3.ENVHARNESS),
        extra={
            "experiment": e3.EXPERIMENT,
            "arm": arm,
            "prereg_sha": PREREG_SHA,
            "tasks": list(TASKS),
            "task_order": "pre-registered (PREREG12)",
            "warm_start_min_history": ARMS[arm],
            "proposer": "off",
            "families": "library only (footer_mask, horizon_squeeze)",
            "policy_endpoint_pin": policy.provider_pin,
            "aea_config": cfg.model_dump(mode="json"),
            "concurrency": {"tasks": 1, "rollouts": e3.ROLLOUT_CONCURRENCY, "inflight_episodes": 4},
        },
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub = e3.substrate(
        ctx.out_dir, ctx.run_id, with_designer=False, concurrency=e3.ROLLOUT_CONCURRENCY
    )
    ctrl = Controller(cfg, sub, ctx.out_dir, ctx.run_id, arm=arm, use_proposer=False)
    stop = e3.start_watchdog(arm, ctx.out_dir / "events.jsonl")
    outcomes = ctrl.run([TaskRef(str(t), t) for t in TASKS], concurrency=1)
    stop.set()
    e3.merge(ctx.out_dir)
    for o in outcomes:
        print(
            json.dumps(
                {
                    "arm": arm,
                    "task": o.task.task_id,
                    "outcome": o.outcome,
                    "reason": o.reason,
                    "regime": o.regime,
                    "n_search": o.n_search,
                }
            ),
            flush=True,
        )
    e3.write_arm_manifest(
        ctx.out_dir, arm, {"run_id": ctx.run_id, "leverage_table": ctrl.leverage.snapshot()}
    )
    print(json.dumps({"stage": arm, "done": True, "usd": round(e3.dir_spend(ctx.out_dir), 2)}))


def accepted_envs() -> list[dict[str, Any]]:
    """Every accepted (transformed) environment of either arm, deduplicated by (task, candidate)."""
    envs: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        corpus = RUNS / f"e5-{arm}" / "corpus.jsonl"
        if not corpus.exists():
            continue
        for e in read_corpus(corpus):
            if e.aea.kind == "kept":
                continue
            cand = {"rules_code": e.rules_code, "in_env_actions": e.in_env_actions}
            env_id = f"{e.aea.task_id}:{e3.candidate_key(cand)}"
            rec = envs.setdefault(
                env_id,
                {
                    "id": env_id,
                    "task": e.aea.task_id,
                    "candidate": cand,
                    "kind": str(e.aea.kind),
                    "family": e.aea.family,
                    "d": e.aea.d,
                    "arms": [],
                },
            )
            if arm not in rec["arms"]:
                rec["arms"].append(arm)
    return sorted(envs.values(), key=lambda e: (int(e["task"]), e["id"]))


def stage_confirm(concurrency: int) -> None:
    e3.guard("confirm")
    d = RUNS / "e5-confirm"
    d.mkdir(parents=True, exist_ok=True)
    envs = accepted_envs()
    (d / "envs.json").write_text(json.dumps(envs, indent=1), encoding="utf-8")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub = e3.substrate(d, "e5-confirm", with_designer=False, concurrency=concurrency)
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "confirm.jsonl")
    for env in envs:
        if env["id"] in summary:
            summary[env["id"]]["arms"] = env["arms"]
            continue
        task = TaskRef(env["task"], int(env["task"]))
        rec = e3._k16(
            sub, writer, env["id"], task, e3.to_candidate(env["candidate"]), arm="confirm"
        )
        summary[env["id"]] = {
            **rec,
            "kind": env["kind"],
            "family": env["family"],
            "d": env["d"],
            "arms": env["arms"],
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": env["id"], "arms": env["arms"], **rec}), flush=True)
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    e3.merge(d)
    print(json.dumps({"stage": "confirm", "envs": len(envs), "usd": round(e3.dir_spend(d), 2)}))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["A2", "A4", "confirm", "tables", "spend"])
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args(argv)
    try:
        if args.stage in ARMS:
            stage_arm(args.stage)
        elif args.stage == "confirm":
            stage_confirm(args.concurrency)
        elif args.stage == "tables":
            mt5 = importlib.import_module("make_tables_e5")
            return int(mt5.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            p.name: round(e3.dir_spend(p), 2)
                            for p in sorted(RUNS.glob("e5-*"))
                            if p.is_dir()
                        },
                        "ts": time.strftime("%FT%TZ", time.gmtime()),
                    }
                )
            )
    except ConfigError as exc:
        print(f"CONFIG/GATE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
