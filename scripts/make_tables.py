"""Round-1 tables (PREREG7 + Amendments 1-2) from ledgers, traces, confirmations and eval cells.

Writes experiments/alfworld_sl/results/round1.md and results/r1/ (accounting.csv, evals.json,
c1.json, c2.json, statuses.json, spend.json). Every number in round1.md comes from this script.

  C1  learnable TRANSFORMED environments per 1,000 charged search rollouts, Protocol T2, per arm;
      task-level bootstrap CI (10k resamples of tasks)
  C2  held-out success per condition (pooled over seeds, per seed), paired differences A vs O (U),
      A vs R / G (T2 and U) with 10k bootstrap CIs over paired episodes and the pooled normal SE
  A2.2 seed-extension decision; PREREG7 stop rule (after the extension step)
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
RESULTS = ROOT / "experiments" / "alfworld_sl" / "results"
ARMS = ("R", "G", "Gplus", "A", "Aex", "AplusH")
ARM_LABEL = {
    "R": "R",
    "G": "G",
    "Gplus": "G+",
    "A": "A",
    "Aex": "A-ex",
    "AplusH": "A+H",
    "O": "O",
    "N": "N",
}
STATUSES = (
    "band",
    "accepted_knob",
    "accepted_stage",
    "frozen_no_leverage",
    "exhausted",
    "unresolved",
    "unresolved_budget_limited",
    "budget_cap_hit",
    "infra_error",
    "no_failed_trajectory",
)
SPLITS = ("in_distribution", "out_of_distribution")
BOOT = 10_000


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().strip("\0")
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------- search accounting
def search_rollouts(arm: str) -> dict[str, int]:
    """Charged search rollouts per task. aea arms: accounting.csv (errored rollouts refunded);
    released arms and O: policy episodes in traces.jsonl without an error."""
    d = RUNS / f"r1-{arm}"
    per: dict[str, int] = defaultdict(int)
    acc = d / "accounting.csv"
    if arm in ("A", "Aex", "AplusH") and acc.exists():
        with acc.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("budget") == "search":
                    per[str(row["task_id"])] += int(float(row.get("n") or row.get("rollouts") or 0))
        return dict(per)
    for r in jsonl(d / "traces.jsonl"):
        if r.get("error") or str(r.get("candidate_id")) == "hint":
            continue
        per[str(r["rollout_seed"])] += 1
    return dict(per)


def confirm_summary(arm: str) -> dict[str, dict[str, Any]]:
    p = RUNS / f"r1-{arm}" / "confirm_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def shared_confirm() -> dict[str, dict[str, Any]]:
    p = RUNS / "r1-shared" / "confirm_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def statuses(arm: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in jsonl(RUNS / f"r1-{arm}" / "events.jsonl"):
        if e.get("kind") == "task_done":
            out[str(e["payload"]["task_id"])] = dict(e["payload"])
    return out


def released_statuses(arm: str) -> dict[str, str]:
    """R / G / G+: accepted | skipped (empty candidate or no attempt) | all_rejected, per task."""
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in jsonl(RUNS / f"r1-{arm}" / "traces.jsonl"):
        per[str(r["rollout_seed"])][str(r.get("kind"))] += 1
    out = {}
    for t, kinds in per.items():
        if kinds.get("accepted"):
            out[t] = "accepted"
        elif kinds.get("exploration"):
            out[t] = "all_rejected"
        else:
            out[t] = "skipped"
    return out


def c1(arm: str, rng: random.Random) -> dict[str, Any]:
    conf = confirm_summary(arm)
    per_task_learn: dict[str, int] = defaultdict(int)
    for env in conf.values():
        if not env.get("shared") and env.get("learnable"):
            per_task_learn[str(env["task"])] += 1
    rolls = search_rollouts(arm)
    tasks = sorted(set(rolls) | set(per_task_learn), key=int)
    total_learn = sum(per_task_learn.values())
    total_roll = sum(rolls.values())
    rate = 1000 * total_learn / total_roll if total_roll else float("nan")
    boots = []
    for _ in range(BOOT):
        sample = [tasks[rng.randrange(len(tasks))] for _ in tasks] if tasks else []
        lr = sum(per_task_learn.get(t, 0) for t in sample)
        rr = sum(rolls.get(t, 0) for t in sample)
        boots.append(1000 * lr / rr if rr else 0.0)
    boots.sort()
    return {
        "learnable_transformed": total_learn,
        "transformed_envs": sum(1 for e in conf.values() if not e.get("shared")),
        "search_rollouts": total_roll,
        "per_1000": rate,
        "ci95": [boots[int(0.025 * BOOT)], boots[int(0.975 * BOOT)]] if boots else None,
        "band_tasks_learnable": sum(
            1
            for t, s in statuses(arm).items()
            if s.get("status") == "band" and shared_confirm().get(f"{t}:orig", {}).get("learnable")
        ),
    }


# ---------------------------------------------------------------------------- evals
def eval_cells() -> dict[str, dict[str, dict[int, list[dict[str, Any]]]]]:
    """{condition: {split: {seed: [records]}}} from
    runs/r1-eval/<cond>-seeds-<s>[-resume-*]/round*/."""
    out: dict[str, dict[str, dict[int, list[dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    root = RUNS / "r1-eval"
    if not root.exists():
        return {}
    for d in sorted(root.iterdir()):
        m = re.match(r"(.+)-seeds-(\d+)(-resume-\d+)?$", d.name)
        if not m or not d.is_dir():
            continue
        cond, start = m.group(1), int(m.group(2))
        block = (start // 1000) * 1000
        for f in sorted(d.glob(f"round*/{cond}_eval_*.jsonl")):
            split = f.stem.rsplit("_eval_", 1)[1]
            out[cond][split][block].extend(jsonl(f))
    return {c: {s: dict(b) for s, b in sp.items()} for c, sp in out.items()}


def rate(recs: list[dict[str, Any]]) -> tuple[float, int]:
    n = len(recs)
    return (100 * sum(1 for r in recs if r.get("success")) / n if n else float("nan")), n


def paired(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Pairs on (seed, split, episode seed) present in both conditions."""
    ka = {(r["seed"], r["split"]): int(bool(r.get("success"))) for r in a}
    kb = {(r["seed"], r["split"]): int(bool(r.get("success"))) for r in b}
    keys = sorted(set(ka) & set(kb))
    return [(ka[k], kb[k]) for k in keys]


def diff_stats(pairs: list[tuple[int, int]], rng: random.Random) -> dict[str, Any]:
    n = len(pairs)
    if not n:
        return {"n": 0}
    x = np.array([a for a, _ in pairs], dtype=np.int8)
    y = np.array([b for _, b in pairs], dtype=np.int8)
    pa, pb = float(x.mean()), float(y.mean())
    diff = 100 * (pa - pb)
    se = 100 * ((pa * (1 - pa) / n) + (pb * (1 - pb) / n)) ** 0.5
    d = (x.astype(np.int16) - y.astype(np.int16)).astype(np.int8)
    gen = np.random.default_rng(rng.randrange(2**32))
    idx = gen.integers(0, n, size=(BOOT, n))
    boots = np.sort(100 * d[idx].mean(axis=1))
    return {
        "n": n,
        "diff": diff,
        "se_pooled_normal": se,
        "ci95_boot": [float(boots[int(0.025 * BOOT)]), float(boots[int(0.975 * BOOT)])],
        "z": diff / se if se else float("nan"),
    }


def cells_by_seed_common(
    cells: dict[str, dict[str, dict[int, list[dict[str, Any]]]]], a: str, b: str, split: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Records of ``a`` and ``b`` on the seeds both have for ``split``."""
    sa, sb = cells.get(a, {}).get(split, {}), cells.get(b, {}).get(split, {})
    common = sorted(set(sa) & set(sb))
    return [r for s in common for r in sa[s]], [r for s in common for r in sb[s]]


# ---------------------------------------------------------------------------- spend
def spend() -> dict[str, dict[str, float]]:
    """USD by run dir and budget for Round-1 run ids (``r1-*``); rows with a Phase-0 run id (R's
    reused corpus) are reported under ``<dir>/reused-phase0``."""
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for d in sorted(RUNS.glob("r1-*")):
        if not d.is_dir():
            continue
        files = (
            [d / "ledger.jsonl"]
            if (d / "ledger.jsonl").exists()
            else list(d.glob("ledger.*.jsonl"))
        )
        for sub in d.glob("*/"):
            if (sub / "ledger.jsonl").exists():
                files.append(sub / "ledger.jsonl")
        for f in files:
            for r in jsonl(f):
                if r.get("event") != "call":
                    continue
                key = (
                    d.name
                    if str(r.get("run_id", "")).startswith("r1-")
                    else f"{d.name}/reused-phase0"
                )
                out[key][str(r.get("budget"))] += float(r.get("usd") or 0.0)
    return {k: dict(v) for k, v in out.items()}


# ---------------------------------------------------------------------------- report
def fmt(x: float | None, nd: int = 1) -> str:
    return "-" if x is None or x != x else f"{x:.{nd}f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "round1.md"))
    ap.add_argument("--seed", type=int, default=20260908)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    out_dir = RESULTS / "r1"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# E1-SL Round 1 (PREREG7 + Amendments 1-2)", ""]

    # ---- C1
    c1_rows = {arm: c1(arm, rng) for arm in ARMS}
    (out_dir / "c1.json").write_text(json.dumps(c1_rows, indent=1), encoding="utf-8")
    lines += [
        "## C1 — learnable transformed environments per 1,000 charged search rollouts (Protocol T2)",  # noqa: E501
        "",
        "| arm | transformed envs | learnable (B_L at K=16) | search rollouts | per 1,000 [95% CI, task bootstrap] | band tasks learnable (secondary) |",  # noqa: E501
        "|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        r = c1_rows[arm]
        ci = f"[{fmt(r['ci95'][0])}, {fmt(r['ci95'][1])}]" if r["ci95"] else "-"
        lines.append(
            f"| {ARM_LABEL[arm]} | {r['transformed_envs']} | {r['learnable_transformed']} | {r['search_rollouts']} "  # noqa: E501
            f"| {fmt(r['per_1000'])} {ci} | {r['band_tasks_learnable']} |"
        )
    a, rr, g = c1_rows["A"], c1_rows["R"], c1_rows["G"]
    c1_ar = a["per_1000"] > rr["per_1000"]
    c1_ag = a["per_1000"] > g["per_1000"]
    lines += [
        "",
        f"**C1 outcome: A > R {'holds' if c1_ar else 'fails'} ({fmt(a['per_1000'])} vs {fmt(rr['per_1000'])}); "  # noqa: E501
        f"A > G {'holds' if c1_ag else 'fails'} ({fmt(a['per_1000'])} vs {fmt(g['per_1000'])}) (point estimates).**",  # noqa: E501
        "",
    ]

    # ---- statuses, unlocked zero tasks, family of origin
    st: dict[str, Any] = {}
    lines += [
        "## Per-arm task statuses",
        "",
        "| arm | " + " | ".join(STATUSES) + " |",
        "|---|" + "---|" * len(STATUSES),
    ]
    for arm in ("A", "Aex", "AplusH"):
        s = statuses(arm)
        counts = {k: sum(1 for p in s.values() if p.get("status") == k) for k in STATUSES}
        st[arm] = counts
        lines.append(f"| {ARM_LABEL[arm]} | " + " | ".join(str(counts[k]) for k in STATUSES) + " |")
    lines += ["", "| arm | accepted | all_rejected | skipped |", "|---|---|---|---|"]
    for arm in ("R", "G", "Gplus"):
        rs = released_statuses(arm)
        counts = {
            k: sum(1 for v in rs.values() if v == k)
            for k in ("accepted", "all_rejected", "skipped")
        }
        st[arm] = counts
        lines.append(
            f"| {ARM_LABEL[arm]} | {counts['accepted']} | {counts['all_rejected']} | {counts['skipped']} |"  # noqa: E501
        )
    shared = shared_confirm()
    zero_tasks = sorted(
        {t for t, e in shared.items() if e.get("successes") == 0},
    )
    unlocked: dict[str, list[str]] = {}
    for arm in ("A", "Aex", "AplusH"):
        conf = confirm_summary(arm)
        unlocked[arm] = sorted(
            {
                str(e["task"])
                for e in conf.values()
                if e.get("kind") == "stage"
                and e.get("learnable")
                and f"{e['task']}:orig" in {z for z in zero_tasks}
            },
            key=int,
        )
    st["zero_tasks_shared_K16"] = [z.split(":")[0] for z in zero_tasks]
    st["unlocked"] = unlocked
    fam: dict[str, dict[str, int]] = {}
    for arm in ("A", "Aex"):
        fc: dict[str, int] = defaultdict(int)
        for e in jsonl(RUNS / f"r1-{arm}" / "corpus.jsonl"):
            meta = e.get("aea") or {}
            if meta.get("kind") == "knob":
                fc[f"{meta.get('source')}:{meta.get('family')}"] += 1
            elif meta.get("kind") == "stage":
                fc["stage"] += 1
        fam[arm] = dict(fc)
    st["family_of_origin"] = fam
    (out_dir / "statuses.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
    lines += [
        "",
        f"Zero tasks at the shared K=16 (0/16 on the original environment): {len(st['zero_tasks_shared_K16'])}"  # noqa: E501
        + (
            f" (task {', '.join(st['zero_tasks_shared_K16'])}). "
            if st["zero_tasks_shared_K16"]
            else ". "
        )
        + f"Unlocked zero tasks (learnable accepted stage): A {unlocked['A'] or 'none'}; A-ex {unlocked['Aex'] or 'none'}.",  # noqa: E501
        f"Family of origin of accepted environments — A: {fam.get('A')}; A-ex: {fam.get('Aex')}.",
        "",
    ]

    # ---- C2
    cells = eval_cells()
    ev: dict[str, Any] = {}
    lines += [
        "## C2 — held-out success (released eval, %; pooled over seeds, per-seed in brackets)",
        "",
        "| condition | seeds | ID | OOD |",
        "|---|---|---|---|",
    ]
    for cond in sorted(cells, key=lambda c: (c.split("_")[0] not in ("N", "O"), c)):
        row: dict[str, Any] = {}
        cellparts = []
        for split in SPLITS:
            by_seed = cells[cond].get(split, {})
            pooled = [r for s in sorted(by_seed) for r in by_seed[s]]
            p, n = rate(pooled)
            per = " / ".join(fmt(rate(by_seed[s])[0]) for s in sorted(by_seed))
            row[split] = {"rate": p, "n": n, "per_seed": {s: rate(by_seed[s])[0] for s in by_seed}}
            cellparts.append(f"{fmt(p)} (n={n}) [{per}]")
        ev[cond] = row
        seeds = sorted(set().union(*(set(cells[cond].get(s, {})) for s in SPLITS)))
        lines.append(f"| {cond} | {len(seeds)} | {cellparts[0]} | {cellparts[1]} |")
    comparisons = [
        ("A_U", "O_U", "A vs O (U; pre-registered)"),
        ("A_U", "R_U", "A vs R (U; pre-registered inequality)"),
        ("A_T2", "R_T2", "A vs R (T2; transformation-only)"),
        ("A_U", "G_U", "A vs G (U)"),
        ("A_T2", "G_T2", "A vs G (T2)"),
        ("A_U", "N", "A vs N (U)"),
        ("R_U", "N", "R vs N (U)"),
        ("O_U", "N", "O vs N"),
        ("A_U", "Aex_U", "A vs A-ex (U; ablation)"),
        ("A_T2", "Aex_T2", "A vs A-ex (T2; ablation)"),
        ("Gplus_U", "G_U", "G+ vs G (U; ablation)"),
        ("Gplus_T2", "G_T2", "G+ vs G (T2; ablation)"),
        ("AplusH_U", "A_U", "A+H vs A (U)"),
        ("AplusH_T2", "A_T2", "A+H vs A (T2)"),
        ("A_rel", "R_rel", "A vs R (released protocol)"),
        ("A_rel", "A_U", "A released vs A single-success (U)"),
        ("R_rel", "R_U", "R released vs R single-success (U)"),
    ]
    comp: dict[str, Any] = {}
    lines += [
        "",
        "Paired differences (points; pairs = same seed, split and episode; 10k bootstrap; SE = pooled normal):",  # noqa: E501
        "",
        "| comparison | ID diff [95% CI] (SE) | OOD diff [95% CI] (SE) | pairs |",
        "|---|---|---|---|",
    ]
    for a_c, b_c, label in comparisons:
        if a_c not in cells or b_c not in cells:
            continue
        parts = []
        rec: dict[str, Any] = {}
        for split in SPLITS:
            ra, rb = cells_by_seed_common(cells, a_c, b_c, split)
            d = diff_stats(paired(ra, rb), rng)
            rec[split] = d
            if d["n"]:
                parts.append(
                    f"{d['diff']:+.1f} [{d['ci95_boot'][0]:+.1f}, {d['ci95_boot'][1]:+.1f}] ({d['se_pooled_normal']:.1f})"  # noqa: E501
                )
            else:
                parts.append("-")
        comp[f"{a_c}-{b_c}"] = rec
        lines.append(
            f"| {label} | {parts[0]} | {parts[1]} | {rec['in_distribution'].get('n', 0)} |"
        )
    (out_dir / "evals.json").write_text(
        json.dumps({"cells": ev, "comparisons": comp}, indent=1), encoding="utf-8"
    )

    def gap(a_c: str, b_c: str, split: str) -> dict[str, Any]:
        rec: dict[str, Any] = comp.get(f"{a_c}-{b_c}", {}).get(split, {"n": 0})
        return rec

    # ---- A2.2 seed extension
    ext_reasons = []
    for a_c, b_c in (("A_U", "R_U"), ("A_U", "O_U")):
        d = gap(a_c, b_c, "in_distribution")
        if d.get("n") and d["se_pooled_normal"] and 1.0 <= abs(d["z"]) <= 2.0:
            ext_reasons.append(f"{a_c} - {b_c} on ID: {d['diff']:+.1f} = {d['z']:.2f} SE")
    lines += [
        "",
        "## A2.2 seed-extension decision",
        "",
        (
            "Extension to 12 seeds for A, R, O, N is TRIGGERED (|gap| between 1 and 2 SE on ID): "
            + "; ".join(ext_reasons)
            if ext_reasons
            else "No extension: no ID gap of A - R (U) or A - O (U) lies between 1 and 2 SE."
        ),
        "",
    ]

    # ---- C2 outcome and stop rule
    def point(a_c: str, b_c: str, split: str) -> float | None:
        d = gap(a_c, b_c, split)
        return float(d["diff"]) if d.get("n") else None

    c2_ao = [point("A_U", "O_U", s) for s in SPLITS]
    c2_ar = [point("A_U", "R_U", s) for s in SPLITS]
    c2_hold = all(x is not None and x >= 0 for x in c2_ao + c2_ar)
    ci_excl = any(
        gap("A_U", "R_U", s).get("n")
        and (gap("A_U", "R_U", s)["ci95_boot"][0] > 0 or gap("A_U", "R_U", s)["ci95_boot"][1] < 0)
        for s in SPLITS
    )
    lines += [
        "## C2 outcome (round 1)",
        "",
        f"**A ≥ O (U): ID {fmt(c2_ao[0])}, OOD {fmt(c2_ao[1])}; A ≥ R (U): ID {fmt(c2_ar[0])}, OOD {fmt(c2_ar[1])} → "  # noqa: E501
        f"{'holds' if c2_hold else 'fails'} on point estimates; A - R 95% CI excluding 0 on ID or OOD: {'yes' if ci_excl else 'no'}.**",  # noqa: E501
        "",
    ]
    below = all(x is not None and x < -3.0 for x in c2_ar)
    c1_below = c1_rows["A"]["per_1000"] < c1_rows["R"]["per_1000"]
    stop = below or c1_below
    lines += [
        "## Stop rule (PREREG7)",
        "",
        f"A - R (U) on ID {fmt(c2_ar[0])} and OOD {fmt(c2_ar[1])} (both below -3.0: {'yes' if below else 'no'}); "  # noqa: E501
        f"A's C1 rate below R's: {'yes' if c1_below else 'no'}.",
        "",
        f"**Stop-rule verdict: {'STOP — rounds 2-3 do not run; diagnosis required' if stop else "PASS — rounds 2-3 may run on the owner's go"}.**"  # noqa: E501
        + (
            " (Applied before the A2.2 extension; the extension is pending.)" if ext_reasons else ""
        ),
        "",
    ]

    # ---- accounting
    sp = spend()
    (out_dir / "spend.json").write_text(json.dumps(sp, indent=1), encoding="utf-8")
    lines += [
        "## Accounting",
        "",
        "| arm / run | search rollouts (charged) | learnable transformed | per 1,000 | USD by budget |",  # noqa: E501
        "|---|---|---|---|---|",
    ]
    acc_rows = []
    for arm in [*ARMS, "O"]:
        rolls = search_rollouts(arm)
        c = c1_rows.get(arm, {})
        usd = sp.get(f"r1-{arm}", {})
        usd_s = ", ".join(f"{k} {v:.2f}" for k, v in sorted(usd.items()))
        lines.append(
            f"| {ARM_LABEL[arm]} | {sum(rolls.values())} | {c.get('learnable_transformed', '-')} | {fmt(c.get('per_1000'))} | {usd_s or '-'} |"  # noqa: E501
        )
        for t, n in sorted(rolls.items(), key=lambda kv: int(kv[0])):
            acc_rows.append({"arm": arm, "task_id": t, "budget": "search", "rollouts": n})
    for name in ("r1-shared", "r1-banks", "r1-eval"):
        usd = sp.get(name, {})
        if usd:
            lines.append(
                f"| {name} | - | - | - | "
                + ", ".join(f"{k} {v:.2f}" for k, v in sorted(usd.items()))
                + " |"
            )
    total = sum(v for k, arm in sp.items() if "/reused" not in k for v in arm.values())
    reused = sum(v for k, arm in sp.items() if "/reused" in k for v in arm.values())
    lines += [
        "",
        f"Round 1 spend USD {total:.2f} (Round-1 run ids; R's reused corpus USD {reused:.2f} was "
        f"counted in Phase 0); E1-SL total USD {99.08 + total:.2f} against the soft gate 500 and "
        "hard cap 560.",
        "",
    ]
    with (out_dir / "accounting.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["arm", "task_id", "budget", "rollouts"])
        w.writeheader()
        w.writerows(acc_rows)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
