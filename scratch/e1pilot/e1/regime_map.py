"""P1 — Qwen3-8B regime map: smoke (2 tasks × 2) with parse-failure rate and cost projection, then K=16 baseline rollouts
per task via the released Orchestrator._rollout_baseline_k (only k_per_candidate / rollout_concurrency overridden).

Parse failure (per policy step): the raw response has no <action>...</action> tag OR the executed command is not in the
admissible list shown to the policy (the bridge then answers "Nothing happens").
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(EOBS))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402
from eobs.llm import ledger_totals  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402

RES = ROOT / "results" / "e1pilot"
WORK = ROOT / "work"
ACTION_RE = re.compile(r"<action>(.*?)</action>", re.DOTALL)


def _run(run_name: str, n_tasks: int, k: int, conc: int, phase: str, task_ids: list[int] | None = None) -> None:
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["EOBS_RUN_ID"] = run_name; os.environ["EOBS_PHASE"] = phase
    os.environ["PYTHONPATH"] = str(EOBS) + os.pathsep + os.environ.get("PYTHONPATH", "")
    sys.path.insert(0, str(ENVHARNESS_ROOT / "scripts")); sys.path.insert(0, str(ENVHARNESS_ROOT))
    os.chdir(ENVHARNESS_ROOT)
    import run_harness
    orch = run_harness.build_from_config(ROOT / "configs" / "qwen_map.yaml", run_name,
                                         overrides={"n_tasks": n_tasks, "n_iterations": n_tasks, "k_per_candidate": k, "rollout_concurrency": conc})
    orch.log.event("p1_start", n_tasks=n_tasks, k=k, conc=conc, phase=phase)
    ids = task_ids if task_ids is not None else list(range(n_tasks))
    for task_idx in ids:
        task_id = orch.config.base_seed + task_idx * orch.config.task_id_stride + orch.config.task_id_base_offset
        if sum(1 for t in orch.trace_store.all() if t.rollout_seed == task_id) >= k:
            continue
        os.environ["EOBS_TASK_ID"] = str(task_id)
        t0 = time.time()
        traces = orch._rollout_baseline_k(task_idx, task_id)
        for t in traces:
            t.kind = "baseline"
            orch.trace_store.add(t)
        sr = sum(1 for t in traces if t.success) / max(len(traces), 1)
        orch.log.event("p1_task_done", task_idx=task_idx, task_id=task_id, k=len(traces), sr=round(sr, 3), n_errors=sum(1 for t in traces if t.error), wall_s=round(time.time() - t0, 1))
        print(f"[P1] task {task_id}: sr={sr:.3f} errors={sum(1 for t in traces if t.error)} {time.time() - t0:.0f}s", flush=True)
    orch.log.event("p1_end", n_traces=len(orch.trace_store))


def parse_stats(run_name: str) -> dict:
    tr = [json.loads(l) for l in (WORK / "runs" / run_name / "traces.jsonl").read_text().splitlines() if l.strip()]
    n_steps = n_noaction = n_inadmissible = 0
    per_ep = []
    for t in tr:
        prev_adm = None
        bad = 0
        for s in t.get("steps", []):
            n_steps += 1
            raw = s.get("policy_raw_response") or ""
            text = (s.get("raw_action") or {}).get("kwargs", {}).get("text", "")
            no_tag = not ACTION_RE.search(raw)
            inadm = prev_adm is not None and text not in prev_adm
            n_noaction += no_tag; n_inadmissible += inadm; bad += (no_tag or inadm)
            prev_adm = ((s.get("raw_observation") or {}).get("data") or {}).get("admissible_commands")
        per_ep.append(bad / max(len(t.get("steps", [])), 1))
    return {"episodes": len(tr), "steps": n_steps, "no_action_tag": n_noaction, "inadmissible": n_inadmissible,
            "parse_fail_rate": (n_noaction + n_inadmissible - 0) / max(n_steps, 1), "mean_per_episode": sum(per_ep) / max(len(per_ep), 1),
            "errors": sum(1 for t in tr if t.get("error")), "mean_steps": sum(t.get("duration_steps", 0) for t in tr) / max(len(tr), 1)}


def smoke() -> None:
    _run("e1_qwen_smoke", 2, 2, 2, "p1_map")
    st = parse_stats("e1_qwen_smoke")
    led = ledger_totals(RES / "ledger.jsonl")
    calls = [json.loads(l) for l in (RES / "ledger.jsonl").read_text().splitlines() if l.strip() and '"run_id": "e1_qwen_smoke"' in l]
    usd = sum(float(c.get("usd", 0)) for c in calls)
    usd_ep = usd / max(st["episodes"], 1)
    proj16 = 30 * 16 * usd_ep
    print(json.dumps({**st, "calls": len(calls), "calls_per_episode": len(calls) / max(st["episodes"], 1), "usd_per_episode": round(usd_ep, 4), "projected_P1_K16": round(proj16, 2), "projected_P1_K12": round(30 * 12 * usd_ep, 2)}, indent=1))
    from eobs.phase1 import prove_prompt_identity
    print("prompt identity vs E-obs Phase 1 (task 0):", prove_prompt_identity(EOBS / "work" / "runs" / "eobs_phase1_extra", WORK / "runs" / "e1_qwen_smoke", 0))


def bulk(k: int, conc: int) -> None:
    _run("e1_qwen_map", 30, k, conc, "p1_map")


def outputs(k: int) -> None:
    RES.mkdir(parents=True, exist_ok=True)
    tr = [json.loads(l) for l in (WORK / "runs" / "e1_qwen_map" / "traces.jsonl").read_text().splitlines() if l.strip()]
    by = defaultdict(list)
    for t in tr:
        if not t.get("error"):
            by[t["rollout_seed"]].append(t)
    tasks = {int(t["task_id"]): t for t in csv.DictReader(open(EOBS / "results/eobs/tasks.csv"))}
    flash = {int(r["task_id"]): r for r in csv.DictReader(open(EOBS / "results/eobs/followup/flash_p8.csv"))}
    rows = []
    for tid in range(30):
        rs_ = by.get(tid, [])
        p = sum(x["success"] for x in rs_) / len(rs_) if rs_ else None
        n_steps = n_inadm = n_cap = 0
        for t in rs_:
            prev = None
            for s in t.get("steps", []):
                n_steps += 1
                text = (s.get("raw_action") or {}).get("kwargs", {}).get("text", "")
                n_inadm += int(prev is not None and text not in prev)
                prev = ((s.get("raw_observation") or {}).get("data") or {}).get("admissible_commands")
            n_cap += int(t.get("duration_steps", 0) >= 50 and not t.get("success"))
        rows.append({"task_id": tid, "type": tasks[tid]["type"], "p16_qwen": "" if p is None else round(p, 4), "n_qwen": len(rs_), "p16_pro": tasks[tid]["p16"], "p8_flash": flash[tid]["p8_flash"],
                     "inadmissible_rate": round(n_inadm / n_steps, 4) if n_steps else "", "cap50_share": round(n_cap / len(rs_), 4) if rs_ else "", "mean_steps": round(sum(t.get("duration_steps", 0) for t in rs_) / len(rs_), 1) if rs_ else ""})
    with open(RES / "qwen_p16.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    def regime(p):
        return "zero" if p == 0 else ("edge-low" if p < 0.2 else ("band" if p <= 0.8 else ("edge-high" if p < 1 else "saturated")))
    g = {r["task_id"]: [r] for r in rows if r["p16_qwen"] != ""}
    table, shares = [], {}
    for name, key in (("Qwen3-8B p16", "p16_qwen"), ("Pro p16", "p16_pro"), ("Flash p8", "p8_flash")):
        rec = {"consumer": name}
        for reg in ("zero", "edge-low", "band", "edge-high", "saturated"):
            r = boot_rate(g, lambda x, reg=reg, key=key: regime(float(x[key])) == reg, lambda x: 1)
            rec[reg] = f"{fmt(r[0])} [{fmt(r[1])}, {fmt(r[2])}]"
            shares[(name, reg)] = r[0]
        table.append(rec)
    with open(RES / "regime_by_consumer.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys())); w.writeheader(); w.writerows(table)
    low = shares[("Qwen3-8B p16", "zero")] + shares[("Qwen3-8B p16", "edge-low")]
    high = shares[("Qwen3-8B p16", "saturated")] + shares[("Qwen3-8B p16", "edge-high")]
    k1 = "both-sides" if (low >= 0.15 and high >= 0.15) else ("one-sided: saturated side kept; P2 runs on Qwen" if high >= 0.15 else ("one-sided: zero side kept; P2 uses the Pro fallback" if low >= 0.15 else "neither side >= 0.15; P2 uses the Pro fallback"))
    st = parse_stats("e1_qwen_map")
    summary = {"K1": k1, "zero+edge-low": round(low, 3), "saturated+edge-high": round(high, 3), "parse_stats": st, "mean_p16_qwen": sum(float(r["p16_qwen"]) for r in rows if r["p16_qwen"] != "") / max(len(g), 1)}
    (RES / "p1_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    for r in table:
        print(r)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["smoke", "bulk", "outputs"], required=True)
    ap.add_argument("--k", type=int, default=16); ap.add_argument("--conc", type=int, default=6)
    a = ap.parse_args()
    {"smoke": smoke, "bulk": lambda: bulk(a.k, a.conc), "outputs": lambda: outputs(a.k)}[a.stage]()
