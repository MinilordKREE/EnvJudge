"""P0 — ΔSR by operator type on the E-obs H-arm saturated tasks (S_H: p5_H = 1.0; S_H': p5_H >= 0.8). $0."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(EOBS))
from eobs.analyze import boot_rate, fmt  # noqa: E402

OUT = ROOT / "results" / "e1pilot"


def optype(r: dict) -> str:
    ops = []
    if int(r["S0_n_actions"] or 0):
        ops.append("S0:setup_actions")
    if "filter_action" in r["hooks"]:
        ops.append("A:block(" + ("regex" if r["A_uses_regex"] == "True" else "literal") + ")" if r["A_returns_Blocked"] == "True" else "A:rewrite")
    if "modify_transition" in r["hooks"]:
        ops.append("T:" + ("nothing_happens" if r["T_nothing_happens"] == "True" else "text_edit") + ("+random" if r["T_uses_random"] == "True" else ""))
    if "filter_observation" in r["hooks"]:
        ops.append("O:" + ("admissible" if r["O_touches_admissible"] == "True" else "text") + ("+regex" if r["O_uses_regex"] == "True" else ""))
    return "+".join(ops) or "none"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tax = {r["candidate_id"]: r for r in csv.DictReader(open(EOBS / "results/eobs/followup/candidate_taxonomy.csv"))}
    tasks = {int(t["task_id"]): t for t in csv.DictReader(open(EOBS / "results/eobs/tasks.csv"))}
    cands = [json.loads(l) for l in open(EOBS / "results/eobs/candidates.jsonl") if l.strip()]
    rows = []
    for setname, thr in (("S_H", 1.0), ("S_H_prime", 0.8)):
        sat = {tid for tid, t in tasks.items() if t.get("p5_H") not in ("", None) and float(t["p5_H"]) >= thr}
        by = defaultdict(lambda: defaultdict(list))
        for c in cands:
            if c["arm"] != "H" or int(c["task_id"]) not in sat:
                continue
            by[optype(tax[c["candidate_id"]])][int(c["task_id"])].append(c)
        for op, g in sorted(by.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
            n = sum(len(v) for v in g.values())
            mean = boot_rate(g, lambda c: float(c["SR_c"]), lambda c: 1)
            moved = boot_rate(g, lambda c: float(c["SR_c"]) <= 0.6, lambda c: 1)
            band = boot_rate(g, lambda c: 0.4 <= float(c["SR_c"]) <= 0.6, lambda c: 1)
            acc = boot_rate(g, lambda c: c["decision"] == "accept", lambda c: 1)
            rows.append({"set": setname, "operator_type": op, "n_attempts": n, "n_tasks": len(g), "mean_SR_c": f"{fmt(mean[0])} [{fmt(mean[1])}, {fmt(mean[2])}]",
                         "share_SR_le_0.6": f"{fmt(moved[0])} [{fmt(moved[1])}, {fmt(moved[2])}]", "share_in_band": f"{fmt(band[0])} [{fmt(band[1])}, {fmt(band[2])}]",
                         "share_accepted": f"{fmt(acc[0])} [{fmt(acc[1])}, {fmt(acc[2])}]", "SR_values": " ".join(str(c["SR_c"]) for v in g.values() for c in v)})
    with open(OUT / "p0_dsr_by_operator.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(f"{r['set']:9} {r['operator_type']:32} n={r['n_attempts']:3} tasks={r['n_tasks']:2} meanSR {r['mean_SR_c']:28} moved {r['share_SR_le_0.6']:28} band {r['share_in_band']}")


if __name__ == "__main__":
    main()
