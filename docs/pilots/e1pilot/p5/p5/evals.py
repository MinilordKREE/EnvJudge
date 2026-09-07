"""P5 held-out evals (released protocol, 30 ID + 30 OOD, 3 same-task replicates) for the P5.2 matched banks and the P5.3 bank-size
subsamples; every existing condition (nobank, orig, orig_m, ours, P4 arms) is reused from its run dir, never re-run.
Run dirs work/runs/e1_p5_eval_r{rep}; --skip-done resumes at the condition level. Tables → p5/results/evals_p5.csv."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
for p in (ROOT, EOBS, ROOT / "p4", ROOT / "p5"):
    sys.path.insert(0, str(p))
from e1 import p3a  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402

RES = ROOT / "p5" / "results"


def conditions(group: str) -> dict[str, Path]:
    if group == "ss":
        return {c: RES / f"{c}_m.jsonl" for c in ("isat_ss", "origc_isat_ss") if (RES / f"{c}_m.jsonl").exists()}
    if group == "banksize":
        return {p.stem: p for p in sorted((RES / "banks").glob("orig_m_k*.jsonl"))}
    raise ValueError(group)


def done_conditions(rep: int, conds: dict, n: int = 30) -> list[str]:
    d = ROOT / "work" / "runs" / f"e1_p5_eval_r{rep}" / "round1"
    return [c for c in conds if all((d / f"{c}_{s}.jsonl").exists() and sum(1 for l in (d / f"{c}_{s}.jsonl").read_text().splitlines() if l.strip()) >= n
                                    for s in ("eval_in_distribution", "eval_out_of_distribution"))]


def run_rep(rep: int, group: str, concurrency: int = 6, skip_done: bool = True) -> None:
    p3a.install_wrappers("p5_eval", "openrouter")
    os.environ["EOBS_RUN_ID"] = f"e1_p5_eval_r{rep}"
    sys.path.insert(0, str(ENVHARNESS_ROOT)); sys.path.insert(0, str(ENVHARNESS_ROOT / "experiments" / "alfworld"))
    os.chdir(ENVHARNESS_ROOT)
    import reasoning_bank_eval as rbe
    cfg = p3a.make_eval_config(30, 30, concurrency)
    conds = conditions(group)
    if skip_done:
        done = done_conditions(rep, conds)
        conds = {c: p for c, p in conds.items() if c not in done}
        print(f"[P5.5] rep {rep} {group}: skipping {done}; running {list(conds)}", flush=True)
    if not conds:
        print(f"[P5.5] rep {rep} {group} rc=0 (nothing to run)", flush=True); return
    out = ROOT / "work" / "runs" / f"e1_p5_eval_r{rep}"
    argv = ["--config", str(cfg), "--out-dir", str(out), "--start-seeds", "0", "--conditions", ",".join(conds), "--concurrency", str(concurrency),
            "--bank-overrides", ",".join(f"{c}={p}" for c, p in conds.items())]
    rc = rbe.main(argv)
    print(f"[P5.5] rep {rep} {group} rc={rc}", flush=True)


def tables(reps=(1, 2, 3)) -> None:
    rows = []
    def load(run, conds, rep):
        for p in sorted((ROOT / "work" / "runs" / run).rglob("*.jsonl")):
            cond = next((c for c in sorted(conds, key=len, reverse=True) if p.stem.startswith(c + "_")), None)
            if cond is None:
                continue
            split = p.stem[len(cond) + 1:]
            for l in p.read_text().splitlines():
                if l.strip():
                    r = json.loads(l); rows.append({"rep": rep, "condition": cond, "split": split, "seed": r["seed"], "success": bool(r["success"]), "steps": r["duration_steps"], "error": r.get("error", "")})
    p4conds = [c for c in json.loads((ROOT / "p4" / "results" / "banks.json").read_text()) if not c.startswith("pair_")]
    p4conds = [c for c in p4conds if c not in ("nzero",)]
    p4all = [f"{a}_m" for a in ("isat", "nsat", "fhmid")] + [f"origc_{a}_m" for a in ("isat", "nsat", "fhmid")] + [f"{a}_full" for a in ("isat", "nsat", "fhmid")]
    for rep in reps:
        load(f"e1_p3a_eval_r{rep}", ("nobank", "orig"), rep); load(f"e1_p3b_eval_r{rep}", ("orig_m", "ours"), rep); load(f"e1_p4_eval_r{rep}", p4all, rep)
        load(f"e1_p5_eval_r{rep}", list(conditions("ss")) + list(conditions("banksize")), rep)
    with open(RES / "evals_p5.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"[P5.5] {len(rows)} episode rows -> evals_p5.csv", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["eval", "tables"], required=True); ap.add_argument("--group", choices=["ss", "banksize"], default="banksize")
    ap.add_argument("--rep", type=int, default=1); ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args()
    run_rep(a.rep, a.group, a.concurrency) if a.stage == "eval" else tables()
