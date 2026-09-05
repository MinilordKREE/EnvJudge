"""Phase 3: certificates for every logged candidate (both arms). LLM only for R_hint.

R_old / R_exp: eobs.replay (LLM-free), multiprocess. R_hint: <=3 policy rollouts in E'_c through the released
`run_episode` with the released PolicySpec, except that the task_prompt is extended with the base expert plan as a
hint (this is OUR probe, not EnvRigger's policy; the ledger phase is "phase3_hint"). Cap 60 candidates × 3 attempts,
priority: SR_c=0 first, then A/T-axis with R_old=0, then the rest in random order (seeded).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from eobs.certs import HintResult, ReplayResult, certificate_row, needs_hint
from eobs.settings import ENVHARNESS_ROOT, EOBS_ROOT, RESULTS, secrets


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()] if Path(p).exists() else []


def _cert_one(args: tuple) -> dict:
    cand, expert_actions = args
    from envharness.core.types import Action, Candidate
    from eobs.replay import r_exp, r_old
    c = Candidate(rules_code=cand.get("rules_code", "") or "", in_env_actions=[Action(name=a["name"], kwargs=dict(a.get("kwargs") or {})) for a in cand.get("in_env_actions", [])])
    seed = int(cand["task_id"])
    try:
        ro = r_old(c, seed, expert_actions) if expert_actions else ReplayResult(ok=False, reason="not_run")
    except Exception as e:  # noqa: BLE001
        ro = ReplayResult(ok=False, reason=f"env_error:{type(e).__name__}"[:60])
    try:
        rx = r_exp(c, seed)
    except Exception as e:  # noqa: BLE001
        rx = ReplayResult(ok=False, reason=f"env_error:{type(e).__name__}"[:60])
    return {"candidate_id": cand["candidate_id"], "task_id": seed, "arm": cand.get("arm"), "axis": cand.get("axis"), "SR_c": cand.get("SR_c"),
            "R_old": ro.to_dict(), "R_exp": rx.to_dict()}


def run_replays(cands: list[dict], witness: dict[int, list[str]], out: Path, workers: int = 8) -> list[dict]:
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    done = {r["candidate_id"] for r in _jsonl(out)}
    todo = [(c, witness.get(int(c["task_id"]), [])) for c in cands if c["candidate_id"] not in done]
    print(f"[phase3] replays: {len(todo)} candidates to do ({len(done)} done)", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool, open(out, "a", encoding="utf-8") as fh:
        for row in pool.map(_cert_one, todo):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
    return _jsonl(out)


def hint_prompt(base_prompt: str, expert_actions: list[str]) -> str:
    plan = "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(expert_actions))
    return (base_prompt.rstrip() + "\n\nHint: in the unmodified version of this task the following command sequence "
            "solved it (the environment may now behave differently; blocked or altered commands will show in the observations):\n" + plan + "\n")


def run_hints(cands: list[dict], replays: dict[str, dict], witness: dict[int, list[str]], out: Path, cap: int = 60, attempts: int = 3) -> None:
    import yaml
    sys.path.insert(0, str(ENVHARNESS_ROOT / "scripts")); sys.path.insert(0, str(ENVHARNESS_ROOT))
    os.environ["OPENAI_API_KEY"] = secrets().deepseek_api_key.get_secret_value()
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["EOBS_PHASE"] = "phase3_hint"; os.environ["EOBS_RUN_ID"] = "eobs_phase3_hint"
    os.environ["PYTHONPATH"] = str(EOBS_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    from envharness.core.types import Action, Candidate
    from envharness.orchestration.runner import EnvSpec, EpisodeSpec, PolicySpec, SubprocessRunner
    cfg = yaml.safe_load((EOBS_ROOT / "configs" / "corpus_eobs.yaml").read_text())
    pol = cfg["policy"]
    done = {r["candidate_id"] for r in _jsonl(out)}
    eligible = [c for c in cands if c["candidate_id"] not in done and needs_hint(float(c.get("SR_c") or 0.0), ReplayResult(**replays[c["candidate_id"]]["R_old"]) if c["candidate_id"] in replays else None)]
    rnd = random.Random(20260906)
    zero = [c for c in eligible if float(c.get("SR_c") or 0.0) == 0.0]
    at_r0 = [c for c in eligible if c not in zero and set(c.get("axes", [])) & {"A", "T"} and c["candidate_id"] in replays and not replays[c["candidate_id"]]["R_old"]["ok"]]
    rest = [c for c in eligible if c not in zero and c not in at_r0]
    rnd.shuffle(rest)
    picked = (zero + at_r0 + rest)[: max(0, cap - len(done))]
    print(f"[phase3] R_hint on {len(picked)} candidates (zero {len(zero)}, A/T R_old=0 {len(at_r0)}, rest {len(rest)}; cap {cap}, done {len(done)})", flush=True)
    runner = SubprocessRunner(timeout=500, subprocess_log_dir=EOBS_ROOT / "work" / "runs" / "eobs_phase3_hint" / "subprocess")
    with open(out, "a", encoding="utf-8") as fh:
        for c in picked:
            seed = int(c["task_id"])
            plan = witness.get(seed, [])
            cand = Candidate(rules_code=c.get("rules_code", "") or "", in_env_actions=[Action(name=a["name"], kwargs=dict(a.get("kwargs") or {})) for a in c.get("in_env_actions", [])])
            spec_policy = PolicySpec(client_factory=pol["client_factory"], client_kwargs=pol["client_kwargs"], action_format=pol.get("action_format", "think_action"),
                                     task_prompt=hint_prompt(pol["task_description"], plan), max_history=int(pol.get("max_history", 50)), temperature=float(pol.get("temperature", 0.5)))
            os.environ["EOBS_TASK_ID"] = str(seed); os.environ["EOBS_CANDIDATE_ID"] = c["candidate_id"]
            res = HintResult(attempts=0, ok=False, passing_actions=None)
            for k in range(attempts):
                os.environ["EOBS_SEED"] = str(k)
                spec = EpisodeSpec(env=EnvSpec(import_path="envharness.bridges.alfworld:AlfworldEnv", reset_options=cfg["env"]["reset_options"], reset_seed=seed),
                                   candidate=cand, policy=spec_policy, iteration_id="eobs-hint", task_id=cfg["orchestrator"]["task_id"], max_steps=int(cfg["orchestrator"]["max_episode_steps"]))
                tr = runner.run(spec)
                res.attempts += 1
                if tr.success:
                    res.ok = True
                    res.passing_actions = [s.raw_action.kwargs.get("text", "") for s in tr.steps]
                    break
            fh.write(json.dumps({"candidate_id": c["candidate_id"], "task_id": seed, "arm": c.get("arm"), "R_hint": res.to_dict()}, ensure_ascii=False) + "\n"); fh.flush()
            print(f"[phase3] hint {c['candidate_id']} task {seed}: ok={res.ok} attempts={res.attempts}", flush=True)


def assemble(cands: list[dict], replays: dict[str, dict], hints: dict[str, dict], out_cert: Path, out_wit: Path, witness: dict[int, list[str]]) -> None:
    rows, wits = [], []
    for c in cands:
        rp = replays.get(c["candidate_id"])
        if not rp:
            continue
        ro, rx = ReplayResult(**rp["R_old"]), ReplayResult(**rp["R_exp"])
        h = hints.get(c["candidate_id"])
        rh = HintResult(**h["R_hint"]) if h else None
        wit = ro.actions if ro.ok else (rx.actions if rx.ok else (rh.passing_actions if rh and rh.ok else None))
        sha = hashlib.sha256(json.dumps(wit).encode()).hexdigest()[:16] if wit else None
        row = certificate_row(c["candidate_id"], c.get("axis", "?"), ro, rx, rh, sha)
        row.update({"task_id": c["task_id"], "arm": c.get("arm"), "SR_c": c.get("SR_c"), "decision": c.get("decision")})
        rows.append(row)
        if wit:
            wits.append({"candidate_id": c["candidate_id"], "task_id": c["task_id"], "actions": wit, "source": "R_old" if ro.ok else ("R_exp" if rx.ok else "R_hint")})
    for t, acts in witness.items():
        if acts:
            wits.append({"task_id": t, "candidate_id": None, "actions": acts, "source": "W_base"})
    with open(out_cert, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out_wit, "w", encoding="utf-8") as fh:
        for w in wits:
            fh.write(json.dumps(w, ensure_ascii=False) + "\n")
    print(f"[phase3] certificates {len(rows)}: certified {sum(r['certified'] for r in rows)}, unresolved {sum(r['unresolved'] for r in rows)}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["replays", "hints", "assemble", "all"], default="all")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    cands = _jsonl(RESULTS / "candidates.jsonl")
    witness = {int(w["task_id"]): [x for x in w.get("expert_actions", [])] for w in _jsonl(RESULTS / "witness_base.jsonl") if w.get("W_base")}
    rep_path, hint_path = RESULTS / "certificates_replays.jsonl", RESULTS / "certificates_hints.jsonl"
    if a.stage in ("replays", "all"):
        run_replays(cands, witness, rep_path, a.workers)
    replays = {r["candidate_id"]: r for r in _jsonl(rep_path)}
    if a.stage in ("hints", "all"):
        run_hints(cands, replays, witness, hint_path)
    hints = {h["candidate_id"]: h for h in _jsonl(hint_path)}
    if a.stage in ("assemble", "all"):
        assemble(cands, replays, hints, RESULTS / "certificates.jsonl", RESULTS / "witnesses.jsonl", witness)


if __name__ == "__main__":
    main()
