"""P4.7 analysis: K2b correction, per-arm env tables, bank counts, H1–H4, K4, unlock, report.md."""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402
from eobs.llm import ledger_totals  # noqa: E402

RES = ROOT / "p4" / "results"
LED = ROOT / "results" / "e1pilot" / "ledger.jsonl"


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def _csv(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p))) if Path(p).exists() else []


def paired(rows: list[dict], a: str, b: str, split: str) -> tuple | None:
    per = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["split"] == split and r["condition"] in (a, b):
            per[r["seed"]][r["condition"]].append(int(r["success"] in ("True", True)))
    d = {s: sum(c[a]) / len(c[a]) - sum(c[b]) / len(c[b]) for s, c in per.items() if c.get(a) and c.get(b)}
    if not d:
        return None
    x = np.array(list(d.values())); idx = np.random.default_rng(20260906).integers(0, len(x), size=(10000, len(x))); m = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), len(d)


def rate(rows: list[dict], cond: str, split: str):
    g = defaultdict(list)
    for r in rows:
        if r["condition"] == cond and r["split"] == split:
            g[r["seed"]].append(r)
    return boot_rate(g, lambda r: r["success"] in ("True", True), lambda r: 1) if g else None


def ps(t) -> str:
    return "n/a" if t is None else f"{fmt(t[0])} [{fmt(t[1])}, {fmt(t[2])}] (n={t[3]})"


def main(prereg_sha: str) -> None:
    led = ledger_totals(LED)
    isat = _csv(RES / "isat_confirm.csv"); nz = _csv(RES / "nzero_envs.csv"); ns = _csv(RES / "nsat_envs.csv"); nsd = _jsonl(RES / "nsat_doses.jsonl")
    om = {r["task_id"]: r for r in _csv(RES / "omega.csv")}
    banks = json.loads((RES / "banks.json").read_text()) if (RES / "banks.json").exists() else {}
    ev = _csv(RES / "evals.csv"); unl = _csv(RES / "unlock.csv")
    p4_usd = sum(v for k, v in led["by_phase"].items() if k.startswith("p4"))
    L = [f"# P4 report — behavioral novelty vs interface difficulty — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
         f"PREREG4 sha `{prereg_sha}`; inputs E1-pilot @ 103b285; policy openai/qwen/qwen3-8b via OpenRouter (provider Alibaba, reasoning off, 0.117/0.455 USD/M); extractor DeepSeek V4 Pro; P4 spend USD {p4_usd:.2f} of 70 ({ {k: round(v, 2) for k, v in led['by_phase'].items() if k.startswith('p4')} }); pilot total USD {led['usd']:.2f} (hard 115 / soft 100).", ""]
    # K2b correction
    prim = [r for r in isat if r.get("primary") == "True"]
    conf = [r for r in isat if r["confirmed"] == "True"]
    g = {r["task_id"]: [r] for r in isat}
    rc = boot_rate(g, lambda r: r["confirmed"] == "True", lambda r: 1) if isat else None
    L += ["## P4.1 I-sat confirmation and K2b correction", "", "| task | env | p̂_8 (P2b) | p̂_8 (new) | p̂_16 | confirmed | ω | primary |", "|---|---|---|---|---|---|---|---|"]
    for r in isat:
        L.append(f"| {r['task_id']} | {r['env']} | {r['p8_p2b']} | {r['p8_new']} | {r['p16']} | {r['confirmed']} | {r['omega']} | {r['primary']} |")
    if isat:
        n_conf_prim = sum(r["confirmed"] == "True" for r in prim)
        k2b_corr = n_conf_prim / 11
        L += ["", f"Confirmed at K = 16: {len(conf)}/{len(isat)} envs = {rs(rc)}; primary confirmed {n_conf_prim}/7. **K2b correction: {'share of the 9 in-band envs confirmed ≥ 0.60 — K2b stands' if rc[0] >= 0.60 else f'confirmed share < 0.60 → K2b restated on the confirmed count: {n_conf_prim}/11 = {fmt(k2b_corr)}'}**", ""]
    # N-zero
    L += ["## P4.2 N-zero (CHS) environments", "", "| task | candidates | visited (t: successes/4) | status | selected t | p̂_12 | staged len |", "|---|---|---|---|---|---|---|"]
    for r in nz:
        L.append(f"| {r['task_id']} | {r['n_candidates']} | {r['visited']} | {r['status']} | {r.get('selected_t', '')} | {r.get('p12', '')} | {r.get('staged_len', '')} |")
    # N-sat
    L += ["", "## P4.3 N-sat environments", "", "| task | family | dose | ω | certified by | p̂ (4→8) | class | p̂_16 | confirmed |", "|---|---|---|---|---|---|---|---|---|"]
    for r in nsd:
        L.append(f"| {r['task_id']} | {r['family']} | {r.get('dose')} | {r.get('omega')} | {r.get('certified_by')} | {r.get('p_hat', '')} | {r.get('class')} | {r.get('p16', '')} | {r.get('confirmed', '')} |")
    fam_lev = defaultdict(set); fam_tasks = defaultdict(set)
    for r in nsd:
        if r.get("rollouts"):
            fam_tasks[r["family"]].add(r["task_id"])
            if r["class"] != "NOEFFECT":
                fam_lev[r["family"]].add(r["task_id"])
    L += ["", "Per-family leverage (tasks moved out of NOEFFECT / tasks reached): " + "; ".join(f"{f}: {len(fam_lev[f])}/{len(fam_tasks[f])}" for f in fam_tasks) + f". Rollouts: {sum(int(r.get('rollouts') or 0) for r in nsd)}; uncertified: {sum(r.get('class') == 'UNCERTIFIED' for r in nsd)}; infeasible/not built: {sum(r.get('class') in ('INFEASIBLE', 'NOT_BUILT') for r in nsd)}; confirmed: {sum(bool(r.get('confirmed')) for r in nsd)}.", ""]
    # banks
    L += ["## P4.4 banks", "", f"{json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ('built', 'items', 'items_matched', 'item_types', 'tasks', 'reason', 'matched_items')} for k, v in banks.items()}, indent=1)}", ""]
    # evals / H
    st = {}
    if ev:
        L += ["## P4.5 held-out evals (released protocol; 30 ID + 30 OOD; 3 same-task replicates)", "", "| condition | ID | OOD |", "|---|---|---|"]
        for c in ("nobank", "orig", "orig_m", "ours", "isat_m", "origc_isat_m", "isat_full", "nsat_m", "origc_nsat_m", "nsat_full", "nzero_m", "origc_nzero_m", "nzero_full"):
            a, b = rate(ev, c, "eval_in_distribution"), rate(ev, c, "eval_out_of_distribution")
            if a or b:
                L.append(f"| {c} | {rs(a) if a else 'n/a'} | {rs(b) if b else 'n/a'} |")
        h1 = paired(ev, "isat_m", "origc_isat_m", "eval_in_distribution"); h2a = paired(ev, "nsat_m", "origc_nsat_m", "eval_in_distribution")
        h2b = paired(ev, "nzero_m", "origc_nzero_m", "eval_in_distribution"); h2b2 = paired(ev, "nzero_m", "nobank", "eval_in_distribution")
        st["H1"] = None if h1 is None else ("holds" if h1[0] <= -0.02 else "fails")
        st["H2a"] = None if h2a is None else ("holds" if h2a[0] >= -0.02 else "fails")
        st["H2b"] = None if h2b is None else ("holds" if (h2b[0] >= -0.02 and h2b2 is not None and h2b2[0] >= 0) else "fails")
        L += ["", f"**H1 (interface replication, I-sat(m) − orig_c(I)(m) ≤ −0.02): {st['H1'] or 'not evaluable'}** — {ps(h1)}; OOD {ps(paired(ev, 'isat_m', 'origc_isat_m', 'eval_out_of_distribution'))}.",
              f"**H2a (saturated-side novelty, N-sat(m) − orig_c(N-sat)(m) ≥ −0.02): {st['H2a'] or 'not evaluable (arm not built)'}** — {ps(h2a)}; OOD {ps(paired(ev, 'nsat_m', 'origc_nsat_m', 'eval_out_of_distribution'))}.",
              f"**H2b (zero-side novelty, N-zero(m) − orig_c(N-zero)(m) ≥ −0.02 and N-zero(m) − nobank ≥ 0): {st['H2b'] or 'not evaluable (arm not built)'}** — vs control {ps(h2b)}; vs nobank {ps(h2b2)}; OOD vs control {ps(paired(ev, 'nzero_m', 'origc_nzero_m', 'eval_out_of_distribution'))}."]
        # H4 descriptive: ID gain vs own control by ω group
        gains = []
        for arm, w in (("isat", "ω≈1 (interface)"), ("nsat", "ω≤0.5 (novel)"), ("nzero", "ω n/a (CHS)")):
            d = paired(ev, f"{arm}_m", f"origc_{arm}_m", "eval_in_distribution")
            if d:
                gains.append(f"{arm} [{w}]: {fmt(d[0])}")
        L += [f"H4 (descriptive): ID gains vs own control — " + "; ".join(gains) + "."]
    # unlock
    if unl:
        L += ["", "## P4.6 unlock on the 8 zero tasks (original env, eval protocol, 8 rollouts each)", "", "| condition | unlocked tasks | unlock share | mean success | per task |", "|---|---|---|---|---|"]
        for r in unl:
            L.append(f"| {r['condition']} | {r['unlocked_tasks']}/{r['n_tasks']} | {r['unlock_share']} | {r['mean_success']} | {r['per_task']} |")
        u = {r["condition"]: float(r["unlock_share"]) for r in unl}
        if "nzero_full" in u and "nobank" in u:
            st["H3"] = "holds" if (u["nzero_full"] >= 0.25 and u["nzero_full"] > u["nobank"]) else "fails"
            L += ["", f"**H3 (unlock ≥ 0.25 and > nobank): {st['H3']}** — N-zero {u['nzero_full']}, nobank {u['nobank']}, orig_c(N-zero) {u.get('origc_nzero_full', 'n/a')}."]
    # K4
    h2a, h2b = st.get("H2a"), st.get("H2b")
    if h2a is None and h2b is None:
        k4 = "not evaluable (neither novelty arm built)"
    elif h2a == "fails" and h2b == "fails":
        k4 = "H2a and H2b both fail → skills from any transformed environment do not help this consumer; the SL line is dead; the RL Study is the downstream evidence"
    elif h2b == "holds" and h2a != "holds":
        k4 = "H2b holds, H2a fails/not built → the SL evidence in the paper is zero-side (CHS) only; the saturated side is evaluated in RL"
    elif h2a == "holds" and h2b != "holds":
        k4 = "H2a holds, H2b fails/not built → the saturated side stays in SL; CHS is evaluated in RL"
    else:
        k4 = "H2a and H2b both hold"
    if st.get("H1") == "fails":
        k4 += " | H1 fails → the interface/novelty distinction is not supported by these data; the K3 result is attributed to bank size/composition"
    L += ["", f"## K4 outcome: **{k4}**", "", "## Measurement notes", "",
          "- Link audit: chain runs under the released runner via a two-env Link subclass (p4/docs/link_audit.md); Chain-3 not buildable with a two-env tree (reported, not substituted).",
          "- Fidelity: Setup lists end with `look`; CHS prefixes reproduce the stored observation at the cut with and without no-op actions (3 trajectories).",
          "- ω replays the policy's own P1 successes verbatim through the released stack; for O-axis envs ω = 1 as expected.",
          "- Held-out evals reuse P3's nobank/orig/orig_m/ours runs; new arms run under the same protocol and seeds; paired differences with 10k task-level bootstrap.",
          "", "## Caveats", "", "- Single benchmark, N = 30 train tasks, 8 zero / 11 saturated tasks, Qwen3-8B via API, small banks (item-matched to the smaller side), one consumer protocol; no method proposals."]
    (RES / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:6])); print("... wrote", RES / "report.md")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
