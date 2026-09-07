"""Post-run correction for the F_H ω/certificate bug (Session.done ignored Rules-level termination). Archives nsat_doses.jsonl
and isat_confirm.csv as *_v1_omega_bug, recomputes ω for every F_H row (and the I-sat F_H env), re-establishes certificates
(by construction → R_pol → expert ×3 with the fixed replay), runs the 8 confirmation rollouts for IN-BAND F_H doses whose
corrected ω ≤ 0.5, and rewrites nsat_envs.csv / isat_confirm.csv."""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from envharness.core.types import Candidate  # noqa: E402
from e1.operators import h_horizon  # noqa: E402
from e1.p2b_run import expert_len_from_reset  # noqa: E402
from eobs.replay import open_session, run_expert  # noqa: E402
from p4.nsat import Runner, confirm  # noqa: E402
from p4.omega import omega  # noqa: E402

RES = ROOT / "p4" / "results"


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def main() -> None:
    os.environ["EOBS_PHASE"] = "p4_build"
    src = RES / "nsat_doses.jsonl"
    shutil.copyfile(src, RES / "nsat_doses_v1_omega_bug.jsonl")
    shutil.copyfile(RES / "isat_confirm.csv", RES / "isat_confirm_v1_omega_bug.csv")
    shutil.copyfile(RES / "omega.csv", RES / "omega_v1_omega_bug.csv")
    rows = _jsonl(src)
    runner = Runner(ROOT / "configs" / "qwen_map.yaml", "e1_p4_nsat", "qwen")
    os.environ["EOBS_PHASE"] = "p4_build"
    L_exp = {}
    out = []
    for r in rows:
        if r["family"] != "F_H" or not r.get("rollouts"):
            out.append(r); continue
        tid, m = int(r["task_id"]), int(r["dose"])
        cand = Candidate(rules_code=h_horizon.rules_code(m), in_env_actions=[], rationale="F_H")
        w, ok, n = omega(tid, cand)
        if tid not in L_exp:
            L_exp[tid] = expert_len_from_reset(tid)[0]
        cert = "by_construction" if (L_exp[tid] is not None and L_exp[tid] <= m) else ("R_pol" if (w or 0) > 0 else None)
        if cert is None:
            for _ in range(3):
                s = open_session(cand, tid)
                try:
                    if run_expert(s, max_steps=min(m, 50)).ok:
                        cert = "R_exp"; break
                finally:
                    s.close()
        r2 = {**r, "omega_v1": r.get("omega"), "omega": w, "omega_ok": w is not None and w <= 0.5, "certified_by_v1": r.get("certified_by"), "certified_by": cert or "uncertified_post_hoc"}
        r2.pop("note", None)
        if r2["class"] == "IN-BAND" and r2["omega_ok"] and cert and not r.get("confirmed"):
            tag = f"p4nsat-{tid}-F_H-{m}"
            s_new, p16 = confirm(runner, cand, tid, tag, int(r["successes"]))
            r2.update({"bank_successes": s_new, "p16": round(p16, 4), "confirmed": 0.25 <= p16 <= 0.75, "rollouts": int(r["rollouts"]) + 8})
        elif r2["class"] == "IN-BAND" and not r2["omega_ok"]:
            r2["note"] = "in-band but omega > 0.5 (corrected): not behavior-breaking; not confirmed"
        print("[P4.3-fix]", {k: r2[k] for k in ("task_id", "dose", "omega_v1", "omega", "certified_by_v1", "certified_by", "class", "confirmed") if k in r2}, flush=True)
        out.append(r2)
    with open(src, "w") as fh:
        for r in out:
            fh.write(json.dumps(r, default=str) + "\n")
    # isat: recompute ω for the F_H env (task 7)
    isat = list(csv.DictReader(open(RES / "isat_confirm_v1_omega_bug.csv")))
    om = list(csv.DictReader(open(RES / "omega_v1_omega_bug.csv")))
    for r in isat:
        if r["env"].startswith("F_H:"):
            w, ok, n = omega(int(r["task_id"]), Candidate(rules_code=h_horizon.rules_code(int(r["env"].split(":")[1])), in_env_actions=[]))
            r["omega"] = w
            for o in om:
                if o["task_id"] == r["task_id"]:
                    o["omega"], o["survived"] = w, ok
    with open(RES / "isat_confirm.csv", "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(isat[0].keys())); w_.writeheader(); w_.writerows(isat)
    with open(RES / "omega.csv", "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(om[0].keys())); w_.writeheader(); w_.writerows(om)
    # nsat_envs.csv: per task, the confirmed row if any
    res = {}
    for r in out:
        if r.get("confirmed"):
            res.setdefault(r["task_id"], r)
    for r in out:
        res.setdefault(r["task_id"], {"task_id": r["task_id"], "confirmed": False})
    keys = sorted({k for r in res.values() for k in r if k != "in_env_actions"})
    with open(RES / "nsat_envs.csv", "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=keys); w_.writeheader(); w_.writerows([{k: v for k, v in r.items() if k != "in_env_actions"} for r in res.values()])
    print("[P4.3-fix] confirmed:", [t for t, r in res.items() if r.get("confirmed")], flush=True)


if __name__ == "__main__":
    main()
