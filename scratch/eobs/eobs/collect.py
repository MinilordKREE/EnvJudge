"""Collect EnvRigger run artifacts (both arms) + Phase-1 outputs into the results/eobs schema.

tasks.csv: task_id, type, expert_plan_len, W_base, within_policy_cap, p5, p11, p16, accepted, n_attempts, skipped, p5_H, accepted_H, n_attempts_H
baseline_rollouts.jsonl: rigger baselines (released arm) + extra (Phase 1)
candidates.jsonl / validation_rollouts.jsonl: both arms, field `arm` ∈ {released, H}
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from eobs import hooks
from eobs.settings import RESULTS, WORK


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()] if Path(p).exists() else []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--released", default="eobs_alfworld_001")
    ap.add_argument("--hard", default="eobs_alfworld_H_001,eobs_alfworld_H_001b_s10,eobs_alfworld_H_001b_s15,eobs_alfworld_H_001b_s20,eobs_alfworld_H_001b_s25")
    ap.add_argument("--phase1", default="eobs_phase1_extra")
    ap.add_argument("--n-tasks", type=int, default=30)
    a = ap.parse_args()
    runs = WORK / "runs"
    rel = hooks.extract(runs / a.released) if (runs / a.released / "traces.jsonl").exists() else None
    # The hardening arm may be split across run dirs (resume after the 2026-09-05 interruption): comma-separated,
    # later dirs override earlier ones for the task_ids they COMPLETED (task_end event); incomplete tasks are dropped.
    hard = None
    for d in [x for x in a.hard.split(",") if x]:
        if not (runs / d / "traces.jsonl").exists():
            continue
        ex = hooks.extract(runs / d)
        events = [json.loads(l) for l in (runs / d / "orchestrator.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        ended = {e.get("task_idx") for e in events if e.get("kind") == "task_end"}
        # task_idx in a shard is relative; task_id (= seed) is absolute -> key by task_id
        idx_to_id = {t["task_idx"]: t["task_id"] for t in ex["tasks"].values()}
        complete_ids = {idx_to_id[i] for i in ended if i in idx_to_id}
        ex["candidates"] = [c for c in ex["candidates"] if c["task_id"] in complete_ids]
        ex["validation_rollouts"] = [v for v in ex["validation_rollouts"] if v["task_id"] in complete_ids]
        ex["tasks"] = {t["task_id"]: t for t in ex["tasks"].values() if t["task_id"] in complete_ids}
        if hard is None:
            hard = ex
        else:
            for tid in ex["tasks"]:
                hard["candidates"] = [c for c in hard["candidates"] if c["task_id"] != tid]
                hard["validation_rollouts"] = [v for v in hard["validation_rollouts"] if v["task_id"] != tid]
            hard["candidates"] += ex["candidates"]; hard["validation_rollouts"] += ex["validation_rollouts"]; hard["tasks"].update(ex["tasks"])
            for k, v in ex.get("align_stats", {}).items():
                hard.setdefault("align_stats", {})[k] = hard.get("align_stats", {}).get(k, 0) + v
    extra = _jsonl(runs / a.phase1 / "traces.jsonl")
    witness = {int(w["task_id"]): w for w in _jsonl(RESULTS / "witness_base.jsonl")}

    baseline = []
    if rel:
        baseline += rel["baseline_rollouts"]
    for t in extra:
        acts = [(s.get("raw_action") or {}).get("kwargs", {}).get("text", "") for s in t.get("steps", [])]
        baseline.append({"task_id": t.get("rollout_seed"), "source": "extra", "seed_idx": t.get("rollout_idx"), "success": bool(t.get("success")),
                         "steps": t.get("duration_steps"), "actions": acts, "timeout": t.get("error") == "subprocess timeout", "error": t.get("error"),
                         "kind": "baseline", "episode_id": t.get("episode_id"), "candidate_id": "extra"})
    hooks.write_jsonl(RESULTS / "baseline_rollouts.jsonl", baseline)

    cands, vals = [], []
    for arm, ex in (("released", rel), ("H", hard)):
        if not ex:
            continue
        for c in ex["candidates"]:
            cands.append({**c, "arm": arm})
        for v in ex["validation_rollouts"]:
            vals.append({**v, "arm": arm})
        print(f"[collect] {arm}: candidates {len(ex['candidates'])}, validation rollouts {len(ex['validation_rollouts'])}, align {ex.get('align_stats')}")
    hooks.write_jsonl(RESULTS / "candidates.jsonl", cands)
    hooks.write_jsonl(RESULTS / "validation_rollouts.jsonl", vals)

    rows = []
    for tid in range(a.n_tasks):
        w = witness.get(tid, {})
        rig = [b for b in baseline if b["source"] == "rigger" and b["task_id"] == tid and not b.get("error")]
        ext = [b for b in baseline if b["source"] == "extra" and b["task_id"] == tid and not b.get("error")]
        p5 = sum(b["success"] for b in rig) / len(rig) if rig else None
        p11 = sum(b["success"] for b in ext) / len(ext) if ext else None
        allb = rig + ext
        p16 = sum(b["success"] for b in allb) / len(allb) if allb else None
        tr = (rel or {}).get("tasks", {}).get(tid, {}) if rel else {}
        th = (hard or {}).get("tasks", {}).get(tid, {}) if hard else {}   # keyed by task_id after the merge above
        rows.append({"task_id": tid, "type": w.get("type", ""), "expert_plan_len": w.get("expert_plan_len", ""), "W_base": w.get("W_base", ""),
                     "W_reason": w.get("reason", ""), "within_policy_cap": w.get("within_policy_cap", ""),
                     "p5": "" if p5 is None else round(p5, 4), "p11": "" if p11 is None else round(p11, 4), "p16": "" if p16 is None else round(p16, 4),
                     "n_base": len(allb), "accepted": tr.get("accepted", ""), "n_attempts": tr.get("n_attempts", ""), "skipped": tr.get("skipped", ""),
                     "p5_H": th.get("p5", ""), "accepted_H": th.get("accepted", ""), "n_attempts_H": th.get("n_attempts", ""), "skipped_H": th.get("skipped", "")})
    with open(RESULTS / "tasks.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"[collect] tasks {len(rows)}; baseline rollouts {len(baseline)}; candidates {len(cands)}")


if __name__ == "__main__":
    main()
