"""P4.6 unlock on the 8 zero tasks (original env, eval protocol, 8 rollouts each): nobank vs nzero_full vs origc_nzero_full.
Uses the released `reasoning_bank_eval.run_episode` directly with split='train' and the zero tasks' seeds."""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from e1 import p3a  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402

RES = ROOT / "p4" / "results"
BANKS = RES / "banks"
_CFG = None; _BANK = None


def _init(cfg, bank_path):
    global _CFG, _BANK
    p3a.install_wrappers("p4_unlock", "openrouter")
    os.environ["EOBS_RUN_ID"] = "e1_p4_unlock"
    sys.path.insert(0, str(ENVHARNESS_ROOT)); sys.path.insert(0, str(ENVHARNESS_ROOT / "experiments" / "alfworld"))
    from envharness.reasoning_bank import Bank
    _CFG = cfg; _BANK = Bank.load(bank_path) if bank_path else None


def _one(args):
    seed, k = args
    import reasoning_bank_eval as rbe
    os.environ["EOBS_TASK_ID"] = str(seed)
    r = rbe.run_episode(cfg=_CFG, bank=_BANK, seed=seed, split="train", gemini_api_key=None)
    return {"seed": seed, "k": k, "success": bool(r["success"]), "steps": r["duration_steps"], "error": r.get("error", "")}


def main(n_roll: int = 8, concurrency: int = 6) -> None:
    import yaml
    zero = [int(r["task_id"]) for r in csv.DictReader(open(ROOT / "results" / "e1pilot" / "qwen_p16.csv")) if r["p16_qwen"] != "" and float(r["p16_qwen"]) == 0.0]
    cfg = yaml.safe_load((ROOT / "configs" / "reasoning_bank_eval_qwen.yaml").read_text())
    cfg["env"]["reset_options"] = {"repetition_threshold": 0}
    conds = {"nobank": None, "nzero_full": BANKS / "nzero_full.jsonl", "origc_nzero_full": BANKS / "origc_nzero_full.jsonl"}
    out = RES / "unlock_episodes.jsonl"
    done = defaultdict(int)
    if out.exists():
        for l in out.read_text().splitlines():
            if l.strip():
                r = json.loads(l); done[(r["condition"], r["seed"])] += 1
    for cond, bank in conds.items():
        if bank is not None and not Path(bank).exists():
            print(f"[P4.6] {cond}: bank missing, skipped", flush=True); continue
        jobs = [(s, k) for s in zero for k in range(done[(cond, s)], n_roll)]
        if not jobs:
            continue
        with ProcessPoolExecutor(max_workers=concurrency, initializer=_init, initargs=(cfg, str(bank) if bank else None)) as pool, open(out, "a") as fh:
            for r in pool.map(_one, jobs):
                fh.write(json.dumps({"condition": cond, **r}) + "\n"); fh.flush()
        print(f"[P4.6] {cond}: {len(jobs)} episodes done", flush=True)
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    summ = []
    for cond in conds:
        by = defaultdict(list)
        for r in rows:
            if r["condition"] == cond:
                by[r["seed"]].append(r["success"])
        if by:
            summ.append({"condition": cond, "n_tasks": len(by), "episodes": sum(len(v) for v in by.values()), "unlocked_tasks": sum(any(v) for v in by.values()),
                         "unlock_share": round(sum(any(v) for v in by.values()) / len(by), 4), "mean_success": round(sum(sum(v) for v in by.values()) / sum(len(v) for v in by.values()), 4),
                         "per_task": " ".join(f"{s}:{sum(v)}/{len(v)}" for s, v in sorted(by.items()))})
    with open(RES / "unlock.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
    for s in summ:
        print("[P4.6]", s, flush=True)


if __name__ == "__main__":
    main()
