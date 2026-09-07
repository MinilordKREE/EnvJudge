"""P5.3 — bank-size dose on orig_m (P3b's 23 single_succ items): seeded subsamples (20260915) of sizes 3, 6, 9, 15 (23 = existing
orig_m condition), evaluated under the released protocol (30 ID + 30 OOD, 3 same-task replicates). Retrieval top_k recorded from the
eval yaml. Outputs p5/results/banks/orig_m_k{n}.jsonl and the eval runs work/runs/e1_p5_eval_r{rep}; tables via p5/evals.py."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = 20260915
SIZES = (3, 6, 9, 15)
SRC = ROOT / "results" / "e1pilot" / "banks" / "orig_m_qwen.jsonl"
OUT = ROOT / "p5" / "results" / "banks"


def subsample(items: list, k: int, seed: int) -> list:
    if k >= len(items):
        return list(items)
    rnd = random.Random(seed)
    idx = sorted(rnd.sample(range(len(items)), k))
    return [items[i] for i in idx]


def build() -> dict[str, Path]:
    items = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    OUT.mkdir(parents=True, exist_ok=True)
    conds = {}
    for k in SIZES:
        sub = subsample(items, k, SEED)
        p = OUT / f"orig_m_k{k}.jsonl"
        with open(p, "w") as fh:
            for it in sub:
                fh.write(json.dumps(it) + "\n")
        conds[f"orig_m_k{k}"] = p
        print(f"[P5.3] orig_m_k{k}: {len(sub)} items -> {p.name}", flush=True)
    return conds


if __name__ == "__main__":
    build()
