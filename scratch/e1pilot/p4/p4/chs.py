"""P4.2 N-zero — Certified Hindsight Stage on the 8 Qwen zero tasks.

Stage 1 (LLM-free): for 3 seeded failed P1 trajectories per zero task, C_any3(s_t) on every prefix (closed-loop expert,
3 attempts, `recover.c_at`); L_any3 = latest certified state. Candidates (≤ 4): latest certified state of each trajectory
plus the certified state closest to L/2 of the trajectory with the largest L.
Stage 2 (corpus-protocol rollouts): learnability probe per candidate, latest first: 4 rollouts from the staged env (Setup =
the student's own prefix with no-ops dropped, ending with `look`); 1–3 successes → select; 4/4 → next-earlier candidate;
0/4 → next-later candidate; ≤ 4 candidates. Selected env: 8 more rollouts (bank) → p̂_12.
Resumable: nzero_states.jsonl (prefix certificates), nzero_probe.jsonl (probes), nzero_envs.csv (result)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))

RES = ROOT / "p4" / "results"
SEED = 20260913


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def zero_tasks() -> list[int]:
    return [int(r["task_id"]) for r in csv.DictReader(open(ROOT / "results" / "e1pilot" / "qwen_p16.csv")) if r["p16_qwen"] != "" and float(r["p16_qwen"]) == 0.0]


def sample_trajectories() -> dict[int, list[dict]]:
    tr = [json.loads(l) for l in (ROOT / "work" / "runs" / "e1_qwen_map" / "traces.jsonl").read_text().splitlines() if l.strip()]
    rnd = random.Random(SEED)
    out = {}
    for tid in zero_tasks():
        fails = [t for t in tr if int(t["rollout_seed"]) == tid and not t["success"] and t.get("steps")]
        out[tid] = rnd.sample(fails, min(3, len(fails)))
    return out


def _job(args):
    tid, eid, t, prefix, attempt = args
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    from eobs.recover import c_at
    c, reason = c_at(tid, prefix)
    return {"task_id": tid, "episode_id": eid, "t": t, "attempt": attempt, "C": c, "reason": reason}


def certify(workers: int = 6) -> None:
    traj = sample_trajectories()
    out = RES / "nzero_states.jsonl"
    done = {(r["episode_id"], r["t"], r["attempt"]) for r in _jsonl(out)}
    jobs = []
    for tid, ts in traj.items():
        for t in ts:
            acts = [s["raw_action"]["kwargs"]["text"] for s in t["steps"]]
            for k in range(min(len(acts), 50) + 1):
                for attempt in (1, 2, 3):
                    if (t["episode_id"], k, attempt) not in done:
                        jobs.append((tid, t["episode_id"], k, acts[:k], attempt))
    print(f"[P4.2] tasks {sorted(traj)}; trajectories {sum(len(v) for v in traj.values())}; prefix-attempts to run {len(jobs)} (done {len(done)})", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool, open(out, "a") as fh:
        for i, row in enumerate(pool.map(_job, jobs, chunksize=4), 1):
            fh.write(json.dumps(row) + "\n")
            if i % 300 == 0:
                fh.flush(); print(f"[P4.2] {i}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    print(f"[P4.2] certify done {time.time() - t0:.0f}s", flush=True)


def candidates() -> dict[int, list[dict]]:
    """Per task: latest certified state of each trajectory + the state closest to L/2 of the longest-L trajectory."""
    traj = sample_trajectories()
    cert = defaultdict(lambda: defaultdict(list))
    for r in _jsonl(RES / "nzero_states.jsonl"):
        cert[r["episode_id"]][r["t"]].append(r["C"])
    out = {}
    for tid, ts in traj.items():
        cands = []
        L_by = {}
        for t in ts:
            acts = [s["raw_action"]["kwargs"]["text"] for s in t["steps"]]
            eff = [i for i, s in enumerate(t["steps"]) if s.get("info", {}).get("effective", True)]
            certified = [k for k, cs in cert[t["episode_id"]].items() if any(cs) and k > 0]
            L = max(certified) if certified else None
            L_by[t["episode_id"]] = (L, acts, certified)
            if L:
                cands.append({"episode_id": t["episode_id"], "t": L, "kind": "latest", "prefix": acts[:L]})
        if L_by:
            eid, (L, acts, certified) = max(L_by.items(), key=lambda kv: (kv[1][0] or 0))
            if L and L >= 4:
                half = min(certified, key=lambda k: abs(k - L / 2))
                if half != L and not any(c["episode_id"] == eid and c["t"] == half for c in cands):
                    cands.append({"episode_id": eid, "t": half, "kind": "half", "prefix": acts[:half]})
        for c in cands:
            c["task_id"] = tid
        out[tid] = cands[:4]
    return out


def staged_actions(tid: int, prefix: list[str]) -> list[str]:
    """Drop no-op actions (those the env answered with 'Nothing happens' or that were inadmissible) by replaying; end with look."""
    from eobs.replay import open_session
    s = open_session(None, tid)
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


def probe(kmax_bank: int = 8) -> None:
    from envharness.core.types import Action, Candidate
    from e1.p2_run import Runner
    os.environ["EOBS_PHASE"] = "p4_build"
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p4_nzero", "qwen")
    os.environ["EOBS_PHASE"] = "p4_build"
    cands = candidates()
    probes = _jsonl(RES / "nzero_probe.jsonl")
    done = {(r["task_id"], r["episode_id"], r["t"]): r for r in probes}
    results = []
    for tid, cs in sorted(cands.items()):
        order = sorted(cs, key=lambda c: -c["t"])          # latest first
        # selection walk: start at latest; 4/4 → next earlier; 0/4 → next later; 1-3 → select
        idx = 0; tried = set(); selected = None; visited = []
        while idx is not None and 0 <= idx < len(order) and len(tried) < 4:
            c = order[idx]; key = (tid, c["episode_id"], c["t"])
            if key in tried:
                break
            tried.add(key)
            if key in done:
                r = done[key]
            else:
                acts = staged_actions(tid, c["prefix"])
                cand = Candidate(rules_code="", in_env_actions=[Action(name="do", kwargs={"text": a}) for a in acts], rationale="CHS")
                tag = f"p4chs-{tid}-{c['episode_id']}-{c['t']}"
                with ThreadPoolExecutor(max_workers=4) as pool:
                    succ = sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid, tag), range(4)))
                r = {"task_id": tid, "episode_id": c["episode_id"], "t": c["t"], "kind": c["kind"], "staged_actions": acts, "probe_successes": succ, "probe_n": 4, "tag": tag}
                with open(RES / "nzero_probe.jsonl", "a") as fh:
                    fh.write(json.dumps(r) + "\n")
                done[key] = r
            visited.append((c["t"], r["probe_successes"]))
            print(f"[P4.2] task {tid} state t={c['t']} ({c['kind']}): {r['probe_successes']}/4", flush=True)
            if 1 <= r["probe_successes"] <= 3:
                selected = r; break
            idx = idx + 1 if r["probe_successes"] == 4 else idx - 1   # 4/4 → earlier (next in latest-first order); 0/4 → later
        row = {"task_id": tid, "n_candidates": len(cs), "visited": json.dumps(visited), "selected_t": selected["t"] if selected else "", "selected_episode": selected["episode_id"] if selected else "",
               "status": "selected" if selected else ("frontier_all_4of4" if visited and all(v[1] == 4 for v in visited) else ("dead_all_0of4" if visited and all(v[1] == 0 for v in visited) else ("no_candidate" if not cs else "mixed_no_selection")))}
        if selected:
            tag = selected["tag"]; acts = selected["staged_actions"]
            cand = Candidate(rules_code="", in_env_actions=[Action(name="do", kwargs={"text": a}) for a in acts], rationale="CHS")
            have = sum(1 for l in (ROOT / "work" / "runs" / "e1_p4_nzero" / "traces.jsonl").read_text().splitlines() if l.strip() and json.loads(l)["candidate_id"] == tag + "-bank")
            need = kmax_bank - have
            if need > 0:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(lambda _: runner.episode(cand, tid, tag + "-bank"), range(need)))
            bank = [json.loads(l) for l in (ROOT / "work" / "runs" / "e1_p4_nzero" / "traces.jsonl").read_text().splitlines() if l.strip() and json.loads(l)["candidate_id"] == tag + "-bank"]
            s12 = selected["probe_successes"] + sum(bool(t["success"]) for t in bank)
            row.update({"bank_successes": sum(bool(t["success"]) for t in bank), "p12": round(s12 / (4 + len(bank)), 4), "staged_len": len(acts)})
        results.append(row); print("[P4.2]", row, flush=True)
    with open(RES / "nzero_envs.csv", "w", newline="") as fh:
        keys = sorted({k for r in results for k in r})
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(results)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["certify", "probe"], required=True); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    certify(a.workers) if a.stage == "certify" else probe()
