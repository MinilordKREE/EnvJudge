"""P5.1 — Certified Hindsight Staging with the stage budget re-based (PREREG5).

Every staged session (certificate sweep, probe, bank rollouts) uses p5/configs/alfworld_config_100.yaml through the released
`reset_options.config_path`; the runner's max_steps = 50 is the policy budget. Unstaged sessions keep the default config.

Stages
  certify   (LLM-free) C_any3(s_t) for every prefix of the 24 P4.2 trajectories (seed 20260913), expert ≤ 50 own steps.
  probe     candidates per trajectory = latest certified L + certified states nearest 3L/4, L/2, L/4; union, latest-first,
            cap 6 per task (drop the ones nearest in t to a kept one). ALL candidates get 4 corpus-protocol rollouts
            (0/4 dead, 4/4 saturated, 1–3 learnable). Selected = LATEST learnable → 8 more rollouts → p̂_12, confirmed iff
            p̂_12 ∈ [0.2, 0.8]. Earliest learnable recorded. K5 = confirmed tasks, written to LOG immediately.
Outputs: p5/results/chs_certs.jsonl, chs_profile.csv, chs_selected.csv. Ledger phase p5_chs; run dir work/runs/e1_p5_chs."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
for p in (ROOT, EOBS, ROOT / "p4", ROOT / "p5"):
    sys.path.insert(0, str(p))

RES = ROOT / "p5" / "results"
CFG100 = ROOT / "p5" / "configs" / "alfworld_config_100.yaml"
RO100 = {"split": "train", "repetition_threshold": 0, "config_path": str(CFG100)}
LOG = ROOT / "LOG.md"
CAP = 6
EXPERT_STEPS = 50


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def _job(args):
    tid, eid, t, prefix, attempt = args
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    from eobs.recover import c_at
    c, reason = c_at(tid, prefix, max_steps=EXPERT_STEPS, reset_options=RO100)
    return {"task_id": tid, "episode_id": eid, "t": t, "attempt": attempt, "C": c, "reason": reason}


def certify(workers: int = 6) -> None:
    from p4.chs import sample_trajectories
    traj = sample_trajectories()
    out = RES / "chs_certs.jsonl"
    done = {(r["episode_id"], r["t"], r["attempt"]) for r in _jsonl(out)}
    jobs = []
    for tid, ts in traj.items():
        for t in ts:
            acts = [s["raw_action"]["kwargs"]["text"] for s in t["steps"]]
            for k in range(min(len(acts), 50) + 1):
                for attempt in (1, 2, 3):
                    if (t["episode_id"], k, attempt) not in done:
                        jobs.append((tid, t["episode_id"], k, acts[:k], attempt))
    print(f"[P5.1] certify: tasks {sorted(traj)}; trajectories {sum(len(v) for v in traj.values())}; prefix-attempts {len(jobs)} (done {len(done)}); config {CFG100.name}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool, open(out, "a") as fh:
        for i, row in enumerate(pool.map(_job, jobs, chunksize=4), 1):
            fh.write(json.dumps(row) + "\n")
            if i % 300 == 0:
                fh.flush(); print(f"[P5.1] certify {i}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    print(f"[P5.1] certify done {time.time() - t0:.0f}s", flush=True)


def select_candidates(certified_by_traj: dict[str, list[int]], cap: int = CAP) -> list[tuple[str, int, str]]:
    """certified_by_traj: episode_id -> certified t's (t > 0). Returns [(episode_id, t, kind)] latest-first, ≤ cap.
    Per trajectory: L and the certified states nearest 3L/4, L/2, L/4. Capping: repeatedly drop the candidate whose t is
    nearest to another kept candidate's t (the latest state overall is never dropped; ties → drop the earlier one)."""
    cands: dict[tuple[str, int], str] = {}
    for eid, ts in certified_by_traj.items():
        ts = sorted(set(k for k in ts if k > 0))
        if not ts:
            continue
        L = ts[-1]
        cands.setdefault((eid, L), "L")
        for frac, kind in ((0.75, "3L/4"), (0.5, "L/2"), (0.25, "L/4")):
            k = min(ts, key=lambda x: (abs(x - frac * L), -x))
            cands.setdefault((eid, k), kind)
    items = sorted(cands.items(), key=lambda kv: (-kv[0][1], kv[0][0]))
    while len(items) > cap:
        latest = items[0]
        def gap(it):
            return min(abs(it[0][1] - o[0][1]) for o in items if o is not it)
        drop = min((it for it in items if it is not latest), key=lambda it: (gap(it), it[0][1]))
        items.remove(drop)
    return [(eid, t, kind) for (eid, t), kind in items]


def candidates() -> dict[int, list[dict]]:
    from p4.chs import sample_trajectories
    traj = sample_trajectories()
    cert = defaultdict(lambda: defaultdict(list))
    for r in _jsonl(RES / "chs_certs.jsonl"):
        cert[r["episode_id"]][r["t"]].append(r["C"])
    out = {}
    for tid, ts in traj.items():
        acts_by = {t["episode_id"]: [s["raw_action"]["kwargs"]["text"] for s in t["steps"]] for t in ts}
        cby = {eid: [k for k, cs in cert[eid].items() if any(cs) and k > 0] for eid in acts_by}
        out[tid] = [{"task_id": tid, "episode_id": eid, "t": t, "kind": kind, "prefix": acts_by[eid][:t]} for eid, t, kind in select_candidates(cby)]
    return out


def staged_actions(tid: int, prefix: list[str]) -> list[str]:
    """Drop no-ops by replaying the prefix (on the 100-config session); end with look."""
    from eobs.replay import open_session
    s = open_session(None, tid, RO100)
    kept = []
    try:
        for a in prefix:
            if a in s.admissible():
                r = s.step_text(a)
                if r["effective"]:
                    kept.append(a)
    finally:
        s.close()
    if not kept or kept[-1] != "look":
        kept.append("look")
    return kept


def cls(succ: int, n: int = 4) -> str:
    return "dead" if succ == 0 else ("saturated" if succ == n else "learnable")


def probe(kmax_bank: int = 8) -> None:
    from envharness.core.types import Action, Candidate
    from p4.nsat import Runner
    os.environ["EOBS_PHASE"] = "p5_chs"
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p5_chs", "qwen")
    os.environ["EOBS_PHASE"] = "p5_chs"
    cands = candidates()
    print("[P5.1] candidates", {t: [(c["episode_id"][:6], c["t"], c["kind"]) for c in cs] for t, cs in cands.items()}, flush=True)
    prof_path = RES / "chs_profile.jsonl"
    done = {(r["task_id"], r["episode_id"], r["t"]): r for r in _jsonl(prof_path)}
    traces_path = ROOT / "work" / "runs" / "e1_p5_chs" / "traces.jsonl"
    selected_rows = []
    for tid, cs in sorted(cands.items()):
        rows = []
        for c in cs:                                      # ALL candidates, latest first
            key = (tid, c["episode_id"], c["t"])
            if key in done:
                r = done[key]
            else:
                acts = staged_actions(tid, c["prefix"])
                cand = Candidate(rules_code="", in_env_actions=[Action(name="do", kwargs={"text": a}) for a in acts], rationale="CHS-100")
                tag = f"p5chs-{tid}-{c['episode_id']}-{c['t']}"
                with ThreadPoolExecutor(max_workers=4) as pool:
                    succ = sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid, tag, reset_options=RO100), range(4)))
                r = {"task_id": tid, "episode_id": c["episode_id"], "t": c["t"], "kind": c["kind"], "staged_actions": acts, "staged_len": len(acts), "probe_successes": succ, "probe_n": 4, "p4": succ / 4, "class": cls(succ), "tag": tag}
                with open(prof_path, "a") as fh:
                    fh.write(json.dumps(r) + "\n")
                done[key] = r
            rows.append(r)
            print(f"[P5.1] task {tid} t={c['t']} ({c['kind']}): {r['probe_successes']}/4 {r['class']}", flush=True)
        learn = [r for r in rows if r["class"] == "learnable"]
        row = {"task_id": tid, "n_candidates": len(cs), "profile": " ".join(f"{r['t']}:{r['probe_successes']}/4" for r in rows),
               "n_learnable": len(learn), "n_dead": sum(r["class"] == "dead" for r in rows), "n_saturated": sum(r["class"] == "saturated" for r in rows),
               "earliest_learnable_t": min((r["t"] for r in learn), default=""), "selected_t": "", "selected_episode": "", "p12": "", "confirmed": False,
               "status": ("selected" if learn else ("all_dead" if all(r["class"] == "dead" for r in rows) else ("all_saturated" if all(r["class"] == "saturated" for r in rows) else "mixed_dead_saturated"))) if rows else "no_candidate"}
        if learn:
            sel = max(learn, key=lambda r: r["t"])
            cand = Candidate(rules_code="", in_env_actions=[Action(name="do", kwargs={"text": a}) for a in sel["staged_actions"]], rationale="CHS-100")
            have = sum(1 for t in _jsonl(traces_path) if t["candidate_id"] == sel["tag"] + "-bank")
            if have < kmax_bank:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(lambda _: runner.episode(cand, tid, sel["tag"] + "-bank", reset_options=RO100), range(kmax_bank - have)))
            bank = [t for t in _jsonl(traces_path) if t["candidate_id"] == sel["tag"] + "-bank"]
            bs = sum(bool(t["success"]) for t in bank); p12 = (sel["probe_successes"] + bs) / (4 + len(bank))
            row.update({"selected_t": sel["t"], "selected_episode": sel["episode_id"], "bank_successes": bs, "p12": round(p12, 4), "confirmed": 0.2 <= p12 <= 0.8, "staged_len": sel["staged_len"]})
        selected_rows.append(row); print("[P5.1]", row, flush=True)
    keys = sorted({k for r in selected_rows for k in r})
    with open(RES / "chs_selected.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(selected_rows)
    with open(RES / "chs_profile.csv", "w", newline="") as fh:
        rows = [{k: v for k, v in r.items() if k != "staged_actions"} for r in _jsonl(prof_path)]
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    k5 = sum(bool(r["confirmed"]) for r in selected_rows)
    verdict = "≥ 4 → zero side alive (CHS primary operator)" if k5 >= 4 else ("2–3 → marginal (design meeting decides with the profiles)" if k5 >= 2 else "≤ 1 → CHS has no working targets for this policy on this substrate")
    line = (f"- {time.strftime('%H:%M', time.gmtime())} UTC P5.1 K5 OUTCOME: {k5}/8 zero tasks with a confirmed selected env ({verdict}). "
            + "; ".join(f"task {r['task_id']}: {r['status']}" + (f" t={r['selected_t']} p̂_12={r['p12']}" + (" CONFIRMED" if r["confirmed"] else " not confirmed") if r["status"] == "selected" else "") for r in selected_rows) + ".")
    with open(LOG, "a") as fh:
        fh.write(line + "\n")
    print("[P5.1] done;", line, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["certify", "probe"], required=True); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    certify(a.workers) if a.stage == "certify" else probe()
