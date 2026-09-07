"""F5 — DeepSeek V4 Flash policy probe: K=8 baseline rollouts per task on seeds 0-29 through the released
Orchestrator._rollout_baseline_k (same code path as Phase 1), config = corpus_eobs.yaml with ONLY the policy model
id changed. Designer never called. Ledger phase flash_probe. Then an LLM-free recoverability sweep on ≤30 Flash
failed trajectories from tasks with p8 ≤ 0.2 (≤1 per task, seed 20260908)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eobs.settings import ENVHARNESS_ROOT, EOBS_ROOT, RESULTS, secrets  # noqa: E402

OUT = RESULTS / "followup"
RUN = "eobs_flash_probe"
FLASH = "openai/deepseek-v4-flash"


def make_config() -> Path:
    cfg = yaml.safe_load((EOBS_ROOT / "configs" / "corpus_eobs.yaml").read_text())
    cfg["policy"]["client_kwargs"]["inner_kwargs"]["model"] = FLASH
    p = EOBS_ROOT / "followup" / "corpus_eobs_flash.yaml"
    p.write_text("# F5: corpus_eobs.yaml with ONLY policy.client_kwargs.inner_kwargs.model -> openai/deepseek-v4-flash\n" + yaml.safe_dump(cfg, sort_keys=False, width=100))
    print("[F5] config sha256", hashlib.sha256(p.read_bytes()).hexdigest(), flush=True)
    return p


def rollouts(n: int = 30, k: int = 8) -> None:
    cfg_path = make_config()
    os.environ["OPENAI_API_KEY"] = secrets().deepseek_api_key.get_secret_value()
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["EOBS_RUN_ID"] = RUN; os.environ["EOBS_PHASE"] = "flash_probe"
    os.environ["PYTHONPATH"] = str(EOBS_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    sys.path.insert(0, str(ENVHARNESS_ROOT / "scripts")); sys.path.insert(0, str(ENVHARNESS_ROOT))
    os.chdir(ENVHARNESS_ROOT)
    import run_harness
    orch = run_harness.build_from_config(cfg_path, RUN, overrides={"n_tasks": n, "n_iterations": n, "k_per_candidate": k, "rollout_concurrency": k})
    orch.log.event("flash_probe_start", n_tasks=n, k=k, model=FLASH)
    for task_idx in range(n):
        task_id = orch.config.base_seed + task_idx * orch.config.task_id_stride + orch.config.task_id_base_offset
        if sum(1 for t in orch.trace_store.all() if t.rollout_seed == task_id) >= k:
            continue
        os.environ["EOBS_TASK_ID"] = str(task_id)
        t0 = time.time()
        traces = orch._rollout_baseline_k(task_idx, task_id)
        for t in traces:
            t.kind = "baseline"
            orch.trace_store.add(t)
        sr = sum(1 for t in traces if t.success) / max(len(traces), 1)
        orch.log.event("flash_probe_task_done", task_idx=task_idx, task_id=task_id, k=len(traces), sr=round(sr, 3), n_errors=sum(1 for t in traces if t.error), wall_s=round(time.time() - t0, 1))
        print(f"[F5] task {task_id}: p8_flash={sr:.2f} errors={sum(1 for t in traces if t.error)} {time.time() - t0:.0f}s", flush=True)
    orch.log.event("flash_probe_end", n_traces=len(orch.trace_store))


def tables() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tr = [json.loads(l) for l in (EOBS_ROOT / "work" / "runs" / RUN / "traces.jsonl").read_text().splitlines() if l.strip()]
    by = defaultdict(list)
    for t in tr:
        if not t.get("error"):
            by[t["rollout_seed"]].append(t)
    tasks = list(csv.DictReader(open(RESULTS / "tasks.csv", encoding="utf-8")))
    rows = []
    for t in tasks:
        tid = int(t["task_id"])
        rs = by.get(tid, [])
        p8 = sum(x["success"] for x in rs) / len(rs) if rs else None
        rows.append({"task_id": tid, "type": t["type"], "p8_flash": "" if p8 is None else round(p8, 4), "p16_pro": t["p16"], "n_flash": len(rs)})
    with open(OUT / "flash_p8.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("[F5] wrote flash_p8.csv", flush=True)


def flash_recoverability(cap: int = 30, workers: int = 6) -> None:
    from concurrent.futures import ProcessPoolExecutor
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    tr = [json.loads(l) for l in (EOBS_ROOT / "work" / "runs" / RUN / "traces.jsonl").read_text().splitlines() if l.strip()]
    by = defaultdict(list)
    for t in tr:
        if not t.get("error"):
            by[t["rollout_seed"]].append(t)
    rnd = random.Random(20260908)
    picked = []
    for tid in sorted(by):
        rs = by[tid]
        p8 = sum(x["success"] for x in rs) / len(rs)
        fails = [x for x in rs if not x["success"] and x.get("steps")]
        if p8 <= 0.2 and fails:
            picked.append(rnd.choice(fails))
    rnd.shuffle(picked)
    picked = picked[:cap]
    out = OUT / "flash_recoverability.jsonl"
    done = {json.loads(l)["trajectory_id"] for l in out.read_text().splitlines() if l.strip()} if out.exists() else set()
    jobs = [(f"flash:{t['episode_id']}", int(t["rollout_seed"]), [s["raw_action"]["kwargs"].get("text", "") for s in t["steps"]]) for t in picked if f"flash:{t['episode_id']}" not in done]
    print(f"[F5] flash recoverability: {len(picked)} trajectories from tasks with p8<=0.2; to do {len(jobs)}", flush=True)
    from eobs.phase4 import _one
    with ProcessPoolExecutor(max_workers=workers) as pool, open(out, "a") as fh:
        for rec in pool.map(_one, jobs):
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"[F5] {rec['trajectory_id']} T={rec['T']} L={rec['L']} monotone={rec['monotone']}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["rollouts", "tables", "recover", "all"], default="all"); a = ap.parse_args()
    if a.stage in ("rollouts", "all"):
        rollouts()
    if a.stage in ("tables", "all"):
        tables()
    if a.stage in ("recover", "all"):
        flash_recoverability()
