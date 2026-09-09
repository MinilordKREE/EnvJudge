"""Round-1b tables (PREREG7 Amendment 3): experiments/alfworld_sl/results/round1b.md.

Every number comes from ledgers, traces, confirmations and eval cells through scripts/make_tables.py
helpers (eval cells, paired bootstrap, C1). Sections: corrected zero-task line; G/G+ rules summary;
corrected A-family U rows and the corrected A-vs-O / A-vs-R (U) differences; placebo row and gains
at matched item counts; A' C1 / C2 / statuses / family / budget breakdown; Amendment-3 paragraph.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_tables as mt

ROOT = mt.ROOT
RUNS = mt.RUNS
RESULTS = mt.RESULTS
SPLITS = mt.SPLITS


def table_row(cells: dict[str, Any], cond: str) -> str:
    parts = []
    for split in SPLITS:
        by_seed = cells.get(cond, {}).get(split, {})
        pooled = [r for s in sorted(by_seed) for r in by_seed[s]]
        p, n = mt.rate(pooled)
        per = " / ".join(mt.fmt(mt.rate(by_seed[s])[0]) for s in sorted(by_seed))
        parts.append(f"{mt.fmt(p)} (n={n}) [{per}]")
    seeds = sorted(set().union(*(set(cells.get(cond, {}).get(s, {})) for s in SPLITS)))
    return f"| {cond} | {len(seeds)} | {parts[0]} | {parts[1]} |"


def diff_row(
    cells: dict[str, Any], a: str, b: str, label: str, rng: random.Random
) -> tuple[str, dict[str, Any]]:
    rec: dict[str, Any] = {}
    parts = []
    for split in SPLITS:
        ra, rb = mt.cells_by_seed_common(cells, a, b, split)
        d = mt.diff_stats(mt.paired(ra, rb), rng)
        rec[split] = d
        parts.append(
            f"{d['diff']:+.1f} [{d['ci95_boot'][0]:+.1f}, {d['ci95_boot'][1]:+.1f}] ({d['se_pooled_normal']:.1f})"  # noqa: E501
            if d.get("n")
            else "-"
        )
    return f"| {label} | {parts[0]} | {parts[1]} | {rec['in_distribution'].get('n', 0)} |", rec


def aprime_budget() -> list[dict[str, Any]]:
    """Per task: rollouts by phase (estimate / leverage / dose / hint / probe), doses visited,
    accepted dose, leverage tests skipped by prior, families demoted."""
    d = RUNS / "r1-Aprime"
    ev = mt.jsonl(d / "events.jsonl")
    per: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "estimate": 0,
            "leverage": 0,
            "dose": 0,
            "hint": 0,
            "probe": 0,
            "doses": [],
            "accepted": None,
            "skipped": [],
            "demoted": [],
            "status": None,
            "family": None,
        }
    )
    for e in ev:
        k, p = e.get("kind"), e.get("payload", {})
        t = str(p.get("task_id"))
        if k == "rollouts":
            phase = str(p.get("phase", ""))
            n = int(p.get("n", 0))
            if phase == "estimate":
                per[t]["estimate"] += n
            elif phase.startswith("hint:"):
                per[t]["hint"] += n
            elif phase == "probe":
                per[t]["probe"] += n
            elif phase.startswith("dose:"):
                per[t]["dose"] += n
        elif k == "dose_search":
            hist = p.get("history") or []
            if p.get("leverage_tested") and hist and hist[0].get("d") == 1.0:
                per[t]["leverage"] += int(hist[0].get("n", 0))
                per[t]["dose"] -= int(hist[0].get("n", 0))
            per[t]["doses"].append((p.get("family"), [h.get("d") for h in hist], p.get("status")))
        elif k == "leverage_skipped":
            per[t]["skipped"].append((p.get("family"), p.get("start")))
        elif k == "families_demoted":
            per[t]["demoted"] = list(p.get("demoted") or [])
        elif k == "task_done":
            per[t]["status"] = p.get("status")
            per[t]["family"] = p.get("family")
            if p.get("status") == "accepted_knob":
                per[t]["accepted"] = p.get("d")
    return [
        {"task": t, **v}
        for t, v in sorted(per.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 999)
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "round1b.md"))
    ap.add_argument("--seed", type=int, default=20260909)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    out_dir = RESULTS / "r1b"
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = mt.eval_cells()
    lines = ["# E1-SL Round 1b (PREREG7 Amendment 3): corrections and additions to Round 1", ""]

    # 1. corrected zero-task line
    r1md = (RESULTS / "round1.md").read_text(encoding="utf-8").splitlines()
    zero_line = next((ln for ln in r1md if ln.startswith("Zero tasks at the shared")), "")
    lines += [
        "## 1. Corrected Round-1 zero-task line (rendering fix, numbers unchanged)",
        "",
        zero_line,
        "",
    ]

    # 2. g_rules summary
    g = (RESULTS / "r1" / "g_rules.md").read_text(encoding="utf-8").splitlines()
    i = g.index("## Axis x leverage")
    j = g.index("## Code of every accepted candidate")
    lines += [
        "## 2. G / G+ accepted rules (results/r1/g_rules.md): axis x leverage",
        "",
        *g[i + 1 : j],
        "",
    ]

    # 3. corrected U rows and differences
    lines += [
        "## 3. Protocol U corrected (A3.1): A-family rows re-induced and re-evaluated",
        "",
        "| condition | seeds | ID | OOD |",
        "|---|---|---|---|",
    ]
    for cond in (
        "N",
        "O_U",
        "R_U",
        "A_U_v1",
        "A_U",
        "Aex_U_v1",
        "Aex_U",
        "AplusH_U_v1",
        "AplusH_U",
    ):
        if cond in cells:
            lines.append(table_row(cells, cond))
    lines += [
        "",
        "| comparison | ID diff [95% CI] (SE) | OOD diff [95% CI] (SE) | pairs |",
        "|---|---|---|---|",
    ]
    comps: dict[str, Any] = {}
    for a, b, label in (
        ("A_U", "O_U", "A vs O (U, corrected; pre-registered)"),
        ("A_U", "R_U", "A vs R (U, corrected; pre-registered inequality)"),
        ("A_U", "N", "A vs N (U, corrected)"),
        ("A_U", "A_U_v1", "A_U corrected vs Round-1 A_U"),
        ("Aex_U", "Aex_U_v1", "A-ex_U corrected vs Round-1"),
        ("AplusH_U", "AplusH_U_v1", "A+H_U corrected vs Round-1"),
        ("A_U", "Aex_U", "A vs A-ex (U, corrected)"),
        ("AplusH_U", "A_U", "A+H vs A (U, corrected)"),
    ):
        if a in cells and b in cells:
            row, rec = diff_row(cells, a, b, label, rng)
            lines.append(row)
            comps[f"{a}-{b}"] = rec

    # 4. placebo and matched sizes
    lines += [
        "",
        "## 4. Bank-size controls (A3.2)",
        "",
        "| condition | seeds | ID | OOD |",
        "|---|---|---|---|",
    ]
    if "placebo" in cells:
        lines.append(table_row(cells, "placebo"))
    matched_meta = (
        json.loads((RUNS / "r1-banks" / "matched" / "matched.json").read_text(encoding="utf-8"))
        if (RUNS / "r1-banks" / "matched" / "matched.json").exists()
        else {}
    )
    lines += [
        "",
        "Gain over N and over the placebo at matched item counts (points; 3 seeds unless the full bank; "  # noqa: E501
        "a bank smaller than the target is evaluated at its full size and flagged):",
        "",
        "| bank | size | items | vs N: ID | vs N: OOD | vs placebo: ID | vs placebo: OOD |",
        "|---|---|---|---|---|---|---|",
    ]
    for bank in ("O_U", "R_T2", "R_U", "G_T2", "G_U", "A_T2", "A_U", "Aex_U", "AplusH_T2"):
        for k in (8, 20):
            name = f"{bank}@{k}"
            meta = matched_meta.get(name, {})
            cond = bank if meta.get("flag") else name
            if cond not in cells:
                continue
            gain_n = diff_row(cells, cond, "N", "", rng)[1]
            gain_p = diff_row(cells, cond, "placebo", "", rng)[1] if "placebo" in cells else {}

            def f(rec: dict[str, Any], split: str) -> str:
                d = rec.get(split, {})
                return (
                    f"{d['diff']:+.1f} [{d['ci95_boot'][0]:+.1f}, {d['ci95_boot'][1]:+.1f}]"
                    if d.get("n")
                    else "-"
                )

            items = meta.get("items", "?")
            flag = " (full, flagged)" if meta.get("flag") else ""
            lines.append(
                f"| {bank} | {k} | {items}{flag} | {f(gain_n, 'in_distribution')} | {f(gain_n, 'out_of_distribution')} | "  # noqa: E501
                f"{f(gain_p, 'in_distribution')} | {f(gain_p, 'out_of_distribution')} |"
            )
            comps[f"{cond}-N"] = gain_n
            comps[f"{cond}-placebo"] = gain_p
    lines += [
        "",
        "\"No content effect\" = the bank's gain at matched size is not distinguishable from the placebo's (the vs-placebo CI covers 0).",  # noqa: E501
        "",
    ]

    # 5. A'
    lines += ["## 5. A' (A3.3): cross-task family priors", ""]
    if (RUNS / "r1-Aprime" / "events.jsonl").exists():
        c1 = {arm: mt.c1(arm, rng) for arm in ("A", "Aprime", "R", "G")}
        lines += [
            "| arm | transformed envs | learnable | search rollouts | per 1,000 [95% CI] |",
            "|---|---|---|---|---|",
        ]
        for arm in ("A", "Aprime", "R", "G"):
            r = c1[arm]
            ci = f"[{mt.fmt(r['ci95'][0])}, {mt.fmt(r['ci95'][1])}]" if r["ci95"] else "-"
            lines.append(
                f"| {mt.ARM_LABEL.get(arm, arm)} | {r['transformed_envs']} | {r['learnable_transformed']} | {r['search_rollouts']} | {mt.fmt(r['per_1000'])} {ci} |"  # noqa: E501
            )
        st = mt.statuses("Aprime")
        counts = {k: sum(1 for p in st.values() if p.get("status") == k) for k in mt.STATUSES}
        lines += [
            "",
            "| arm | " + " | ".join(mt.STATUSES) + " |",
            "|---|" + "---|" * len(mt.STATUSES),
            "| A' | " + " | ".join(str(counts[k]) for k in mt.STATUSES) + " |",
            "",
        ]
        fam: dict[str, int] = defaultdict(int)
        for e in mt.jsonl(RUNS / "r1-Aprime" / "corpus.jsonl"):
            meta = e.get("aea") or {}
            fam[
                f"{meta.get('source')}:{meta.get('family')}"
                if meta.get("kind") == "knob"
                else str(meta.get("kind"))
            ] += 1
        lines += [f"Family of origin (A'): {dict(fam)}", ""]
        lines += ["| condition | seeds | ID | OOD |", "|---|---|---|---|"]
        for cond in ("N", "A_T2", "Aprime_T2", "A_U", "Aprime_U", "R_T2", "R_U", "G_T2", "G_U"):
            if cond in cells:
                lines.append(table_row(cells, cond))
        lines += [
            "",
            "| comparison | ID diff [95% CI] (SE) | OOD diff [95% CI] (SE) | pairs |",
            "|---|---|---|---|",
        ]
        for a, b, label in (
            ("Aprime_U", "O_U", "A' vs O (U)"),
            ("Aprime_U", "R_U", "A' vs R (U)"),
            ("Aprime_T2", "R_T2", "A' vs R (T2)"),
            ("Aprime_U", "A_U", "A' vs A (U)"),
            ("Aprime_T2", "A_T2", "A' vs A (T2)"),
            ("Aprime_U", "G_U", "A' vs G (U)"),
            ("Aprime_T2", "G_T2", "A' vs G (T2)"),
            ("Aprime_U", "N", "A' vs N (U)"),
        ):
            if a in cells and b in cells:
                row, rec = diff_row(cells, a, b, label, rng)
                lines.append(row)
                comps[f"{a}-{b}"] = rec
        budget = aprime_budget()
        lines += [
            "",
            "Per-task budget breakdown (A'): rollouts by phase; doses visited per family; accepted dose; leverage tests skipped by prior.",  # noqa: E501
            "",
            "| task | status | estimate | leverage | dose | hint | probe | doses visited (family: d list, status) | accepted d | skipped by prior | demoted |",  # noqa: E501
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for b in budget:
            visited = "; ".join(f"{fam}: {ds} {status}" for fam, ds, status in b["doses"]) or "-"
            lines.append(
                f"| {b['task']} | {b['status']} | {b['estimate']} | {b['leverage']} | {b['dose']} | {b['hint']} | {b['probe']} | {visited} | "  # noqa: E501
                f"{b['accepted'] if b['accepted'] is not None else '-'} | {b['skipped'] or '-'} | {b['demoted'] or '-'} |"  # noqa: E501
            )
        with (out_dir / "aprime_budget.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=[
                    "task",
                    "status",
                    "family",
                    "estimate",
                    "leverage",
                    "dose",
                    "hint",
                    "probe",
                    "accepted",
                    "skipped",
                    "demoted",
                    "doses",
                ],
            )
            w.writeheader()
            for b in budget:
                w.writerow(
                    {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in b.items()}
                )
    else:
        lines += ["A' has not run (pending the owner's budget decision).", ""]

    # 6. what changed
    lines += [
        "",
        "## 6. What changed (PREREG7 Amendment 3)",
        "",
        "A3.1 redefined Protocol U as T2 plus single-success induction over every task with at least one "  # noqa: E501
        "success during the arm's own search regardless of final status; Amendment 1's status list had "  # noqa: E501
        "excluded budget_cap_hit tasks, so Round 1's A_U, Aex_U and AplusH_U were rebuilt (the originals "  # noqa: E501
        "are archived as *_U_v1 with their evaluations) and re-evaluated. A3.2 added a placebo bank of "  # noqa: E501
        "five task-irrelevant items and item-matched evaluations at 8 and 20 items so that C2 gains can "  # noqa: E501
        "be read against bank size and content. A3.3 pre-registered A', the A controller with cross-task "  # noqa: E501
        "family priors (start dose = median accepted dose, the d = 1 leverage test skipped after five "  # noqa: E501
        "ZERO results, families with no leverage on five tasks moved to the end); A itself was not re-run. "  # noqa: E501
        "A3.4 set the hard cap to USD 650 and the soft gate to USD 600.",
        "",
    ]

    # 7. spend
    sp = mt.spend()
    total = sum(v for k, arm in sp.items() if "/reused" not in k for v in arm.values())
    lines += [
        "## 7. Spend",
        "",
        f"Round 1 + 1b spend USD {total:.2f} (Round-1/1b run ids); E1-SL total USD {99.08 + total:.2f} against the soft gate 600 and hard cap 650 (A3.4).",  # noqa: E501
        "",
    ]
    (out_dir / "comparisons.json").write_text(json.dumps(comps, indent=1), encoding="utf-8")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
