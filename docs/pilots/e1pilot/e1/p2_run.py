"""P2 — structural hardening dose pilot (env/LLM plumbing around e1.controller).

Per target task, doses in the fixed order F_S0 k=1,2,3 then F_O λ=0.5,1.0; stop at the first IN-BAND hit unless the task
is in the dose-response subset (first 5 hits in task-id order → continue through all remaining doses at 8 rollouts).
Certificate ladder before ANY rollout at a dose: R_pol (verbatim replay of the shortest successful baseline trajectory of
the SAME policy in E') → R_exp (closed-loop expert from the staged state, ≤ 3 attempts) → uncertified (dose skipped).
Rollouts use the released runner (`run_episode` via SubprocessRunner) with the policy block of the chosen config.
Resumable by (task_id, family, dose); rows appended to results/e1pilot/p2_doses.jsonl; ledger phase p2_dose.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS))
from eobs.certs import ReplayResult  # noqa: E402
from eobs.replay import open_session, replay_actions, run_expert  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT, secrets  # noqa: E402
from e1.controller import DOSES, classify8, classify_after4  # noqa: E402
from e1.operators import o_footer, s0_displace  # noqa: E402

RES = ROOT / "results" / "e1pilot"
WORK = ROOT / "work"
N_TARGETS = {"pick_two_obj_and_place": 2}


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def _traces(run_dir: Path) -> list[dict]:
    return _jsonl(run_dir / "traces.jsonl")


class Runner:
    def __init__(self, config: Path, run_name: str, regime: str):
        from envharness.orchestration.runner import SubprocessRunner
        self.cfg = yaml.safe_load(config.read_text())
        self.run_name, self.regime = run_name, regime
        os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
        os.environ["EOBS_RUN_ID"] = run_name; os.environ["EOBS_PHASE"] = "p2_dose"
        os.environ["PYTHONPATH"] = str(EOBS) + os.pathsep + os.environ.get("PYTHONPATH", "")
        if "api_key_env" not in self.cfg["policy"]["client_kwargs"]:      # legacy DeepSeek block (Pro fallback config)
            os.environ["OPENAI_API_KEY"] = secrets().deepseek_api_key.get_secret_value()
        self.runner = SubprocessRunner(timeout=int(self.cfg["runner"]["timeout_seconds"]), subprocess_log_dir=WORK / "runs" / run_name / "subprocess")
        self.store = WORK / "runs" / run_name / "traces.jsonl"
        self.store.parent.mkdir(parents=True, exist_ok=True)

    def episode(self, candidate, task_id: int, tag: str):
        from envharness.orchestration.runner import EnvSpec, EpisodeSpec, PolicySpec
        pol = self.cfg["policy"]
        spec = EpisodeSpec(env=EnvSpec(import_path=self.cfg["env"]["import_path"], reset_options=self.cfg["env"]["reset_options"], reset_seed=task_id),
                           candidate=candidate, policy=PolicySpec(client_factory=pol["client_factory"], client_kwargs=pol["client_kwargs"], action_format=pol["action_format"],
                                                                   task_prompt=pol["task_description"], max_history=int(pol["max_history"]), temperature=float(pol["temperature"])),
                           iteration_id=tag, task_id=self.cfg["orchestrator"]["task_id"], max_steps=int(self.cfg["orchestrator"]["max_episode_steps"]))
        os.environ["EOBS_TASK_ID"] = str(task_id); os.environ["EOBS_CANDIDATE_ID"] = tag
        tr = self.runner.run(spec)
        tr.kind = "exploration"; tr.candidate_id = tag
        with open(self.store, "a") as fh:
            fh.write(tr.model_dump_json() + "\n")
        return tr


def certificate(candidate, task_id: int, pol_witness: list[str] | None) -> tuple[str, dict]:
    """R_pol → R_exp(≤3) → uncertified. Returns (source, detail)."""
    if pol_witness:
        s = open_session(candidate, task_id)
        try:
            r = replay_actions(s, pol_witness)
        finally:
            s.close()
        if r.ok:
            return "R_pol", {"n_steps": r.n_steps}
        detail = {"R_pol_reason": r.reason, "R_pol_step": r.step}
    else:
        detail = {"R_pol_reason": "no_policy_witness"}
    for attempt in range(1, 4):
        s = open_session(candidate, task_id)
        try:
            r = run_expert(s, max_steps=50)
            if r.ok:
                detail.update({"R_exp_attempt": attempt, "n_steps": r.n_steps, "witness": r.actions})
                return "R_exp", detail
            detail[f"R_exp_{attempt}"] = r.reason
        finally:
            s.close()
    return "uncertified", detail


def make_candidate(family: str, dose, task_id: int, info) -> tuple[object | None, str, list | None]:
    from envharness.core.types import Candidate
    if family == "F_S0":
        if info is None:
            return None, "infeasible: targets not discovered", None
        acts, why = s0_displace.build(info, int(dose))
        if acts is None:
            return None, why, None
        return s0_displace.to_candidate(acts), "ok", acts
    code = o_footer.rules_code(task_id, float(dose))
    return Candidate(rules_code=code, in_env_actions=[], rationale="F_O footer masking"), "ok", None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", choices=["qwen", "pro_fallback"], required=True)
    ap.add_argument("--targets", type=str, default=None, help="comma-separated task ids (computed from the map if omitted)")
    ap.add_argument("--max-rollouts-per-dose", type=int, default=8)
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    if a.regime == "qwen":
        cfg = ROOT / "configs" / "qwen_map.yaml"; base_run = WORK / "runs" / "e1_qwen_map"; run_name = "e1_p2_qwen"
        rows = list(csv.DictReader(open(RES / "qwen_p16.csv")))
        sat = [int(r["task_id"]) for r in rows if r["p16_qwen"] != "" and float(r["p16_qwen"]) == 1.0]
        if len(sat) < 5:
            sat = [int(r["task_id"]) for r in rows if r["p16_qwen"] != "" and float(r["p16_qwen"]) >= 0.875]
        targets = sat
    else:
        cfg = EOBS / "configs" / "corpus_eobs.yaml"; base_run = EOBS / "work" / "runs" / "eobs_phase1_extra"; run_name = "e1_p2_pro_fallback"
        tasks = list(csv.DictReader(open(EOBS / "results/eobs/tasks.csv")))
        sh = sorted(int(t["task_id"]) for t in tasks if t.get("p5_H") not in ("", None) and float(t["p5_H"]) == 1.0)
        rnd = random.Random(20260911); rnd.shuffle(sh); targets = sorted(sh[:10])
    if a.targets:
        targets = [int(x) for x in a.targets.split(",")]
    kmax = min(a.max_rollouts_per_dose, 8)
    print(f"[P2] regime={a.regime} targets={targets} (n={len(targets)}) config={cfg.name} max_rollouts/dose={kmax}", flush=True)
    types = {int(t["task_id"]): t["type"] for t in csv.DictReader(open(EOBS / "results/eobs/tasks.csv"))}
    # policy witnesses: shortest successful baseline trajectory of the same policy
    succ = defaultdict(list)
    for t in _traces(base_run):
        if t.get("success") and not t.get("error"):
            succ[int(t["rollout_seed"])].append([s["raw_action"]["kwargs"].get("text", "") for s in t["steps"]])
    pol_wit = {tid: min(v, key=len) for tid, v in succ.items()}
    runner = Runner(cfg, run_name, a.regime)
    out = RES / "p2_doses.jsonl"
    done = {(r["task_id"], r["family"], r["dose"]) for r in _jsonl(out)}
    hits_so_far = [r["task_id"] for r in _jsonl(out) if r.get("class") == "IN-BAND"]
    curve_tasks = set(sorted(set(hits_so_far))[:5])
    for tid in targets:
        info = None
        if any(fam == "F_S0" and (tid, fam, d) not in done for fam, d in DOSES):
            t0 = time.time()
            info = s0_displace.discover(tid, N_TARGETS.get(types.get(tid, ""), 1))
            print(f"[P2] task {tid}: targets {info.targets if info else None} ({time.time() - t0:.0f}s)", flush=True)
        task_hit = any(r["task_id"] == tid and r.get("class") == "IN-BAND" for r in _jsonl(out))
        for di, (fam, dose) in enumerate(DOSES):
            if (tid, fam, dose) in done:
                continue
            if task_hit and tid not in curve_tasks:
                break
            t0 = time.time()
            cand, why, acts = make_candidate(fam, dose, tid, info)
            row = {"task_id": tid, "type": types.get(tid), "family": fam, "dose": dose, "regime": a.regime, "feasible": cand is not None, "feasibility": why,
                   "in_env_actions": acts, "rules_sha": hashlib.sha256((cand.rules_code if cand else "").encode()).hexdigest()[:12] if cand and cand.rules_code else None}
            if cand is None:
                row.update({"certified_by": None, "rollouts": 0, "successes": 0, "p_hat": None, "class": "INFEASIBLE"})
            else:
                src, detail = certificate(cand, tid, pol_wit.get(tid))
                row.update({"certified_by": src, "cert_detail": {k: v for k, v in detail.items() if k != "witness"}, "witness": detail.get("witness")})
                if src == "uncertified":
                    row.update({"rollouts": 0, "successes": 0, "p_hat": None, "class": "UNCERTIFIED"})
                else:
                    tag = f"p2-{tid}-{fam}-{dose}"
                    from concurrent.futures import ThreadPoolExecutor
                    def _batch(nb: int) -> int:
                        with ThreadPoolExecutor(max_workers=nb) as pool:
                            return sum(int(bool(t.success)) for t in pool.map(lambda _: runner.episode(cand, tid, tag), range(nb)))
                    succs = _batch(4); n = 4
                    cls4 = classify_after4(succs)
                    if cls4 is None and kmax > 4:
                        succs += _batch(kmax - 4); n = kmax
                        cls = classify8(succs) if n == 8 else ("IN-BAND" if 0.375 <= succs / n <= 0.625 else "OTHER")
                    else:
                        cls = cls4 or ("IN-BAND" if 0.375 <= succs / n <= 0.625 else "OTHER")
                    row.update({"rollouts": n, "successes": succs, "p_hat": round(succs / n, 4), "class": cls})
                    if cls == "IN-BAND" and not task_hit:
                        task_hit = True
                        if len(curve_tasks) < 5:
                            curve_tasks.add(tid)
            row["wall_s"] = round(time.time() - t0, 1)
            with open(out, "a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            done.add((tid, fam, dose))
            print(f"[P2] task {tid} {fam} dose {dose}: {row['class']} cert={row.get('certified_by')} p={row.get('p_hat')} rollouts={row.get('rollouts')} ({row['wall_s']}s)", flush=True)
    print("[P2] done", flush=True)


if __name__ == "__main__":
    main()
