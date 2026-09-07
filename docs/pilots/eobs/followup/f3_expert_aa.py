"""F3 — expert A/A on recoverability prefixes (LLM-free). Attempt 1 = existing recoverability.jsonl value;
attempts 2 and 3 re-run `recover.c_at` on every prefix of 40 stratified-sampled failed trajectories.
Resumable by (trajectory_id, t, attempt). Sampling seed 20260907 (PREREG2)."""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # scratch/eobs
sys.path.insert(0, str(ROOT))
RES = ROOT / "results" / "eobs"
OUT = RES / "followup"
SEED = 20260907


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()] if Path(p).exists() else []


def sample(recov: list[dict], n_target: int = 40, per_task: int = 2) -> list[dict]:
    rnd = random.Random(SEED)
    by = defaultdict(list)
    for r in recov:
        by[r["task_id"]].append(r)
    picked = []
    for tid in sorted(by):
        rows = list(by[tid])
        rnd.shuffle(rows)
        picked.append(rows[0])
    # second picks, task order shuffled, until n_target or every task has per_task
    order = sorted(by)
    rnd.shuffle(order)
    for tid in order:
        if len(picked) >= n_target:
            break
        rows = [r for r in by[tid] if r not in picked]
        if rows:
            rnd.shuffle(rows)
            picked.append(rows[0])
    return picked[:n_target]


def _job(args: tuple) -> dict:
    trajectory_id, task_id, t, prefix, attempt = args
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    from eobs.recover import c_at
    t0 = time.time()
    c, reason = c_at(task_id, prefix)
    return {"trajectory_id": trajectory_id, "task_id": task_id, "t": t, "attempt": attempt, "C": c, "reason": reason, "wall_s": round(time.time() - t0, 2)}


def main(workers: int = 6) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    recov = _jsonl(RES / "recoverability.jsonl")
    base = {f"{b['source']}:{b['episode_id']}": b for b in _jsonl(RES / "baseline_rollouts.jsonl")}
    picked = sample(recov)
    (OUT / "expert_aa_sample.json").write_text(json.dumps({"seed": SEED, "n": len(picked), "trajectory_ids": [r["trajectory_id"] for r in picked],
                                                              "note": "only 19 tasks have failed trajectories; at most 2 per task caps n at 38 < 40 (logged deviation)"}, indent=1))
    out = OUT / "expert_aa_attempts.jsonl"
    done = {(r["trajectory_id"], r["t"], r["attempt"]) for r in _jsonl(out)}
    jobs = []
    for r in picked:
        acts = base[r["trajectory_id"]]["actions"]
        for t in range(r["T_eval"] + 1):
            for attempt in (2, 3):
                if (r["trajectory_id"], t, attempt) not in done:
                    jobs.append((r["trajectory_id"], r["task_id"], t, acts[:t], attempt))
    print(f"[F3] trajectories {len(picked)}; prefix-attempts to run {len(jobs)} (done {len(done)}); projected wall ≈ {len(jobs) * 3 / workers / 60:.0f} min at 3 s/session on {workers} workers", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool, open(out, "a", encoding="utf-8") as fh:
        for i, row in enumerate(pool.map(_job, jobs, chunksize=4), 1):
            fh.write(json.dumps(row) + "\n")
            if i % 200 == 0:
                fh.flush()
                print(f"[F3] {i}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    print(f"[F3] done in {time.time() - t0:.0f}s", flush=True)
    # merge into expert_aa.jsonl
    att = defaultdict(dict)
    for r in _jsonl(out):
        att[(r["trajectory_id"], r["t"])][r["attempt"]] = r
    rows = []
    for r in picked:
        for t in range(r["T_eval"] + 1):
            a2, a3 = att[(r["trajectory_id"], t)].get(2), att[(r["trajectory_id"], t)].get(3)
            rows.append({"trajectory_id": r["trajectory_id"], "task_id": r["task_id"], "t": t, "C_1": r["C_seq"][t], "C_2": a2 and a2["C"], "C_3": a3 and a3["C"],
                         "reasons": [r["reasons"][t], a2 and a2["reason"], a3 and a3["reason"]]})
    with open(OUT / "expert_aa.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    print(f"[F3] wrote expert_aa.jsonl ({len(rows)} prefixes)", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
