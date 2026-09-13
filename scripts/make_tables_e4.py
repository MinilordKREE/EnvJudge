"""E4 tables (PREREG11) -> experiments/alfworld_e4/results/e4_regime_origin.md and
e4_regime_origin_data.json. Cells: runs/e4-eval (M, B, S, MB matched and full; B2 / S2 groups) and
the reused E3-SL cells (runs/e3sl-eval: N, placebo, O_lf as O_all matched-12 and full). Estimator
as E3-SL: per-episode induction average, per-task mean, 10k task-clustered bootstrap.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e4
import make_tables_e3sl as ms

RUNS = e4.RUNS
RESULTS = e4.RESULTS
SPLITS = ms.SPLITS
fmt = ms.fmt
INDIST = ms.INDIST


def verdict_e4_2(d: dict[str, dict[str, Any]]) -> str:
    """M >= B - 3 on either split -> 'rare successes are as valuable'; M < B - 3 with the CI
    excluding 0 on both -> 'rare successes are worse'; else 'indistinguishable'."""
    if not all(d[s].get("n") for s in SPLITS):
        return "not evaluated"
    if any(d[s]["diff"] >= -INDIST for s in SPLITS):
        return "rare successes are as valuable (M >= B - 3 on at least one split)"
    if all(d[s]["diff"] < -INDIST and d[s]["excludes_zero"] for s in SPLITS):
        return "rare successes are worse (M < B - 3 with CIs excluding 0)"
    return "indistinguishable"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "e4_regime_origin.md"))
    ap.add_argument("--seed", type=int, default=20260914)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    RESULTS.mkdir(parents=True, exist_ok=True)
    cells = ms.eval_cells(e4.EVAL)
    reused = ms.eval_cells(RUNS / "e3sl-eval")
    for c in ("N", "placebo", "O_lf_i1_m", "O_lf_i2_m", "O_lf_i1", "O_lf_i2"):
        if c in reused:
            cells[c] = reused[c]
    meta = e4.meta()
    matched = meta.get("matched", {})
    for name, rep in matched.get("banks", {}).items():  # a matched bank identical to its full
        if rep.get("full_row_is_matched_row") and name not in cells and name[:-2] in cells:
            cells[name] = cells[name[:-2]]  # bank (M_i2): the full cells serve the matched row
    groups = meta.get("groups", {})
    count_groups = meta.get("count_groups", {})
    arms = ("M", "B", "S", "MB")
    lf = {a: [f"{a}_i1_m", f"{a}_i2_m"] for a in arms}
    full = {a: [f"{a}_i1", f"{a}_i2"] for a in arms}
    lf["O_all(k12)"] = ["O_lf_i1_m", "O_lf_i2_m"]
    full["O_all"] = ["O_lf_i1", "O_lf_i2"]
    avg = {(a, s): ms.averaged(cells, lf[a], s) for a in lf for s in SPLITS}
    favg = {(a, s): ms.averaged(cells, full[a], s) for a in full for s in SPLITS}
    anchors = {(c, s): ms.episode_values(cells, c, s) for c in ("N", "placebo") for s in SPLITS}
    diffs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for s in SPLITS:
        diffs["B - S (matched)"][s] = ms.diff_stats(avg[("B", s)], avg[("S", s)], rng)
        diffs["M - B (matched)"][s] = ms.diff_stats(avg[("M", s)], avg[("B", s)], rng)
        diffs["M - S (matched)"][s] = ms.diff_stats(avg[("M", s)], avg[("S", s)], rng)
        diffs["MB - S (matched)"][s] = ms.diff_stats(avg[("MB", s)], avg[("S", s)], rng)
        diffs["MB - O_all(k12) (matched)"][s] = ms.diff_stats(
            avg[("MB", s)], avg[("O_all(k12)", s)], rng
        )
        for a in arms:
            for anc in ("N", "placebo"):
                diffs[f"{a} - {anc} (matched)"][s] = ms.diff_stats(
                    avg[(a, s)], anchors[(anc, s)], rng
                )
        diffs["B - S (full)"][s] = ms.diff_stats(favg[("B", s)], favg[("S", s)], rng)
        diffs["M - B (full)"][s] = ms.diff_stats(favg[("M", s)], favg[("B", s)], rng)
        diffs["MB - S (full)"][s] = ms.diff_stats(favg[("MB", s)], favg[("S", s)], rng)
        diffs["MB - O_all (full)"][s] = ms.diff_stats(favg[("MB", s)], favg[("O_all", s)], rng)
    # task-count-matched sub-row: M (2 tasks, full bank) vs B2 / S2 (2 tasks each, 3 groups)
    cnt: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    count_rows: dict[str, list[str]] = {}
    for g in sorted(count_groups):
        for a in ("B", "S"):
            count_rows[f"{a}2_{g}"] = [f"{a}2_{g}_i1", f"{a}2_{g}_i2"]
    for s in SPLITS:
        for a in ("B", "S"):
            per_group = [
                ms.averaged(cells, count_rows[f"{a}2_{g}"], s) for g in sorted(count_groups)
            ]
            per_group = [p for p in per_group if p]
            if per_group:  # mean over the groups per episode
                keys = set(per_group[0])
                for p in per_group[1:]:
                    keys &= set(p)
                pooled = {k: sum(p[k] for p in per_group) / len(per_group) for k in keys}
                cnt[f"M - {a}2 (2 tasks each, {len(per_group)} groups)"][s] = ms.diff_stats(
                    favg[("M", s)], pooled, rng
                )
        b2 = [ms.averaged(cells, count_rows[f"B2_{g}"], s) for g in sorted(count_groups)]
        s2 = [ms.averaged(cells, count_rows[f"S2_{g}"], s) for g in sorted(count_groups)]
        b2 = [p for p in b2 if p]
        s2 = [p for p in s2 if p]
        if b2 and s2:
            kb = set(b2[0])
            for p in b2[1:]:
                kb &= set(p)
            ks = set(s2[0])
            for p in s2[1:]:
                ks &= set(p)
            pb = {k: sum(p[k] for p in b2) / len(b2) for k in kb}
            ps = {k: sum(p[k] for p in s2) / len(s2) for k in ks}
            cnt["B2 - S2 (2 tasks each)"][s] = ms.diff_stats(pb, ps, rng)
    # verdicts: per PREREG11 amendment 1 the FULL-bank rows decide (matched rows = robustness)
    e41 = [
        s
        for s in SPLITS
        if diffs["B - S (full)"][s].get("n")
        and diffs["B - S (full)"][s]["diff"] > 0
        and diffs["B - S (full)"][s]["excludes_zero"]
    ]
    e42 = verdict_e4_2(diffs["M - B (full)"])
    mb_s = diffs["MB - S (full)"]
    mb_o = diffs["MB - O_all (full)"]
    e43_a = all(mb_s[s].get("n") and mb_s[s]["diff"] > 0 for s in SPLITS)
    e43_b = all(mb_o[s].get("n") and mb_o[s]["diff"] >= 0 for s in SPLITS)
    evaluated = all(diffs["B - S (full)"][s].get("n") for s in SPLITS)

    lines: list[str] = [
        "# E4 — regime origin of successful trajectories (PREREG11)",
        "",
        f"Material: the shared original-environment K=16 successes of seeds 0-29 (runs/e2-shared, runs/e3-shared), no new search rollout. Groups by shared p16: marginal {groups.get('M')}, band {groups.get('B')}, saturated {groups.get('S')} ({len(groups.get('S') or [])} tasks). Banks: released single-success induction (shortest success per task), DeepSeek V4 Pro extractor (thinking off; temperature 0 in the released code, so the two inductions labelled 20260930 / 20260931 are replicate runs), two per bank. Item matching: k = {matched.get('k', '-')} (min over M, B, S, floor {e4.K_FLOOR}; seed {e4.MATCHED_SEED}); drained arms: {matched.get('drained') or 'none'}. Task-count-matched sub-row: 2 tasks drawn from B and from S, {len(count_groups)} groups (seed {e4.COUNT_SEED}): {json.dumps(count_groups)}. Eval as E3-SL (released reasoning_bank_eval.py through the eval hook, Qwen3-8B, SkillOS prompt, history 4, temperature 0.4, top-5 MMR, ID 140 + OOD 134, seeds 0 / 1000 / 2000); N, placebo and O_all reused from E3-SL (O_all rows: the E3-SL O bank at its 12-item matched size and at full size). PREREG11 @ {e4.PREREG_SHA}; tables from scripts/make_tables_e4.py.",  # noqa: E501
        "",
        "## Verdicts",
        "",
    ]
    if not evaluated:
        lines.append("**E4: not evaluated yet (full-bank cells incomplete).**")
    else:
        lines += [
            "Per PREREG11 amendment 1 the full-bank rows decide; the item-matched rows (k = 4, where top-5 retrieval returns the whole bank on every step) are a size-control robustness check; the task-count sub-row (group g3 only) is indicative.",  # noqa: E501
            "",
            f"- **E4-1 (B > S, full banks, CI excluding 0 on ID or OOD): {'holds on ' + ' and '.join(e41) if e41 else 'FAILS'}.**",  # noqa: E501
            f"- **E4-2 (M vs B, full banks): {e42}.**",
            f"- **E4-3 (MB > S and MB >= O_all, full banks, point estimates): MB > S {'holds' if e43_a else 'fails'}; MB >= O_all {'holds' if e43_b else 'fails'}.**",  # noqa: E501
        ]
    lines += [
        "",
        "Paired per-task differences (points; induction-averaged per episode, per-task mean over seed blocks, 10k task-clustered bootstrap; ≈ = gap within 3 points, * = CI excludes 0):",  # noqa: E501
        "",
        "| difference | ID | OOD | n (ID / OOD) |",
        "|---|---|---|---|",
    ]
    for name, by in diffs.items():
        lines.append(
            f"| {name} | {ms.diff_cell(by['in_distribution'])} | {ms.diff_cell(by['out_of_distribution'])} | {by['in_distribution'].get('n', 0)} / {by['out_of_distribution'].get('n', 0)} |"  # noqa: E501
        )
    lines += [
        "",
        "## Task-count-matched sub-row (indicative; amendment 1: group g3 only — M's 2 tasks vs B{16, 19} and S{1, 13})",  # noqa: E501
        "",
        "| difference | ID | OOD | n (ID / OOD) |",
        "|---|---|---|---|",
    ]
    for name, by in cnt.items():
        lines.append(
            f"| {name} | {ms.diff_cell(by['in_distribution'])} | {ms.diff_cell(by['out_of_distribution'])} | {by['in_distribution'].get('n', 0)} / {by['out_of_distribution'].get('n', 0)} |"  # noqa: E501
        )
    lines += [
        "",
        f"## Item-matched table (k = {matched.get('k', '-')}; success %, n, per seed 0 / 1000 / 2000; mean ± SE over the two inductions)",  # noqa: E501
        "",
        "| bank | induction | ID | OOD |",
        "|---|---|---|---|",
    ]
    for a in ("M", "B", "S", "MB", "O_all(k12)"):
        lines += ms.bank_rows(cells, f"{a} (matched)", lf[a])
    for anc in ("N", "placebo"):
        lines += ms.bank_rows(cells, anc, [anc])
    lines += [
        "",
        "## Task-count-matched banks (full size)",
        "",
        "| bank | induction | ID | OOD |",
        "|---|---|---|---|",
    ]
    lines += ms.bank_rows(cells, "M (full, 2 tasks)", full["M"])
    for name, conds in count_rows.items():
        if any(c in cells for c in conds):
            lines += ms.bank_rows(cells, name, conds)
    lines += [
        "",
        "## Full-bank rows (supplementary)",
        "",
        "| bank | induction | ID | OOD |",
        "|---|---|---|---|",
    ]
    for a in ("M", "B", "S", "MB", "O_all"):
        if any(c in cells for c in full[a]):
            lines += ms.bank_rows(cells, f"{a} (full)", full[a])
    lines += [
        "",
        "## Banks — items, tasks, induction types",
        "",
        "| bank | arm | items | tasks | trajectories | induction types |",
        "|---|---|---|---|---|---|",
    ]
    for name, b in sorted(meta.items()):
        if name in ("groups", "count_groups", "matched") or not isinstance(b, dict):
            continue
        lines.append(
            f"| {name} | {b.get('arm')} | {b.get('items')} | {', '.join(b.get('tasks') or [])} | {sum((b.get('trajectories') or {}).values())} | {b.get('induction')} |"  # noqa: E501
        )
    if matched:
        lines += [
            "",
            f"Matched: k = {matched.get('k')} from "
            + ", ".join(f"{n} {v}" for n, v in sorted((matched.get("sizes") or {}).items()))
            + f"; drained {matched.get('drained') or 'none'}.",
        ]
    sp: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for top in sorted(RUNS.glob("e4-*")):
        if not top.is_dir():
            continue
        for d in [top, *sorted(p for p in top.rglob("*") if p.is_dir())]:
            files = (
                [d / "ledger.jsonl"]
                if (d / "ledger.jsonl").exists()
                else sorted(d.glob("ledger.*.jsonl"))
            )
            for f in files:
                for r in e4.e3.jsonl(f):
                    if r.get("event") == "call":
                        sp[top.name][f"{r.get('budget')}/{r.get('phase')}"] += float(
                            r.get("usd") or 0.0
                        )
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
    inc = len(e4.e3.jsonl(e4.EVAL / "guard_incidents.jsonl"))
    lines += [
        "",
        f"E4 total USD {total:.2f} (cap {e4.CAP_USD:.0f}).",
        "",
        "## Incidents (UTC timestamps in experiments/alfworld_e4/LOG.md)",
        "",
        f"- Guard incidents {inc}.",
        "",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "e4_regime_origin_data.json").write_text(
        json.dumps(
            {
                "verdicts": {
                    "E4-1_holds_on": e41,
                    "E4-2": e42,
                    "E4-3": {"MB>S": e43_a, "MB>=O_all": e43_b},
                    "evaluated": evaluated,
                },
                "diffs": diffs,
                "count_matched": cnt,
                "matched": matched,
                "groups": groups,
                "count_groups": count_groups,
                "banks": {
                    k: v for k, v in meta.items() if k not in ("groups", "count_groups", "matched")
                },
                "spend": {k: dict(v) for k, v in sp.items()},
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
