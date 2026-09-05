"""Phase 4: recoverability sweep over EVERY failed base-env trajectory (Phase-1 extras + EnvRigger baselines), multiprocess.
No sampling. Each prefix is a fresh reset+replay session (~5 s), so a 50-step trajectory costs ~51 sessions."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from eobs.settings import RESULTS


def _one(args: tuple) -> dict:
    tid, task_id, actions = args
    from eobs.recover import recoverability
    return recoverability(tid, task_id, actions)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=None, help="debug only; a limit must be declared in LOG before use")
    a = ap.parse_args()
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    rows = [json.loads(l) for l in (RESULTS / "baseline_rollouts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    failed = [r for r in rows if not r["success"] and not r.get("error") and r.get("actions")]
    out = RESULTS / "recoverability.jsonl"
    done = {json.loads(l)["trajectory_id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
    todo = [(f"{r['source']}:{r['episode_id']}", int(r["task_id"]), r["actions"]) for r in failed if f"{r['source']}:{r['episode_id']}" not in done]
    if a.limit:
        todo = todo[: a.limit]
    print(f"[phase4] failed trajectories {len(failed)}; to do {len(todo)} (done {len(done)}); total prefixes ≈ {sum(min(len(t[2]), 50) + 1 for t in todo)}", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool, open(out, "a", encoding="utf-8") as fh:
        for rec in pool.map(_one, todo):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[phase4] {rec['trajectory_id']} T={rec['T']} L={rec['L']} first_zero={rec['first_zero']} monotone={rec['monotone']} expert_fail={rec['expert_errors']}", flush=True)


if __name__ == "__main__":
    main()
