"""P2b — refined dose pilot per PREREG3b (0c317f9). Families in order F_O (λ search) → F_H (horizon squeeze) → F_S0′ (expert
oracle); stop at the first IN-BAND; 4→8 rollouts per dose; uncertified doses get 4 provisional rollouts (a success certifies
post hoc). Targets: 11 Qwen-saturated tasks (+3 edge-high secondary). Resumable by (task, family, dose); rows appended to
results/e1pilot/p2b_doses.jsonl; ledger phase p2_dose (same sub-cap accounting as P2)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS))
from e1.controller import classify8, classify_after4  # noqa: E402
from e1.lam_search import monotonicity_violations, next_lambda  # noqa: E402
from e1.operators import h_horizon, o_footer, s0_displace  # noqa: E402
from e1.p2_run import N_TARGETS, Runner, _jsonl, _traces, certificate  # noqa: E402
from eobs.replay import open_session, run_expert  # noqa: E402

RES = ROOT / "results" / "e1pilot"
WORK = ROOT / "work"
OUT = RES / "p2b_doses.jsonl"


def expert_len_from_reset(task_id: int, attempts: int = 3) -> tuple[int | None, list[str] | None]:
    best = None
    for _ in range(attempts):
        s = open_session(None, task_id)
        try:
            r = run_expert(s, max_steps=50)
            if r.ok and (best is None or r.n_steps < best[0]):
                best = (r.n_steps, list(r.actions))
        finally:
            s.close()
    return (best[0], best[1]) if best else (None, None)


def run_dose(runner: Runner, cand, tid: int, tag: str, kmax: int = 8) -> tuple[int, int, str]:
    from concurrent.futures import ThreadPoolExecutor
    def batch(nb: int) -> int:
        with ThreadPoolExecutor(max_workers=nb) as pool:
            return sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid, tag), range(nb)))
    s = batch(4); n = 4
    c4 = classify_after4(s)
    if c4 is None:
        s += batch(kmax - 4); n = kmax
        return s, n, classify8(s)
    return s, n, c4


def provisional(runner: Runner, cand, tid: int, tag: str) -> tuple[int, int, str]:
    """Uncertified dose: 4 provisional rollouts; any success certifies post hoc (then continue to 8 if not decided)."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        s = sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid, tag), range(4)))
    if s == 0:
        return 0, 4, "UNCERTIFIED"
    c4 = classify_after4(s)
    if c4 is None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            s += sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid, tag), range(4)))
        return s, 8, classify8(s)
    return s, 4, c4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=None)
    ap.add_argument("--secondary", action="store_true", help="also run the 3 edge-high tasks")
    a = ap.parse_args()
    from envharness.core.types import Candidate
    rows = list(csv.DictReader(open(RES / "qwen_p16.csv")))
    primary = [int(r["task_id"]) for r in rows if r["p16_qwen"] != "" and float(r["p16_qwen"]) == 1.0]
    secondary = [int(r["task_id"]) for r in rows if r["p16_qwen"] != "" and 0.8 < float(r["p16_qwen"]) < 1.0]
    targets = [int(x) for x in a.targets.split(",")] if a.targets else (primary + (secondary if a.secondary else []))
    types = {int(r["task_id"]): r["type"] for r in rows}
    print(f"[P2b] targets {targets} (primary {primary}, secondary {secondary})", flush=True)
    succ = defaultdict(list)
    for t in _traces(WORK / "runs" / "e1_qwen_map"):   # run DIR (bug fixed after P2b: the file path made pol_wit empty)
        if t.get("success") and not t.get("error"):
            succ[int(t["rollout_seed"])].append([s["raw_action"]["kwargs"].get("text", "") for s in t["steps"]])
    pol_wit = {tid: min(v, key=len) for tid, v in succ.items()}
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p2b_qwen", "qwen")
    done_rows = _jsonl(OUT)
    done = {(r["task_id"], r["family"], str(r["dose"])) for r in done_rows}

    def emit(row: dict) -> None:
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print(f"[P2b] task {row['task_id']} {row['family']} {row['dose']}: {row['class']} cert={row.get('certified_by')} p={row.get('p_hat')} n={row.get('rollouts')} ({row.get('wall_s')}s)", flush=True)

    def dose_rollouts(cand, tid, fam, dose, cert_src, detail, extra):
        t0 = time.time()
        tag = f"p2b-{tid}-{fam}-{dose}"
        if cert_src == "uncertified":
            s, n, cls = provisional(runner, cand, tid, tag)
            cert_src = "R_post_hoc" if s > 0 else "uncertified"
        else:
            s, n, cls = run_dose(runner, cand, tid, tag)
        row = {"task_id": tid, "type": types.get(tid), "family": fam, "dose": dose, "feasible": True, "certified_by": cert_src, "cert_detail": {k: v for k, v in (detail or {}).items() if k != "witness"},
               "rollouts": n, "successes": s, "p_hat": round(s / n, 4), "class": cls, "wall_s": round(time.time() - t0, 1), **extra}
        emit(row)
        return row

    for tid in targets:
        prior = [r for r in done_rows if r["task_id"] == tid]
        hit = any(r.get("class") == "IN-BAND" for r in prior)
        if hit:
            continue
        total = sum(int(r.get("rollouts") or 0) for r in prior)
        # ---- F_O λ search
        hist = [(float(r["dose"]), r["class"]) for r in prior if r["family"] == "F_O" and r["class"] not in ("UNCERTIFIED",)]
        while not hit:
            lam = next_lambda(hist)
            if lam is None:
                break
            if (tid, "F_O", str(lam)) in done:
                break
            cand = Candidate(rules_code=o_footer.rules_code(tid, lam), in_env_actions=[], rationale="F_O")
            src, det = certificate(cand, tid, pol_wit.get(tid))
            row = dose_rollouts(cand, tid, "F_O", lam, src, det, {"lambda_history": hist})
            hist.append((lam, row["class"])); hit = row["class"] == "IN-BAND"
        if hit:
            continue
        # ---- F_H horizon squeeze
        L, wit = expert_len_from_reset(tid)
        if L is None:
            emit({"task_id": tid, "type": types.get(tid), "family": "F_H", "dose": None, "feasible": False, "class": "INFEASIBLE", "feasibility": "no certified expert plan from reset (3 attempts)", "rollouts": 0, "wall_s": 0})
        else:
            for m in (L + 6, L + 3, L):
                if hit or (tid, "F_H", str(m)) in done:
                    continue
                cand = Candidate(rules_code=h_horizon.rules_code(m), in_env_actions=[], rationale="F_H")
                row = dose_rollouts(cand, tid, "F_H", m, "R_exp_by_construction", {"L_exp": L, "n_steps": L}, {"L_exp": L})
                hit = row["class"] == "IN-BAND"
        if hit:
            continue
        # ---- F_S0′ expert-oracle displacement
        info = s0_displace.discover(tid, N_TARGETS.get(types.get(tid, ""), 1))
        if info is None:
            emit({"task_id": tid, "type": types.get(tid), "family": "F_S0p", "dose": None, "feasible": False, "class": "INFEASIBLE", "feasibility": "targets not discovered", "rollouts": 0, "wall_s": 0})
            continue
        top, allrows = s0_displace.oracle_doses(info, top=2)
        emit({"task_id": tid, "type": types.get(tid), "family": "F_S0p", "dose": "oracle_scan", "feasible": bool(allrows), "class": "SCAN", "rollouts": 0, "wall_s": 0,
              "destinations": [{"dest": r["dest"], "L_exp_staged": r["L_exp_staged"]} for r in allrows]})
        if not top:
            emit({"task_id": tid, "type": types.get(tid), "family": "F_S0p", "dose": None, "feasible": False, "class": "INFEASIBLE", "feasibility": "no destination with a certified expert plan", "rollouts": 0, "wall_s": 0})
            continue
        for rank, r in enumerate(top, 1):
            if hit or (tid, "F_S0p", str(rank)) in done:
                continue
            cand = s0_displace.to_candidate(r["actions"])
            row = dose_rollouts(cand, tid, "F_S0p", rank, "R_exp", {"L_exp_staged": r["L_exp_staged"], "dest": r["dest"]}, {"dest": r["dest"], "L_exp_staged": r["L_exp_staged"], "in_env_actions": r["actions"]})
            hit = row["class"] == "IN-BAND"
    print("[P2b] done", flush=True)


if __name__ == "__main__":
    main()
