"""Assemble results/eobs/followup/followup_report.md from the F1-F7 outputs and evaluate D1-D3 (PREREG2)."""

from __future__ import annotations

import csv
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402
from eobs.llm import ledger_totals  # noqa: E402

RES = ROOT / "results" / "eobs"
OUT = RES / "followup"


def jsonl(p: Path) -> list[dict]:
    out = []
    if Path(p).exists():
        for l in Path(p).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                continue
    return out


def status(r, thr, ge=True) -> str:
    if r[0] != r[0]:
        return "inconclusive"
    ok = r[0] >= thr if ge else r[0] <= thr
    dec = (r[1] >= thr if ge else r[2] <= thr) if ok else (r[2] < thr if ge else r[1] > thr)
    return ("met" if ok else "not met") + (" (CI-decisive)" if dec else " (CI not decisive)")


def f3_summary() -> dict | None:
    rows = jsonl(OUT / "expert_aa.jsonl")
    if not rows or any(r["C_2"] is None or r["C_3"] is None for r in rows):
        return None
    recov = {r["trajectory_id"]: r for r in jsonl(RES / "recoverability.jsonl")}
    by = defaultdict(list)
    for r in rows:
        by[r["trajectory_id"]].append(r)
    g_task = defaultdict(list)
    per_traj = []
    for tid, rs_ in by.items():
        rs_.sort(key=lambda r: r["t"])
        c1 = [r["C_1"] for r in rs_]
        any3 = [int(bool(r["C_1"] or r["C_2"] or r["C_3"])) for r in rs_]
        maj3 = [int((r["C_1"] + r["C_2"] + r["C_3"]) >= 2) for r in rs_]
        def stats(c):
            ones = [t for t, x in enumerate(c) if x == 1]
            zeros = [t for t, x in enumerate(c) if x == 0]
            L = max(ones) if ones else -1
            fz = min(zeros) if zeros else None
            mono = 1 if (fz is None or not any(t > fz for t in ones)) else 0
            return L, mono
        L1, m1 = stats(c1); La, ma = stats(any3); Lm, mm = stats(maj3)
        rec = {"trajectory_id": tid, "task_id": rs_[0]["task_id"], "T_eval": len(rs_) - 1, "L_1": L1, "L_any3": La, "L_maj3": Lm, "monotone_1": m1, "monotone_any3": ma, "monotone_maj3": mm,
               "flips": sum(1 for r in rs_ if not (r["C_1"] == r["C_2"] == r["C_3"])), "n_prefix": len(rs_)}
        per_traj.append(rec)
        g_task[rs_[0]["task_id"]].append(rec)
    g_prefix = defaultdict(list)
    for r in rows:
        g_prefix[r["task_id"]].append(r)
    flip = boot_rate(g_prefix, lambda r: not (r["C_1"] == r["C_2"] == r["C_3"]), lambda r: 1)
    p1_given_any = boot_rate(g_prefix, lambda r: r["C_1"] == 1, lambda r: bool(r["C_1"] or r["C_2"] or r["C_3"]))
    L_any_ge2 = boot_rate(g_task, lambda r: r["L_any3"] >= 2, lambda r: 1)
    nonmono_any = boot_rate(g_task, lambda r: r["monotone_any3"] == 0, lambda r: 1)
    nonmono_1 = boot_rate(g_task, lambda r: r["monotone_1"] == 0, lambda r: 1)
    L1_ge2 = boot_rate(g_task, lambda r: r["L_1"] >= 2, lambda r: 1)
    nonmono_maj = boot_rate(g_task, lambda r: r["monotone_maj3"] == 0, lambda r: 1)
    # expert calibration from reset on these tasks: witness_base attempts
    wit = {int(w["task_id"]): w for w in jsonl(RES / "witness_base.jsonl")}
    tasks = sorted(g_task)
    att = [a for t in tasks for a in wit.get(t, {}).get("attempts", [])]
    fail_from_reset = sum(1 for a in att if not a["W_base"]) / len(att) if att else float("nan")
    summary = [{"stat": "prefix flip rate P(not all three equal)", "value": rs(flip)},
               {"stat": "P(C_1 = 1 | C_any3 = 1)", "value": rs(p1_given_any)},
               {"stat": "expert failure rate from reset on these tasks (witness attempts)", "value": f"{fmt(fail_from_reset)} ({len(att)} attempts on {len(tasks)} tasks)"},
               {"stat": "share L_1 >= 2", "value": rs(L1_ge2)}, {"stat": "share L_any3 >= 2", "value": rs(L_any_ge2)},
               {"stat": "share non-monotone (attempt 1)", "value": rs(nonmono_1)}, {"stat": "share non-monotone_any3", "value": rs(nonmono_any)}, {"stat": "share non-monotone_maj3", "value": rs(nonmono_maj)},
               {"stat": "n trajectories / prefixes", "value": f"{len(per_traj)} / {len(rows)}"}]
    with open(OUT / "expert_aa_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stat", "value"]); w.writeheader(); w.writerows(summary)
    with open(OUT / "expert_aa_per_trajectory.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_traj[0].keys())); w.writeheader(); w.writerows(per_traj)
    return {"summary": summary, "flip": flip, "L_any_ge2": L_any_ge2, "nonmono_any": nonmono_any, "nonmono_1": nonmono_1, "n": len(per_traj)}


def f5_summary() -> dict | None:
    p = OUT / "flash_p8.csv"
    if not p.exists():
        return None
    rows = list(csv.DictReader(open(p)))
    if any(r["p8_flash"] == "" for r in rows):
        return None
    def regime(p):
        return "zero" if p == 0 else ("edge-low" if p < 0.2 else ("band" if p <= 0.8 else ("edge-high" if p < 1 else "saturated")))
    g = {r["task_id"]: [r] for r in rows}
    table = []
    for name, key in (("Pro p16", "p16_pro"), ("Flash p8", "p8_flash")):
        rec = {"consumer": name}
        for reg in ("zero", "edge-low", "band", "edge-high", "saturated"):
            r = boot_rate(g, lambda x, reg=reg, key=key: regime(float(x[key])) == reg, lambda x: 1)
            rec[reg] = f"{fmt(r[0])} [{fmt(r[1])}, {fmt(r[2])}]"
        table.append(rec)
    zl = boot_rate(g, lambda x: float(x["p8_flash"]) < 0.2, lambda x: 1)
    zl_pro = boot_rate(g, lambda x: float(x["p16_pro"]) < 0.2, lambda x: 1)
    with open(OUT / "regime_by_consumer.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys())); w.writeheader(); w.writerows(table)
    fr = jsonl(OUT / "flash_recoverability.jsonl")
    fg = defaultdict(list)
    for r in fr:
        fg[r["task_id"]].append(r)
    frec = {"n": len(fr), "L2": boot_rate(fg, lambda r: r["L"] >= 2, lambda r: 1), "nonmono": boot_rate(fg, lambda r: r["monotone"] == 0, lambda r: 1)} if fr else None
    mean_flash = np.mean([float(r["p8_flash"]) for r in rows]); mean_pro = np.mean([float(r["p16_pro"]) for r in rows])
    return {"table": table, "zero_edge_low_flash": zl, "zero_edge_low_pro": zl_pro, "rows": rows, "recov": frec, "mean_flash": mean_flash, "mean_pro": mean_pro}


def main(prereg2_sha: str, flash_sha: str) -> None:
    R = pickle.loads((OUT / "_reanalyses_cache.pkl").read_bytes())
    f1, f2, f4, f6, f7 = R["f1"], R["f2"], R["f4"], R["f6"], R["f7"]
    f3 = f3_summary()
    f5 = f5_summary()
    led = ledger_totals(RES / "ledger.jsonl")
    L = [f"# E-obs-F follow-up report — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
         f"PREREG2 sha `{prereg2_sha}`; inputs E-obs @ `8ee43da`; Flash config sha256 `{flash_sha}`; follow-up spend (ledger phase flash_probe) USD {led['by_phase'].get('flash_probe', 0.0):.2f} of the USD 10 cap; all other items LLM-free.", ""]
    # ---- F1
    S = f1["S_H"]; Sp = f1["S_H_prime"]
    a, b, c = S["a"], S["b"], S["c"]
    L += ["## F1 — Hardening breakdown on saturated tasks (H arm)", "",
          f"S_H (p5_H = 1.0): {S['n_tasks']} tasks {S['tasks']}; S_H' (p5_H >= 0.8): {Sp['n_tasks']} tasks. Task classes on S_H: {S['task_class_counts']}; on S_H': {Sp['task_class_counts']}.", "",
          "| attempt-level rate on failed attempts (S_H) | value |", "|---|---|",
          f"| a = share NOEFFECT | {rs(a)} |", f"| b = share OVERSHOOT ∪ ZERO | {rs(b)} |", f"| c = share INBAND-but-not-accepted | {rs(c)} |", "",
          f"S_H' (supplementary): a = {rs(Sp['a'])}; b = {rs(Sp['b'])}; c = {rs(Sp['c'])}.", "",
          "| controllability (S_H) | rate | CI | n | tasks |", "|---|---|---|---|---|"]
    for row in S["ctrl"]:
        L.append(f"| {row['rate']} | {row['rate_point']} | [{row['ci_lo']}, {row['ci_hi']}] | {row['n']} | {row['tasks']} |")
    cls_hist = Counter(r["class"] for r in S["attempts"])
    L += ["", f"Attempt classes on S_H (all validated attempts): {dict(cls_hist)}; attempts = {len(S['attempts'])}.", ""]
    d1 = []
    if a[0] == a[0] and a[0] >= 0.5:
        d1.append("expressivity branch (a ≥ 0.50)")
    if b[0] == b[0] and b[0] >= 0.5:
        d1.append("dose branch (b ≥ 0.50)")
    if not d1:
        d1.append("both branches (neither a nor b ≥ 0.50)")
    if c[0] == c[0] and c[0] >= 0.25:
        d1.append("acceptance-rule branch (c ≥ 0.25), reported alongside")
    L += [f"**D1 outcome: {'; '.join(d1)}** — a {status(a, 0.5)}, b {status(b, 0.5)}, c {status(c, 0.25)}.", ""]
    # ---- F2
    L += ["## F2 — Certificate source decomposition", "", "| arm | axis | n | R_old ok | R_old not run | R_exp ok / R_old fail | R_hint run | R_hint ok / R_exp fail | certified | unresolved | USD R_hint | USD per hint-certified |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in f2["rows"]:
        L.append(f"| {r['arm']} | {r['axis']} | {r['n']} | {r['R_old_ok']} | {r['R_old_not_run']} | {r['R_exp_ok_among_R_old_fail']} | {r['R_hint_run']} | {r['R_hint_ok_among_R_exp_fail']} | {r['certified']} | {r['unresolved']} | {r['usd_R_hint_total']} | {r['usd_R_hint_per_hint_certified']} |")
    L += ["", f"Cost: R_old and R_exp are LLM-free (one env session each, ~1.5–5 s). R_hint spent USD {f2['hint_usd_total']:.2f} in total over the Phase-3 run and certified {f2['n_hint_certified']} candidates that neither replay certified, i.e. USD {f2['hint_usd_total'] / max(f2['n_hint_certified'], 1):.3f} per hint-certified candidate. "
          f"O5H detail: among the {f2['o5h_n']} certified A/T candidates with R_old = 0, the certifying source was {f2['o5h_sources']}; their R_old reasons were {f2['o5h_r_old_reasons']} ('not_run' = the task has no base expert witness).", ""]
    # ---- F3
    L += ["## F3 — Expert A/A on recoverability prefixes", ""]
    if f3:
        L += ["| statistic | value |", "|---|---|"] + [f"| {s['stat']} | {s['value']} |" for s in f3["summary"]]
        d2 = []
        d2.append("a recoverability certificate needs ≥ 3 expert attempts (or a policy-success suffix) per state" if f3["flip"][0] >= 0.10 else "single expert attempt is adequate (flip rate < 0.10)")
        d2.append("bisection stays inadmissible (non-monotone_any3 ≥ 0.20; PREREG O6 stands)" if f3["nonmono_any"][0] >= 0.20 else f"single-run non-monotonicity was expert noise (non-monotone_any3 < 0.20); the O6 non-monotone figure 0.667 in verdict.md is annotated with the de-noised value {fmt(f3['nonmono_any'][0])}")
        d2.append("CHS branch kept (L_any3 ≥ 2 share ≥ 0.50)" if f3["L_any_ge2"][0] >= 0.50 else "CHS branch not supported by L_any3")
        L += ["", f"**D2 outcome: {'; '.join(d2)}** — flip {status(f3['flip'], 0.10)}; non-monotone_any3 {status(f3['nonmono_any'], 0.20)}; L_any3 ≥ 2 {status(f3['L_any_ge2'], 0.50)}. n = {f3['n']} trajectories (35, not 40: see measurement notes).", ""]
    else:
        L += ["F3 not complete at report time.", ""]
    # ---- F4
    cov = f4["coverage"]
    L += ["## F4 — Witness ladder and the expert-failure tasks", "", "| witness | coverage |", "|---|---|"] + [f"| {k} | {rs(v)} |" for k, v in cov.items()]
    for tid, info in f4["four"].items():
        L += ["", f"Task {tid}: p16 = {info['p16']}; candidates = {info['n_candidates']} (H {info['n_H']}); certified = {info['certified']}; certificate sources: {dict(Counter(d['source'] for d in info['detail']))}; R_old reasons: {dict(Counter(d['R_old_reason'] for d in info['detail']))}; policy-success witness available: {info['policy_success_available']}."]
        rp = info.get("R_old_policy") or []
        if rp:
            L.append(f"  R_old_policy (verbatim replay of the shortest successful Pro baseline trajectory, {rp[0]['witness_len']} steps): pass {sum(1 for p in rp if p['R_old_policy_ok'])}/{len(rp)}; fails: {[(p['candidate_id'], p['reason']) for p in rp if not p['R_old_policy_ok']]}.")
    L += ["", "No Phase-3 certificate on these four tasks used a policy-success witness: R_old was skipped ('not_run') because W_base failed, so certification came from R_exp/R_hint; R_old_policy above is the supplementary certificate.", ""]
    # ---- F5
    L += ["## F5 — Flash policy probe", ""]
    if f5:
        L += ["| consumer | zero | edge-low | band | edge-high | saturated |", "|---|---|---|---|---|---|"] + [f"| {r['consumer']} | {r['zero']} | {r['edge-low']} | {r['band']} | {r['edge-high']} | {r['saturated']} |" for r in f5["table"]]
        L += ["", f"Mean success: Pro p16 {fmt(f5['mean_pro'])}, Flash p8 {fmt(f5['mean_flash'])}. zero + edge-low share: Flash {rs(f5['zero_edge_low_flash'])}; Pro {rs(f5['zero_edge_low_pro'])}.", ""]
        d3 = "the zero side has SL targets with Flash as consumer (CHS evaluable in SL)" if f5["zero_edge_low_flash"][0] >= 0.30 else "CHS is evaluated in the RL Study only (Flash zero + edge-low < 0.30)"
        L += [f"**D3 outcome: {d3}** — {status(f5['zero_edge_low_flash'], 0.30)}.", ""]
        if f5["recov"]:
            L += [f"Flash recoverability (single expert attempt, {f5['recov']['n']} failed trajectories from tasks with p8 ≤ 0.2, ≤ 1 per task, seed 20260908): L ≥ 2 share {rs(f5['recov']['L2'])}; non-monotone share {rs(f5['recov']['nonmono'])}.", ""]
        else:
            L += ["Flash recoverability sweep not complete at report time.", ""]
    else:
        L += ["F5 not complete at report time.", ""]
    # ---- F6
    L += ["## F6 — Candidate taxonomy (dose parameters in the wild)", "", f"H arm ({f6['H_n']} candidates) operator types: {f6['H_optype_dist']}.", f"Released arm operator types: {f6['released_optype_dist']}.",
          f"H-arm candidates carrying an explicit numeric parameter other than 0/1: {f6['H_tunable']}/{f6['H_n']} = {f6['H_tunable'] / max(f6['H_n'], 1):.3f}.", "", "### 15 candidates for manual review (random, seed 20260909)", ""]
    for c in f6["review"]:
        L += [f"#### {c['candidate_id']} — task {c['task_id']}, axis {c['axis']}, SR_c {c['SR_c']}, decision {c['decision']}", f"rationale: {c['rationale']}", f"in_env_actions: {c['in_env_actions']}", "```python", c["rules_code"] or "(no rules_code)", "```", ""]
    # ---- F7
    L += ["## F7 — Acceptance discretion in the H arm", "", "| statistic | value |", "|---|---|"] + [f"| {r['stat']} | {r['value']} |" for r in f7["rows"]]
    L += ["", f"Accepted outside [0.4, 0.6] (task-resampled): {rs(f7['outside_rate'])}.", ""]
    # ---- notes
    L += ["## Measurement notes", "",
          "- Sampling seeds: F3 20260907 (stratified: every task with a failed trajectory contributes 1, then second picks in shuffled task order; only 19 tasks have failed trajectories and 3 have a single one, so n = 35 < 40); F5 recoverability 20260908; F6 review list 20260909.",
          "- F3 attempt 1 is the existing Phase-4 value; attempts 2 and 3 are fresh closed-loop expert runs through the same `recover.c_at` path with per-process bridge reuse; resumable by (trajectory_id, t, attempt).",
          "- F5 runs the released Orchestrator baseline path (`_rollout_baseline_k`, K = 8, concurrency 8) on a config differing from corpus_eobs.yaml only in the policy model id (test followup/tests/test_flash_config.py); prompt identity to Phase 1 on task 0 is recorded in LOG.",
          "- The ledger's one truncated line (from the 2026-09-05 kill) is skipped by the readers; nothing was rewritten.", "",
          "## Caveats", "",
          "- Same substrate caveats as E-obs (single benchmark, N = 30, DeepSeek backbones, stochastic handcoded expert, 50-step env cap).",
          "- F1 classes use the App. G band [0.4, 0.6] inclusive on K = 5 (SR ∈ {0, .2, .4, .6, .8, 1}); 'failed attempt' = decision ≠ ACCEPT. Task 17 in S_H had no validated attempt (skipped) and enters no attempt-level rate.",
          "- F5 compares p8 (Flash) with p16 (Pro); the regime bins are the same but the resolutions differ (1/8 vs 1/16)."]
    (OUT / "followup_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))
    print("... wrote", OUT / "followup_report.md")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "", sys.argv[2] if len(sys.argv) > 2 else "")
