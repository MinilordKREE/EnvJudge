"""Labels, unlock rates, dose table, A/A, phi, P1-P8 and the GO/CONDITIONAL/NO-GO verdict.

Inputs (results/emin/): witness_probe.csv, rollouts.jsonl, r1.jsonl (optional), ledger.jsonl;
plus the pilot reference cache (H_sub). Outputs (results/emin/): regime_table.csv,
unlock_rates.csv, dose_table.csv, aa_band.csv, phi.csv, supplementary_paired.csv, verdict.md.
All rates carry 10,000-resample task-level bootstrap 95% CIs.
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from emin.data import pool_ids
from emin.settings import config

B = 10_000
RNG = np.random.default_rng(20260905)
ENV_OF_ARM = {"A1": "E_sub", "A1p": "E_sub", "A2": "E_c12", "A3": "E_off", "A4": "E_all", "A5": "E_sub", "A6": "E_all", "A7": "E_sub", "A8": "E_all"}
KEY_OF_ENV = {"E_sub": "sub_raw", "E_c12": "sub_c12", "E_off": "off_raw", "E_all": "off_c12"}


# ---------------------------------------------------------------- helpers
def ci_rate(flags: list[bool]) -> tuple[float, float, float, int]:
    n = len(flags)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0
    x = np.asarray(flags, dtype=float)
    if n == 1:
        return float(x.mean()), float(x.mean()), float(x.mean()), 1
    idx = RNG.integers(0, n, size=(B, n))
    means = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), n


def ci_diff(a: list[bool], b: list[bool]) -> tuple[float, float, float]:
    """difference of two independent group rates, a - b."""
    if not a or not b:
        return float("nan"), float("nan"), float("nan")
    xa, xb = np.asarray(a, float), np.asarray(b, float)
    ma = xa[RNG.integers(0, len(xa), size=(B, len(xa)))].mean(axis=1)
    mb = xb[RNG.integers(0, len(xb), size=(B, len(xb)))].mean(axis=1)
    d = ma - mb
    return float(xa.mean() - xb.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def ci_paired_mean(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return float("nan"), float("nan"), float("nan")
    x = np.asarray(values, float)
    if len(x) == 1:
        return float(x[0]), float(x[0]), float(x[0])
    m = x[RNG.integers(0, len(x), size=(B, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def fmt(x: float, nd: int = 3) -> str:
    return "nan" if x != x else f"{x:.{nd}f}"


def rate_str(r: tuple) -> str:
    m, lo, hi, n = r
    return f"{fmt(m)} [{fmt(lo)}, {fmt(hi)}] (n={n})"


# ---------------------------------------------------------------- loading
def load_witness(path: Path) -> dict[str, dict]:
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows[r["task_id"]] = r
    return rows


def load_hsub(path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))["tasks"]
    out = {}
    for tid, rec in data.items():
        if rec.get("accepted"):
            out[tid] = "pass"
        elif any(h.get("verifier_pass") for h in rec.get("history", [])):
            out[tid] = "restate"
        else:
            out[tid] = "fail"
    return out


def load_rollouts(path: Path) -> dict[tuple[str, str], list[dict]]:
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    if not path.exists():
        return by
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            by[(r["arm"], r["unit_id"])].append(r)
    return by


def phat(rows: list[dict], key: str | None = None) -> float | None:
    if not rows:
        return None
    if key is None:
        return sum(bool(r.get("primary_pass")) for r in rows) / len(rows)
    return sum(r.get("scores", {}).get(key, {}).get("verdict") == "PASS" for r in rows) / len(rows)


def load_r1(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {json.loads(l)["unit_id"]: json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


def ledger_summary(path: Path) -> dict:
    tot = Counter()
    usd = usd_peak = 0.0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            tot[(r.get("arm"), r.get("model"))] += 1
            usd += float(r.get("usd", 0.0))
            usd_peak += float(r.get("usd_peak_bound", 0.0))
    return {"calls": sum(tot.values()), "usd": usd, "usd_peak_bound": usd_peak, "by_arm_model": dict(tot)}


# ---------------------------------------------------------------- core
def label_for(w: dict | None, hsub: str | None, p0: float | None) -> str:
    if p0 is None:
        return "n/a"
    if p0 > 0:
        return "solved"
    if w is None or str(w.get("W_pass")) != "True":
        return "L0"
    if hsub == "fail":
        return "L1"
    if hsub == "pass":
        return "L2"
    return "L?"


def main() -> None:
    cfg = config()
    rd = Path(cfg["results_dir"])
    ids = pool_ids()
    witness = load_witness(rd / "witness_probe.csv") if (rd / "witness_probe.csv").exists() else {}
    hsub = load_hsub(cfg["reference_cache"])
    roll = load_rollouts(rd / "rollouts.jsonl")
    r1 = load_r1(rd / "r1.jsonl")
    arms = list(cfg["arms"].keys())
    arms_present = {a for a in arms if any((a, t) in roll for t in ids)}
    n_roll = {a: sum(len(roll.get((a, t), [])) for t in ids) for a in arms}

    # per task table
    P = {a: {t: phat(roll.get((a, t), [])) for t in ids} for a in arms}
    lab_pro = {t: label_for(witness.get(t), hsub.get(t), P["A1"][t]) for t in ids}
    lab_flash = {t: label_for(witness.get(t), hsub.get(t), P["A7"][t]) for t in ids}
    lab_pro_aa = {t: label_for(witness.get(t), hsub.get(t), P["A1p"][t]) for t in ids}

    regime_rows = []
    for t in ids:
        w = witness.get(t, {})
        rr = r1.get(t)
        row = {"task": t, "instruction_type": w.get("instruction_type", ""), "W_pass": w.get("W_pass", ""), "W_a_reason": w.get("W_a_reason", ""),
               "h": w.get("h", ""), "n_cells": w.get("n_cells", ""), "n_formula": w.get("n_formula", ""),
               "sub_recalc_vs_raw": w.get("sub_recalc_vs_raw", ""), "H_sub": hsub.get(t, "none"),
               "H_off": ("" if rr is None else ("pass" if rr.get("H_off_pass") else "fail")),
               "H_off_authentic": ("" if rr is None else rr.get("H_off_authentic")),
               "label_pro": lab_pro[t], "label_flash": lab_flash[t], "label_pro_AA": lab_pro_aa[t]}
        for a in arms:
            row[f"p_{a}"] = "" if P[a][t] is None else f"{P[a][t]:.3f}"
            row[f"n_{a}"] = len(roll.get((a, t), []))
        # paired re-scoring of A1 responses under the four env verdicts (supplementary)
        for env, key in KEY_OF_ENV.items():
            v = phat(roll.get(("A1", t), []), key)
            row[f"A1_as_{env}"] = "" if v is None else f"{v:.3f}"
        regime_rows.append(row)
    with open(rd / "regime_table.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(regime_rows[0].keys()))
        wtr.writeheader()
        wtr.writerows(regime_rows)

    # groups (Pro labels from A1; Flash labels from A7)
    def group(labels: dict[str, str], name: str) -> list[str]:
        return [t for t in ids if labels[t] == name]

    zero_pro = [t for t in ids if P["A1"][t] == 0.0]
    zero_flash = [t for t in ids if P["A7"][t] == 0.0]
    groups_pro = {L: group(lab_pro, L) for L in ("L0", "L1", "L2", "L?")}
    groups_flash = {L: group(lab_flash, L) for L in ("L0", "L1", "L2", "L?")}

    # A/A
    aa_rows = []
    f_aa = ci_rate([P["A1p"][t] > 0 for t in zero_pro if P["A1p"][t] is not None]) if "A1p" in arms_present else (float("nan"),) * 3 + (0,)
    zero_p = [t for t in ids if P["A1p"][t] == 0.0]
    f_aa_rev = ci_rate([P["A1"][t] > 0 for t in zero_p]) if "A1p" in arms_present else (float("nan"),) * 3 + (0,)
    flips = [t for t in ids if P["A1"][t] is not None and P["A1p"][t] is not None and ((P["A1"][t] == 0) != (P["A1p"][t] == 0))]
    label_flip = [t for t in ids if lab_pro[t] != lab_pro_aa[t] and P["A1"][t] is not None and P["A1p"][t] is not None]
    deltas = [abs(P["A1"][t] - P["A1p"][t]) for t in ids if P["A1"][t] is not None and P["A1p"][t] is not None]
    for a in arms:
        if a not in arms_present:
            continue
        ps = [P[a][t] for t in ids if P[a][t] is not None]
        band = [2 / 8 <= p <= 6 / 8 for p in ps]
        aa_rows.append({"arm": a, "env": ENV_OF_ARM[a], "consumer": cfg["arms"][a]["consumer"], "agent": cfg["arms"][a]["agent"], "rollouts": n_roll[a],
                        "tasks": len(ps), "mean_p": fmt(float(np.mean(ps))) if ps else "", "zero_share": fmt(float(np.mean([p == 0 for p in ps]))) if ps else "",
                        "full_share": fmt(float(np.mean([p == 1 for p in ps]))) if ps else "", "band_2_6_share": fmt(float(np.mean(band))) if ps else ""})
    aa_summary = {"f_AA_unlock_given_zero_A1": f_aa, "f_AA_reverse": f_aa_rev, "zero_status_flips": len(flips), "label_flips": len(label_flip),
                  "abs_delta_mean": float(np.mean(deltas)) if deltas else float("nan"),
                  "abs_delta_quantiles": [float(np.percentile(deltas, q)) for q in (50, 75, 90, 100)] if deltas else [],
                  "abs_delta_hist": dict(Counter(f"{d:.3f}" for d in deltas))}
    with open(rd / "aa_band.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(aa_rows[0].keys()) if aa_rows else ["arm"])
        wtr.writeheader()
        wtr.writerows(aa_rows)

    # unlock rates by label x env x consumer
    unlock_rows = []
    unlock: dict[tuple[str, str], tuple] = {}     # (label, arm) -> ci tuple
    unlock_flags: dict[tuple[str, str], list[bool]] = {}
    for consumer, groups, zero in (("pro", groups_pro, zero_pro), ("flash", groups_flash, zero_flash)):
        for a in arms:
            if cfg["arms"][a]["consumer"] != consumer or cfg["arms"][a]["agent"] != "parent_minus" or a in ("A1", "A1p", "A7"):
                continue
            if a not in arms_present:
                continue
            for L, members in list(groups.items()) + [("all_zero", zero)]:
                flags = [P[a][t] > 0 for t in members if P[a][t] is not None]
                r = ci_rate(flags)
                unlock[(L, a)] = r
                unlock_flags[(L, a)] = flags
                unlock_rows.append({"consumer": consumer, "label": L, "env": ENV_OF_ARM[a], "arm": a, "n": r[3], "unlocked": int(sum(flags)),
                                    "rate": fmt(r[0]), "ci_lo": fmt(r[1]), "ci_hi": fmt(r[2]),
                                    "rate_minus_fAA": fmt(r[0] - f_aa[0]) if f_aa[0] == f_aa[0] else ""})
    with open(rd / "unlock_rates.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["consumer", "label", "env", "arm", "n", "unlocked", "rate", "ci_lo", "ci_hi", "rate_minus_fAA"])
        wtr.writeheader()
        wtr.writerows(unlock_rows)

    # dose table (Pro)
    dose_rows = []
    for a in ("A2", "A3", "A4"):
        if a not in arms_present:
            continue
        rec = {"env": ENV_OF_ARM[a], "arm": a}
        for L in ("L1", "L2", "L?", "L0", "all_zero"):
            r = unlock.get((L, a))
            rec[f"unlock_{L}"] = "" if r is None else f"{fmt(r[0])} [{fmt(r[1])}, {fmt(r[2])}] n={r[3]}"
        dose_rows.append(rec)
    if ("L1", "A3") in unlock and ("L1", "A4") in unlock and unlock[("L1", "A4")][0] > 0:
        dose_rows.append({"env": "c3_alone_share_of_L1_unlock", "arm": "A3/A4", "unlock_L1": fmt(unlock[("L1", "A3")][0] / unlock[("L1", "A4")][0])})
    if ("L1", "A2") in unlock and ("L1", "A4") in unlock and unlock[("L1", "A4")][0] > 0:
        dose_rows.append({"env": "c12_alone_share_of_L1_unlock", "arm": "A2/A4", "unlock_L1": fmt(unlock[("L1", "A2")][0] / unlock[("L1", "A4")][0])})
    with open(rd / "dose_table.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["env", "arm", "unlock_L1", "unlock_L2", "unlock_L?", "unlock_L0", "unlock_all_zero"])
        wtr.writeheader()
        wtr.writerows(dose_rows)

    # phi
    phi_rows = []
    phi = None
    common = [t for t in ids if all(P[a][t] is not None for a in ("A1", "A4", "A5"))]
    if common:
        G = ci_paired_mean([P["A5"][t] - P["A1"][t] for t in common])
        Gp = ci_paired_mean([P["A4"][t] - P["A1"][t] for t in common])
        g = np.asarray([P["A5"][t] - P["A1"][t] for t in common]); gp = np.asarray([P["A4"][t] - P["A1"][t] for t in common])
        idx = RNG.integers(0, len(common), size=(B, len(common)))
        gm, gpm = g[idx].mean(axis=1), gp[idx].mean(axis=1)
        ratios = gpm[gm > 0] / gm[gm > 0]
        phi = (float(Gp[0] / G[0]) if G[0] > 0 else float("nan"), float(np.percentile(ratios, 2.5)) if len(ratios) else float("nan"),
               float(np.percentile(ratios, 97.5)) if len(ratios) else float("nan"), int((gm > 0).sum()))
        phi_rows.append({"quantity": "G = mean p(A5 parent,E_sub) - mean p(A1 parent-,E_sub)", "value": fmt(G[0]), "ci_lo": fmt(G[1]), "ci_hi": fmt(G[2]), "n_tasks": len(common)})
        phi_rows.append({"quantity": "G' = mean p(A4 parent-,E_all) - mean p(A1)", "value": fmt(Gp[0]), "ci_lo": fmt(Gp[1]), "ci_hi": fmt(Gp[2]), "n_tasks": len(common)})
        phi_rows.append({"quantity": "phi = G'/G (CI over resamples with G>0)", "value": fmt(phi[0]), "ci_lo": fmt(phi[1]), "ci_hi": fmt(phi[2]), "n_tasks": phi[3]})
        if all(P["A6"][t] is not None for t in common):
            d1 = ci_paired_mean([P["A6"][t] - P["A4"][t] for t in common])
            d2 = ci_paired_mean([P["A6"][t] - P["A5"][t] for t in common])
            phi_rows.append({"quantity": "A6 - A4 (skill increment on top of Contract)", "value": fmt(d1[0]), "ci_lo": fmt(d1[1]), "ci_hi": fmt(d1[2]), "n_tasks": len(common)})
            phi_rows.append({"quantity": "A6 - A5 (Contract increment on top of skill)", "value": fmt(d2[0]), "ci_lo": fmt(d2[1]), "ci_hi": fmt(d2[2]), "n_tasks": len(common)})
    for a in arms:
        if a in arms_present:
            m = ci_paired_mean([P[a][t] for t in ids if P[a][t] is not None])
            phi_rows.append({"quantity": f"mean p({a} {cfg['arms'][a]['agent']},{ENV_OF_ARM[a]},{cfg['arms'][a]['consumer']})", "value": fmt(m[0]), "ci_lo": fmt(m[1]), "ci_hi": fmt(m[2]), "n_tasks": n_roll[a] // 8 if n_roll[a] else 0})
    with open(rd / "phi.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["quantity", "value", "ci_lo", "ci_hi", "n_tasks"])
        wtr.writeheader()
        wtr.writerows(phi_rows)

    # supplementary: paired re-scoring of A1 responses (same programs, four env verdicts)
    supp_rows = []
    if "A1" in arms_present:
        for env, key in KEY_OF_ENV.items():
            pe = {t: phat(roll.get(("A1", t), []), key) for t in ids}
            rec = {"env_verdict_on_A1_responses": env, "mean_p": fmt(float(np.mean([pe[t] for t in ids if pe[t] is not None])))}
            for L, members in list(groups_pro.items()) + [("all_zero", zero_pro)]:
                r = ci_rate([pe[t] > 0 for t in members if pe[t] is not None])
                rec[f"unlock_{L}"] = f"{fmt(r[0])} [{fmt(r[1])}, {fmt(r[2])}] n={r[3]}"
            supp_rows.append(rec)
        with open(rd / "supplementary_paired.csv", "w", newline="", encoding="utf-8") as fh:
            wtr = csv.DictWriter(fh, fieldnames=list(supp_rows[0].keys()))
            wtr.writeheader()
            wtr.writerows(supp_rows)

    # reasons per arm (primary)
    reasons = {a: Counter(r.get("primary_reason", "?") for t in ids for r in roll.get((a, t), [])) for a in arms if a in arms_present}
    extraction = {a: Counter((r.get("raw_extraction", "?") == "ok", r.get("c1_extraction", "?") == "ok", bool(r.get("c2_fired"))) for t in ids for r in roll.get((a, t), [])) for a in arms if a in arms_present}

    # ------------------------------------------------------------ predictions
    V: list[str] = []
    verdicts: dict[str, str] = {}

    def judge(name: str, cond_point: bool | None, cond_ci: bool | None, text: str) -> None:
        if cond_point is None:
            status = "inconclusive"
        else:
            status = ("supported" if cond_point else "contradicted") + (" (CI-decisive)" if cond_ci else " (CI not decisive)")
        verdicts[name] = status
        V.append(f"### {name}: {status}\n\n{text}\n")

    nz = len(zero_pro)
    shares = {L: ci_rate([lab_pro[t] == L for t in zero_pro]) for L in ("L0", "L1", "L2", "L?")}
    if "A1" in arms_present and nz:
        ok = shares["L1"][0] >= 0.15 and shares["L2"][0] >= 0.15
        ci_ok = shares["L1"][1] >= 0.15 and shares["L2"][1] >= 0.15
        judge("P1 mixture (L1, L2 each >= 15% of p0=0 tasks)", ok, ci_ok,
              f"p0=0 tasks (A1, Pro): {nz}/{len(ids)}. Shares: " + "; ".join(f"{L} {rate_str(shares[L])}" for L in shares) +
              f". Counts: {dict(Counter(lab_pro[t] for t in zero_pro))}.")
    else:
        judge("P1 mixture", None, None, "A1 not run.")

    def p2_block(name: str, arm_all: str, groups, f_aa_tuple, consumer) -> tuple:
        u1, u2 = unlock.get(("L1", arm_all)), unlock.get(("L2", arm_all))
        if u1 is None or u2 is None or u1[3] == 0 or u2[3] == 0:
            judge(name, None, None, f"{arm_all} not run or a label group is empty (L1 n={0 if u1 is None else u1[3]}, L2 n={0 if u2 is None else u2[3]}).")
            return None
        d = ci_diff(unlock_flags[("L1", arm_all)], unlock_flags[("L2", arm_all)])
        f = f_aa_tuple[0] if f_aa_tuple[0] == f_aa_tuple[0] else 0.0
        ok = (d[0] >= 0.25) and (u1[0] >= 0.40) and ((u1[0] - f) >= 0.40) and ((d[0]) >= 0.25)
        ci_ok = (d[1] >= 0.25) and (u1[1] >= 0.40)
        judge(name, ok, ci_ok,
              f"{consumer} E_all ({arm_all}): unlock(L1) = {rate_str(u1)}, unlock(L2) = {rate_str(u2)}, difference = {fmt(d[0])} [{fmt(d[1])}, {fmt(d[2])}]. "
              f"f_AA (spurious unlock of an identical env) = {fmt(f)}; unlock(L1) - f_AA = {fmt(u1[0] - f)}; unlock(L2) - f_AA = {fmt(u2[0] - f)}. "
              f"Thresholds: difference >= 0.25 and unlock(L1) >= 0.40 (after subtracting f_AA).")
        return u1, u2, d

    p2 = p2_block("P2 interaction (Pro): unlock(L1) - unlock(L2) >= 0.25 and unlock(L1) >= 0.40 in E_all", "A4", groups_pro, f_aa, "Pro")

    if all(a in arms_present for a in ("A2", "A3", "A4")) and ("L1", "A4") in unlock and unlock[("L1", "A4")][3]:
        u2_, u3_, u4_ = unlock[("L1", "A2")], unlock[("L1", "A3")], unlock[("L1", "A4")]
        ok = u3_[0] > 0 and u2_[0] > 0 and u4_[0] >= max(u3_[0], u2_[0])
        ci_ok = u3_[1] > 0 and u2_[1] > 0
        judge("P3 dose: unlock(L1) > 0 in both E_off and E_c12; E_all >= max", ok, ci_ok,
              f"unlock(L1): E_c12 (A2) = {rate_str(u2_)}; E_off (A3) = {rate_str(u3_)}; E_all (A4) = {rate_str(u4_)}. "
              f"c3-alone share of the E_all L1 unlock = {fmt(u3_[0] / u4_[0]) if u4_[0] > 0 else 'nan'}; c1+c2-alone share = {fmt(u2_[0] / u4_[0]) if u4_[0] > 0 else 'nan'}.")
    else:
        judge("P3 dose", None, None, "A2/A3/A4 not all run.")

    solved = [t for t in ids if P["A1"][t] is not None and P["A1"][t] >= 0.875]
    if "A4" in arms_present and solved and all(P["A4"][t] is not None for t in solved):
        r = ci_rate([P["A4"][t] >= 0.75 for t in solved])
        judge("P4 harmlessness: tasks with p0 >= 0.875 keep p >= 0.75 in E_all for >= 90%", r[0] >= 0.9, r[1] >= 0.9,
              f"Tasks with p0 >= 0.875 in A1: {len(solved)}. Share with p(A4) >= 0.75: {rate_str(r)}. "
              f"Mean p over these tasks: A1 {fmt(float(np.mean([P['A1'][t] for t in solved])))} -> A4 {fmt(float(np.mean([P['A4'][t] for t in solved])))}.")
    else:
        judge("P4 harmlessness", None, None, "A4 not run or no task with p0 >= 0.875.")

    f_aa_flash = ci_rate([P["A8"][t] > 0 for t in zero_flash if P["A8"][t] is not None])  # no Flash A/A arm; reported for transparency only
    p5 = None
    if "A7" in arms_present and "A8" in arms_present and ("L1", "A8") in unlock and ("L2", "A8") in unlock and unlock[("L1", "A8")][3] and unlock[("L2", "A8")][3]:
        u1f, u2f = unlock[("L1", "A8")], unlock[("L2", "A8")]
        df = ci_diff(unlock_flags[("L1", "A8")], unlock_flags[("L2", "A8")])
        direction = df[0] > 0
        cmp_ = None
        if ("L1", "A4") in unlock and unlock[("L1", "A4")][3]:
            cmp_ = ci_diff(unlock_flags[("L1", "A8")], unlock_flags[("L1", "A4")])
        ok = direction and (cmp_ is not None and cmp_[0] >= 0)
        ci_ok = df[1] > 0 and (cmp_ is not None and cmp_[1] >= 0)
        judge("P5 consumer (Flash): P2 direction holds and unlock_Flash(L1) >= unlock_Pro(L1)", ok, ci_ok,
              f"Flash labels from A7 (p0=0 tasks: {len(zero_flash)}; L1 n={u1f[3]}, L2 n={u2f[3]}). E_all (A8): unlock(L1) = {rate_str(u1f)}, unlock(L2) = {rate_str(u2f)}, "
              f"difference = {fmt(df[0])} [{fmt(df[1])}, {fmt(df[2])}]. unlock_Flash(L1) - unlock_Pro(L1) = "
              + ("n/a" if cmp_ is None else f"{fmt(cmp_[0])} [{fmt(cmp_[1])}, {fmt(cmp_[2])}]") + ". No Flash A/A arm was pre-registered, so no f_AA subtraction for Flash.")
        p5 = ok
    else:
        judge("P5 consumer (Flash)", None, None, "A7/A8 not run or a Flash label group is empty.")

    if phi is not None:
        judge("P6 phi = G'/G >= 0.6", phi[0] >= 0.6 if phi[0] == phi[0] else None, phi[1] >= 0.6 if phi[1] == phi[1] else None,
              "; ".join(f"{r['quantity']} = {r['value']} [{r['ci_lo']}, {r['ci_hi']}]" for r in phi_rows[:5]) + ".")
    else:
        judge("P6 phi", None, None, "A1/A4/A5 not all run.")

    if "A1" in arms_present and nz:
        share_l1 = shares["L1"]
        judge("P7 baseline misrouting: designer rule sr==0 -> SKIP skips every p0=0 task; L1 share among them", True, True,
              f"envharness corpus.yaml Phase 1: 'baseline_sr == 0.0: SKIP'. All {nz} p0=0 tasks are skipped by construction. "
              f"Skipped L1 share = |L1|/|p0=0| = {shares['L1'][3] and int(round(share_l1[0] * nz))}/{nz} = {rate_str(share_l1)}; skipped L2 share = {rate_str(shares['L2'])}.")
    else:
        judge("P7 baseline misrouting", None, None, "A1 not run.")

    if witness:
        hp = ci_rate([int(witness[t]["h"] or 0) > 0 for t in ids if t in witness])
        h_all = [int(r["h"] or 0) > 0 for r in witness.values() if r.get("split") != "excluded" and r.get("h") not in ("", None)]
        ha = ci_rate(h_all)
        judge("P8 witness bias: h(t) > 0 for >= 10% of pool 76", hp[0] >= 0.10, hp[1] >= 0.10,
              f"pool 76: {rate_str(hp)}; all evaluable verified_400 (396): {rate_str(ha)}. Substrate path rejects recalc(golden) vs raw golden "
              f"(sub_recalc_vs_raw == FAIL) for {sum(witness[t].get('sub_recalc_vs_raw') == 'FAIL' for t in ids if t in witness)}/{len(ids)} pool tasks; "
              f"W fails (L0 candidates) for {sum(str(witness[t].get('W_pass')) != 'True' for t in ids if t in witness)}/{len(ids)} pool tasks.")
    else:
        judge("P8 witness bias", None, None, "witness_probe.csv missing.")

    # ------------------------------------------------------------ overall verdict
    def is_supported(name_prefix: str) -> bool | None:
        for k, v in verdicts.items():
            if k.startswith(name_prefix):
                return None if v == "inconclusive" else v.startswith("supported")
        return None

    s1, s2, s5 = is_supported("P1"), is_supported("P2"), is_supported("P5")
    s4 = is_supported("P4")
    if None in (s1, s2, s5):
        overall = "INCONCLUSIVE (arms missing)"
    elif s1 and s2 and s5:
        overall = "GO"
    elif s1 and not s2:
        overall = "CONDITIONAL"
    elif (not s1) and (not s2):
        overall = "NO-GO"
    else:
        overall = "CONDITIONAL (P1 and P2 hold but P5 direction does not; section 3 does not name this cell -- reported, not decided)"
    if s4 is False:
        overall += " + implementation-suspect (P4 failed: Contract harmed solved tasks)"

    led = ledger_summary(rd / "ledger.jsonl")
    lines = [f"# E-min verdict — generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", "",
             f"Pre-registration: `PREREG.md` @ git sha `{cfg['prereg_git_sha']}`. Rollouts per arm: " + ", ".join(f"{a}={n_roll[a]}" for a in arms) + ".",
             f"Spend so far: {led['calls']} API calls, USD {led['usd']:.2f} at the applicable tariff (USD {led['usd_peak_bound']:.2f} at the peak bound). Budget: hard 20 / soft 12.", "",
             f"## Overall (section 3 rule): **{overall}**", "",
             "Rule: GO = P1 ∧ P2(Pro) ∧ P5-direction; CONDITIONAL = P1 ∧ ¬P2; NO-GO = ¬P1 ∧ ¬P2; P4 failure adds 'implementation-suspect'. "
             "Bold is used only for the overall call; every rate below carries a 10,000-resample task-level bootstrap 95% CI, and 'CI-decisive' means the CI excludes the threshold.", "",
             "## Predictions", ""] + V + [
             "## Regime counts (Pro labels from A1)", "",
             f"p0=0: {nz}; labels: {dict(Counter(lab_pro[t] for t in ids))}", "",
             f"Flash (A7) p0=0: {len(zero_flash)}; labels: {dict(Counter(lab_flash[t] for t in ids))}", "",
             "## A/A (A1 vs A1', parent⁻, E_sub, Pro)", "",
             f"f_AA = P(p(A1') > 0 | p(A1) = 0) = {rate_str(f_aa)}; reverse = {rate_str(f_aa_rev)}; zero-status flips = {len(flips)}/{len(ids)}; regime-label flips = {len(label_flip)}/{len(ids)}; "
             f"mean |Δp| = {fmt(aa_summary['abs_delta_mean'])}; |Δp| quantiles (50/75/90/100) = {[fmt(q) for q in aa_summary['abs_delta_quantiles']]}; histogram = {aa_summary['abs_delta_hist']}.", "",
             "## Per-arm summary (aa_band.csv)", "", "| arm | agent | env | consumer | rollouts | mean p | zero share | full share | band [2..6]/8 share |", "|---|---|---|---|---|---|---|---|---|"]
    for r in aa_rows:
        lines.append(f"| {r['arm']} | {r['agent']} | {r['env']} | {r['consumer']} | {r['rollouts']} | {r['mean_p']} | {r['zero_share']} | {r['full_share']} | {r['band_2_6_share']} |")
    lines += ["", "## Unlock rates (unlock_rates.csv)", "", "| consumer | label | env | arm | n | unlocked | rate [CI] | rate − f_AA |", "|---|---|---|---|---|---|---|---|"]
    for r in unlock_rows:
        lines.append(f"| {r['consumer']} | {r['label']} | {r['env']} | {r['arm']} | {r['n']} | {r['unlocked']} | {r['rate']} [{r['ci_lo']}, {r['ci_hi']}] | {r['rate_minus_fAA']} |")
    lines += ["", "## Dose table (dose_table.csv)", ""]
    for r in dose_rows:
        lines.append("- " + "; ".join(f"{k}: {v}" for k, v in r.items() if v))
    lines += ["", "## φ (phi.csv)", ""] + [f"- {r['quantity']} = {r['value']} [{r['ci_lo']}, {r['ci_hi']}] (n={r['n_tasks']})" for r in phi_rows]
    lines += ["", "## Supplementary (not pre-registered): paired re-scoring of the A1 responses under the four env verdicts", "",
              "The prompt does not depend on the env, so every A1 response can be re-scored under E_sub/E_c12/E_off/E_all; this is a paired estimate of the same quantities the independent arms A2–A4 estimate.", ""]
    for r in supp_rows:
        lines.append("- " + "; ".join(f"{k}: {v}" for k, v in r.items()))
    lines += ["", "## Primary failure reasons per arm", ""]
    for a, c in reasons.items():
        lines.append(f"- {a}: {dict(c.most_common())}")
    lines += ["", "## Extraction / c2 activity per arm (raw_extraction_ok, c1_ok, c2_fired) counts", ""]
    for a, c in extraction.items():
        lines.append(f"- {a}: {dict(c)}")
    if r1:
        lines += ["", "## R1 (answer-conditioned regeneration under E_all on L1 tasks)", "",
                  f"tasks {len(r1)}; H_off pass {sum(bool(v.get('H_off_pass')) for v in r1.values())}; authentic {sum(bool(v.get('H_off_authentic')) for v in r1.values())}; "
                  f"attempt histogram {dict(Counter(v.get('n_attempts') for v in r1.values()))}"]
    lines += ["", "## Caveats (section 7 of the brief)", "",
              "- Single benchmark, single-program tasks (short horizon), self-written parent skill; temperature 0.7 is not comparable with the earlier temperature-0 protocol.",
              "- L1/L2 depend on the substrate-path answer-condition cache (H_sub); R1 supplies part of the official-path labelling (H_off); the full witness regeneration protocol is left to M4.",
              "- c2 ('save on exception') wraps the agent program; it is not a repair of environment state. Its contribution is reported separately (dose table, c2_fired counts).",
              "- ALFWorld witness false-positive tests are outside E-min (M1/M4).",
              "- Deviations and nulls: see LOG.md (LibreOffice via extracted AppImage instead of apt; vendored evaluator fetched from GitHub; venv additions)."]
    (rd / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"... wrote {rd / 'verdict.md'} and CSVs")


if __name__ == "__main__":
    main()
