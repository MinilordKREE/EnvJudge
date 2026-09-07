"""Supplementary arm F_H-mid (owner decision at the P4.3 gate; not a substitute, excluded from H2a): the in-band F_H doses
with corrected omega in (0.5, 1] — tasks 2 (m=12), 7 (m=7), 15 (m=18). Each gets 8 more corpus rollouts (tag
p4nsat-<tid>-F_H-<m>-bank, run dir e1_p4_nsat) -> p_16; confirmed iff p_16 in [0.25, 0.75]. Output p4/results/fhmid_confirm.jsonl.
Used only for H4's omega ordering (three levels: ~1, (0.5,1], <=0.5) with its own orig_c control."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from envharness.core.types import Candidate  # noqa: E402
from e1.operators import h_horizon  # noqa: E402
from p4.nsat import Runner, confirm  # noqa: E402

RES = ROOT / "p4" / "results"
OUT = RES / "fhmid_confirm.jsonl"


def main() -> None:
    os.environ["EOBS_PHASE"] = "p4_build"
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p4_nsat", "qwen")
    os.environ["EOBS_PHASE"] = "p4_build"
    rows = [json.loads(l) for l in (RES / "nsat_doses.jsonl").read_text().splitlines() if l.strip()]
    mid = [r for r in rows if r["family"] == "F_H" and r["class"] == "IN-BAND" and r.get("omega") is not None and 0.5 < r["omega"] <= 1.0 and not r.get("confirmed")]
    done = {(r["task_id"], r["dose"]) for r in ([json.loads(l) for l in OUT.read_text().splitlines() if l.strip()] if OUT.exists() else [])}
    print("[P4.3-mid] doses", [(r["task_id"], r["dose"], r["omega"], r["successes"]) for r in mid], flush=True)
    for r in mid:
        tid, m = int(r["task_id"]), int(r["dose"])
        if (tid, m) in done:
            continue
        cand = Candidate(rules_code=h_horizon.rules_code(m), in_env_actions=[], rationale="F_H")
        s_new, p16 = confirm(runner, cand, tid, f"p4nsat-{tid}-F_H-{m}", int(r["successes"]))
        row = {"task_id": tid, "family": "F_H", "dose": m, "omega": r["omega"], "certified_by": r["certified_by"], "successes8": int(r["successes"]), "bank_successes": s_new,
               "p16": round(p16, 4), "rollouts": 16, "confirmed": 0.25 <= p16 <= 0.75, "arm": "fhmid"}
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        print("[P4.3-mid]", row, flush=True)
    print("[P4.3-mid] done", flush=True)


if __name__ == "__main__":
    main()
