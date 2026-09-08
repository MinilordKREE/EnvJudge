"""Phase 0b E0: EnvRigger released on seeds 0-19 with the E1-SL backbone, single-success banks,
released eval on the full splits x 3 seeds, cost per episode and the rounds projection.

Stages (resumable, each writes into runs/<run-id>/):
  corpus  released orchestrator (scripts/run_harness.build_from_config) with both clients routed
          through AeaLLMClient (designer rows budget=designer, policy rows budget=search, arm R)
  banks   N (none) / orig (baseline successes) / R (accepted successes), single-success induction
          through the released _build_bank under the eval hook (Flash-Lite as consumer, embeddings
          via OpenRouter)
  eval    aea.evaldriver.run_eval for N / orig / R, full ID + OOD, start seeds 0/1000/2000
  report  table next to EnvHarness Table 2, USD per corpus episode and per eval episode, projection
Run: uv run python scripts/e0.py --stage corpus|banks|eval|report --run-id e0-<date>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from aea.config import AEAConfig, aea_config_sha256
from aea.core.config import LLMConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import load_run_context, write_manifest
from aea.e0config import derive_corpus_config, write_corpus_config
from aea.errors import ConfigError
from aea.evaldriver import run_eval
from aea.evalhook import install, make_hook
from aea.io import training_traces
from aea.llm.attribution import attributed
from aea.llm.ledger import read_ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution
from aea.runner import AeaSubprocessRunner, merge_ledgers

ROOT = Path(__file__).resolve().parents[1]
ENVHARNESS = ROOT / "third_party" / "envharness"
TABLE2 = {"N": (62.6, 60.7), "orig": (63.3, 61.4), "EnvHarness": (66.2, 70.4)}


def backbone(fallback: bool) -> tuple[LLMConfig, LLMConfig]:
    if fallback:
        policy = LLMConfig(
            provider="openrouter",
            model="qwen/qwen3-8b",
            provider_pin="alibaba",
            thinking=False,
            temperature=0.5,
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
        return policy, designer
    policy = LLMConfig(
        provider="openrouter",
        model="google/gemini-3.1-flash-lite",
        provider_pin="google-ai-studio",
        thinking=None,
        temperature=0.5,
        max_tokens=2048,
    )
    return policy, policy.model_copy(update={"temperature": 0.7, "max_tokens": 4096})


def run_dir_for(run_id: str) -> Path:
    return ROOT / "runs" / run_id


def stage_corpus(run_id: str, n_tasks: int, fallback: bool) -> None:
    policy, designer = backbone(fallback)
    run_config = RunConfig(
        schema_version=1,
        name="e0-corpus",
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=ROOT / "runs",
    )
    ctx = create_run_context(
        run_config,
        runs_root=ROOT / "runs",
        run_id=run_id,
        repo_dir=ROOT,
        aea_config_sha256=aea_config_sha256(AEAConfig()),
    )
    env_sha = (
        subprocess.run(
            ["git", "-C", str(ENVHARNESS), "rev-parse", "HEAD"],
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
        extra={
            "phase": "0b-E0",
            "stage": "corpus",
            "arm": "R",
            "n_tasks": n_tasks,
            "policy_endpoint_pin": policy.provider_pin,
            "designer_endpoint_pin": designer.provider_pin,
            "thinking": policy.thinking,
            "prereg": "experiments/alfworld_sl/PREREG7.md",
        },
    )
    cfg = derive_corpus_config(
        ENVHARNESS / "experiments" / "alfworld" / "corpus.yaml",
        run_dir=ctx.out_dir,
        policy=policy,
        designer=designer,
        pricing_path=ROOT / "configs" / "pricing.yaml",
    )
    cfg_path = write_corpus_config(cfg, ctx.out_dir / "corpus_e0.yaml")
    sys.path.insert(0, str(ENVHARNESS / "scripts"))
    sys.path.insert(0, str(ENVHARNESS))
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"  # the released key presence check only
    os.environ["AEA_RUN_ID"] = ctx.run_id
    run_harness = importlib.import_module("run_harness")
    orch = run_harness.build_from_config(
        cfg_path, run_id, overrides={"n_tasks": n_tasks, "n_iterations": n_tasks}
    )
    orch.runner = AeaSubprocessRunner(
        ctx.run_id,
        default=(Attribution(phase="corpus", budget="search", arm="R", task_id="e0"), 0),
        timeout=float(cfg["runner"].get("timeout_seconds", 600)),
        subprocess_log_dir=ctx.out_dir / "subprocess_logs",
    )
    with attributed(Attribution(phase="corpus", budget="search", arm="R", task_id="e0"), seed=0):
        orch.run()
    merge_ledgers(ctx.out_dir, ctx.run_id)
    print(
        json.dumps(
            {"stage": "corpus", "run_dir": str(ctx.out_dir), "traces": len(orch.trace_store.all())}
        ),
        flush=True,
    )


def stage_banks(run_id: str, fallback: bool) -> None:
    run_dir = run_dir_for(run_id)
    ctx, _manifest = load_run_context(run_dir)
    policy, _ = backbone(fallback)
    pricing = load_pricing(ROOT / "configs" / "pricing.yaml")
    hook = make_hook(policy, run_dir=run_dir, run_id=ctx.run_id, pricing=pricing)
    install(hook)
    sys.path.insert(0, str(ENVHARNESS))
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    spec = importlib.util.spec_from_file_location(
        "induce_pair", ENVHARNESS / "scripts" / "induce_pair.py"
    )
    assert spec and spec.loader
    ip = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ip)
    traces = training_traces(run_dir / "traces.jsonl")
    by_kind: dict[str, dict[str, list[dict[str, Any]]]] = {
        "orig": defaultdict(list),
        "R": defaultdict(list),
    }
    for t in traces:
        if t.error or not t.success:
            continue  # single-success induction: successes only
        task = str(t.rollout_seed)
        if t.kind == "baseline":
            by_kind["orig"][task].append(t.model_dump())
        elif t.kind == "accepted":
            by_kind["R"][task].append(t.model_dump())
    meta: dict[str, Any] = {}
    banks_dir = run_dir / "banks"
    banks_dir.mkdir(exist_ok=True)
    with attributed(Attribution(phase="induce", budget="eval", arm="R", task_id="e0"), seed=0):
        for cond, by_task in by_kind.items():
            out = banks_dir / f"{cond}.jsonl"
            n = (
                ip._build_bank(
                    condition=cond,
                    traces_by_task=dict(by_task),
                    llm_model=f"openai/{policy.model}",
                    concurrency=4,
                    embed_model="openai/google/gemini-embedding-001",
                    out_path=out,
                )
                if by_task
                else 0
            )
            meta[cond] = {
                "tasks": sorted(by_task),
                "items": n,
                "trajectories": {k: len(v) for k, v in by_task.items()},
            }
            print(
                json.dumps(
                    {"stage": "banks", "condition": cond, "items": n, "tasks": len(by_task)}
                ),
                flush=True,
            )
    (run_dir / "banks.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    merge_ledgers(run_dir, ctx.run_id)


def stage_eval(run_id: str, fallback: bool, seeds: tuple[int, ...], concurrency: int) -> None:
    run_dir = run_dir_for(run_id)
    ctx, _ = load_run_context(run_dir)
    policy, _ = backbone(fallback)
    pricing = load_pricing(ROOT / "configs" / "pricing.yaml")
    eval_yaml = ENVHARNESS / "experiments" / "alfworld" / "reasoning_bank_eval.yaml"
    cfg = yaml.safe_load(eval_yaml.read_text(encoding="utf-8"))
    cfg["model"]["name"] = f"openai/{policy.model}"
    cfg["eval"]["concurrency"] = concurrency
    resolved = run_dir / "reasoning_bank_eval_e0.yaml"
    resolved.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    banks_dir = run_dir / "banks"
    conditions = {"nobank": None, "orig": banks_dir / "orig.jsonl", "R": banks_dir / "R.jsonl"}
    conditions = {k: v for k, v in conditions.items() if v is None or v.exists()}
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    rc = run_eval(
        arm="R",
        conditions=conditions,
        config_yaml=resolved,
        out_dir=run_dir / "eval",
        start_seeds=seeds,
        concurrency=concurrency,
        llm=policy,
        pricing=pricing,
        run_id=ctx.run_id,
        envharness_root=ENVHARNESS,
    )
    merge_ledgers(run_dir / "eval", ctx.run_id)
    print(json.dumps({"stage": "eval", "rc": rc, "conditions": list(conditions)}), flush=True)


def stage_report(run_id: str) -> None:
    run_dir = run_dir_for(run_id)
    rows = read_ledger(run_dir / "ledger.jsonl") if (run_dir / "ledger.jsonl").exists() else []
    erows = (
        read_ledger(run_dir / "eval" / "ledger.jsonl")
        if (run_dir / "eval" / "ledger.jsonl").exists()
        else []
    )
    traces = (
        training_traces(run_dir / "traces.jsonl") if (run_dir / "traces.jsonl").exists() else []
    )
    corpus_usd = sum(r.usd for r in rows if r.event == "call" and r.budget == "search")
    designer_usd = sum(r.usd for r in rows if r.event == "call" and r.budget == "designer")
    induce_usd = sum(r.usd for r in rows if r.event == "call" and r.phase == "induce")
    eval_usd = sum(r.usd for r in erows if r.event == "call" and r.budget == "eval")
    episodes = len(traces)
    results: dict[str, dict[str, float]] = {}
    for p in sorted((run_dir / "eval").rglob("*.jsonl")) if (run_dir / "eval").exists() else []:
        if p.name.startswith("ledger"):
            continue
        cond, split = p.stem.rsplit("_eval_", 1)
        recs = [
            json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        results.setdefault(cond, {}).setdefault(split, 0.0)
        results[cond][split + "_n"] = results[cond].get(split + "_n", 0.0) + len(recs)
        results[cond][split] = results[cond].get(split, 0.0) + sum(
            1 for r in recs if r.get("success")
        )
    eval_episodes = int(sum(v for c in results.values() for k, v in c.items() if k.endswith("_n")))
    lines = [
        f"# E0 reproduction ({run_id})",
        "",
        "| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |",
        "|---|---|---|---|---|",
    ]
    for cond, label in (("nobank", "N"), ("orig", "orig"), ("R", "EnvHarness")):
        r = results.get(cond, {})
        idn, oodn = r.get("in_distribution_n", 0.0), r.get("out_of_distribution_n", 0.0)
        ours_id = 100 * r.get("in_distribution", 0.0) / idn if idn else float("nan")
        ours_ood = 100 * r.get("out_of_distribution", 0.0) / oodn if oodn else float("nan")
        t2 = TABLE2[label]
        lines.append(
            f"| {label} | {ours_id:.1f} (n={int(idn)}) | {ours_ood:.1f} (n={int(oodn)}) "
            f"| {t2[0]} | {t2[1]} |"
        )
    per_corpus = corpus_usd / episodes if episodes else float("nan")
    per_eval = eval_usd / eval_episodes if eval_episodes else float("nan")
    lines += [
        "",
        f"Corpus: {episodes} policy episodes, USD {corpus_usd:.2f} (USD {per_corpus:.4f} per "
        f"episode); designer USD {designer_usd:.2f}; induction USD {induce_usd:.2f}.",
        f"Eval: {eval_episodes} episodes, USD {eval_usd:.2f} (USD {per_eval:.4f} per episode).",
        "",
    ]
    n_tasks = len({t.rollout_seed for t in traces})
    per_task = corpus_usd / n_tasks if n_tasks else float("nan")
    for n in (30, 50):
        adapt_arms = 3 * 3 + 4  # rounds 1-3 x {R, A, O} + round-1 {G, G+, A-ex, A+H}
        corpus_cost = adapt_arms * n * per_task
        confirm = adapt_arms * n * 16 * per_corpus
        evals = (3 * 3 + 4 + 1) * 3 * 274 * per_eval  # arms per round incl. N, 3 seeds, full splits
        lines.append(
            f"Projection N={n}: corpus USD {corpus_cost:.0f} + confirmations USD {confirm:.0f} "
            f"+ evals USD {evals:.0f} = USD {corpus_cost + confirm + evals:.0f}"
        )
    lines.append(
        f"Backbone rule: corpus episode USD {per_corpus:.4f} "
        f"{'>' if per_corpus > 0.10 else '<='} 0.10 -> "
        f"{'FALLBACK' if per_corpus > 0.10 else 'Flash-Lite stays'}."
    )
    (run_dir / "phase0b_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["corpus", "banks", "eval", "report"], required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n-tasks", type=int, default=20)
    ap.add_argument("--fallback", action="store_true")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1000, 2000])
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args(argv)
    try:
        if args.stage == "corpus":
            stage_corpus(args.run_id, args.n_tasks, args.fallback)
        elif args.stage == "banks":
            stage_banks(args.run_id, args.fallback)
        elif args.stage == "eval":
            stage_eval(args.run_id, args.fallback, tuple(args.seeds), args.concurrency)
        else:
            stage_report(args.run_id)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
