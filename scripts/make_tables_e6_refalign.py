# ruff: noqa: E501  (report-generation script: long markdown table rows)
"""E6 LOW refalign tables (PREREG_LOW_REFALIGN) -> experiments/alfworld_e6/results/
e6_low_refalign.md (+ _data.json): per-task paired arm-A / arm-B outcomes, secondary rates,
arm-B diagnosis-usage metrics, gates, the exact-reference leakage audit per arm, and the
pre-registered four-way conclusion applied mechanically.
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
import e6_smoke as e6

ORDINAL = {"dead": 0, "unlock_outside_target": 1, "accepted": 2}


def fmt(x: Any) -> str:
    if x is None:
        return "-"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


def arm_rows(arm: str) -> dict[str, dict[str, Any]]:
    d = er.RUNS / er.ARM_IDS[arm]
    ev = e6._by_kind(e6._events(d))
    calls = {str(c["task_id"]): c for c in e3.jsonl(d / "designer_calls.jsonl")}
    rows: dict[str, dict[str, Any]] = {}
    for t in er.TASKS:
        task = str(t)
        r: dict[str, Any] = {"task": task, "arm": arm}
        est = next((e for e in ev.get("estimate", []) if str(e["task_id"]) == task), None)
        if est:
            r.update(regime=est["regime"], p_hat=est["p_hat"], n_est=est["n"])
        done = next((e for e in ev.get("task_done", []) if str(e["task_id"]) == task), None)
        if done:
            r.update(outcome=done["outcome"], reason=done.get("reason"), n_search=done["n_search"])
        ref = next((e for e in ev.get("reference", []) if str(e["task_id"]) == task), None)
        if ref:
            r["reference"] = {k: ref.get(k) for k in ("available", "n_steps", "reference_id")}
        sp = next((e for e in ev.get("llm_stage_proposals", []) if str(e["task_id"]) == task), None)
        if sp:
            r["mode"] = sp.get("mode")
            r["proposals"] = sp.get("accepted", [])
            r["proposal_rejected"] = sp.get("rejected", [])
        dg = next((e for e in ev.get("llm_diagnosis", []) if str(e["task_id"]) == task), None)
        if dg:
            r["diagnoses"] = dg.get("diagnoses", [])
            r["diagnosis_rejected"] = dg.get("rejected", [])
        sc = next((e for e in ev.get("stage_candidates", []) if str(e["task_id"]) == task), None)
        if sc:
            r["certified"] = sc.get("certified", [])
            r["uncertified"] = sc.get("rejected", [])
        pr = next((e for e in ev.get("probe", []) if str(e["task_id"]) == task), None)
        if pr:
            r["probe"] = pr.get("profile", [])
        call = calls.get(task)
        r["designer_called"] = call is not None
        r["probe_rollouts"] = sum(
            int(e.get("n", 0))
            for e in ev.get("rollouts", [])
            if str(e["task_id"]) == task and e.get("phase") == "probe"
        )
        # category: dead < unlock_outside_target < accepted (only for zero tasks)
        if r.get("outcome") == "accepted":
            r["category"] = "accepted"
        elif any(int(p.get("successes", 0)) >= 1 for p in r.get("probe", [])):
            r["category"] = "unlock_outside_target"
        elif r.get("regime") == "zero":
            r["category"] = "dead"
        else:
            r["category"] = None
        rows[task] = r
    for c in e3.jsonl(d / "corpus.jsonl"):
        a = c["aea"]
        if a["kind"] == "stage":
            rows.setdefault(str(a["task_id"]), {})["accepted"] = {
                "id": a["candidate_id"],
                "t": a.get("t"),
                "p_hat": a.get("p_hat"),
            }
    conf_path = er.RUNS / er.CONFIRM_ID / "confirm_summary.json"
    conf = json.loads(conf_path.read_text()) if conf_path.exists() else {}
    for r in rows.values():
        acc = r.get("accepted")
        if acc and f"{arm}:{acc['id']}" in conf:
            r["confirm"] = conf[f"{arm}:{acc['id']}"]
    return rows


def diagnosis_usage(r: dict[str, Any]) -> dict[str, Any]:
    """Arm B only: did the diagnosis land on valid positions; did proposals link; where is the
    selected cut relative to the diagnosed reference step."""
    diags = r.get("diagnoses") or []
    props = r.get("proposals") or []
    out: dict[str, Any] = {
        "n_diagnoses": len(diags),
        "valid_failure_step": bool(diags),  # parse_refalign keeps only valid positions
        "valid_reference_step": bool(diags),
        "n_rejected_diagnoses": len(r.get("diagnosis_rejected") or []),
        "proposals_linked": sum(1 for p in props if p.get("diagnosis")),
        "proposals": len(props),
    }
    rel = []
    for p in props:
        link = p.get("diagnosis")
        if link and 1 <= int(link) <= len(diags):
            ref_step = int(diags[int(link) - 1]["reference_step"])
            rel.append(
                "before" if p["step"] < ref_step else ("at" if p["step"] == ref_step else "after")
            )
        else:
            rel.append("unlinked")
    out["cut_vs_diagnosed_reference_step"] = rel
    return out


def gates(rows_a: dict[str, dict[str, Any]], rows_b: dict[str, dict[str, Any]]) -> dict[str, Any]:
    shared = {str(r["task_id"]): r for r in e3.jsonl(er.shared_dir() / "shared.jsonl")}
    g: dict[str, Any] = {}
    for arm in ("A", "B"):
        d = er.RUNS / er.ARM_IDS[arm]
        ev = e6._by_kind(e6._events(d))
        calls = e3.jsonl(d / "designer_calls.jsonl")
        per: dict[str, int] = {}
        for c in calls:
            per[str(c["task_id"])] = per.get(str(c["task_id"]), 0) + 1
        manifest = json.loads((d / "manifest.json").read_text())
        extra = manifest.get("extra", manifest)
        g[f"{arm}_method_version_runtime"] = extra.get("method_version") == er.ARM_VERSIONS[
            arm
        ] and all(c.get("method_version") == er.ARM_VERSIONS[arm] for c in calls)
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
        g[f"{arm}_designer_calls_le_1"] = all(v <= 1 for v in per.values())
        g[f"{arm}_proposals_le_2"] = all(len(c.get("accepted", [])) <= 2 for c in calls)
        g[f"{arm}_search_le_cap"] = all(
            int(e.get("n_search", 0)) <= 30 for e in ev.get("task_done", [])
        )
        g[f"{arm}_no_fallback"] = all(
            s.get("source") == "designer" for s in ev.get("stage_candidates", [])
        )
        g[f"{arm}_reference_only_on_zero"] = all(
            next(
                (x["regime"] for x in ev.get("estimate", []) if x["task_id"] == e["task_id"]), None
            )
            == "zero"
            for e in ev.get("reference", [])
        )
        audit = e6.leakage_audit(d)
        g[f"{arm}_reference_leakage"] = audit.get("ok", False) and not audit.get(
            "expert_recomputed"
        )
        g[f"{arm}_audit"] = audit
    g["B_mode_refalign_on_every_zero_task"] = all(
        r.get("mode") == "refalign"
        for r in rows_b.values()
        if r.get("regime") == "zero" and (r.get("reference") or {}).get("available")
    )
    g["A_mode_direct_on_every_zero_task"] = all(
        r.get("mode") == "direct"
        for r in rows_a.values()
        if r.get("regime") == "zero" and (r.get("reference") or {}).get("available")
    )
    g["method_unmodified"] = not e6._src_sha().endswith("+DIRTY")
    g["all_pass"] = all(
        v is True for k, v in g.items() if not k.endswith("_audit") and k != "all_pass"
    )
    return g


def conclusion(
    rows_a: dict[str, dict[str, Any]], rows_b: dict[str, dict[str, Any]], g: dict[str, Any]
) -> dict[str, Any]:
    zero = [
        t
        for t in rows_b
        if rows_b[t].get("regime") == "zero" and rows_a.get(t, {}).get("regime") == "zero"
    ]
    out: dict[str, Any] = {"tasks": list(rows_b), "zero_tasks": zero, "n_zero": len(zero)}
    for arm, rows in (("A", rows_a), ("B", rows_b)):
        rs = [rows[t] for t in zero]
        out[f"{arm}_accepted"] = sum(1 for r in rs if r.get("category") == "accepted")
        out[f"{arm}_unlock"] = sum(
            1 for r in rs if r.get("category") in ("unlock_outside_target", "accepted")
        )
        out[f"{arm}_overshoot"] = sum(
            1
            for r in rs
            if r.get("category") == "unlock_outside_target" and r.get("reason") == "too_easy"
        )
        out[f"{arm}_dead"] = sum(1 for r in rs if r.get("category") == "dead")
        out[f"{arm}_valid_proposal_tasks"] = sum(
            1 for r in rs if len(r.get("proposals") or []) >= 1
        )
        out[f"{arm}_certified_tasks"] = sum(1 for r in rs if len(r.get("certified") or []) >= 1)
        probes = sum(int(r.get("probe_rollouts", 0)) for r in rs)
        out[f"{arm}_probe_rollouts"] = probes
        out[f"{arm}_rollouts_per_accepted"] = (
            (probes / out[f"{arm}_accepted"]) if out[f"{arm}_accepted"] else None
        )
    wins = {"A": 0, "tie": 0, "B": 0}
    for t in zero:
        a, b = (
            ORDINAL.get(rows_a[t].get("category") or "", -1),
            ORDINAL.get(rows_b[t].get("category") or "", -1),
        )
        wins["B" if b > a else ("A" if a > b else "tie")] += 1
    out["paired"] = wins
    if not g.get("all_pass") or len(zero) < 2:
        out["conclusion"] = (
            "INCONCLUSIVE" if len(zero) < 2 else "NO_EVIDENCE_REFERENCE_ALIGNMENT_HELPS"
        )
        out["conclusion_reason"] = (
            "fewer than 2 prospectively zero tasks"
            if len(zero) < 2
            else "a correctness gate failed"
        )
        if not g.get("all_pass"):
            out["conclusion"] = "INCONCLUSIVE"
            out["conclusion_reason"] = "a correctness gate failed (infrastructure / protocol)"
    elif out["B_accepted"] >= 2 and out["B_accepted"] > out["A_accepted"]:
        out["conclusion"] = "REFERENCE_ALIGNMENT_SUPPORTED"
    elif wins["B"] > wins["A"] and out["B_accepted"] < 2:
        out["conclusion"] = "CREDIT_ASSIGNMENT_HELPS_BUT_CONTROL_REMAINS_LIMITING"
    else:
        out["conclusion"] = "NO_EVIDENCE_REFERENCE_ALIGNMENT_HELPS"
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    rows_a, rows_b = arm_rows("A"), arm_rows("B")
    g = gates(rows_a, rows_b)
    c = conclusion(rows_a, rows_b, g)
    usage = {t: diagnosis_usage(r) for t, r in rows_b.items() if r.get("regime") == "zero"}
    spend = {
        p.name: round(e3.dir_spend(p), 2)
        for p in sorted(er.RUNS.glob("e6-refalign-*"))
        if p.is_dir()
    }
    er.RESULTS.mkdir(parents=True, exist_ok=True)
    (er.RESULTS / "e6_low_refalign_data.json").write_text(
        json.dumps(
            {
                "A": rows_a,
                "B": rows_b,
                "gates": g,
                "conclusion": c,
                "diagnosis_usage": usage,
                "spend": spend,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    lines: list[str] = []
    lines.append("# E6 LOW refalign: paired shared-evidence comparison (PREREG_LOW_REFALIGN)\n")
    lines.append(
        f"Method commit {er.METHOD_SHA}; prereg commit {er.PREREG_SHA}; runs `runs/{er.SHARED_ID}`, "
        f"`runs/{er.ARM_IDS['A']}`, `runs/{er.ARM_IDS['B']}`, `runs/{er.CONFIRM_ID}`. "
        "Generated by `scripts/make_tables_e6_refalign.py`.\n"
    )
    lines.append("## Paired per-task table\n")
    lines.append(
        "| task | shared regime (p_hat, n) | reference | A proposals | A certified | A probe | A category | "
        "B diagnoses | B proposals (cut, link) | B certified | B probe | B category | paired |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in c["tasks"]:
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
            return (
                "; ".join(
                    f"{p['source']}@{p['step']}"
                    + (f" (diag {p['diagnosis']})" if p.get("diagnosis") else "")
                    for p in r.get("proposals", [])
                )
                or "-"
            )

        diag = (
            "; ".join(
                f"{d['failure_id']}@{d['failure_step']} vs ref@{d['reference_step']}"
                for d in b.get("diagnoses", [])
            )
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
            f"{fmt(ref.get('available'))}, {ref.get('n_steps', '-')} steps",
            props(a),
            str(len(a.get("certified") or [])),
            probe_s(a),
            str(a.get("category")),
            diag,
            props(b),
            str(len(b.get("certified") or [])),
            probe_s(b),
            str(b.get("category")),
            paired,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append(f"\n## Counts over prospectively zero tasks (n = {c['n_zero']})\n")
    lines.append(
        "| metric | arm A (llm_v1, action-only reference) | arm B (llm_v1_refalign, rich reference + diagnosis) |"
    )
    lines.append("|---|---|---|")
    for k, label in (
        ("valid_proposal_tasks", "tasks with >= 1 valid proposal"),
        ("certified_tasks", "tasks with >= 1 certified Stage"),
        ("unlock", "unlock (>= 1 policy success)"),
        ("overshoot", "overshoot (too_easy)"),
        ("dead", "dead"),
        ("accepted", "ACCEPTED (primary)"),
        ("probe_rollouts", "probe rollouts"),
        ("rollouts_per_accepted", "probe rollouts per accepted Stage"),
    ):
        lines.append(f"| {label} | {fmt(c[f'A_{k}'])} | {fmt(c[f'B_{k}'])} |")
    lines.append(
        f"\nPaired ordinal outcome (dead < unlock-outside-target < accepted): A better {c['paired']['A']}, tie {c['paired']['tie']}, B better {c['paired']['B']}."
    )
    lines.append("\n## Arm B diagnosis usage\n")
    lines.append(
        "| task | diagnoses (valid) | rejected diagnoses | proposals | linked | cut vs diagnosed reference step |"
    )
    lines.append("|---|---|---|---|---|---|")
    for t, u in usage.items():
        lines.append(
            f"| {t} | {u['n_diagnoses']} | {u['n_rejected_diagnoses']} | {u['proposals']} | {u['proposals_linked']} | {u['cut_vs_diagnosed_reference_step']} |"
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
        "| arm | task | provenance intact | reference cuts | independently emitted post-cut actions | leaks |"
    )
    lines.append("|---|---|---|---|---|---|")
    for arm in ("A", "B"):
        for t, a in (g[f"{arm}_audit"].get("tasks") or {}).items():
            lines.append(
                f"| {arm} | {t} | {fmt(a.get('provenance_intact'))} | {a.get('reference_cuts', '-')} | {a.get('independent_overlap', '-')} | {a.get('leaks', a.get('reason', '-'))} |"
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
        f"\n## Conclusion (pre-registered rule applied mechanically)\n\n**{c['conclusion']}**"
        + (f" ({c['conclusion_reason']})" if c.get("conclusion_reason") else "")
    )
    lines.append(
        f"\nSpend (USD, ledgers): {json.dumps(spend)}; total {round(sum(spend.values()), 2)} of cap {er.CAP_USD}."
    )
    lines.append("\n## Diagnosis examples (arm B, the LLM's own words)\n")
    for t, r in rows_b.items():
        for d in r.get("diagnoses", []):
            lines.append(
                f"- task {t}, {d['failure_id']} step {d['failure_step']} vs reference step {d['reference_step']}: cause: {str(d['error_cause']).replace(chr(10), ' ')}; fix hint: {str(d['fix_hint']).replace(chr(10), ' ')}"
                + (
                    f"; evidence: {str(d.get('evidence', '')).replace(chr(10), ' ')}"
                    if d.get("evidence")
                    else ""
                )
            )
    narrative = er.RESULTS / "e6_low_refalign_narrative.md"
    if narrative.exists():
        lines.append("\n" + narrative.read_text(encoding="utf-8").rstrip())
    (er.RESULTS / "e6_low_refalign.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in c.items() if k not in ("tasks",)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
