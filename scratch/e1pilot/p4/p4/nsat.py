"""P4.3 N-sat — behavior-breaking hardening on the 11 saturated tasks (order per task: F_H m-search, then Chain).

F_H: sequential on m starting at the policy's median success length from P1 (m_med); NOEFFECT → m − 2; ZERO → m + 1
(then continue by the same rule); ≤ 4 evaluations; certificate by construction when L_exp ≤ m, else expert ×3.
Accept (confirmation eligible) only if ω(E′) ≤ 0.5. Classification 4→8 as in P2b; a hit gets 8 more rollouts → p̂_16
confirmed iff ∈ [0.25, 0.75]; those 8 are the bank trajectories.
Chain (≤ 6 tasks, the six saturated tasks with the shortest L_exp): Chain-2 = task t then its successor in the saturated
list (Chain-3 if Chain-2 is NOEFFECT); certificate = concatenated expert witnesses (×3 each); ω = 0 by construction.
Resumable: nsat_doses.jsonl; result nsat_envs.csv."""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from e1.controller import classify8, classify_after4  # noqa: E402
from e1.operators import h_horizon  # noqa: E402
from e1.p2_run import Runner as _Runner  # noqa: E402


class Runner(_Runner):
    """P4 extension (subclass, e1 untouched): optional env import path (ChainEnv) and structured reset options per episode."""

    def __init__(self, config, run_name, regime, env_import: str | None = None):
        super().__init__(config, run_name, regime)
        self.env_import = env_import

    def episode(self, candidate, task_id: int, tag: str, reset_options: dict | None = None):
        from envharness.orchestration.runner import EnvSpec, EpisodeSpec, PolicySpec
        pol = self.cfg["policy"]
        spec = EpisodeSpec(env=EnvSpec(import_path=self.env_import or self.cfg["env"]["import_path"], reset_options=reset_options or self.cfg["env"]["reset_options"], reset_seed=task_id),
                           candidate=candidate, policy=PolicySpec(client_factory=pol["client_factory"], client_kwargs=pol["client_kwargs"], action_format=pol["action_format"],
                                                                   task_prompt=pol["task_description"], max_history=int(pol["max_history"]), temperature=float(pol["temperature"])),
                           iteration_id=tag, task_id=self.cfg["orchestrator"]["task_id"], max_steps=int(self.cfg["orchestrator"]["max_episode_steps"]))
        os.environ["EOBS_TASK_ID"] = str(task_id); os.environ["EOBS_CANDIDATE_ID"] = tag
        tr = self.runner.run(spec)
        tr.kind = "exploration"; tr.candidate_id = tag
        with open(self.store, "a") as fh:
            fh.write(tr.model_dump_json() + "\n")
        return tr
from e1.p2b_run import expert_len_from_reset  # noqa: E402
from p4.chain_env import ChainEnv, chain_reset_options  # noqa: E402
from p4.omega import omega, p1_successes  # noqa: E402

RES = ROOT / "p4" / "results"
OUT = RES / "nsat_doses.jsonl"
SAT = [1, 2, 7, 12, 13, 15, 21, 22, 24, 25, 29]


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def next_m(history: list[tuple[int, str]], m0: int) -> int | None:
    if not history:
        return m0
    if len(history) >= 4 or history[-1][1] in ("IN-BAND",):
        return None
    m, cls = history[-1]
    nxt = m - 2 if cls in ("NOEFFECT", "NEAR_HIGH") else (m + 1 if cls in ("ZERO", "OVERSHOOT", "NEAR_LOW") else None)
    if nxt is None or nxt < 1 or any(nxt == h[0] for h in history):
        return None
    return nxt


def cls_with_side(succ: int, n: int) -> str:
    if n == 4:
        c = classify_after4(succ)
        return c or "CONTINUE"
    c = classify8(succ)
    if c == "NEAR":
        return "NEAR_LOW" if succ / n < 0.5 else "NEAR_HIGH"
    return c


def run_dose(runner: Runner, cand, tid: int, tag: str, reset_options=None, seed=None) -> tuple[int, int, str]:
    def batch(nb: int) -> int:
        with ThreadPoolExecutor(max_workers=nb) as pool:
            return sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid if seed is None else seed, tag, reset_options=reset_options), range(nb)))
    s = batch(4); n = 4
    c = cls_with_side(s, 4)
    if c == "CONTINUE":
        s += batch(4); n = 8
        c = cls_with_side(s, 8)
    return s, n, c


def confirm(runner: Runner, cand, tid: int, tag: str, s8: int, reset_options=None, seed=None) -> tuple[int, float]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        s_new = sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid if seed is None else seed, tag + "-bank", reset_options=reset_options), range(8)))
    return s_new, (s8 + s_new) / 16


def main() -> None:
    from envharness.core.types import Candidate
    os.environ["EOBS_PHASE"] = "p4_build"
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p4_nsat", "qwen")
    os.environ["EOBS_PHASE"] = "p4_build"
    done_rows = _jsonl(OUT)
    tr = [json.loads(l) for l in (ROOT / "work" / "runs" / "e1_qwen_map" / "traces.jsonl").read_text().splitlines() if l.strip()]
    med = {}
    for tid in SAT:
        lens = sorted(t["duration_steps"] for t in tr if int(t["rollout_seed"]) == tid and t["success"])
        med[tid] = lens[len(lens) // 2] if lens else None
    L_exp, wit = {}, {}
    for tid in SAT:
        L_exp[tid], wit[tid] = expert_len_from_reset(tid)
    print("[P4.3] m_med", med, "| L_exp", L_exp, flush=True)

    def emit(row):
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print("[P4.3]", {k: row[k] for k in row if k not in ("in_env_actions",)}, flush=True)

    results = {}
    for tid in SAT:
        prior = [r for r in done_rows if r["task_id"] == tid]
        confirmed = next((r for r in prior if r.get("confirmed")), None)
        if confirmed:
            results[tid] = confirmed; continue
        # ---- F_H m-search
        hist = [(int(r["dose"]), r["class"]) for r in prior if r["family"] == "F_H" and r.get("rollouts")]
        hit_row = None
        while hit_row is None:
            m = next_m(hist, med[tid] or (L_exp[tid] or 10))
            if m is None:
                break
            cand = Candidate(rules_code=h_horizon.rules_code(m), in_env_actions=[], rationale="F_H")
            w, ok, n_w = omega(tid, cand)
            cert = "by_construction" if (L_exp[tid] is not None and L_exp[tid] <= m) else None
            if cert is None:
                from eobs.replay import open_session, run_expert
                for _ in range(3):
                    s = open_session(cand, tid)
                    try:
                        if run_expert(s, max_steps=min(m, 50)).ok:
                            cert = "R_exp"; break
                    finally:
                        s.close()
            t0 = time.time()
            if cert is None:
                emit({"task_id": tid, "family": "F_H", "dose": m, "omega": w, "certified_by": None, "class": "UNCERTIFIED", "rollouts": 0, "wall_s": round(time.time() - t0, 1)})
                hist.append((m, "UNCERTIFIED")); break
            tag = f"p4nsat-{tid}-F_H-{m}"
            s, n, c = run_dose(runner, cand, tid, tag)
            row = {"task_id": tid, "family": "F_H", "dose": m, "omega": w, "omega_ok": w is not None and w <= 0.5, "certified_by": cert, "rollouts": n, "successes": s, "p_hat": round(s / n, 4), "class": c, "wall_s": round(time.time() - t0, 1)}
            if c == "IN-BAND" and row["omega_ok"]:
                s_new, p16 = confirm(runner, cand, tid, tag, s)
                row.update({"bank_successes": s_new, "p16": round(p16, 4), "confirmed": 0.25 <= p16 <= 0.75, "rollouts": n + 8})
                if row["confirmed"]:
                    hit_row = row
            elif c == "IN-BAND":
                row["note"] = "in-band but omega > 0.5: not behavior-breaking; not confirmed"
            emit(row); hist.append((m, c))
        if hit_row:
            results[tid] = hit_row; continue
        # ---- Chain (six shortest-L_exp saturated tasks only)
        six = sorted([t for t in SAT if L_exp[t] is not None], key=lambda t: L_exp[t])[:6]
        if tid not in six:
            results[tid] = {"task_id": tid, "confirmed": False, "note": "no F_H hit; not in the Chain subset"}; continue
        partner = SAT[(SAT.index(tid) + 1) % len(SAT)]
        for depth in (2, 3):
            if depth == 3 and (tid, "Chain", "2") in {(r["task_id"], r["family"], str(r["dose"])) for r in _jsonl(OUT)} and any(r["family"] == "Chain" and r["dose"] == 2 and r["class"] != "NOEFFECT" for r in _jsonl(OUT) if r["task_id"] == tid):
                break
            if depth == 3:
                emit({"task_id": tid, "family": "Chain", "dose": 3, "class": "NOT_BUILT", "note": "Chain-3 requires a 3-env Link tree; ChainEnv composes two envs — reported, not substituted", "rollouts": 0}); break
            t0 = time.time()
            La, wa = L_exp[tid], wit[tid]; Lb, wb = L_exp[partner], wit[partner]
            if not (wa and wb) or La + Lb > 50:
                emit({"task_id": tid, "family": "Chain", "dose": 2, "partner": partner, "class": "INFEASIBLE", "note": f"L_exp {La}+{Lb} > 50 or no witness", "rollouts": 0}); break
            env = ChainEnv(); env.reset(seed=tid, options={**chain_reset_options(partner), "task_id": "alfworld-corpus-ours-release"})
            from envharness.core.types import Action
            for a in wa + wb:
                r_ = env.step(Action(name="do", kwargs={"text": a}))
                if r_.terminated or r_.truncated: break
            cert_ok = env.evaluate().success; env.close()
            if not cert_ok:
                emit({"task_id": tid, "family": "Chain", "dose": 2, "partner": partner, "class": "UNCERTIFIED", "note": "concatenated expert witnesses did not pass through ChainEnv", "rollouts": 0}); break
            runner_c = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p4_nsat", "qwen", env_import="p4.chain_env:ChainEnv")
            ro = chain_reset_options(partner)
            cand = Candidate(rules_code="", in_env_actions=[], rationale="Chain-2")
            tag = f"p4nsat-{tid}-Chain-2-{partner}"
            s, n, c = run_dose(runner_c, cand, tid, tag, reset_options=ro)
            row = {"task_id": tid, "family": "Chain", "dose": 2, "partner": partner, "omega": 0.0, "omega_ok": True, "certified_by": "concatenated_expert", "rollouts": n, "successes": s, "p_hat": round(s / n, 4), "class": c, "wall_s": round(time.time() - t0, 1)}
            if c == "IN-BAND":
                s_new, p16 = confirm(runner_c, cand, tid, tag, s, reset_options=ro)
                row.update({"bank_successes": s_new, "p16": round(p16, 4), "confirmed": 0.25 <= p16 <= 0.75, "rollouts": n + 8})
            emit(row)
            if row.get("confirmed"):
                results[tid] = row; break
            if c != "NOEFFECT":
                break
        results.setdefault(tid, {"task_id": tid, "confirmed": False})
    with open(RES / "nsat_envs.csv", "w", newline="") as fh:
        keys = sorted({k for r in results.values() for k in r if k != "in_env_actions"})
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows([{k: v for k, v in r.items() if k != "in_env_actions"} for r in results.values()])
    print("[P4.3] done; confirmed:", [t for t, r in results.items() if r.get("confirmed")], flush=True)


if __name__ == "__main__":
    main()
