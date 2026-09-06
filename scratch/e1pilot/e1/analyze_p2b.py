"""P2b analysis (PREREG3b): K2b, per-family leverage, rollouts-to-hit, uncertified/infeasible counts, λ dose-response, monotonicity."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "eobs")); sys.path.insert(0, str(ROOT))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402
from e1.lam_search import monotonicity_violations  # noqa: E402

RES = ROOT / "results" / "e1pilot"


def main(primary_only: bool = True) -> dict:
    rows = [json.loads(l) for l in (RES / "p2b_doses.jsonl").read_text().splitlines() if l.strip()]
    qp = {int(r["task_id"]): float(r["p16_qwen"]) for r in csv.DictReader(open(RES / "qwen_p16.csv")) if r["p16_qwen"] != ""}
    primary = {t for t, p in qp.items() if p == 1.0}
    by = defaultdict(list)
    for r in rows:
        if (not primary_only) or r["task_id"] in primary:
            by[r["task_id"]].append(r)
    summ, curves = [], []
    for tid, rs_ in sorted(by.items()):
        cum = 0; hit = None
        for r in rs_:
            cum += int(r.get("rollouts") or 0)
            if r.get("class") == "IN-BAND" and hit is None:
                hit = (r["family"], r["dose"], cum)
        fams = {}
        for fam in ("F_O", "F_H", "F_S0p"):
            fr = [r for r in rs_ if r["family"] == fam and r.get("rollouts")]
            fams[fam] = ("moved" if any(r["class"] != "NOEFFECT" for r in fr) else ("noeffect" if fr else "none"))
        lam_hist = [(float(r["dose"]), r["class"]) for r in rs_ if r["family"] == "F_O" and r.get("rollouts")]
        summ.append({"task_id": tid, "type": rs_[0].get("type"), "hit": bool(hit), "hit_family": hit[0] if hit else "", "hit_dose": hit[1] if hit else "", "rollouts_to_hit": hit[2] if hit else "",
                     "total_rollouts": cum, "F_O": fams["F_O"], "F_H": fams["F_H"], "F_S0p": fams["F_S0p"], "n_uncertified": sum(r.get("class") == "UNCERTIFIED" for r in rs_),
                     "n_infeasible": sum(r.get("class") == "INFEASIBLE" for r in rs_), "n_post_hoc": sum(r.get("certified_by") == "R_post_hoc" for r in rs_),
                     "lambda_evals": len(lam_hist), "lambda_monotonicity_violations": monotonicity_violations(lam_hist), "lambda_curve": " ".join(f"{l}:{c}" for l, c in lam_hist)})
        for r in rs_:
            if r.get("rollouts"):
                curves.append({"task_id": tid, "family": r["family"], "dose": r["dose"], "rollouts": r["rollouts"], "successes": r["successes"], "p_hat": r["p_hat"], "class": r["class"], "certified_by": r.get("certified_by")})
    with open(RES / "p2b_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
    with open(RES / "p2b_curves.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(curves[0].keys())); w.writeheader(); w.writerows(curves)
    g = {s["task_id"]: [s] for s in summ}
    k2b = boot_rate(g, lambda s: s["hit"] and s["rollouts_to_hit"] != "" and s["rollouts_to_hit"] <= 24, lambda s: 1)
    lev = {fam: boot_rate({t: [s] for t, s in g.items() for s in [g[t][0]] if s[fam] != "none"}, lambda s, fam=fam: s[fam] == "moved", lambda s: 1) for fam in ("F_O", "F_H", "F_S0p")}
    hits = sorted(s["rollouts_to_hit"] for s in summ if s["hit"])
    out = {"K2b": k2b, "text": ("controller alive (≥ 0.60)" if k2b[0] >= 0.60 else ("alive, library needs work (0.30–0.60)" if k2b[0] >= 0.30 else "dead (< 0.30)")),
           "leverage": lev, "median_rollouts_to_hit": hits[len(hits) // 2] if hits else None, "n_hits": len(hits), "n_tasks": len(summ),
           "classes": dict(Counter(r.get("class") for r in rows)), "certs": dict(Counter(r.get("certified_by") for r in rows if r.get("certified_by"))),
           "rollouts": sum(int(r.get("rollouts") or 0) for r in rows), "in_band_envs": [(s["task_id"], s["hit_family"], s["hit_dose"]) for s in summ if s["hit"]]}
    (RES / "p2b_summary.json").write_text(json.dumps(out, default=str, indent=1))
    print(json.dumps({k: (rs(v) if isinstance(v, tuple) else v) for k, v in out.items() if k != "leverage"}, default=str, indent=1)); print("leverage:", {k: rs(v) for k, v in lev.items()})
    return out


if __name__ == "__main__":
    main()
