"""P4.1 I-sat: 8 more corpus-protocol rollouts on each of the 9 P2b in-band envs → p̂_16; confirmed iff p̂_16 ∈ [0.25, 0.75].
The 8 new rollouts are the I-sat bank trajectories (run dir e1_p4_isat, candidate_id tag p4isat-<task>-<fam>-<dose>)."""

from __future__ import annotations

import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from e1.p2_run import Runner  # noqa: E402
from p4.omega import candidate_from_row  # noqa: E402

RES = ROOT / "p4" / "results"


def main() -> None:
    os.environ["EOBS_PHASE"] = "p4_build"
    rows = [json.loads(l) for l in (ROOT / "results" / "e1pilot" / "p2b_doses.jsonl").read_text().splitlines() if l.strip()]
    hits = {}
    for r in rows:
        if r.get("class") == "IN-BAND" and r["task_id"] not in hits:
            hits[r["task_id"]] = r
    omega = {int(r["task_id"]): r for r in csv.DictReader(open(RES / "omega.csv"))}
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p4_isat", "qwen")
    os.environ["EOBS_PHASE"] = "p4_build"
    done = {}
    tr_path = ROOT / "work" / "runs" / "e1_p4_isat" / "traces.jsonl"
    if tr_path.exists():
        for l in tr_path.read_text().splitlines():
            if l.strip():
                t = json.loads(l); done.setdefault(t["candidate_id"], []).append(bool(t["success"]))
    out = []
    for tid, r in sorted(hits.items()):
        tag = f"p4isat-{tid}-{r['family']}-{r['dose']}"
        cand = candidate_from_row(r)
        have = done.get(tag, [])
        need = 8 - len(have)
        if need > 0:
            with ThreadPoolExecutor(max_workers=min(4, need)) as pool:
                have += [bool(t.success) for t in pool.map(lambda _: runner.episode(cand, tid, tag), range(need))]
        s16 = int(r["successes"]) + sum(have); p16 = s16 / (int(r["rollouts"]) + len(have))
        row = {"task_id": tid, "env": f"{r['family']}:{r['dose']}", "p8_p2b": r["p_hat"], "p8_new": sum(have) / len(have), "p16": round(p16, 4), "confirmed": 0.25 <= p16 <= 0.75,
               "omega": omega.get(tid, {}).get("omega", ""), "certified_by_p2b": r.get("certified_by"), "primary": tid in (7, 12, 13, 15, 21, 22, 29)}
        out.append(row); print("[P4.1]", row, flush=True)
    with open(RES / "isat_confirm.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    prim = [r for r in out if r["primary"]]
    print(f"[P4.1] confirmed {sum(r['confirmed'] for r in out)}/{len(out)}; primary confirmed {sum(r['confirmed'] for r in prim)}/{len(prim)}", flush=True)


if __name__ == "__main__":
    main()
