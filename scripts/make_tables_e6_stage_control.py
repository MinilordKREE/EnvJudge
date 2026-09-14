# ruff: noqa: E501  (report-generation script: long markdown rows)
"""E6 LOW stage control tables (PREREG_LOW_STAGE_CONTROL) ->
experiments/alfworld_e6/results/e6_low_stage_control.md (+ _data.json): paired arm-A (refalign)
/ arm-B (stage control) outcomes on the eight untouched LOW_POOL_2 tasks, arm-B controller
diagnostics (t_max verdict, unique cuts, final bracket, accepted depth), conversion, gates, the
provenance-based leakage audit, K16 confirmations, and the pre-registered five-way decision
applied mechanically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_refalign as er
import e6_stage_control as sc
import make_tables_e6_refalign as mr

ORDINAL = {"dead": 0, "leveraged_outside_target": 1, "accepted": 2, "accepted_confirmed": 3}


def fmt(x: Any) -> str:
    return mr.fmt(x)


def arm_rows(arm: str) -> dict[str, dict[str, Any]]:
    rows = mr.arm_rows(arm)
    d = er.RUNS / er.ARM_IDS[arm]
    ev = e3.jsonl(d / "events.jsonl")
    for e in ev:
        p = e.get("payload") or {}
        t = str(p.get("task_id"))
        if e.get("kind") == "stage_control" and t in rows:
            rows[t]["stage_control"] = {
                k: p.get(k)
                for k in (
                    "T",
                    "t_max",
                    "t_max_verdict",
                    "history",
                    "lo",
                    "hi",
                    "status",
                    "unique_cuts",
                    "accepted_t",
                    "accepted_d",
                )
            }
        if e.get("kind") == "stage_family" and t in rows:
            rows[t]["stage_family"] = {k: p.get(k) for k in ("T", "t_max", "rejected")}
    for r in rows.values():
        probes = r.get("probe") or []
        r["leverage"] = any(int(p.get("successes", 0)) >= 1 for p in probes)
        conf = r.get("confirm") or {}
        if r.get("outcome") == "accepted":
            r["category"] = "accepted_confirmed" if conf.get("in_band_l") else "accepted"
        elif r["leverage"]:
            r["category"] = "leveraged_outside_target"
        elif r.get("regime") == "zero":
            r["category"] = "dead"
        else:
            r["category"] = None
    return rows


def counts(rows: dict[str, dict[str, Any]], zero: list[str]) -> dict[str, Any]:
    rs = [rows[t] for t in zero if t in rows]
    out: dict[str, Any] = {
        "accepted": sum(1 for r in rs if r.get("outcome") == "accepted"),
        "k16_confirmed": sum(1 for r in rs if r.get("category") == "accepted_confirmed"),
        "leveraged_outside_target": sum(
            1 for r in rs if r.get("category") == "leveraged_outside_target"
        ),
        "dead": sum(1 for r in rs if r.get("category") == "dead"),
        "leverage": sum(1 for r in rs if r.get("leverage")),
        "budget": sum(1 for r in rs if r.get("reason") == "budget"),
        "resolution_limited": sum(1 for r in rs if r.get("reason") == "resolution_limited"),
        "nonmonotonic_profile": sum(1 for r in rs if r.get("reason") == "nonmonotonic_profile"),
        "invalid_stage": sum(
            1 for r in rs if r.get("reason") in ("invalid_stage", "uncertified", "no_stage_family")
        ),
        "no_stage_leverage": sum(1 for r in rs if r.get("reason") == "no_stage_leverage"),
        "probe_rollouts": sum(int(r.get("probe_rollouts", 0)) for r in rs),
    }
    out["conversion"] = (out["accepted"] / out["leverage"]) if out["leverage"] else None
    return out


def decision(
    rows_a: dict[str, dict[str, Any]], rows_b: dict[str, dict[str, Any]], g: dict[str, Any]
) -> dict[str, Any]:
    zero = [
        t
        for t in rows_b
        if rows_b[t].get("regime") == "zero" and rows_a.get(t, {}).get("regime") == "zero"
    ]
    out: dict[str, Any] = {"tasks": list(rows_b), "zero_tasks": zero, "n_zero": len(zero)}
    ca, cb = counts(rows_a, zero), counts(rows_b, zero)
    out["A"], out["B"] = ca, cb
    wins = {"A": 0, "tie": 0, "B": 0}
    for t in zero:
        a, b = (
            ORDINAL.get(rows_a[t].get("category") or "", -1),
            ORDINAL.get(rows_b[t].get("category") or "", -1),
        )
        wins["B" if b > a else ("A" if a > b else "tie")] += 1
    out["paired"] = wins
    sc_b = [rows_b[t].get("stage_control") or {} for t in zero]
    out["t_max_verdicts"] = {
        v: sum(1 for s in sc_b if s.get("t_max_verdict") == v)
        for v in ("too_hard", "in_band", "too_easy")
    }
    if not g.get("all_pass") or len(zero) < 6:
        out["decision"] = "INCONCLUSIVE"
        out["reason"] = (
            "a correctness gate failed"
            if not g.get("all_pass")
            else "fewer than 6 prospectively zero tasks"
        )
    elif cb["nonmonotonic_profile"] >= 3:
        out["decision"] = "AXIS_ORDERING_BREAKS"
    elif cb["accepted"] >= 3 and cb["accepted"] > ca["accepted"]:
        out["decision"] = "STAGE_CONTROL_SUPPORTED"
    elif (
        cb["accepted"] < 3
        and (wins["B"] > wins["A"] or (cb["conversion"] or 0) > (ca["conversion"] or 0))
        and cb["resolution_limited"] >= 2
    ):
        out["decision"] = "CONTROL_IMPROVES_BUT_RESOLUTION_LIMITS"
    else:
        out["decision"] = "STAGE_CONTROL_NOT_SUPPORTED"
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    rows_a, rows_b = arm_rows("A"), arm_rows("B")
    g = mr.gates(rows_a, rows_b)
    # arm B has no designer call by design: the direct/refalign mode gates do not apply to it
    g.pop("B_mode_refalign_on_every_zero_task", None)
    # arm B's Stage candidates come from the controller (prereg: source `control` for B)
    ev_b = e3.jsonl(er.RUNS / er.ARM_IDS["B"] / "events.jsonl")
    g["B_no_fallback"] = all(
        (e.get("payload") or {}).get("source") == "control"
        for e in ev_b
        if e.get("kind") == "stage_candidates"
    )
    g["A_mode_refalign_on_every_zero_task"] = all(
        r.get("mode") == "refalign"
        for r in rows_a.values()
        if r.get("regime") == "zero" and (r.get("reference") or {}).get("available")
    )
    g.pop("A_mode_direct_on_every_zero_task", None)
    g["B_no_designer_call"] = not (er.RUNS / er.ARM_IDS["B"] / "designer_calls.jsonl").exists()
    g["B_first_probe_is_t_max"] = all(
        (r.get("stage_control") or {}).get("history", [{}])[0].get("t")
        == (r.get("stage_control") or {}).get("t_max")
        for r in rows_b.values()
        if r.get("stage_control") and (r.get("stage_control") or {}).get("history")
    )
    g["B_no_duplicate_cut"] = all(
        len({h["t"] for h in (r.get("stage_control") or {}).get("history", [])})
        == len((r.get("stage_control") or {}).get("history", []))
        for r in rows_b.values()
        if r.get("stage_control")
    )
    g["all_pass"] = all(
        v is True for k, v in g.items() if not k.endswith("_audit") and k != "all_pass"
    )
    d = decision(rows_a, rows_b, g)
    spend = {
        p.name: round(e3.dir_spend(p), 2) for p in sorted(er.RUNS.glob("e6-sc-*")) if p.is_dir()
    }
    designer_usd = {}
    for arm in ("A", "B"):
        u = 0.0
        for r in e3._ledger_rows(er.RUNS / er.ARM_IDS[arm]):
            if r.get("event") == "call" and r.get("budget") == "designer":
                u += float(r.get("usd") or 0)
        designer_usd[arm] = round(u, 3)
    er.RESULTS.mkdir(parents=True, exist_ok=True)
    (er.RESULTS / "e6_low_stage_control_data.json").write_text(
        json.dumps(
            {
                "A": rows_a,
                "B": rows_b,
                "gates": g,
                "decision": d,
                "spend": spend,
                "designer_usd": designer_usd,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    lines: list[str] = []
    lines.append(
        "# E6 LOW stage control: paired shared-evidence comparison (PREREG_LOW_STAGE_CONTROL)\n"
    )
    lines.append(
        f"Method commit {sc.METHOD_SHA}; prereg commit {sc.PREREG_SHA}; runs `runs/{er.SHARED_ID}`, `runs/{er.ARM_IDS['A']}`, `runs/{er.ARM_IDS['B']}`, `runs/{er.CONFIRM_ID}`. Generated by `scripts/make_tables_e6_stage_control.py`.\n"
    )
    lines.append("## Paired per-task table\n")
    lines.append(
        "| task | shared regime (p_hat, n) | reference T | A proposals | A probe | A outcome | A K16 | A category | B t_max (verdict) | B probes (t: s/n verdict) | B final [lo, hi] | B outcome | B K16 | B category | paired |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in d["tasks"]:
        a, b = rows_a.get(t, {}), rows_b.get(t, {})
        ref = b.get("reference") or a.get("reference") or {}

        def probe_s(r: dict[str, Any]) -> str:
            return (
                "; ".join(
                    f"{p['source']}@{p['t']}: {p['successes']}/{p['n']} {p['verdict']}"
                    for p in r.get("probe", [])
                )
                or "-"
            )

        def props(r: dict[str, Any]) -> str:
            return "; ".join(f"{p['source']}@{p['step']}" for p in r.get("proposals", [])) or "-"

        def k16(r: dict[str, Any]) -> str:
            c = r.get("confirm") or {}
            return (
                f"{c['successes']}/{c['n']} (B_L {fmt(c.get('in_band_l'))}, B_T {fmt(c.get('in_band_t'))})"
                if c
                else "-"
            )

        scb = b.get("stage_control") or {}
        hist = (
            "; ".join(f"{h['t']}: {h['s']}/{h['n']} {h['verdict']}" for h in scb.get("history", []))
            or "-"
        )
        ord_a, ord_b = (
            ORDINAL.get(a.get("category") or "", -1),
            ORDINAL.get(b.get("category") or "", -1),
        )
        paired = "B better" if ord_b > ord_a else ("A better" if ord_a > ord_b else "tie")
        cells = [
            t,
            f"{a.get('regime')} ({fmt(a.get('p_hat'))}, {a.get('n_est', '-')})",
            str(ref.get("n_steps", "-")),
            props(a),
            probe_s(a),
            f"{a.get('outcome')} {a.get('reason') or ''}".strip(),
            k16(a),
            str(a.get("category")),
            f"{scb.get('t_max', '-')} ({scb.get('t_max_verdict', '-')})",
            hist,
            f"[{scb.get('lo', '-')}, {scb.get('hi', '-')}]",
            f"{b.get('outcome')} {b.get('reason') or ''}".strip(),
            k16(b),
            str(b.get("category")),
            paired,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append(f"\n## Counts over prospectively zero tasks (n = {d['n_zero']})\n")
    lines.append("| metric | arm A (llm_v1_refalign) | arm B (llm_v1_stage_control) |")
    lines.append("|---|---|---|")
    for k in (
        "accepted",
        "k16_confirmed",
        "leveraged_outside_target",
        "dead",
        "leverage",
        "conversion",
        "budget",
        "resolution_limited",
        "nonmonotonic_profile",
        "invalid_stage",
        "no_stage_leverage",
        "probe_rollouts",
    ):
        lines.append(f"| {k} | {fmt(d['A'][k])} | {fmt(d['B'][k])} |")
    lines.append(f"| designer USD | {designer_usd['A']} | {designer_usd['B']} |")
    lines.append(
        f"\nPaired ordinal outcome (dead < leveraged-outside-target < accepted < K16-confirmed accepted): A better {d['paired']['A']}, tie {d['paired']['tie']}, B better {d['paired']['B']}."
    )
    lines.append(f"\nArm B t_max verdict distribution: {json.dumps(d['t_max_verdicts'])}.")
    lines.append("\n## Arm B controller diagnostics\n")
    lines.append(
        "| task | T | t_max | t_max verdict | unique cuts | history | final [lo, hi] | status | accepted t (d = t / t_max) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for t in d["tasks"]:
        s = (rows_b.get(t) or {}).get("stage_control") or {}
        if not s:
            lines.append(
                f"| {t} | - | - | - | - | - | - | {(rows_b.get(t) or {}).get('reason', '-')} | - |"
            )
            continue
        hist = "; ".join(
            f"{h['t']}: {h['s']}/{h['n']} {h['verdict']}" for h in s.get("history", [])
        )
        acc = (
            f"{s['accepted_t']} ({fmt(s['accepted_d'])})"
            if s.get("accepted_t") is not None
            else "-"
        )
        lines.append(
            f"| {t} | {s.get('T')} | {s.get('t_max')} | {s.get('t_max_verdict')} | {s.get('unique_cuts')} | {hist} | [{s.get('lo')}, {s.get('hi')}] | {s.get('status')} | {acc} |"
        )
    lines.append("\n## Correctness gates\n")
    lines.append("| gate | status |")
    lines.append("|---|---|")
    for k, v in g.items():
        if k.endswith("_audit"):
            continue
        lines.append(f"| {k} | {fmt(v)} |")
    lines.append("\n## Exact-reference leakage audit\n")
    lines.append(
        "| arm | task | provenance intact | reference cuts | prefixes by provenance | independently emitted post-cut actions | leaks |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for arm in ("A", "B"):
        for t, a in (g[f"{arm}_audit"].get("tasks") or {}).items():
            lines.append(
                f"| {arm} | {t} | {fmt(a.get('provenance_intact'))} | {a.get('reference_cuts', '-')} | {a.get('prefixes_by_provenance', '-')} | {a.get('independent_overlap', '-')} | {a.get('leaks', a.get('reason', '-'))} |"
            )
    lines.append("\n## K16 confirmations of accepted Stages\n")
    conf_path = er.RUNS / er.CONFIRM_ID / "confirm_summary.json"
    conf = json.loads(conf_path.read_text()) if conf_path.exists() else {}
    lines.append("| env | arm | successes / n | p16 | in B_L | in B_T |")
    lines.append("|---|---|---|---|---|---|")
    for k, v in conf.items():
        lines.append(
            f"| {k} | {v.get('arm')} | {v.get('successes')} / {v.get('n')} | {fmt(v.get('p16'))} | {fmt(v.get('in_band_l'))} | {fmt(v.get('in_band_t'))} |"
        )
    if not conf:
        lines.append("| (none) | | | | | |")
    lines.append(
        f"\n## Decision (pre-registered rule applied mechanically)\n\n**{d['decision']}**"
        + (f" ({d['reason']})" if d.get("reason") else "")
    )
    lines.append(
        f"\nSpend (USD, ledgers): {json.dumps(spend)}; total {round(sum(spend.values()), 2)} of cap {sc.CAP_USD}; designer {json.dumps(designer_usd)}."
    )
    narrative = er.RESULTS / "e6_low_stage_control_narrative.md"
    if narrative.exists():
        lines.append("\n" + narrative.read_text(encoding="utf-8").rstrip())
    (er.RESULTS / "e6_low_stage_control.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in d.items() if k != "tasks"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
