# ruff: noqa: E501  (report-generation script: long markdown rows and SVG text)
"""Phase 3.3a tables (PREREG_STAGE_PROFILE) -> experiments/alfworld_e6/results/stage_profile.jsonl,
stage_profile.md and figures/stage_profile.svg. Raw measured anchors only: no fit, no smoothing,
no isotonic regression. Every operational rule (leverage, dead / easy / useful thresholds,
meaningful reversal, categories, decision) is the pre-registered one, applied mechanically.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_profile as ep

DEAD_MAX = 1  # successes of 8: <= 1 is dead
EASY_MIN = 6  # >= 6 is easy
USEFUL = (3, 5)  # the operational target band, descriptive here
LEVERAGE_MIN_GAIN = 3  # max_t s(t) - s(0) >= 3 successes of 8
REVERSAL_MIN_DROP = 2  # an adjacent decrease of >= 2 successes is a meaningful reversal


def per_task() -> list[dict[str, Any]]:
    refs = ep.references()
    stages = e3.jsonl(ep.stages_file())
    probes = {(str(r["task_id"]), int(r["t"])): r for r in e3.jsonl(ep.profile_file())}
    out: list[dict[str, Any]] = []
    for t in ep.TASKS:
        task = str(t)
        ref = refs.get(task)
        row: dict[str, Any] = {
            "task": task,
            "reference_available": bool(ref and ref.get("success")),
        }
        if not row["reference_available"]:
            row["reference_reason"] = (ref or {}).get("reason", "missing")
            row["category"] = "REFERENCE_UNAVAILABLE"
            out.append(row)
            continue
        assert ref is not None
        row["reference_id"] = ref["reference_id"]
        row["T"] = ref["n_steps"]
        anchors: list[dict[str, Any]] = []
        for stg in sorted(
            (x for x in stages if str(x["task_id"]) == task), key=lambda x: int(x["t"])
        ):
            p = probes.get((task, int(stg["t"])))
            anchors.append(
                {
                    "t": int(stg["t"]),
                    "frac": round(float(stg["frac"]), 3),
                    "valid": bool(stg.get("valid")),
                    "terminal": stg.get("terminal_reference_state"),
                    "probeable": bool(stg.get("probeable")),
                    "successes": None if p is None else int(p["successes"]),
                    "n": None if p is None else int(p["n"]),
                    "errors": None if p is None else int(p["errors"]),
                }
            )
        row["anchors"] = anchors
        measured = [a for a in anchors if a["probeable"] and a["successes"] is not None and a["n"]]
        s: list[int] = [int(a["successes"] or 0) for a in measured]
        row["n_anchors_defined"] = len(anchors)
        row["n_anchors_invalid"] = sum(1 for a in anchors if not a["valid"])
        row["n_anchors_terminal"] = sum(1 for a in anchors if a["valid"] and a["terminal"])
        row["n_anchors_measured"] = len(measured)
        if len(measured) < 2 or measured[0]["t"] != 0:
            row["category"] = "INSUFFICIENT_ANCHORS"
            out.append(row)
            continue
        s0 = s[0]
        row["s0"], row["min"], row["max"], row["range"] = s0, min(s), max(s), max(s) - min(s)
        deltas = [b - a for a, b in itertools.pairwise(s)]
        row["increases"] = sum(1 for d in deltas if d > 0)
        row["decreases"] = sum(1 for d in deltas if d < 0)
        row["ties"] = sum(1 for d in deltas if d == 0)
        row["meaningful_reversals"] = sum(1 for d in deltas if d <= -REVERSAL_MIN_DROP)
        row["fraction_nondecreasing"] = (
            round((len(deltas) - row["decreases"]) / len(deltas), 3) if deltas else None
        )
        row["leverage"] = (max(s) - s0) >= LEVERAGE_MIN_GAIN
        row["any_success_after_staging"] = any(
            int(a["successes"] or 0) >= 1 for a in measured if int(a["t"]) > 0
        )
        row["useful_anchor"] = any(USEFUL[0] <= v <= USEFUL[1] for v in s)
        row["dead_to_easy"] = any(
            s[i] <= DEAD_MAX and s[j] >= EASY_MIN
            for i in range(len(s))
            for j in range(i + 1, len(s))
        )
        row["dead_to_useful"] = any(
            s[i] <= DEAD_MAX and USEFUL[0] <= s[j] <= USEFUL[1]
            for i in range(len(s))
            for j in range(i + 1, len(s))
        )
        if not row["leverage"]:
            cat = "NO_LEVERAGE"
        elif row["meaningful_reversals"] >= 1:
            cat = "LEVERAGED_BUT_NONMONOTONIC"
        elif not row["useful_anchor"] and row["dead_to_easy"]:
            cat = "STEP_LIKE"
        else:
            cat = "ORDERED_FRONTIER"
        row["category"] = cat
        row["already_useful_at_anchor"] = row["useful_anchor"]
        out.append(row)
    return out


def decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    avail = [r for r in rows if r.get("reference_available")]
    measured = [r for r in avail if r.get("category") not in ("INSUFFICIENT_ANCHORS",)]
    n_defined = sum(int(r.get("n_anchors_defined", 0)) for r in avail)
    n_invalid = sum(int(r.get("n_anchors_invalid", 0)) for r in avail)
    out: dict[str, Any] = {
        "tasks": len(rows),
        "references_available": len(avail),
        "tasks_measured": len(measured),
        "anchors_defined": n_defined,
        "anchors_invalid": n_invalid,
    }
    lev = sum(1 for r in measured if r.get("leverage"))
    front = sum(1 for r in measured if r.get("useful_anchor") or r.get("dead_to_easy"))
    nonmono = sum(1 for r in measured if r.get("category") == "LEVERAGED_BUT_NONMONOTONIC")
    step = sum(1 for r in measured if r.get("category") == "STEP_LIKE")
    ordered = sum(1 for r in measured if r.get("category") == "ORDERED_FRONTIER")
    out.update(
        leverage=lev,
        any_success_after_staging=sum(1 for r in measured if r.get("any_success_after_staging")),
        useful_band_anchor=sum(1 for r in measured if r.get("useful_anchor")),
        dead_to_easy=sum(1 for r in measured if r.get("dead_to_easy")),
        frontier_evidence=front,
        ordered_frontier=ordered,
        nonmonotonic=nonmono,
        step_like=step,
        no_leverage=sum(1 for r in measured if r.get("category") == "NO_LEVERAGE"),
    )
    if len(avail) < 4 or (n_defined and n_invalid > n_defined / 3) or len(measured) < 4:
        out["decision"] = "INCONCLUSIVE"
        out["reason"] = (
            "fewer than 4 verified references / measured tasks, or more than a third of the anchors invalid"
        )
    elif lev < 3:
        out["decision"] = "STAGE_AXIS_NO_LEVERAGE"
    elif lev >= 4 and front >= 3 and nonmono < lev / 2:
        out["decision"] = "STAGE_AXIS_SUPPORTS_CONTROL"
    elif nonmono >= lev / 2:
        out["decision"] = "STAGE_AXIS_EFFECTIVE_BUT_NOT_ORDERED"
    else:
        out["decision"] = "STAGE_AXIS_TOO_STEP_LIKE"
        out["reason"] = (
            "leverage present but frontier evidence / resolution insufficient (residual rule)"
        )
    return out


def svg(rows: list[dict[str, Any]]) -> str:
    """Small multiples: raw anchors (t/T vs successes of 8), the 3..5 band shaded; no curve."""
    w, h, pad = 220, 150, 28
    cols = 3
    n = len(rows)
    rws = (n + cols - 1) // cols
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols * w}" height="{rws * h}" font-family="sans-serif" font-size="10">'
    ]
    for i, r in enumerate(rows):
        x0, y0 = (i % cols) * w, (i // cols) * h
        parts.append(
            f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="white" stroke="#ccc"/>'
        )
        parts.append(
            f'<text x="{x0 + 6}" y="{y0 + 12}">task {r["task"]}: {r.get("category")}</text>'
        )
        px, py, pw, ph = x0 + pad, y0 + 18, w - pad - 8, h - pad - 18

        # band 3..5 of 8
        def yb(v: float, py: float = py, ph: float = ph) -> float:
            return py + ph - (v / 8.0) * ph

        parts.append(
            f'<rect x="{px}" y="{yb(5)}" width="{pw}" height="{yb(3) - yb(5)}" fill="#e8f5e9"/>'
        )
        parts.append(
            f'<line x1="{px}" y1="{py + ph}" x2="{px + pw}" y2="{py + ph}" stroke="#333"/>'
        )
        parts.append(f'<line x1="{px}" y1="{py}" x2="{px}" y2="{py + ph}" stroke="#333"/>')
        for v in (0, 4, 8):
            parts.append(f'<text x="{px - 14}" y="{yb(v) + 3}">{v}</text>')
        parts.append(f'<text x="{px + pw - 30}" y="{py + ph + 12}">t/T</text>')
        for a in r.get("anchors", []):
            x = px + float(a["frac"]) * pw
            if a.get("successes") is not None and a.get("probeable"):
                parts.append(
                    f'<circle cx="{x:.1f}" cy="{yb(a["successes"]):.1f}" r="4" fill="#1565c0"/>'
                )
                parts.append(
                    f'<text x="{x - 6:.1f}" y="{yb(a["successes"]) - 6:.1f}">{a["successes"]}/{a["n"]}</text>'
                )
            elif a.get("terminal"):
                parts.append(f'<text x="{x - 4:.1f}" y="{py + ph - 4}" fill="#999">T</text>')
            else:
                parts.append(f'<text x="{x - 4:.1f}" y="{py + ph - 4}" fill="#c62828">x</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    rows = per_task()
    d = decision(rows)
    spend = {
        p.name: round(e3.dir_spend(p), 2) for p in sorted(ep.RUNS.glob("e6-profile*")) if p.is_dir()
    }
    pool_spend = (
        round(e3.dir_spend(ep.RUNS / "e6-pool2-k16"), 2)
        if (ep.RUNS / "e6-pool2-k16").exists()
        else None
    )
    ep.RESULTS.mkdir(parents=True, exist_ok=True)
    (ep.RESULTS / "figures").mkdir(exist_ok=True)
    with (ep.RESULTS / "stage_profile.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    (ep.RESULTS / "figures" / "stage_profile.svg").write_text(svg(rows), encoding="utf-8")
    lines: list[str] = []
    lines.append(
        "# Phase 3.3a: Stage-depth response surface along a verified reference (PREREG_STAGE_PROFILE)\n"
    )
    lines.append(
        f"Method code frozen at {ep.METHOD_SHA}; prereg commit {ep.PREREG_SHA}; run `runs/{ep.RUN_ID}`. Generated by `scripts/make_tables_e6_profile.py`; raw anchors, no fit.\n"
    )
    lines.append(
        "## Raw anchor responses (successes of 8; T = terminal after full replay, x = invalid)\n"
    )
    lines.append("| task | T (expert actions) | anchors t (t/T) | successes / n at each anchor |")
    lines.append("|---|---|---|---|")
    for r in rows:
        if not r.get("reference_available"):
            lines.append(
                f"| {r['task']} | - | - | REFERENCE_UNAVAILABLE ({r.get('reference_reason')}) |"
            )
            continue
        cuts = "; ".join(f"{a['t']} ({a['frac']:.2f})" for a in r["anchors"])
        vals = "; ".join(
            f"t={a['t']}: "
            + (
                f"{a['successes']}/{a['n']}"
                if a.get("successes") is not None
                else ("T" if a.get("terminal") else "x")
            )
            for a in r["anchors"]
        )
        lines.append(f"| {r['task']} | {r['T']} | {cuts} | {vals} |")
    lines.append("\n## Per-task profile metrics\n")
    lines.append(
        "| task | measured anchors | s(0) | min | max | range | increases | decreases | ties | meaningful reversals | fraction nondecreasing | leverage | any success after staging | useful-band anchor | dead-to-easy | dead-to-useful | category |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if "s0" not in r:
            lines.append(
                f"| {r['task']} | {r.get('n_anchors_measured', '-')} | - | - | - | - | - | - | - | - | - | - | - | - | - | - | {r.get('category')} |"
            )
            continue
        lines.append(
            f"| {r['task']} | {r['n_anchors_measured']} | {r['s0']} | {r['min']} | {r['max']} | {r['range']} | {r['increases']} | {r['decreases']} | {r['ties']} | {r['meaningful_reversals']} | {r['fraction_nondecreasing']} | {r['leverage']} | {r['any_success_after_staging']} | {r['useful_anchor']} | {r['dead_to_easy']} | {r['dead_to_useful']} | {r['category']} |"
        )
    lines.append("\n## Aggregate\n")
    for k, v in d.items():
        lines.append(f"- {k}: {v}")
    lines.append(
        f"\n## Decision (pre-registered rule applied mechanically)\n\n**{d['decision']}**"
        + (f" ({d['reason']})" if d.get("reason") else "")
    )
    lines.append(
        f"\nSpend: profile probes {json.dumps(spend)} (cap {ep.CAP_USD}); fresh-pool K16 {pool_spend}; reference generation in-process (USD 0)."
    )
    lines.append("\n![stage profile](figures/stage_profile.svg)")
    narrative = ep.RESULTS / "stage_profile_narrative.md"
    if narrative.exists():
        lines.append("\n" + narrative.read_text(encoding="utf-8").rstrip())
    (ep.RESULTS / "stage_profile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
