"""P3b — third arm: skills from Qwen's trajectories on the IN-BAND controlled environments produced by P2b, matched against a
skills-from-original bank built from the SAME tasks with the SAME trajectory count. Eval = released ReasoningBank protocol
(as P3a), conditions orig_m (matched original) and ours (controlled), 3 replicates on the same 30 ID + 30 OOD tasks.
K3 (PREREG3) = held-out success(ours) − success(orig_m), paired per task, in-distribution, threshold −0.02."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS))
from e1.p3a import EMBED_MODEL, RES, WORK, _traces, evaluate, install_wrappers  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402

SEED = 20260912


def in_band_envs() -> list[dict]:
    rows = [json.loads(l) for l in (RES / "p2b_doses.jsonl").read_text().splitlines() if l.strip()]
    hits = {}
    for r in rows:
        if r.get("class") == "IN-BAND" and r["task_id"] not in hits:
            hits[r["task_id"]] = r
    return [hits[t] for t in sorted(hits)]


def build_banks(concurrency: int = 4) -> None:
    install_wrappers("p3_induce", "deepseek")
    import os
    os.environ["EOBS_RUN_ID"] = "e1_p3b_induce"
    sys.path.insert(0, str(ENVHARNESS_ROOT))
    spec = importlib.util.spec_from_file_location("induce_pair", ENVHARNESS_ROOT / "scripts" / "induce_pair.py")
    ip = importlib.util.module_from_spec(spec); spec.loader.exec_module(ip)
    envs = in_band_envs()
    p2b = _traces(WORK / "runs" / "e1_p2b_qwen" / "traces.jsonl")
    p1 = _traces(WORK / "runs" / "e1_qwen_map" / "traces.jsonl")
    rnd = random.Random(SEED)
    ours, orig_m, meta = {}, {}, []
    for e in envs:
        tid = e["task_id"]; tag = f"p2b-{tid}-{e['family']}-{e['dose']}"
        ctrl = [t for t in p2b if t.get("candidate_id") == tag and not t.get("error")]
        base = [t for t in p1 if int(t["rollout_seed"]) == tid and not t.get("error")]
        n = min(len(ctrl), len(base), 8)
        ours[str(tid)] = rnd.sample(ctrl, n); orig_m[str(tid)] = rnd.sample(base, n)
        meta.append({"task_id": tid, "env": tag, "n_trajectories_each": n, "ctrl_successes": sum(t["success"] for t in ours[str(tid)]), "orig_successes": sum(t["success"] for t in orig_m[str(tid)])})
    (RES / "p3b_bank_sources.json").write_text(json.dumps(meta, indent=1))
    print("[P3b] bank sources:", meta, flush=True)
    for cond, by in (("ours", ours), ("orig_m", orig_m)):
        out = RES / "banks" / f"{cond}_qwen.jsonl"
        n_items = ip._build_bank(condition=cond, traces_by_task=by, llm_model="openai/deepseek-v4-pro", concurrency=concurrency, embed_model=EMBED_MODEL, out_path=out)
        print(f"[P3b] {cond}: {n_items} items -> {out}", flush=True)


def eval_rep(rep: int, n_id: int, n_ood: int, concurrency: int) -> None:
    import os
    # reuse P3a's evaluate() but with the two P3b conditions and bank overrides
    from e1 import p3a
    install_wrappers("p3_skills", "openrouter")
    os.environ["EOBS_RUN_ID"] = f"e1_p3b_eval_r{rep}"
    sys.path.insert(0, str(ENVHARNESS_ROOT)); sys.path.insert(0, str(ENVHARNESS_ROOT / "experiments" / "alfworld"))
    os.chdir(ENVHARNESS_ROOT)
    import reasoning_bank_eval as rbe
    cfg = p3a.make_eval_config(n_id, n_ood, concurrency)
    out = WORK / "runs" / f"e1_p3b_eval_r{rep}"
    argv = ["--config", str(cfg), "--out-dir", str(out), "--start-seeds", "0", "--conditions", "orig_m,ours", "--concurrency", str(concurrency),
            "--bank-overrides", f"orig_m={RES / 'banks' / 'orig_m_qwen.jsonl'},ours={RES / 'banks' / 'ours_qwen.jsonl'}"]
    rc = rbe.main(argv)
    print(f"[P3b] eval rep {rep} rc={rc} -> {out}", flush=True)


def tables(reps: list[int]) -> None:
    from eobs.analyze import boot_rate, fmt
    import numpy as np
    rows = []
    for rep in reps:
        for run, conds in ((f"e1_p3a_eval_r{rep}", ("nobank", "orig")), (f"e1_p3b_eval_r{rep}", ("orig_m", "ours"))):
            for p in sorted((WORK / "runs" / run).rglob("*.jsonl")):
                cond, _, split = p.stem.partition("_")
                if cond not in conds:
                    continue
                for r in _traces(p):
                    rows.append({"rep": rep, "condition": cond, "split": split, "seed": r["seed"], "success": bool(r["success"]), "steps": r["duration_steps"], "error": r.get("error", "")})
    with open(RES / "p3b_episodes.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summ = []
    for cond in ("nobank", "orig", "orig_m", "ours"):
        for split in sorted({r["split"] for r in rows}):
            g = defaultdict(list)
            for r in rows:
                if r["condition"] == cond and r["split"] == split:
                    g[r["seed"]].append(r)
            if not g:
                continue
            b = boot_rate(g, lambda r: r["success"], lambda r: 1)
            summ.append({"condition": cond, "split": split, "n_tasks": len(g), "episodes": sum(len(v) for v in g.values()), "success": fmt(b[0]), "ci_lo": fmt(b[1]), "ci_hi": fmt(b[2])})
    k3 = {}
    for split in sorted({r["split"] for r in rows}):
        for a, b in (("ours", "orig_m"), ("ours", "orig"), ("ours", "nobank")):
            per = defaultdict(lambda: defaultdict(list))
            for r in rows:
                if r["split"] == split and r["condition"] in (a, b):
                    per[r["seed"]][r["condition"]].append(int(r["success"]))
            d = {s: sum(c[a]) / len(c[a]) - sum(c[b]) / len(c[b]) for s, c in per.items() if c.get(a) and c.get(b)}
            if d:
                x = np.array(list(d.values())); idx = np.random.default_rng(20260906).integers(0, len(x), size=(10000, len(x))); m = x[idx].mean(axis=1)
                summ.append({"condition": f"{a} - {b} (paired per task)", "split": split, "n_tasks": len(d), "episodes": "", "success": fmt(float(x.mean())), "ci_lo": fmt(float(np.percentile(m, 2.5))), "ci_hi": fmt(float(np.percentile(m, 97.5)))})
                if a == "ours" and b == "orig_m":
                    k3[split] = (float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))
    with open(RES / "p3_skills.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
    idd = k3.get("eval_in_distribution")
    verdict = None if idd is None else ("SL line alive (≥ −0.02 in-distribution)" if idd[0] >= -0.02 else "SL line at risk (< −0.02); the RL Study becomes the primary downstream evidence")
    (RES / "p3b_summary.json").write_text(json.dumps({"K3": k3, "verdict": verdict}, indent=1))
    for s in summ:
        print(s)
    print("K3:", k3, verdict)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["banks", "eval", "tables"], required=True)
    ap.add_argument("--rep", type=int, default=1); ap.add_argument("--concurrency", type=int, default=6); ap.add_argument("--reps", default="1,2,3")
    a = ap.parse_args()
    if a.stage == "banks":
        build_banks()
    elif a.stage == "eval":
        eval_rep(a.rep, 30, 30, a.concurrency)
    else:
        tables([int(x) for x in a.reps.split(",")])
