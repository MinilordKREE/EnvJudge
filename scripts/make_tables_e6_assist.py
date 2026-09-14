# ruff: noqa: E501  (report-generation script: long markdown rows)
"""E6 LOW assistive Rules tables (PREREG_LOW_ASSISTIVE_RULES) ->
experiments/alfworld_e6/results/e6_low_assistive_rules.md (+ _data.json): paired arm-A (stage
control) / arm-B (assistive Rules) outcomes on the eight LOW_POOL_3 tasks, the frozen six-level
classification, K16-confirmed delivery (primary), secondary rates, the Rules behavioural-resolution
characterisation, arm-A granularity, gates, the provenance-based leakage audit, and the
pre-registered five-way decision applied mechanically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_assist as ea
import e6_refalign as er
import make_tables_e6_refalign as mr
import make_tables_e6_stage_control as msc

ea.apply()  # msc's import re-targeted e6_refalign to the stage-control experiment

CLASSES = [
    "reference_unavailable",
    "no_leverage",
    "leveraged_unresolved",
    "search_accepted_k16_failed",
    "k16_confirmed_learnable",
    "k16_confirmed_target",
]
ORDINAL = {c: i for i, c in enumerate(CLASSES)}


def fmt(x: Any) -> str:
    return mr.fmt(x)


def _extremes(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Behavioural resolution along one family / axis: which discrete regimes were observed."""
    verdicts = {h.get("verdict") for h in history}
    intermediate = [h for h in history if 0 < int(h.get("s", 0)) < int(h.get("n", 0))]
    return {
        "probes": len(history),
        "dead": "too_hard" in verdicts,
        "easy": "too_easy" in verdicts,
        "in_band": "in_band" in verdicts,
        "intermediate_probes": len(intermediate),
        "regimes": sorted(v for v in verdicts if v),
    }


def arm_rows(arm: str) -> dict[str, dict[str, Any]]:
    rows = msc.arm_rows(arm) if arm == "A" else mr.arm_rows(arm)
    d = er.RUNS / er.ARM_IDS[arm]
    ev = e3.jsonl(d / "events.jsonl")
    calls = {str(c["task_id"]): c for c in e3.jsonl(d / "designer_calls.jsonl")}
    if arm == "B":
        # the assistive variant records its mode in the designer record (the refalign-era
        # ``llm_stage_proposals`` event does not exist on this path) and accepts a Rules
        # candidate (corpus kind ``knob``), confirmed under ``B:<candidate_id>``
        for t, c in calls.items():
            if t in rows:
                rows[t]["mode"] = c.get("mode")
        conf_path = er.RUNS / er.CONFIRM_ID / "confirm_summary.json"
        conf = json.loads(conf_path.read_text()) if conf_path.exists() else {}
        for rec in e3.jsonl(d / "corpus.jsonl"):
            a = rec["aea"]
            if a["kind"] == "knob" and str(a["task_id"]) in rows:
                r = rows[str(a["task_id"])]
                r["accepted"] = {
                    "id": a["candidate_id"],
                    "family": a.get("family"),
                    "d": a.get("d"),
                    "p_hat": a.get("p_hat"),
                }
                if f"B:{a['candidate_id']}" in conf:
                    r["confirm"] = conf[f"B:{a['candidate_id']}"]
    for e in ev:
        p = e.get("payload") or {}
        t = str(p.get("task_id"))
        if t not in rows:
            continue
        k = e.get("kind")
        if k == "llm_assist_proposals":
            rows[t]["families"] = p.get("accepted", [])
            rows[t]["families_rejected"] = p.get("rejected", [])
        elif k == "dose_control":
            rows[t].setdefault("dose_control", []).append(
                {x: p.get(x) for x in ("family", "status", "lo", "hi", "history")}
            )
        elif k == "solvable":
            rows[t].setdefault("guards", []).append(
                {"family": p.get("family"), "ok": p.get("ok"), "source": p.get("source")}
            )
        elif k == "leverage" and "tested" in p:
            rows[t].setdefault("leverage_by_family", {})[str(p.get("family"))] = bool(
                p.get("has_leverage")
            )
        elif k == "no_leverage":
            rows[t].setdefault("no_leverage_families", []).append(p.get("family"))
    for t, r in rows.items():
        c = calls.get(t)
        if c and arm == "B":
            r["families_full"] = c.get("families", [])
            r["diagnoses"] = c.get("diagnoses", [])
        probes = r.get("probe") or []
        # leverage: at least one probed intervention changed the zero response (>= 1 success)
        lev_probe = any(int(p.get("successes", 0)) >= 1 for p in probes)
        lev_fam = any(r.get("leverage_by_family", {}).values())
        dose_hist = [h for dc in r.get("dose_control", []) for h in dc.get("history", [])]
        lev_dose = any(int(h.get("s", 0)) >= 1 for h in dose_hist)
        r["leverage"] = lev_probe or lev_fam or lev_dose
        conf = r.get("confirm") or {}
        if not (r.get("reference") or {}).get("available"):
            cls = "reference_unavailable"
        elif r.get("outcome") == "accepted":
            if conf.get("in_band_t"):
                cls = "k16_confirmed_target"
            elif conf.get("in_band_l"):
                cls = "k16_confirmed_learnable"
            else:
                cls = "search_accepted_k16_failed"
        elif r["leverage"]:
            cls = "leveraged_unresolved"
        else:
            cls = "no_leverage"
        r["cls"] = cls
        # behavioural resolution along the axis
        if arm == "A":
            hist = [
                {"s": h["s"], "n": h["n"], "verdict": h["verdict"]}
                for h in (r.get("stage_control") or {}).get("history", [])
            ]
            r["resolution"] = _extremes(hist)
        else:
            per_fam = {
                dc["family"]: _extremes(
                    [
                        {"s": h["s"], "n": h["n"], "verdict": h["verdict"]}
                        for h in dc.get("history", [])
                    ]
                )
                for dc in r.get("dose_control", [])
            }
            r["resolution"] = per_fam
            r["intermediate_regime"] = any(x["intermediate_probes"] >= 1 for x in per_fam.values())
    return rows


def counts(rows: dict[str, dict[str, Any]], zero: list[str], arm: str) -> dict[str, Any]:
    rs = [rows[t] for t in zero if t in rows]
    out: dict[str, Any] = {c: sum(1 for r in rs if r.get("cls") == c) for c in CLASSES}
    out["search_accepted"] = sum(1 for r in rs if r.get("outcome") == "accepted")
    out["k16_learnable"] = out["k16_confirmed_learnable"] + out["k16_confirmed_target"]
    out["k16_target"] = out["k16_confirmed_target"]
    out["leverage"] = sum(1 for r in rs if r.get("leverage"))
    out["leverage_to_accept"] = (
        (out["search_accepted"] / out["leverage"]) if out["leverage"] else None
    )
    out["leverage_to_k16"] = (out["k16_learnable"] / out["leverage"]) if out["leverage"] else None
    out["budget"] = sum(1 for r in rs if r.get("reason") == "budget")
    out["probe_rollouts"] = sum(int(r.get("probe_rollouts", 0)) for r in rs)
    if arm == "B":
        fams = [f for r in rs for f in (r.get("families") or [])]
        rej = [x for r in rs for x in (r.get("families_rejected") or [])]
        out["valid_families"] = len(fams)
        out["rejected_families"] = len(rej)
        out["valid_family_rate"] = (len(fams) / (len(fams) + len(rej))) if (fams or rej) else None
        guards = [g for r in rs for g in (r.get("guards") or [])]
        out["solvable_rate"] = (
            (sum(1 for g in guards if g.get("ok")) / len(guards)) if guards else None
        )
        levs = [v for r in rs for v in (r.get("leverage_by_family") or {}).values()]
        out["d1_leverage_rate"] = (sum(1 for v in levs if v) / len(levs)) if levs else None
        out["dose_order_violation"] = sum(
            1 for r in rs if r.get("reason") == "dose_order_violation"
        )
        out["no_valid_proposal"] = sum(1 for r in rs if r.get("reason") == "no_valid_proposal")
        out["uncertified"] = sum(1 for r in rs if r.get("reason") == "uncertified")
        out["exhausted"] = sum(1 for r in rs if r.get("reason") == "exhausted")
        out["intermediate_regime_tasks"] = sum(1 for r in rs if r.get("intermediate_regime"))
    else:
        out["resolution_limited"] = sum(1 for r in rs if r.get("reason") == "resolution_limited")
        out["final_gaps"] = {
            t: [
                (rows[t].get("stage_control") or {}).get("lo"),
                (rows[t].get("stage_control") or {}).get("hi"),
            ]
            for t in zero
            if rows[t].get("reason") == "resolution_limited"
        }
        out["intermediate_regime_tasks"] = sum(
            1 for r in rs if (r.get("resolution") or {}).get("intermediate_probes", 0) >= 1
        )
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
    ca, cb = counts(rows_a, zero, "A"), counts(rows_b, zero, "B")
    out["A"], out["B"] = ca, cb
    wins = {"A": 0, "tie": 0, "B": 0}
    for t in zero:
        a, b = ORDINAL[rows_a[t]["cls"]], ORDINAL[rows_b[t]["cls"]]
        wins["B" if b > a else ("A" if a > b else "tie")] += 1
    out["paired"] = wins
    refs = sum(1 for t in zero if (rows_b[t].get("reference") or {}).get("available"))
    out["references_available"] = refs
    upstream = (
        cb["no_valid_proposal"] + cb["uncertified"] + cb["no_leverage"] + cb["dose_order_violation"]
    )
    out["B_upstream_failures"] = upstream
    if not g.get("all_pass") or len(zero) < 6 or refs < 4:
        out["decision"] = "INCONCLUSIVE"
        out["reason"] = (
            "a correctness gate failed"
            if not g.get("all_pass")
            else (
                "fewer than 6 prospectively zero tasks"
                if len(zero) < 6
                else "fewer than 4 verified references"
            )
        )
    elif cb["k16_learnable"] >= 3 and cb["k16_learnable"] > ca["k16_learnable"]:
        out["decision"] = "ASSISTIVE_RULES_SUPPORTED"
    elif upstream > refs / 2:
        out["decision"] = "RULE_GENERATION_FAILURE"
    elif (
        cb["k16_learnable"] < 3
        and cb["leverage"] > refs / 2
        and cb["intermediate_regime_tasks"] > ca["intermediate_regime_tasks"]
    ):
        out["decision"] = "ASSISTIVE_RULES_HAVE_LEVERAGE_BUT_CONTROL_LIMITED"
    else:
        out["decision"] = "ASSISTIVE_RULES_NOT_SUPPORTED"
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    rows_a, rows_b = arm_rows("A"), arm_rows("B")
    g = mr.gates(rows_a, rows_b)
    g.pop("B_mode_refalign_on_every_zero_task", None)
    g.pop("A_mode_direct_on_every_zero_task", None)
    ev_a = e3.jsonl(er.RUNS / er.ARM_IDS["A"] / "events.jsonl")
    g["A_no_fallback"] = all(
        (e.get("payload") or {}).get("source") == "control"
        for e in ev_a
        if e.get("kind") == "stage_candidates"
    )
    ev_b = e3.jsonl(er.RUNS / er.ARM_IDS["B"] / "events.jsonl")
    g["B_no_fallback"] = not any(
        e.get("kind") in ("stage_candidates", "stage_family", "families") for e in ev_b
    )
    g["A_no_designer_call"] = not (er.RUNS / er.ARM_IDS["A"] / "designer_calls.jsonl").exists()
    g["B_mode_assist_on_every_zero_task"] = all(
        r.get("mode") == "assist"
        for r in rows_b.values()
        if r.get("regime") == "zero" and (r.get("reference") or {}).get("available")
    )
    g["B_first_probe_is_d1"] = all(
        (dc.get("history") or [{}])[0].get("d") == 1.0
        for r in rows_b.values()
        for dc in r.get("dose_control", [])
    )
    g["B_no_axis_bypass"] = all(
        gd.get("source") != "by_construction" for r in rows_b.values() for gd in r.get("guards", [])
    )
    g["all_pass"] = all(
        v is True for k, v in g.items() if not k.endswith("_audit") and k != "all_pass"
    )
    d = decision(rows_a, rows_b, g)
    spend = {
        p.name: round(e3.dir_spend(p), 2) for p in sorted(er.RUNS.glob("e6-ar-*")) if p.is_dir()
    }
    designer_usd = {}
    for arm in ("A", "B"):
        u = 0.0
        for r in e3._ledger_rows(er.RUNS / er.ARM_IDS[arm]):
            if r.get("event") == "call" and r.get("budget") == "designer":
                u += float(r.get("usd") or 0)
        designer_usd[arm] = round(u, 3)
    er.RESULTS.mkdir(parents=True, exist_ok=True)
    (er.RESULTS / "e6_low_assistive_rules_data.json").write_text(
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
        "# E6 LOW assistive Rules: paired shared-evidence comparison (PREREG_LOW_ASSISTIVE_RULES)\n"
    )
    lines.append(
        f"Method commit {ea.METHOD_SHA}; prereg commit {ea.PREREG_SHA}; runs `runs/{er.SHARED_ID}`, `runs/{er.ARM_IDS['A']}`, `runs/{er.ARM_IDS['B']}`, `runs/{er.CONFIRM_ID}`. Generated by `scripts/make_tables_e6_assist.py`.\n"
    )
    lines.append("## Paired per-task table\n")
    lines.append(
        "| task | shared regime | reference T | A (stage control): t_max verdict, probes, outcome, K16 | A class | B (assistive Rules): families, probes (family d: s/n verdict), outcome, K16 | B class | paired |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for t in d["tasks"]:
        a, b = rows_a.get(t, {}), rows_b.get(t, {})
        ref = b.get("reference") or a.get("reference") or {}
        sca = a.get("stage_control") or {}
        a_hist = (
            "; ".join(f"{h['t']}: {h['s']}/{h['n']} {h['verdict']}" for h in sca.get("history", []))
            or "-"
        )
        a_k16 = (lambda c: f"K16 {c['successes']}/{c['n']}" if c else "")(a.get("confirm") or {})
        a_s = f"t_max {sca.get('t_max', '-')} ({sca.get('t_max_verdict', '-')}); {a_hist}; {a.get('outcome')} {a.get('reason') or ''} {a_k16}".strip()
        b_fams = "; ".join(f"{f['name']} ({f['axis']})" for f in (b.get("families") or [])) or "-"
        b_probes = "; ".join(
            f"{dc['family']} "
            + ", ".join(
                f"{h['d']}: {h['s']}/{h['n']} {h['verdict']}" for h in dc.get("history", [])
            )
            + f" -> {dc['status']}"
            for dc in b.get("dose_control", [])
        )
        b_lev = "; ".join(
            f"{f}: d=1 {'leverage' if v else 'no leverage'}"
            for f, v in (b.get("leverage_by_family") or {}).items()
        )
        b_k16 = (lambda c: f"K16 {c['successes']}/{c['n']}" if c else "")(b.get("confirm") or {})
        b_s = f"{b_fams} | {b_lev} | {b_probes or '-'} | {b.get('outcome')} {b.get('reason') or ''} {b_k16}".strip()
        ord_a, ord_b = ORDINAL.get(a.get("cls", ""), -1), ORDINAL.get(b.get("cls", ""), -1)
        paired = "B better" if ord_b > ord_a else ("A better" if ord_a > ord_b else "tie")
        lines.append(
            f"| {t} | {a.get('regime')} | {ref.get('n_steps', '-')} | {a_s} | {a.get('cls')} | {b_s} | {b.get('cls')} | {paired} |"
        )
    lines.append(
        f"\n## Counts over prospectively zero tasks (n = {d['n_zero']}; references {d['references_available']})\n"
    )
    lines.append("| metric | arm A (stage control) | arm B (assistive Rules) |")
    lines.append("|---|---|---|")
    for k in (
        "search_accepted",
        "k16_learnable",
        "k16_target",
        "search_accepted_k16_failed",
        "leveraged_unresolved",
        "no_leverage",
        "reference_unavailable",
        "leverage",
        "leverage_to_accept",
        "leverage_to_k16",
        "budget",
        "probe_rollouts",
        "intermediate_regime_tasks",
    ):
        lines.append(f"| {k} | {fmt(d['A'].get(k))} | {fmt(d['B'].get(k))} |")
    for k in (
        "valid_families",
        "rejected_families",
        "valid_family_rate",
        "solvable_rate",
        "d1_leverage_rate",
        "dose_order_violation",
        "no_valid_proposal",
        "uncertified",
        "exhausted",
    ):
        lines.append(f"| B {k} | - | {fmt(d['B'].get(k))} |")
    lines.append(f"| A resolution_limited | {fmt(d['A'].get('resolution_limited'))} | - |")
    lines.append(f"| A final gaps | {json.dumps(d['A'].get('final_gaps'))} | - |")
    lines.append(f"| designer USD | {designer_usd['A']} | {designer_usd['B']} |")
    lines.append(
        f"\nPaired (reference_unavailable < no_leverage < leveraged_unresolved < search_accepted_k16_failed < k16_confirmed_learnable < k16_confirmed_target): A better {d['paired']['A']}, tie {d['paired']['tie']}, B better {d['paired']['B']}."
    )
    lines.append("\n## Arm B: proposals and behavioural resolution\n")
    lines.append(
        "| task | family | axis | mechanism (LLM's own words) | why | d=1 guard | d=1 leverage | regimes observed along the family | intermediate probes |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for t in d["tasks"]:
        b = rows_b.get(t, {})
        for f in b.get("families_full") or []:
            g_: dict[str, Any] = next(
                (x for x in b.get("guards", []) if x.get("family") == f["name"]), {}
            )
            res = (b.get("resolution") or {}).get(f["name"], {})
            lev = (b.get("leverage_by_family") or {}).get(f["name"])
            lines.append(
                f"| {t} | {f['name']} | {f['axis']} | {str(f.get('mechanism', '')).replace('|', '/')} | {str(f.get('why', '')).replace('|', '/')} | {g_.get('source', '-')}/{fmt(g_.get('ok'))} | {fmt(lev)} | {res.get('regimes', '-')} | {res.get('intermediate_probes', '-')} |"
            )
        for rej in b.get("families_rejected") or []:
            lines.append(
                f"| {t} | (rejected) | - | {str(rej).replace('|', '/')} | - | - | - | - | - |"
            )
        if not b.get("families_full") and not b.get("families_rejected"):
            lines.append(f"| {t} | - | - | {b.get('reason', '-')} | - | - | - | - | - |")
    lines.append("\n## Arm B diagnoses (LLM's own words)\n")
    for t in d["tasks"]:
        for dg in (rows_b.get(t) or {}).get("diagnoses") or []:
            lines.append(
                f"- task {t}, {dg['failure_id']} step {dg['failure_step']} vs reference step {dg['reference_step']}: cause: {str(dg['error_cause']).replace(chr(10), ' ')}; fix hint: {str(dg['fix_hint']).replace(chr(10), ' ')}"
            )
    lines.append("\n## Correctness gates\n")
    lines.append("| gate | status |")
    lines.append("|---|---|")
    for k, v in g.items():
        if not k.endswith("_audit"):
            lines.append(f"| {k} | {fmt(v)} |")
    lines.append("\n## Exact-reference leakage audit\n")
    lines.append("| arm | task | provenance intact | prefixes by provenance | leaks |")
    lines.append("|---|---|---|---|---|")
    for arm in ("A", "B"):
        for t, a in (g[f"{arm}_audit"].get("tasks") or {}).items():
            lines.append(
                f"| {arm} | {t} | {fmt(a.get('provenance_intact'))} | {a.get('prefixes_by_provenance', '-')} | {a.get('leaks', a.get('reason', '-'))} |"
            )
    lines.append("\n## K16 confirmations of accepted environments\n")
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
        f"\nSpend (USD, ledgers): {json.dumps(spend)}; total {round(sum(spend.values()), 2)} of cap {ea.CAP_USD}; designer {json.dumps(designer_usd)}."
    )
    narrative = er.RESULTS / "e6_low_assistive_rules_narrative.md"
    if narrative.exists():
        lines.append("\n" + narrative.read_text(encoding="utf-8").rstrip())
    (er.RESULTS / "e6_low_assistive_rules.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in d.items() if k != "tasks"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
