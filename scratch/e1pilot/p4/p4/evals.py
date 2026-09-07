"""P4.5 held-out evals (released protocol, same 30 ID + 30 OOD tasks, 3 same-task replicates) for the item-matched arms and
controls, plus the three full treatment banks (supplementary). nobank / P3 arms are reused, not re-run."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from e1 import p3a  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402

RES = ROOT / "p4" / "results"
BANKS = RES / "banks"


def conditions() -> dict[str, Path]:
    meta = json.loads((RES / "banks.json").read_text())
    conds = {}
    for arm in ("isat", "nsat", "nzero", "fhmid"):
        if not meta.get(arm, {}).get("built"):
            continue
        conds[f"{arm}_m"] = BANKS / f"{arm}_m.jsonl"; conds[f"origc_{arm}_m"] = BANKS / f"origc_{arm}_m.jsonl"; conds[f"{arm}_full"] = BANKS / f"{arm}_full.jsonl"
    return conds


def run_rep(rep: int, concurrency: int = 6) -> None:
    p3a.install_wrappers("p4_eval", "openrouter")
    os.environ["EOBS_RUN_ID"] = f"e1_p4_eval_r{rep}"
    sys.path.insert(0, str(ENVHARNESS_ROOT)); sys.path.insert(0, str(ENVHARNESS_ROOT / "experiments" / "alfworld"))
    os.chdir(ENVHARNESS_ROOT)
    import reasoning_bank_eval as rbe
    cfg = p3a.make_eval_config(30, 30, concurrency)
    conds = conditions()
    out = ROOT / "work" / "runs" / f"e1_p4_eval_r{rep}"
    argv = ["--config", str(cfg), "--out-dir", str(out), "--start-seeds", "0", "--conditions", ",".join(conds), "--concurrency", str(concurrency),
            "--bank-overrides", ",".join(f"{c}={p}" for c, p in conds.items())]
    rc = rbe.main(argv)
    print(f"[P4.5] rep {rep} rc={rc}", flush=True)


def tables(reps=(1, 2, 3)) -> None:
    rows = []
    def load(run, conds):
        for p in sorted((ROOT / "work" / "runs" / run).rglob("*.jsonl")):
            cond = next((c for c in sorted(conds, key=len, reverse=True) if p.stem.startswith(c + "_")), None)
            if cond is None:
                continue
            split = p.stem[len(cond) + 1:]
            for l in p.read_text().splitlines():
                if l.strip():
                    r = json.loads(l); rows.append({"rep": rep, "condition": cond, "split": split, "seed": r["seed"], "success": bool(r["success"]), "steps": r["duration_steps"], "error": r.get("error", "")})
    for rep in reps:
        load(f"e1_p3a_eval_r{rep}", ("nobank", "orig")); load(f"e1_p3b_eval_r{rep}", ("orig_m", "ours")); load(f"e1_p4_eval_r{rep}", list(conditions()))
    with open(RES / "evals.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"[P4.5] {len(rows)} episode rows -> evals.csv", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["eval", "tables"], required=True); ap.add_argument("--rep", type=int, default=1); ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args()
    run_rep(a.rep, a.concurrency) if a.stage == "eval" else tables()
