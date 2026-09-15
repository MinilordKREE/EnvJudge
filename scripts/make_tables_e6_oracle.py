# ruff: noqa: E501  (report-generation script: long markdown rows)
"""Tables for the E6 LOW oracle actuator ceiling (PREREG_LOW_ORACLE_ACTUATOR.md): per-task
controller results of the single oracle arm O (rows of the O1 / O2 processes merged), counts,
the generated-vs-oracle decomposition table against the FROZEN phase-3.4 results (read from
``results/e6_low_assistive_rules_data.json``; never re-run), gates, the provenance-based leakage
audit, K16 confirmations and the pre-registered decision. Every number of the report comes from
this script. Oracle numbers are a ceiling, never a method result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_oracle as eo
import e6_refalign as er
import e6_smoke as e6
import make_tables_e6_assist as ma
import oracle_actuators as oa

eo.apply()  # importing the phase-3.4 tables module re-targets e6_refalign; re-target back

CLASSES = ma.CLASSES
ORDINAL = ma.ORDINAL


def rows_oracle() -> dict[str, dict[str, Any]]:
    """The oracle arm rows: the phase-3.4 arm-B row builder over each process directory (it
    reads events, corpus kind ``knob``, dose control, leverage, K16), merged by task."""
    merged: dict[str, dict[str, Any]] = {}
    for arm in er.ARM_IDS:
        saved = er.TASKS
        er.TASKS = er.arm_tasks(arm)
        try:
            rows = _assist_rows(arm)
        finally:
            er.TASKS = saved
        for t, r in rows.items():
            if int(t) in er.arm_tasks(arm):
                merged[t] = r
    return merged


def _assist_rows(arm: str) -> dict[str, dict[str, Any]]:
    # reuse the phase-3.4 row builder by temporarily aliasing this process as arm "B"
    ids, versions = dict(er.ARM_IDS), dict(er.ARM_VERSIONS)
    er.ARM_IDS = {"B": ids[arm]}
    er.ARM_VERSIONS = {"B": versions[arm]}
    try:
        rows = ma.arm_rows("B")
    finally:
        er.ARM_IDS, er.ARM_VERSIONS = ids, versions
    d = er.RUNS / ids[arm]
    ev = e6._by_kind(e6._events(d))
    for e in ev.get("oracle_actuator", []):
        t = str(e["task_id"])
        if t in rows:
            rows[t]["families"] = e.get("families", [])
            rows[t]["families_rejected"] = e.get("rejected", [])
            rows[t]["mode"] = "oracle"
    for r in rows.values():
        r["arm"] = "O"
        r["process"] = ids[arm]
    return rows


def gates(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    shared = {str(r["task_id"]): r for r in e3.jsonl(er.shared_dir() / "shared.jsonl")}
    g: dict[str, Any] = {}
    frozen_sha = {t: oa.sha(oa.template_path(t).read_text(encoding="utf-8")) for t in oa.TASKS}
    for arm in er.ARM_IDS:
        d = er.RUNS / er.ARM_IDS[arm]
        ev = e6._by_kind(e6._events(d))
        manifest = (
            json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        )
        extra = manifest.get("extra", manifest)
        g[f"{arm}_method_version_runtime"] = extra.get("method_version") == er.ARM_VERSIONS[arm]
        g[f"{arm}_manifest_oracle"] = (
            extra.get("experiment") == "oracle_actuator_ceiling"
            and extra.get("oracle_actuators_sha256_16") == frozen_sha
        )
        g[f"{arm}_shared_estimate_identical"] = all(
            str(e["task_id"]) in shared
            and e["regime"] == shared[str(e["task_id"])]["regime"]
            and e["n"] == shared[str(e["task_id"])]["n"]
            and abs(float(e["p_hat"]) - float(shared[str(e["task_id"])]["p_hat"])) < 1e-9
            for e in ev.get("estimate", [])
        )
        g[f"{arm}_shared_reference_identical"] = all(
            (shared.get(str(e["task_id"]), {}).get("reference") or {}).get("reference_id")
            == e.get("reference_id")
            for e in ev.get("reference", [])
            if e.get("available")
        )
        g[f"{arm}_no_designer_call"] = not (d / "designer_calls.jsonl").exists()
        oracle_ev = ev.get("oracle_actuator", [])
        g[f"{arm}_one_family_per_task"] = all(len(e.get("families", [])) == 1 for e in oracle_ev)
        g[f"{arm}_family_sha_frozen"] = all(
            f.get("code_sha256") == frozen_sha.get(str(e["task_id"]))
            and f.get("source") == "oracle"
            for e in oracle_ev
            for f in e.get("families", [])
        )
        g[f"{arm}_search_le_cap"] = all(
            int(e.get("n_search", 0)) <= 30 for e in ev.get("task_done", [])
        )
        g[f"{arm}_no_fallback"] = not any(
            e.get("kind") in ("stage_candidates", "stage_family", "families") for e in e6._events(d)
        )
        g[f"{arm}_first_probe_is_d1"] = all(
            (dc.get("history") or [{}])[0].get("d") == 1.0 for dc in ev.get("dose_control", [])
        )
        g[f"{arm}_no_axis_bypass"] = all(
            s.get("source") != "by_construction" for s in ev.get("solvable", [])
        )
        prefixes = [
            t
            for t in e3.jsonl(d / "traces.jsonl")
            if (t.get("candidate") or {}).get("in_env_actions")
        ] + [c for c in e3.jsonl(d / "corpus.jsonl") if c.get("in_env_actions")]
        g[f"{arm}_no_setup_prefix"] = not prefixes
        g[f"{arm}_reference_only_on_zero"] = all(
            next(
                (x["regime"] for x in ev.get("estimate", []) if x["task_id"] == e["task_id"]), None
            )
            == "zero"
            for e in ev.get("reference", [])
        )
        audit = er.leakage_audit(d)
        g[f"{arm}_reference_leakage"] = audit.get("ok", False) and not audit.get(
            "expert_recomputed"
        )
        g[f"{arm}_audit"] = audit
    g["every_task_has_a_row"] = all(
        str(t) in rows and rows[str(t)].get("outcome") for t in er.TASKS
    )
    g["method_unmodified"] = er.src_unmodified()
    g["all_pass"] = all(
        v is True for k, v in g.items() if not k.endswith("_audit") and k != "all_pass"
    )
    return g


def frozen_phase34() -> dict[str, Any]:
    p = er.RESULTS / "e6_low_assistive_rules_data.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def decomposition(rows: dict[str, dict[str, Any]], p34: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    b34 = p34.get("B", {})
    for t in map(str, er.TASKS):
        b = b34.get(t, {})
        o = rows.get(t, {})
        gen = {
            "valid": bool(b.get("families")),
            "leverage": bool(b.get("leverage")),
            "accepted": b.get("outcome") == "accepted",
            "k16": bool((b.get("confirm") or {}).get("in_band_l")),
            "cls": b.get("cls"),
        }
        orc = {
            "available": bool(o.get("families")),
            "leverage": bool(o.get("leverage")),
            "accepted": o.get("outcome") == "accepted",
            "k16": bool((o.get("confirm") or {}).get("in_band_l")),
            "cls": o.get("cls"),
        }
        if orc["k16"]:
            interp = "oracle successfully delivers useful environment" + (
                "" if gen["k16"] else " (generated did not)"
            )
        elif not orc["available"]:
            interp = "no oracle family available"
        elif not orc["leverage"] and not gen["leverage"]:
            interp = "both generated and oracle have no leverage"
        elif not orc["leverage"]:
            interp = "oracle has no leverage (generated had)"
        elif not gen["valid"] or not gen["leverage"]:
            interp = "generation failure recovered by oracle actuator (leverage), controller did not land"
        else:
            interp = "oracle has leverage but controller cannot land"
        out.append({"task": t, "generated": gen, "oracle": orc, "interpretation": interp})
    return out


def counts(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    zero = [t for t in map(str, er.TASKS) if rows.get(t, {}).get("regime") == "zero"]
    c = ma.counts(rows, zero, "B")
    c["available"] = sum(1 for t in zero if rows[t].get("families"))
    c["unique_doses"] = {
        t: sorted(
            {h["d"] for dc in rows[t].get("dose_control", []) for h in dc.get("history", [])}
            | {m["d"] for m in rows[t].get("d1_measurements", [])}
        )
        for t in zero
    }
    c["d1_leverage_tasks"] = sum(
        1 for t in zero if any((rows[t].get("leverage_by_family") or {}).values())
    )
    return c


def decision(
    rows: dict[str, dict[str, Any]], g: dict[str, Any], c: dict[str, Any]
) -> dict[str, Any]:
    n = len(er.TASKS)
    infeasible = n - c["available"]
    out: dict[str, Any] = {
        "n_tasks": n,
        "available": c["available"],
        "d1_leverage": c["d1_leverage_tasks"],
        "k16_learnable": c["k16_learnable"],
        "k16_target": c["k16_target"],
        "search_accepted": c["search_accepted"],
    }
    if not g.get("all_pass"):
        out["decision"], out["reason"] = "INCONCLUSIVE", "a correctness gate failed"
    elif infeasible >= 2:
        out["decision"] = "ORACLE_CONSTRUCTION_INFEASIBLE"
    elif c["available"] >= 6 and c["d1_leverage_tasks"] >= 5 and c["k16_learnable"] >= 3:
        out["decision"] = "GENERATION_BOTTLENECK_SUPPORTED"
    elif c["available"] >= 6 and c["d1_leverage_tasks"] >= 5:
        out["decision"] = "ACTUATOR_EXISTS_BUT_CONTROL_REMAINS_LIMITING"
    elif c["d1_leverage_tasks"] < 5:
        out["decision"] = "ASSISTIVE_RULES_ACTUATOR_NOT_SUPPORTED"
    else:
        out["decision"], out["reason"] = (
            "INCONCLUSIVE",
            "availability below 6 with leverage >= 5 (not a pre-registered state)",
        )
    return out


def fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def main(argv: list[str] | None = None) -> int:
    rows = rows_oracle()
    g = gates(rows)
    c = counts(rows)
    p34 = frozen_phase34()
    dec = decision(rows, g, c)
    decomp = decomposition(rows, p34)
    spend = {
        p.name: round(e3.dir_spend(p), 2) for p in sorted(er.RUNS.glob("e6-oa-*")) if p.is_dir()
    }
    a34, b34 = p34.get("decision", {}).get("A", {}), p34.get("decision", {}).get("B", {})
    data = {
        "rows": rows,
        "gates": g,
        "counts": c,
        "decision": dec,
        "decomposition": decomp,
        "spend": spend,
        "phase34": {"A": a34, "B": b34, "decision": p34.get("decision", {}).get("decision")},
    }
    er.RESULTS.mkdir(parents=True, exist_ok=True)
    (er.RESULTS / "e6_low_oracle_actuator_data.json").write_text(
        json.dumps(data, indent=1, default=str), encoding="utf-8"
    )
    with (er.RESULTS / "e6_low_oracle_actuator.jsonl").open("w", encoding="utf-8") as fh:
        for t in map(str, er.TASKS):
            r = rows.get(t, {})
            fh.write(
                json.dumps(
                    {
                        "task": t,
                        "arm": "oracle",
                        "process": r.get("process"),
                        "regime": r.get("regime"),
                        "reference": r.get("reference"),
                        "families": r.get("families"),
                        "outcome": r.get("outcome"),
                        "reason": r.get("reason"),
                        "n_search": r.get("n_search"),
                        "probe_rollouts": r.get("probe_rollouts"),
                        "leverage": r.get("leverage"),
                        "d1_measurements": r.get("d1_measurements"),
                        "dose_control": r.get("dose_control"),
                        "accepted": r.get("accepted"),
                        "confirm": r.get("confirm"),
                        "cls": r.get("cls"),
                        "resolution": r.get("resolution"),
                    },
                    default=str,
                )
                + "\n"
            )
    lines = [
        "# E6 LOW oracle actuator ceiling (PREREG_LOW_ORACLE_ACTUATOR)\n",
        "**Oracle / ceiling experiment.** The families are hand-verified, privileged experimental assistance; the numbers below are an oracle actuator ceiling and a bottleneck localisation, never AEA / llm_v1 / LOW performance and never a fair comparison against an automated method.\n",
        f"Actuator-freeze commit {eo.METHOD_SHA}; prereg commit {eo.PREREG_SHA}; frozen evidence `runs/{er.SHARED_ID}` (phase 3.4); runs `runs/{er.ARM_IDS['O1']}`, `runs/{er.ARM_IDS['O2']}`, `runs/{er.CONFIRM_ID}`. Generated by `scripts/make_tables_e6_oracle.py`.\n",
        "## Per-task controller results (oracle arm O)\n",
        "| task | goal | class / family | reference T | d = 1 guard | d = 1 measurement | dose control (d: s/n verdict) | outcome | K16 | class (six-level) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in map(str, er.TASKS):
        r = rows.get(t, {})
        spec = oa.SPEC_BY_TASK.get(t)
        fam = f"{spec.cls} / {spec.name}" if spec else "-"
        guards = (
            "; ".join(f"{gd.get('source')}/{fmt(gd.get('ok'))}" for gd in r.get("guards", []))
            or "-"
        )
        d1 = (
            "; ".join(f"{m['s']}/{m['n']} {m['verdict']}" for m in r.get("d1_measurements", []))
            or "-"
        )
        dc = (
            "; ".join(
                ", ".join(
                    f"{h['d']}: {h['s']}/{h['n']} {h['verdict']}" for h in x.get("history", [])
                )
                + f" -> {x['status']} [{x.get('lo')}, {x.get('hi')}]"
                for x in r.get("dose_control", [])
            )
            or "-"
        )
        k16 = (
            lambda cf: (
                f"{cf['successes']}/{cf['n']} (p16 {fmt(cf.get('p16'))}; B_L {fmt(cf.get('in_band_l'))}, B_T {fmt(cf.get('in_band_t'))})"
                if cf
                else "-"
            )
        )(r.get("confirm") or {})
        lines.append(
            f"| {t} | {spec.goal if spec else '-'} | {fam} | {(r.get('reference') or {}).get('n_steps', '-')} | {guards} | {d1} | {dc} | {r.get('outcome')} {r.get('reason') or ''} | {k16} | {r.get('cls')} |"
        )
    lines.append("\n## Counts over the 7 tasks (oracle arm)\n")
    lines.append(
        "| metric | oracle arm O | phase-3.4 arm B (generated, frozen) | phase-3.4 arm A (Stage control, frozen) |"
    )
    lines.append("|---|---|---|---|")
    for k in (
        "available",
        "search_accepted",
        "k16_learnable",
        "k16_target",
        "search_accepted_k16_failed",
        "leveraged_unresolved",
        "no_leverage",
        "leverage",
        "d1_leverage_tasks",
        "budget",
        "dose_order_violation",
        "no_valid_proposal",
        "uncertified",
        "exhausted",
        "intermediate_regime_tasks",
        "probe_rollouts",
    ):
        lines.append(f"| {k} | {fmt(c.get(k))} | {fmt(b34.get(k))} | {fmt(a34.get(k))} |")
    lines.append(f"| unique doses per task | {json.dumps(c['unique_doses'])} | - | - |")
    lines.append(
        "\nPhase-3.4 columns are the frozen results (descriptive context only; the oracle arm used hand-verified families).\n"
    )
    lines.append("## Generated-vs-oracle decomposition (central table)\n")
    lines.append(
        "| task | 3.4 generated: valid / leverage / accepted / K16 | 3.5a oracle: available / leverage / accepted / K16 | interpretation |"
    )
    lines.append("|---|---|---|---|")
    for x in decomp:
        gg, oo = x["generated"], x["oracle"]
        lines.append(
            f"| {x['task']} | {fmt(gg['valid'])} / {fmt(gg['leverage'])} / {fmt(gg['accepted'])} / {fmt(gg['k16'])} | {fmt(oo['available'])} / {fmt(oo['leverage'])} / {fmt(oo['accepted'])} / {fmt(oo['k16'])} | {x['interpretation']} |"
        )
    lines.append("\n## Oracle families (frozen dossier)\n")
    lines.append("| task | class | family | mechanism | relation to the 3.4 proposal | code sha |")
    lines.append("|---|---|---|---|---|---|")
    for spec in oa.SPECS:
        lines.append(
            f"| {spec.task} | {spec.cls} | {spec.name} | {spec.need} | {spec.relation} | {oa.sha(oa.template_path(spec.task).read_text(encoding='utf-8'))} |"
        )
    lines.append("\n## Correctness gates\n")
    lines.append("| gate | status |")
    lines.append("|---|---|")
    for k, v in g.items():
        if not k.endswith("_audit"):
            lines.append(f"| {k} | {fmt(v)} |")
    lines.append("\n## Exact-reference leakage audit (provenance)\n")
    lines.append("| process | task | provenance intact | prefixes by provenance | leaks |")
    lines.append("|---|---|---|---|---|")
    for arm in er.ARM_IDS:
        for t, a in (g[f"{arm}_audit"].get("tasks") or {}).items():
            lines.append(
                f"| {arm} | {t} | {fmt(a.get('provenance_intact'))} | {a.get('prefixes_by_provenance', '-')} | {a.get('leaks', a.get('reason', '-'))} |"
            )
    lines.append("\n## K16 confirmations of accepted environments\n")
    conf_path = er.RUNS / er.CONFIRM_ID / "confirm_summary.json"
    conf = json.loads(conf_path.read_text()) if conf_path.exists() else {}
    lines.append("| env | successes / n | p16 | in B_L | in B_T |")
    lines.append("|---|---|---|---|---|")
    for k, v in conf.items():
        lines.append(
            f"| {k} | {v.get('successes')} / {v.get('n')} | {fmt(v.get('p16'))} | {fmt(v.get('in_band_l'))} | {fmt(v.get('in_band_t'))} |"
        )
    if not conf:
        lines.append("| (none) | | | | |")
    lines.append(
        f"\n## Decision (pre-registered rule applied mechanically)\n\n**{dec['decision']}**"
        + (f" ({dec['reason']})" if dec.get("reason") else "")
        + f"\n\navailable {dec['available']} / {dec['n_tasks']}; d = 1 leverage {dec['d1_leverage']} / {dec['n_tasks']}; K16-confirmed learnable {dec['k16_learnable']} / {dec['n_tasks']}; K16 target {dec['k16_target']}; search-accepted {dec['search_accepted']}. Phase-3.4 frozen decision: {p34.get('decision', {}).get('decision')} (generated families: {fmt(b34.get('k16_learnable'))} / 7 K16-confirmed learnable)."
    )
    lines.append(
        f"\nSpend (USD, ledgers): {json.dumps(spend)}; total {round(sum(spend.values()), 2)} of cap {eo.CAP_USD}; designer USD 0 (no designer in the oracle arm)."
    )
    narrative = er.RESULTS / "e6_low_oracle_actuator_narrative.md"
    if narrative.exists():
        lines.append("\n" + narrative.read_text(encoding="utf-8").rstrip())
    (er.RESULTS / "e6_low_oracle_actuator.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": dec,
                "counts": {
                    k: c[k]
                    for k in (
                        "available",
                        "search_accepted",
                        "k16_learnable",
                        "k16_target",
                        "leverage",
                        "d1_leverage_tasks",
                        "probe_rollouts",
                    )
                },
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
