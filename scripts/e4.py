"""E4 (PREREG11 @ experiments/alfworld_e4/PREREG11.md): does the regime a successful trajectory
comes from change the value of the skills induced from it? No new search rollout: every
trajectory is a success of the shared original-environment K=16 (runs/e2-shared, runs/e3-shared),
grouped by the shared p16 as in E3 layer 1: marginal (0, 0.2), band [0.2, 0.8], saturated (0.8, 1].

Arms (released single-success induction, DeepSeek V4 Pro extractor, two inductions per bank):
  M     the marginal tasks' successes (rare successes)
  B     the band tasks' successes
  S     the saturated tasks' successes
  MB    marginal + band (the skill-paradigm "learnable" set)
  B2_g<g>, S2_g<g>  task-count-matched sub-row: 2 tasks drawn from B and from S, 3 groups
  O_all, N, placebo  reused from E3-SL (runs/e3sl-eval), never re-run
Item matching: M, B, S, MB subsampled to k = min(items over M, B, S), floor 4 (an arm below the
floor keeps all its items and is recorded as drained). Evals as E3-SL (released
reasoning_bank_eval.py through the eval hook, Qwen3-8B consumer, ID 140 + OOD 134, seeds
0 / 1000 / 2000); paired per-task differences with the task-clustered bootstrap.

Runs write runs/e4-banks and runs/e4-eval; spend = every runs/e4-* ledger against the cap.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from aea.core.io import append_jsonl, read_jsonl
from aea.errors import ConfigError
from aea.evaldriver import run_eval
from aea.evalhook import GUARD_MARKER, install, make_hook
from aea.llm.attribution import attributed
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution
from aea.runner import merge_ledgers

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e3sl
import make_tables_e3 as mt

ROOT = e3.ROOT
RUNS = e3.RUNS
ENVHARNESS = e3.ENVHARNESS
PRICING = e3.PRICING
RESULTS = ROOT / "experiments" / "alfworld_e4" / "results"
BANKS = RUNS / "e4-banks"
EVAL = RUNS / "e4-eval"
META = BANKS / "banks_e4.json"
PREREG_SHA = "0833b8d"
AMENDMENT1_SHA = "419b45b"
CAP_USD = 130.0  # PREREG11 amendment 1 (2026-09-13): 130, full-bank rows decide
INDUCTIONS: tuple[int, ...] = (20260930, 20260931)
MATCHED_SEED = 20260932
COUNT_SEED = 20260933
K_FLOOR = 4
COUNT_GROUPS = 3
COUNT_TASKS = 2
SEEDS = e3sl.SEEDS
SPLITS = e3sl.SPLITS


# ---------------------------------------------------------------------------- groups
def groups() -> dict[str, list[str]]:
    """Task ids per regime from the shared K16 classes of E3 layer 1."""
    sh = mt.shared_classes()
    m = [t for t in mt.TASKS if sh[t]["cls"] == "marginal-low"]
    b = [t for t in mt.TASKS if sh[t]["cls"] == "band"]
    s = [t for t in mt.TASKS if sh[t]["cls"] == "saturated"]
    return {"M": m, "B": b, "S": s, "MB": m + b}


def shared_successes() -> dict[str, list[dict[str, Any]]]:
    """task -> successful shared K16 trajectories (the released picker takes the shortest)."""
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in (RUNS / "e2-shared", RUNS / "e3-shared"):
        for r in e3.jsonl(d / "confirm.jsonl"):
            if r.get("success") and not r.get("error") and r.get("steps"):
                by_task[str(r["rollout_seed"])].append(r)
    return dict(by_task)


# ---------------------------------------------------------------------------- spend
def spend() -> float:
    total = 0.0
    for top in RUNS.glob("e4-*"):
        if not top.is_dir():
            continue
        for d, _, _ in os.walk(top):
            total += e3sl._dir_usd(Path(d))
    return total


def guard(where: str) -> None:
    total = spend()
    print(
        json.dumps(
            {
                "spend_check": where,
                "usd": round(total, 2),
                "cap": CAP_USD,
                "ts": time.strftime("%FT%TZ", time.gmtime()),
            }
        ),
        flush=True,
    )
    if total >= CAP_USD:
        raise ConfigError(f"E4 cap USD {CAP_USD} reached ({total:.2f}); stopped at {where}")


# ---------------------------------------------------------------------------- banks
def meta() -> dict[str, Any]:
    return json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}


def save_meta(m: dict[str, Any]) -> None:
    BANKS.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(m, indent=1), encoding="utf-8")


def induce(name: str, by_task: dict[str, list[dict[str, Any]]], arm: str, seed: int) -> int:
    """Single-success induction through the released ``_build_bank`` (DeepSeek extractor for
    the completions, OpenRouter for the embeddings; rows on ``eval``, run id e4-banks)."""
    BANKS.mkdir(parents=True, exist_ok=True)
    label = Attribution(phase="induce", budget="eval", arm=arm, task_id="e4")
    install(
        make_hook(
            e3.designer_deepseek(),
            run_dir=BANKS,
            run_id="e4-banks",
            pricing=load_pricing(PRICING),
            default=(label, seed),
            embed_config=e3.policy_qwen(),
        )
    )
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    ip = e3sl._load_released("induce_pair", "scripts/induce_pair.py")
    path = BANKS / f"{name}.jsonl"
    with attributed(label, seed=seed):
        n = ip._build_bank(
            condition=name,
            traces_by_task=by_task,
            llm_model=f"openai/{e3.designer_deepseek().model}",
            concurrency=4,
            embed_model="openai/google/gemini-embedding-001",
            out_path=path,
        )
    merge_ledgers(BANKS, "e4-banks")
    return int(n)


def _record(
    m: dict[str, Any],
    name: str,
    arm: str,
    tasks: list[str],
    inputs: dict[str, Any],
    seed: int,
    n: int,
) -> None:
    m[name] = {
        "arm": arm,
        "items": n,
        "tasks": sorted(tasks, key=int),
        "trajectories": {t: len(inputs[t]) for t in tasks},
        "induction": e3sl._induction_mix(BANKS / f"{name}.jsonl"),
        "seed_label": seed,
        "extractor": e3.designer_deepseek().model,
        "note": "released single-success induction (temperature 0), shortest success per task",
    }
    save_meta(m)
    print(json.dumps({"bank": name, "items": n, "tasks": len(tasks)}), flush=True)


def stage_banks() -> None:
    guard("banks")
    m = meta()
    succ = shared_successes()
    g = groups()
    m["groups"] = g
    save_meta(m)
    for arm, tasks in g.items():
        missing = [t for t in tasks if t not in succ]
        if missing:
            raise ConfigError(f"arm {arm}: tasks without a shared success {missing}")
        inputs = {t: succ[t] for t in tasks}
        for k, seed in enumerate(INDUCTIONS, 1):
            name = f"{arm}_i{k}"
            if name in m and (BANKS / f"{name}.jsonl").exists():
                continue
            n = induce(name, inputs, arm, seed)
            _record(m, name, arm, tasks, inputs, seed, n)
    # task-count-matched sub-row: 2 tasks from B and from S, 3 groups (seed 20260933)
    rng = random.Random(COUNT_SEED)
    draws = m.get("count_groups") or {
        f"g{i}": {
            "B": sorted(rng.sample(g["B"], COUNT_TASKS), key=int),
            "S": sorted(rng.sample(g["S"], COUNT_TASKS), key=int),
        }
        for i in range(1, COUNT_GROUPS + 1)
    }
    m["count_groups"] = draws
    save_meta(m)
    for gname, picks in draws.items():
        for arm in ("B", "S"):
            tasks = picks[arm]
            inputs = {t: succ[t] for t in tasks}
            for k, seed in enumerate(INDUCTIONS, 1):
                name = f"{arm}2_{gname}_i{k}"
                if name in m and (BANKS / f"{name}.jsonl").exists():
                    continue
                n = induce(name, inputs, f"{arm}2", seed)
                _record(m, name, f"{arm}2", tasks, inputs, seed, n)
    print(json.dumps({"stage": "banks", "done": True, "usd": round(spend(), 2)}))


def stage_matched() -> None:
    m = meta()
    names = [f"{arm}_i{k}" for arm in ("M", "B", "S") for k in (1, 2)]
    sizes = {n: len(read_jsonl(BANKS / f"{n}.jsonl")) for n in names}
    k = min(sizes.values())
    drained: list[str] = []
    if k < K_FLOOR:
        k = K_FLOOR
        drained = [n for n, v in sizes.items() if v < K_FLOOR]
    (BANKS / "matched").mkdir(exist_ok=True)
    rng = random.Random(MATCHED_SEED)
    report: dict[str, Any] = {
        "k": k,
        "sizes": sizes,
        "drained": drained,
        "seed": MATCHED_SEED,
        "banks": {},
    }
    for arm in ("M", "B", "S", "MB"):
        for i in (1, 2):
            n = f"{arm}_i{i}"
            items = read_jsonl(BANKS / f"{n}.jsonl")
            sample = items if len(items) <= k else rng.sample(items, k)
            out = BANKS / "matched" / f"{n}_m.jsonl"
            out.write_text("".join(json.dumps(it) + "\n" for it in sample), encoding="utf-8")
            report["banks"][f"{n}_m"] = {
                "items": len(sample),
                "of": len(items),
                "full_row_is_matched_row": len(items) <= k,
            }
    m["matched"] = report
    save_meta(m)
    print(json.dumps(report, indent=0))


# ---------------------------------------------------------------------------- conditions / jobs
def conditions() -> dict[str, tuple[str, Path | None]]:
    out: dict[str, tuple[str, Path | None]] = {}
    m = meta()
    for name in m:
        if name in ("groups", "count_groups", "matched"):
            continue
        p = BANKS / f"{name}.jsonl"
        if p.exists():
            out[name] = (str(m[name].get("arm")), p)
        pm = BANKS / "matched" / f"{name}_m.jsonl"
        if pm.exists():
            out[f"{name}_m"] = (str(m[name].get("arm")), pm)
    return out


def jobs(group: str) -> list[tuple[str, int]]:
    m = meta()
    matched_report = m.get("matched", {}).get("banks", {})
    # amendment 1: full-bank rows decide and run first (every bank, including one whose full
    # bank is its matched bank); the matched rows skip a bank identical to its full bank (the
    # tables alias its cells); the task-count sub-row runs group g3 only (indicative)
    if group == "full":
        names = [f"{a}_i{k}" for a in ("M", "B", "S", "MB") for k in (1, 2)]
    elif group == "matched":
        names = [
            f"{a}_i{k}_m"
            for a in ("M", "B", "S", "MB")
            for k in (1, 2)
            if not matched_report.get(f"{a}_i{k}_m", {}).get("full_row_is_matched_row")
        ]
    elif group == "count":
        names = [f"{a}2_g3_i{k}" for a in ("B", "S") for k in (1, 2)]
    else:
        raise ConfigError(f"unknown group {group}")
    conds = conditions()
    missing = [n for n in names if n not in conds]
    if missing:
        raise ConfigError(f"conditions without a bank: {missing}")
    return [(n, s) for n in names for s in SEEDS]


def eval_dir(cond: str, seed: int) -> Path:
    return EVAL / f"{cond}-seeds-{seed}"


def _cells(d: Path, cond: str, split: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in e3sl.cell_files(d, cond, split):
        out.extend(e3.jsonl(f))
    return out


def cell_count(d: Path, cond: str, split: str) -> int:
    return sum(1 for r in _cells(d, cond, split) if not r.get("error"))


def stage_eval_job(cond: str, seed: int, concurrency: int) -> None:
    """One (condition, seed): both splits fresh, or exactly the missing episode seeds."""
    arm, bank = conditions()[cond]
    if bank is None or not bank.exists() or bank.stat().st_size == 0:
        raise ConfigError(f"empty bank for {cond}")
    policy = e3.policy_qwen()
    pricing = load_pricing(PRICING)
    base = eval_dir(cond, seed)
    for split in SPLITS:
        dropped = e3sl.drop_errored(base, cond, split)
        if dropped:
            print(json.dumps({"eval_job": cond, "seed": seed, "split": split, "dropped": dropped}))
    plan: list[tuple[str, int, int]] = []
    for split, n in SPLITS.items():
        plan += [(split, st, k) for st, k in e3sl.missing_runs(base, cond, split, seed, n)]
    if not plan:
        print(json.dumps({"eval_job": cond, "seed": seed, "complete": True}))
        return
    fresh = plan == [(split, seed, n) for split, n in SPLITS.items()]
    eval_yaml = ENVHARNESS / "experiments" / "alfworld" / "reasoning_bank_eval.yaml"
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    invocations = [(None, seed, SPLITS)] if fresh else [(sp, st, {sp: k}) for sp, st, k in plan]
    for only_split, start_seed, splits in invocations:
        cfg = yaml.safe_load(eval_yaml.read_text(encoding="utf-8"))
        cfg["model"]["name"] = f"openai/{policy.model}"
        cfg["eval"]["concurrency"] = concurrency
        cfg["eval"]["splits"] = {f"eval_{k}": v for k, v in splits.items()}
        out_dir = base if fresh else base.parent / f"{base.name}-resume-{int(time.time() * 1000)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved = out_dir / "reasoning_bank_eval_e4.yaml"
        resolved.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        rc = run_eval(
            arm=arm,
            conditions={cond: bank},
            config_yaml=resolved,
            out_dir=out_dir,
            start_seeds=(start_seed,),
            concurrency=concurrency,
            llm=policy,
            pricing=pricing,
            run_id="e4-eval",
            envharness_root=ENVHARNESS,
        )
        merge_ledgers(out_dir, "e4-eval")
        print(
            json.dumps(
                {
                    "eval_job": cond,
                    "seed": seed,
                    "split": only_split,
                    "start": start_seed,
                    "n": sum(splits.values()),
                    "concurrency": concurrency,
                    "rc": rc,
                    "out_dir": str(out_dir),
                }
            ),
            flush=True,
        )


def stage_evals(group: str) -> None:
    guard(f"evals-{group}")
    todo = jobs(group)
    pending = [
        (c, s)
        for c, s in todo
        if any(cell_count(eval_dir(c, s), c, split) < n for split, n in SPLITS.items())
    ]
    print(
        json.dumps({"stage": f"evals-{group}", "jobs": len(todo), "pending": len(pending)}),
        flush=True,
    )
    log_dir = EVAL / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    def run_job(job: tuple[str, int], concurrency: int) -> int:
        cond, seed = job
        with (log_dir / f"{cond}-{seed}.log").open("a", encoding="utf-8") as fh:
            return subprocess.call(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "e4.py"),
                    "--stage",
                    "eval-job",
                    "--cond",
                    cond,
                    "--seed",
                    str(seed),
                    "--concurrency",
                    str(concurrency),
                ],
                stdout=fh,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
            )

    def guard_incidents(job: tuple[str, int]) -> list[dict[str, Any]]:
        base = eval_dir(*job)
        found = []
        for d in [base, *base.parent.glob(f"{base.name}-resume-*")]:
            marker = d / GUARD_MARKER
            if marker.exists():
                found.append({"job": list(job), "dir": d.name, **json.loads(marker.read_text())})
                marker.rename(d / "guard_failure.handled.json")
        return found

    for done, job in enumerate(pending, 1):
        concurrency = e3sl.job_concurrency()
        print(json.dumps({"eval_start": job, "concurrency": concurrency}), flush=True)
        rc = 0
        for attempt in range(4):
            rc = run_job(job, concurrency)
            incidents = guard_incidents(job)
            for inc in incidents:
                append_jsonl(EVAL / "guard_incidents.jsonl", {**inc, "attempt": attempt})
                print(json.dumps({"guard_incident": inc}), flush=True)
            if rc == 0 or not incidents:
                break
        print(
            json.dumps(
                {
                    "eval_done": job,
                    "rc": rc,
                    "done": done,
                    "of": len(pending),
                    "usd": round(spend(), 2),
                }
            ),
            flush=True,
        )
        if rc:
            raise ConfigError(f"eval job {job} failed rc={rc}; see {log_dir}")
        if done % 3 == 0:
            guard(f"evals-{group} after {done} jobs")
    print(json.dumps({"stage": f"evals-{group}", "done": True, "usd": round(spend(), 2)}))


# ---------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["banks", "matched", "eval-job", "evals", "tables", "spend"],
    )
    ap.add_argument("--group", default="matched")
    ap.add_argument("--cond", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args(argv)
    try:
        if args.stage == "banks":
            stage_banks()
        elif args.stage == "matched":
            stage_matched()
        elif args.stage == "eval-job":
            stage_eval_job(args.cond, args.seed, args.concurrency)
        elif args.stage == "evals":
            stage_evals(args.group)
        elif args.stage == "tables":
            mt4 = importlib.import_module("make_tables_e4")
            return int(mt4.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(spend(), 2),
                        "cap": CAP_USD,
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
