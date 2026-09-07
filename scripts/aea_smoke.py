"""Phase D paid smoke: the AEA controller on three known-regime ALFWorld tasks (one band, one
saturated, one zero); Qwen3-8B via OpenRouter (Alibaba, reasoning off), DeepSeek V4 Pro designer.

Run from the repository root with a Python that has ALFWorld installed:
    PYTHONPATH=src python scripts/aea_smoke.py --tasks 6 1 9 --cap-usd 10 --run-id smoke-<date>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import LLMConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import write_manifest
from aea.llm.ledger import per_task_totals, read_ledger
from aea.runner import merge_ledgers
from aea.substrate import AeaSubstrate

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, nargs="+", default=[6, 1, 9])
    ap.add_argument("--cap-usd", type=float, default=10.0)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--arm", default="A")
    ap.add_argument("--no-designer", action="store_true")
    args = ap.parse_args(argv)

    policy = LLMConfig(
        provider="openrouter",
        model="qwen/qwen3-8b",
        provider_pin="alibaba",
        thinking=False,
        temperature=0.5,
        max_tokens=2048,
    )
    designer = LLMConfig(
        provider="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        provider_pin=None,
        thinking=False,
        temperature=0.7,
        max_tokens=4096,
    )
    run_config = RunConfig(
        schema_version=1,
        name="aea-smoke",
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=ROOT / "runs",
    )
    aea_config = AEAConfig()
    ctx = create_run_context(
        run_config,
        runs_root=ROOT / "runs",
        run_id=args.run_id,
        repo_dir=ROOT,
        aea_config_sha256=aea_config_sha256(aea_config),
    )
    env_sha = (
        subprocess.run(
            ["git", "-C", str(ROOT / "third_party" / "envharness"), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or None
    )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=env_sha,
        extra={"phase": "D-smoke", "tasks": args.tasks, "cap_usd": args.cap_usd, "arm": args.arm},
    )
    substrate = AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=ctx.out_dir,
        run_id=ctx.run_id,
        policy_llm=policy,
        designer_llm=None if args.no_designer else designer,
        aea_config=aea_config,
        stage_config_path=ROOT / "configs" / "alfworld_config_100.yaml",
        pricing_path=ROOT / "configs" / "pricing.yaml",
        rollout_concurrency=4,
    )
    controller = Controller(
        aea_config,
        substrate,
        ctx.out_dir,
        ctx.run_id,
        arm=args.arm,
        use_designer=not args.no_designer,
    )
    report: dict[str, object] = {"run_id": ctx.run_id, "tasks": {}}
    spent = 0.0
    for tid in args.tasks:
        outcome = controller.run_task(TaskRef(str(tid), tid))
        merge_ledgers(ctx.out_dir, ctx.run_id)
        totals = per_task_totals(read_ledger(ctx.out_dir / "ledger.jsonl"))
        spent = sum(t.usd for t in totals.values())
        report["tasks"][str(tid)] = {
            "status": outcome.status,
            "regime": outcome.regime,
            "p_hat": outcome.p_hat,
            "n_search": outcome.n_search,
            "detail": outcome.detail,
            "usd": totals.get(str(tid)).usd if str(tid) in totals else 0.0,
        }
        print(
            json.dumps(
                {
                    "task": tid,
                    "status": outcome.status,
                    "regime": outcome.regime,
                    "p_hat": outcome.p_hat,
                    "n_search": outcome.n_search,
                    "spent_usd": round(spent, 3),
                }
            ),
            flush=True,
        )
        if spent > args.cap_usd:
            print(f"SPEND CAP {args.cap_usd} exceeded ({spent:.2f}); stopping", flush=True)
            break
    from aea.io import write_accounting

    write_accounting(ctx.out_dir / "accounting.csv", controller.budget.accounting_rows())
    report["spent_usd"] = round(spent, 4)
    (ctx.out_dir / "smoke_report.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8"
    )
    print("run dir:", ctx.out_dir, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
