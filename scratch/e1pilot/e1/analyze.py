"""E1-pilot analysis: P2 summary/curves + K2/K2', and report.md assembly (P0, P1/K1, P2, P3 if present)."""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(EOBS))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402
from eobs.llm import ledger_totals  # noqa: E402
from eobs.settings import PRICING_VERSION, PRICING_VERSION_QWEN  # noqa: E402

RES = ROOT / "results" / "e1pilot"
DOSE_ORDER = [("F_S0", 1), ("F_S0", 2), ("F_S0", 3), ("F_O", 0.5), ("F_O", 1.0)]


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def p2_tables() -> dict | None:
    rows = _jsonl(RES / "p2_doses.jsonl")
    if not rows:
        return None
    by = defaultdict(list)
    for r in rows:
        by[r["task_id"]].append(r)
    summ = []
    for tid, rs_ in sorted(by.items()):
        rs_.sort(key=lambda r: DOSE_ORDER.index((r["family"], r["dose"])))
        cum = 0; hit = None; hit_dose = None; rollouts_to_hit = None
        for r in rs_:
            cum += int(r.get("rollouts") or 0)
            if r.get("class") == "IN-BAND" and hit is None:
                hit, hit_dose, rollouts_to_hit = True, f"{r['family']}:{r['dose']}", cum
        feas = [r for r in rs_ if r.get("class") not in ("INFEASIBLE", "UNCERTIFIED")]
        ceiling = feas[-1]["class"] if feas else "none-feasible"
        max_dose_classes = {}
        for fam in ("F_S0", "F_O"):
            ff = [r for r in feas if r["family"] == fam]
            max_dose_classes[fam] = ff[-1]["class"] if ff else "none-feasible"
        summ.append({"task_id": tid, "type": rs_[0].get("type"), "regime": rs_[0].get("regime"), "n_doses_tried": len(rs_), "hit": bool(hit), "hit_dose": hit_dose or "",
                     "rollouts_to_hit": rollouts_to_hit or "", "total_rollouts": cum, "ceiling_class_last_feasible": ceiling,
                     "F_S0_max_feasible_class": max_dose_classes["F_S0"], "F_O_max_feasible_class": max_dose_classes["F_O"],
                     "n_infeasible": sum(r.get("class") == "INFEASIBLE" for r in rs_), "n_uncertified": sum(r.get("class") == "UNCERTIFIED" for r in rs_),
                     "cert_sources": " ".join(f"{r['family']}:{r['dose']}={r.get('certified_by')}" for r in rs_ if r.get("certified_by"))})
    with open(RES / "p2_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
    g = {s["task_id"]: [s] for s in summ}
    k2 = boot_rate(g, lambda s: s["hit"] and s["rollouts_to_hit"] != "" and s["rollouts_to_hit"] <= 16, lambda s: 1)
    both_max_noeffect = boot_rate(g, lambda s: s["F_S0_max_feasible_class"] in ("NOEFFECT", "none-feasible") and s["F_O_max_feasible_class"] in ("NOEFFECT", "none-feasible") and not s["hit"], lambda s: 1)
    hits = sorted(s["rollouts_to_hit"] for s in summ if s["hit"])
    med = hits[len(hits) // 2] if hits else None
    curves = [r for r in rows if r.get("rollouts")]
    with open(RES / "p2_curves.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task_id", "type", "family", "dose", "rollouts", "successes", "p_hat", "class", "certified_by"]); w.writeheader()
        for r in sorted(curves, key=lambda r: (r["task_id"], DOSE_ORDER.index((r["family"], r["dose"])))):
            w.writerow({k: r.get(k) for k in w.fieldnames})
    k2_text = "controller alive (≥ 0.60)" if k2[0] >= 0.60 else ("alive but the operator library needs a third family before E1 (0.30–0.60)" if k2[0] >= 0.30 else "dead for this policy (< 0.30)")
    k2p_text = "ceiling: structural hardening cannot move this policy either (≥ 0.40)" if both_max_noeffect[0] >= 0.40 else "no expressivity ceiling (< 0.40)"
    counts = Counter(r.get("class") for r in rows); certs = Counter(r.get("certified_by") for r in rows if r.get("certified_by"))
    return {"summary": summ, "k2": k2, "k2_text": k2_text, "k2p": both_max_noeffect, "k2p_text": k2p_text, "median_rollouts_to_hit": med, "class_counts": dict(counts), "cert_counts": dict(certs),
            "n_rollouts": sum(int(r.get("rollouts") or 0) for r in rows), "n_tasks": len(summ)}


def main(prereg_sha: str, cfg_sha: str) -> None:
    led = ledger_totals(RES / "ledger.jsonl")
    L = [f"# E1-pilot report — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
         f"PREREG3 sha `{prereg_sha}`; qwen_map.yaml sha256 `{cfg_sha}`; policy model `openai/qwen3-8b` at `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (enable_thinking=false); pricing {PRICING_VERSION_QWEN} (Qwen) / {PRICING_VERSION} (DeepSeek); spend by phase (USD): { {k: round(v, 3) for k, v in led['by_phase'].items()} }; total USD {led['usd']:.2f} of the 30 cap.", ""]
    # P0
    L += ["## P0 — ΔSR by operator type (E-obs H arm, saturated tasks)", "", "| set | operator | n | tasks | mean SR_c | share SR ≤ 0.6 | share in band | share accepted |", "|---|---|---|---|---|---|---|---|"]
    for r in csv.DictReader(open(RES / "p0_dsr_by_operator.csv")):
        L.append(f"| {r['set']} | {r['operator_type']} | {r['n_attempts']} | {r['n_tasks']} | {r['mean_SR_c']} | {r['share_SR_le_0.6']} | {r['share_in_band']} | {r['share_accepted']} |")
    # P1
    L += ["", "## P1 — Qwen3-8B regime map", ""]
    if (RES / "p1_summary.json").exists():
        s = json.loads((RES / "p1_summary.json").read_text())
        L += ["| consumer | zero | edge-low | band | edge-high | saturated |", "|---|---|---|---|---|---|"]
        for r in csv.DictReader(open(RES / "regime_by_consumer.csv")):
            L.append(f"| {r['consumer']} | {r['zero']} | {r['edge-low']} | {r['band']} | {r['edge-high']} | {r['saturated']} |")
        ps = s["parse_stats"]
        L += ["", f"Mean p16 (Qwen) = {fmt(s['mean_p16_qwen'])}; parse-failure rate = {fmt(ps['parse_fail_rate'])} of {ps['steps']} policy steps ({ps['no_action_tag']} without an <action> tag, {ps['inadmissible']} inadmissible); episodes {ps['episodes']}, errors {ps['errors']}, mean steps {fmt(ps['mean_steps'])}.", "",
              f"**K1 outcome: {s['K1']}** — zero + edge-low = {s['zero+edge-low']}, saturated + edge-high = {s['saturated+edge-high']}.", ""]
    else:
        L += ["P1 not run (DashScope model access pending).", ""]
    # P2
    L += ["## P2 — structural hardening dose pilot", ""]
    p2 = p2_tables()
    if p2:
        L += [f"Targets: {p2['n_tasks']} tasks; regime {p2['summary'][0]['regime']}; rollouts {p2['n_rollouts']}; dose outcomes {p2['class_counts']}; certificate sources {p2['cert_counts']}.", "",
              "| task | type | hit | hit dose | rollouts to hit | total rollouts | F_S0 max-dose class | F_O max-dose class | infeasible | uncertified |", "|---|---|---|---|---|---|---|---|---|---|"]
        for s in p2["summary"]:
            L.append(f"| {s['task_id']} | {s['type']} | {s['hit']} | {s['hit_dose']} | {s['rollouts_to_hit']} | {s['total_rollouts']} | {s['F_S0_max_feasible_class']} | {s['F_O_max_feasible_class']} | {s['n_infeasible']} | {s['n_uncertified']} |")
        L += ["", f"Share of target tasks reaching IN-BAND with ≤ 16 rollouts = {rs(p2['k2'])}; median rollouts-to-hit = {p2['median_rollouts_to_hit']}.",
              f"Share still NOEFFECT (or infeasible) at the maximum feasible dose of BOTH families = {rs(p2['k2p'])}.", "",
              f"**K2 outcome: {p2['k2_text']}**; **K2′: {p2['k2p_text']}**.", "", "Dose–response rows (all doses with rollouts) are in p2_curves.csv."]
    else:
        L += ["P2 not run.", ""]
    L += ["", "## P3 — downstream skill sanity (P3a: nobank / orig; P3b: orig_m / ours)", ""]
    if (RES / "p3_skills.csv").exists():
        L += ["| condition | split | tasks | episodes | success | CI |", "|---|---|---|---|---|---|"]
        for r in csv.DictReader(open(RES / "p3_skills.csv")):
            L.append(f"| {r['condition']} | {r['split']} | {r['n_tasks']} | {r['episodes']} | {r['success']} | [{r['ci_lo']}, {r['ci_hi']}] |")
        if (RES / "p3b_summary.json").exists():
            k3 = json.loads((RES / "p3b_summary.json").read_text())
            idd = k3["K3"].get("eval_in_distribution"); ood = k3["K3"].get("eval_out_of_distribution")
            L += ["", f"Held-out = first 30 tasks of each released split (start seed 0), the SAME tasks × 3 replicates (owner deviation from the released 0/1000/2000 rounds). Banks: orig = P3a bank from all 30 train tasks; orig_m = matched-original (8 P1 trajectories on each of the 9 in-band tasks); ours = 8 Qwen rollouts on each in-band controlled env (P2b hit dose). Item counts: orig 67, orig_m 23, ours 9 (trajectory counts matched; the released induction emits fewer items from paired success/failure trajectories).", "",
                  f"**K3 outcome: {k3['verdict']}** — ours − orig_m (paired per task): in-distribution {fmt(idd[0])} [{fmt(idd[1])}, {fmt(idd[2])}]; out-of-distribution {fmt(ood[0])} [{fmt(ood[1])}, {fmt(ood[2])}]; threshold −0.02 on the in-distribution split."]
        else:
            L += ["", "K3: not evaluable, pending P3b."]
    else:
        L += ["Not run."]
    L += ["",
          "## Measurement notes", "", "- Parse failure = no <action> tag or a command outside the admissible list shown to the policy; computed per step from traces.",
          "- Certificates: R_pol replays the shortest successful baseline trajectory of the same policy; R_exp is the stochastic handcoded expert (≤ 3 attempts) from the staged state; uncertified doses are skipped and counted.",
          "- F_S0 placement verb fixed to `move <obj> to <recep>` before any dose was run (LOG).", "",
          "## Caveats", "", "- Qwen3-8B via the DashScope API (international endpoint), not local weights; single benchmark; N = 30; operator library of two families; no EnvRigger comparison under Qwen yet."]
    (RES / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:8]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "", sys.argv[2] if len(sys.argv) > 2 else "")
