"""E3-SL tables (PREREG9 Addendum SL) -> experiments/alfworld_e3/results/e3_sl.md and
e3_sl_data.json. Every number comes from runs/e3sl-banks (banks_e3.json) and runs/e3sl-eval
(the released eval cells) through this script.

Sections: the E3-SL verdict; the item-matched table (A_lf, G_lf, R_lf, O; induction 1 / 2 / mean;
N, placebo; ID / OOD; per seed); paired per-episode differences (induction-averaged) vs G_lf, R_lf,
O, N and placebo with 10k bootstrap CIs; full-bank rows; released-cascade rows; item counts and
induction types per bank; spend by budget and phase; incidents.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3sl  # the SL driver: layout, conditions, spend

RUNS = e3sl.RUNS
EVAL = e3sl.EVAL
BANKS = e3sl.BANKS
RESULTS = e3sl.RESULTS
SPLITS = tuple(e3sl.SPLITS)
BOOT = 10_000
INDIST = 3.0  # points: gaps within this are reported as indistinguishable

Cells = dict[str, dict[str, dict[int, list[dict[str, Any]]]]]


def fmt(x: float | None, nd: int = 1) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "-"
    return f"{x:.{nd}f}"


# ---------------------------------------------------------------------------- cells
def eval_cells() -> Cells:
    """{condition: {split: {seed block: [records]}}} from runs/e3sl-eval."""
    out: Cells = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    if not EVAL.exists():
        return {}
    for d in sorted(EVAL.iterdir()):
        m = re.match(r"(.+)-seeds-(\d+)(-resume-\d+)?$", d.name)
        if not m or not d.is_dir():
            continue
        cond, start = m.group(1), int(m.group(2))
        block = (start // 1000) * 1000
        for f in sorted(d.glob(f"round*/{cond}_eval_*.jsonl")):
            split = f.stem.rsplit("_eval_", 1)[1]
            out[cond][split][block].extend(r for r in e3sl.e3.jsonl(f) if not r.get("error"))
    return {c: {s: dict(b) for s, b in sp.items()} for c, sp in out.items()}


def rate(recs: list[dict[str, Any]]) -> tuple[float, int]:
    n = len(recs)
    return (100 * sum(1 for r in recs if r.get("success")) / n if n else float("nan")), n


def episode_values(cells: Cells, cond: str, split: str) -> dict[tuple[int, int], float]:
    """(seed block, episode seed) -> success (0/1) for one condition."""
    out: dict[tuple[int, int], float] = {}
    for block, recs in cells.get(cond, {}).get(split, {}).items():
        for r in recs:
            out[(block, int(r["seed"]))] = float(bool(r.get("success")))
    return out


def averaged(cells: Cells, conds: list[str], split: str) -> dict[tuple[int, int], float]:
    """Per-episode mean over the inductions of a bank (an episode counts only when every
    induction has it)."""
    per = [episode_values(cells, c, split) for c in conds if c in cells]
    if not per or len(per) != len(conds):
        return {}
    keys = set(per[0])
    for p in per[1:]:
        keys &= set(p)
    return {k: sum(p[k] for p in per) / len(per) for k in keys}


def diff_stats(
    a: dict[tuple[int, int], float], b: dict[tuple[int, int], float], rng: random.Random
) -> dict[str, Any]:
    keys = sorted(set(a) & set(b))
    n = len(keys)
    if not n:
        return {"n": 0}
    x = np.array([a[k] for k in keys])
    y = np.array([b[k] for k in keys])
    d = x - y
    gen = np.random.default_rng(rng.randrange(2**32))
    idx = gen.integers(0, n, size=(BOOT, n))
    boots = np.sort(100 * d[idx].mean(axis=1))
    diff = float(100 * d.mean())
    lo, hi = float(boots[int(0.025 * BOOT)]), float(boots[int(0.975 * BOOT)])
    return {
        "n": n,
        "diff": diff,
        "ci95": [lo, hi],
        "excludes_zero": bool(lo > 0 or hi < 0),
        "indistinguishable": abs(diff) <= INDIST,
        "a_mean": float(100 * x.mean()),
        "b_mean": float(100 * y.mean()),
    }


def diff_cell(d: dict[str, Any]) -> str:
    if not d.get("n"):
        return "-"
    tag = " ≈" if d["indistinguishable"] else (" *" if d["excludes_zero"] else "")
    return f"{d['diff']:+.1f} [{d['ci95'][0]:+.1f}, {d['ci95'][1]:+.1f}]{tag}"


def per_seed(cells: Cells, cond: str, split: str) -> str:
    by = cells.get(cond, {}).get(split, {})
    return " / ".join(fmt(rate(by[s])[0]) for s in sorted(by)) or "-"


def bank_rows(cells: Cells, label: str, conds: list[str]) -> list[str]:
    """Rows for one bank: each induction and the mean of the inductions."""
    rows = []
    means: dict[str, list[float]] = defaultdict(list)
    for i, c in enumerate(conds, 1):
        parts = []
        for split in SPLITS:
            by = cells.get(c, {}).get(split, {})
            pooled = [r for s in sorted(by) for r in by[s]]
            p, n = rate(pooled)
            if n:
                means[split].append(p)
            parts.append(f"{fmt(p)} (n={n}) [{per_seed(cells, c, split)}]")
        rows.append(f"| {label} | i{i} | {parts[0]} | {parts[1]} |")
    if len(conds) > 1:
        parts = [fmt(sum(means[s]) / len(means[s])) if means[s] else "-" for s in SPLITS]
        rows.append(f"| **{label}** | mean | **{parts[0]}** | **{parts[1]}** |")
    return rows


# ---------------------------------------------------------------------------- spend, incidents
def spend() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for top in sorted(RUNS.glob("e3sl-*")):
        if not top.is_dir():
            continue
        for d in [top, *sorted(p for p in top.rglob("*") if p.is_dir())]:
            files = (
                [d / "ledger.jsonl"]
                if (d / "ledger.jsonl").exists()
                else sorted(d.glob("ledger.*.jsonl"))
            )
            for f in files:
                for r in e3sl.e3.jsonl(f):
                    if r.get("event") == "call":
                        out[top.name][f"{r.get('budget')}/{r.get('phase')}"] += float(
                            r.get("usd") or 0.0
                        )
    return {k: dict(v) for k, v in out.items()}


def incidents() -> dict[str, Any]:
    out: dict[str, Any] = {
        "guard_incidents": len(e3sl.e3.jsonl(EVAL / "guard_incidents.jsonl")),
        "retries_429": 0,
        "retries_other": 0,
        "errored_episodes": 0,
    }
    for top in RUNS.glob("e3sl-*"):
        if not top.is_dir():
            continue
        for f in top.rglob("ledger*.jsonl"):
            if f.name != "ledger.jsonl" and (f.parent / "ledger.jsonl").exists():
                continue
            for r in e3sl.e3.jsonl(f):
                if r.get("event") == "infra_retry":
                    out["retries_429" if r.get("status_code") == 429 else "retries_other"] += 1
    if EVAL.exists():
        for f in EVAL.rglob("*.jsonl.with_errors"):
            out["errored_episodes"] += sum(1 for r in e3sl.e3.jsonl(f) if r.get("error"))
    return out


# ---------------------------------------------------------------------------- report
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "e3_sl.md"))
    ap.add_argument("--seed", type=int, default=20260912)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    RESULTS.mkdir(parents=True, exist_ok=True)
    cells = eval_cells()
    meta = e3sl.meta()
    matched = meta.get("matched", {})
    lf = {arm: [f"{arm}_lf_i1_m", f"{arm}_lf_i2_m"] for arm in e3sl.LF_ARMS}
    full = {arm: [f"{arm}_lf_i1", f"{arm}_lf_i2"] for arm in e3sl.LF_ARMS}
    cas = {arm: [f"{arm}_cas_i1", f"{arm}_cas_i2"] for arm in e3sl.CAS_ARMS}
    avg = {
        (arm, split): averaged(cells, lf[arm], split) for arm in e3sl.LF_ARMS for split in SPLITS
    }
    anchors = {
        (c, split): episode_values(cells, c, split) for c in ("N", "placebo") for split in SPLITS
    }
    diffs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for split in SPLITS:
        for other in ("G", "R", "O"):
            diffs[f"A_lf - {other}_lf" if other != "O" else "A_lf - O"][split] = diff_stats(
                avg[("A", split)], avg[(other, split)], rng
            )
        for arm in e3sl.LF_ARMS:
            for anc in ("N", "placebo"):
                diffs[f"{arm}_lf - {anc}"][split] = diff_stats(
                    avg[(arm, split)], anchors[(anc, split)], rng
                )
        diffs["placebo - N"][split] = diff_stats(
            anchors[("placebo", split)], anchors[("N", split)], rng
        )
    # verdict: A_lf >= G_lf and A_lf >= R_lf on ID or OOD with a 95% CI excluding 0
    holds_on = []
    for split in SPLITS:
        dg, dr = diffs["A_lf - G_lf"][split], diffs["A_lf - R_lf"][split]
        if (
            dg.get("n")
            and dr.get("n")
            and dg["diff"] > 0
            and dr["diff"] > 0
            and dg["excludes_zero"]
            and dr["excludes_zero"]
        ):
            holds_on.append(split)
    evaluated = all(diffs["A_lf - G_lf"][s].get("n") for s in SPLITS)

    lines: list[str] = [
        "# E3-SL — downstream skill evaluation of the E3 learner-facing sets (PREREG9 Addendum SL)",
        "",
        f"Banks: released single-success induction (`_build_bank`, success-only trajectories, shortest success per environment), DeepSeek V4 Pro extractor (thinking off) through the eval hook, embeddings through OpenRouter; two inductions per bank (i1 / i2, labelled by the addendum's seeds 20260920 / 20260921 — the released single-success induction samples at temperature 0, so i1 and i2 are replicate runs whose spread is the endpoint's own nondeterminism). Item matching: every learner-facing bank subsampled to k = {matched.get('k', '-')} items (seed {e3sl.MATCHED_SEED}). Eval: released `reasoning_bank_eval.py` through the eval hook, Qwen3-8B consumer (alibaba pin, reasoning off), SkillOS prompt, history 4, temperature 0.4, top-5 MMR, ID 140 + OOD 134, seeds 0 / 1000 / 2000. Addendum @ {e3sl.ADDENDUM_SHA}. Tables from scripts/make_tables_e3sl.py.",  # noqa: E501
        "",
        "## Verdict",
        "",
    ]
    if not evaluated:
        lines.append("**E3-SL: not evaluated yet (matched cells incomplete).**")
    elif holds_on:
        lines.append(
            f"**E3-SL holds on {' and '.join(holds_on)}: item-matched, induction-averaged A_lf above G_lf and R_lf with 95% CIs excluding 0.**"  # noqa: E501
        )
    else:
        lines.append(
            "**E3-SL fails: on neither split are both A_lf - G_lf and A_lf - R_lf positive with 95% CIs excluding 0.**"  # noqa: E501
        )
    lines += [
        "",
        "Per-episode paired differences (points; induction-averaged per episode; 10k episode bootstrap; ≈ = gap within 3 points, * = CI excludes 0):",  # noqa: E501
        "",
        "| difference | ID | OOD | n (ID / OOD) |",
        "|---|---|---|---|",
    ]
    for name, by_split in diffs.items():
        lines.append(
            f"| {name} | {diff_cell(by_split['in_distribution'])} | {diff_cell(by_split['out_of_distribution'])} | {by_split['in_distribution'].get('n', 0)} / {by_split['out_of_distribution'].get('n', 0)} |"  # noqa: E501
        )
    lines += [
        "",
        f"## Item-matched table (k = {matched.get('k', '-')} items per bank; success %, n, per seed 0 / 1000 / 2000)",  # noqa: E501
        "",
        "| bank | induction | ID | OOD |",
        "|---|---|---|---|",
    ]
    for arm in e3sl.LF_ARMS:
        lines += bank_rows(cells, f"{arm}_lf (matched)", lf[arm])
    for anc in ("N", "placebo"):
        lines += bank_rows(cells, anc, [anc])
    # supplementary paired differences at native bank size and for the released cascades
    supp: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for split in SPLITS:
        favg = {
            arm: averaged(cells, lf[arm] if arm == "R" else full[arm], split)
            for arm in e3sl.LF_ARMS
        }  # R's full bank is its matched bank
        for other in ("G", "R", "O"):
            supp[f"A_lf(full) - {other}_lf(full)"][split] = diff_stats(favg["A"], favg[other], rng)
        cavg = {arm: averaged(cells, cas[arm], split) for arm in e3sl.CAS_ARMS}
        for other in ("G", "R"):
            supp[f"A_cas - {other}_cas"][split] = diff_stats(cavg["A"], cavg[other], rng)
        supp["A_lf(full) - A_cas"][split] = diff_stats(favg["A"], cavg["A"], rng)
    lines += [
        "",
        "## Supplementary paired differences (full-bank and released-cascade rows; same estimator)",
        "",
        "| difference | ID | OOD | n (ID / OOD) |",
        "|---|---|---|---|",
    ]
    for name, by_split in supp.items():
        lines.append(
            f"| {name} | {diff_cell(by_split['in_distribution'])} | {diff_cell(by_split['out_of_distribution'])} | {by_split['in_distribution'].get('n', 0)} / {by_split['out_of_distribution'].get('n', 0)} |"  # noqa: E501
        )
    lines += [
        "",
        "## Full-bank rows (supplementary)",
        "",
        "| bank | induction | ID | OOD |",
        "|---|---|---|---|",
    ]
    for arm in e3sl.LF_ARMS:
        rows = bank_rows(cells, f"{arm}_lf (full)", full[arm])
        same = [
            n
            for n in full[arm]
            if matched.get("banks", {}).get(f"{n}_m", {}).get("full_row_is_matched_row")
        ]
        lines += rows if any(c in cells for c in full[arm]) else []
        if same:
            lines.append(
                f"| {arm}_lf (full) | {', '.join(same)} | = matched row (full bank of k items) | |"
            )
    lines += [
        "",
        "## Released-cascade rows (supplementary)",
        "",
        "| bank | induction | ID | OOD |",
        "|---|---|---|---|",
    ]
    for arm in e3sl.CAS_ARMS:
        if any(c in cells for c in cas[arm]):
            lines += bank_rows(cells, f"{arm}_cas", cas[arm])
        else:
            lines.append(f"| {arm}_cas | - | not evaluated | |")
    lines += [
        "",
        "## Banks — item counts and induction types",
        "",
        "| bank | items | tasks | trajectories | induction types | extractor | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, b in sorted(meta.items()):
        if name == "matched" or not isinstance(b, dict):
            continue
        lines.append(
            f"| {name} | {b.get('items')} | {len(b.get('tasks') or [])} | {sum((b.get('trajectories') or {}).values()) or '-'} | {b.get('induction') or '-'} | {b.get('extractor') or '-'} | {b.get('note') or b.get('vocab_check') or ''} |"  # noqa: E501
        )
    if matched:
        lines += [
            "",
            f"Matched sizes: k = {matched.get('k')} from "
            + ", ".join(f"{n} {v}" for n, v in sorted((matched.get("sizes") or {}).items()))
            + ".",
        ]
    sp = spend()
    total = sum(sum(v.values()) for v in sp.values())
    lines += [
        "",
        "## Spend (USD by run and budget/phase)",
        "",
        "| run | budget/phase | total |",
        "|---|---|---|",
    ]
    for run, by in sorted(sp.items()):
        lines.append(
            f"| {run} | "
            + ", ".join(f"{k} {v:.2f}" for k, v in sorted(by.items()))
            + f" | {sum(by.values()):.2f} |"
        )
    inc = incidents()
    lines += [
        "",
        f"E3-SL total USD {total:.2f} (cap {e3sl.CAP_USD:.0f}).",
        "",
        "## Incidents (UTC timestamps in experiments/alfworld_e3/LOG.md)",
        "",
        f"- Guard incidents {inc['guard_incidents']}; ledgered retries 429 {inc['retries_429']}, other {inc['retries_other']}; errored episodes re-run {inc['errored_episodes']}.",  # noqa: E501
        "",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "e3_sl_data.json").write_text(
        json.dumps(
            {
                "verdict": {"evaluated": evaluated, "holds_on": holds_on},
                "diffs": diffs,
                "supplementary_diffs": supp,
                "matched": matched,
                "banks": {k: v for k, v in meta.items() if k != "matched"},
                "spend": sp,
                "incidents": inc,
                "conditions_evaluated": sorted(cells),
            },
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
