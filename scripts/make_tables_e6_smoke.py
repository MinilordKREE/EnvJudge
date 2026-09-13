"""E6 smoke tables (PREREG_SMOKE) -> experiments/alfworld_e6/results/e6_smoke.md and
e6_smoke_data.json. Every number comes from runs/e6-smoke-llm-v1 (events, designer_calls,
corpus, gates, leakage audit, ledgers) and runs/e6-smoke-confirm; the verdicts apply the
pre-registered criteria mechanically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_smoke as e6

RUN = e6.RUNS / e6.RUN_ID
CONFIRM = e6.RUNS / e6.CONFIRM_RUN_ID


def fmt(x: Any, nd: int = 2) -> str:
    if x is None:
        return "-"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def per_task() -> dict[str, dict[str, Any]]:
    ev = e6._by_kind(e6._events(RUN))
    calls = {(str(c["task_id"]), c["regime"]): c for c in e3.jsonl(RUN / "designer_calls.jsonl")}
    rows: dict[str, dict[str, Any]] = {}
    for t in e6.ORDER:
        task = str(t)
        r: dict[str, Any] = {"task": task, "expected": e6.EXPECTED[task]}
        est = next((e for e in ev.get("estimate", []) if str(e["task_id"]) == task), None)
        if est:
            r.update(regime=est["regime"], p_hat=est["p_hat"], n_est=est["n"])
        done = next((e for e in ev.get("task_done", []) if str(e["task_id"]) == task), None)
        if done:
            r.update(outcome=done["outcome"], reason=done.get("reason"), n_search=done["n_search"])
        r["branch_reached"] = est is not None and est["regime"] == r["expected"]
        call = calls.get((task, r.get("regime", "")))
        r["designer_called"] = call is not None
        if call:
            fams = (
                call.get("arguments", {}).get("families")
                or call.get("arguments", {}).get("stages")
                or []
            )
            r["raw_proposals"] = len(fams)
            r["valid_proposals"] = len(call.get("accepted", []))
            r["rejected"] = call.get("rejected", [])
            r["mechanisms"] = call.get("mechanisms")
            r["reference_used"] = call.get("reference_used")
            r["evidence_chars"] = len(str(call.get("evidence", "")))
        # HIGH details
        prop = next((e for e in ev.get("proposer", []) if str(e["task_id"]) == task), None)
        if prop:
            r["proposed"] = prop.get("proposed", [])
            args_f = call.get("arguments", {}).get("families", []) if call else []
            r["axes"] = {str(f.get("name")): f.get("axis") for f in args_f if isinstance(f, dict)}
        r["guards"] = [
            {"family": s.get("family"), "ok": s.get("ok"), "source": s.get("source")}
            for s in ev.get("solvable", [])
            if str(s["task_id"]) == task
        ]
        lev = [e for e in ev.get("leverage", []) if str(e["task_id"]) == task and "tested" in e]
        r["leverage"] = {str(e["family"]): bool(e["has_leverage"]) for e in lev}
        r["measurable_leverage"] = any(r["leverage"].values())
        r["brackets"] = [
            {
                "family": b["family"],
                "start": b["start"],
                "status": b["status"],
                "history": b["history"],
            }
            for b in ev.get("bracket", [])
            if str(b["task_id"]) == task
        ]
        r["no_leverage"] = [
            e["family"] for e in ev.get("no_leverage", []) if str(e["task_id"]) == task
        ]
        # LOW details
        ref = next((e for e in ev.get("reference", []) if str(e["task_id"]) == task), None)
        if ref:
            r["reference"] = {
                k: ref.get(k) for k in ("requested", "available", "n_steps", "reason")
            }
        sp = next((e for e in ev.get("llm_stage_proposals", []) if str(e["task_id"]) == task), None)
        if sp:
            r["stage_proposals"] = sp.get("accepted", [])
            r["stage_rejected"] = sp.get("rejected", [])
        sc = next((e for e in ev.get("stage_candidates", []) if str(e["task_id"]) == task), None)
        if sc:
            r["certified"] = sc.get("certified", [])
            r["uncertified"] = sc.get("rejected", [])
        pr = next((e for e in ev.get("probe", []) if str(e["task_id"]) == task), None)
        if pr:
            r["probe"] = pr.get("profile", [])
            r["policy_unlock"] = any(int(p.get("successes", 0)) >= 1 for p in pr.get("profile", []))
        rows[task] = r
    for c in e3.jsonl(RUN / "corpus.jsonl"):
        a = c["aea"]
        rows.setdefault(str(a["task_id"]), {})["accepted"] = {
            "id": a["candidate_id"],
            "kind": a["kind"],
            "family": a.get("family"),
            "d": a.get("d"),
            "t": a.get("t"),
            "p_hat": a.get("p_hat"),
        }
    conf = (
        json.loads((CONFIRM / "confirm_summary.json").read_text())
        if (CONFIRM / "confirm_summary.json").exists()
        else {}
    )
    for r in rows.values():
        acc = r.get("accepted")
        if acc and acc["id"] in conf:
            r["confirm"] = conf[acc["id"]]
    return rows


def verdicts(rows: dict[str, dict[str, Any]], gates: dict[str, Any]) -> dict[str, Any]:
    high = [
        r
        for t, r in rows.items()
        if e6.EXPECTED[t] == "saturated" and r.get("regime") == "saturated"
    ]
    low = [r for t, r in rows.items() if e6.EXPECTED[t] == "zero" and r.get("regime") == "zero"]
    out: dict[str, Any] = {"high_reached": len(high), "low_reached": len(low)}
    if len(high) < 2:
        out["high"] = "INCONCLUSIVE"
    else:
        valid = sum(1 for r in high if r.get("valid_proposals", 0) >= 1)
        lev = sum(1 for r in high if r.get("measurable_leverage"))
        out["high_valid_tasks"], out["high_leverage_tasks"] = valid, lev
        out["high"] = "PASS" if valid >= 2 and lev >= 1 else "FAIL"
    if len(low) < 2:
        out["low"] = "INCONCLUSIVE"
    else:
        valid = sum(1 for r in low if len(r.get("stage_proposals", [])) >= 1)
        unlock = sum(
            1
            for r in low
            if r.get("policy_unlock") or (r.get("accepted") or {}).get("kind") == "stage"
        )
        out["low_valid_tasks"], out["low_unlock_tasks"] = valid, unlock
        out["low"] = "PASS" if valid >= 2 and unlock >= 1 else "FAIL"
    if not gates.get("all_pass") or "FAIL" in (out["high"], out["low"]):
        out["overall"] = "NO-GO"
    elif "INCONCLUSIVE" in (out["high"], out["low"]):
        out["overall"] = "INCONCLUSIVE"
    else:
        out["overall"] = "GO"
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    rows = per_task()
    gates = json.loads((RUN / "gates.json").read_text()) if (RUN / "gates.json").exists() else {}
    audit = (
        json.loads((RUN / "leakage_audit.json").read_text())
        if (RUN / "leakage_audit.json").exists()
        else {}
    )
    spend = {p.name: round(e3.dir_spend(p), 2) for p in sorted(e6.RUNS.glob("e6-*")) if p.is_dir()}
    v = verdicts(rows, gates)
    e6.RESULTS.mkdir(parents=True, exist_ok=True)
    (e6.RESULTS / "e6_smoke_data.json").write_text(
        json.dumps(
            {"rows": rows, "gates": gates, "audit": audit, "spend": spend, "verdicts": v}, indent=1
        ),
        encoding="utf-8",
    )
    lines: list[str] = []
    lines.append("# E6 smoke: llm_v1 six-task mechanism smoke (PREREG_SMOKE)\n")
    lines.append(
        f"Method commit {e6.METHOD_SHA}; prereg commit {e6.PREREG_SHA}; runs `runs/{e6.RUN_ID}`, "
        f"`runs/{e6.CONFIRM_RUN_ID}`. Generated by `scripts/make_tables_e6_smoke.py`.\n"
    )
    lines.append("## Per-task table\n")
    lines.append(
        "| task | frozen K16 | prospective | p_hat | n | designer | valid | HIGH leverage | "
        "HIGH accepted d | LOW ref avail | ref used | Stage source/cut | policy unlock | search | "
        "outcome | reason | K16 confirm |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in e6.ORDER:
        r = rows.get(str(t), {})
        acc = r.get("accepted") or {}
        ref = r.get("reference") or {}
        sp = r.get("stage_proposals") or []
        stage = "; ".join(f"{p['source']}@{p['step']}" for p in sp) if sp else "-"
        conf = r.get("confirm") or {}
        conf_s = (
            f"{conf['successes']}/{conf['n']} (B_L {fmt(conf.get('in_band_l'))}, "
            f"B_T {fmt(conf.get('in_band_t'))})"
            if conf
            else "-"
        )
        reached = "" if r.get("branch_reached", True) else " (branch_not_reached)"
        cells = [
            str(t),
            str(r.get("expected")),
            f"{r.get('regime')}{reached}",
            fmt(r.get("p_hat")),
            str(r.get("n_est", "-")),
            fmt(r.get("designer_called")),
            f"{r.get('valid_proposals', '-')}/{r.get('raw_proposals', '-')}",
            fmt(r.get("measurable_leverage")) if r.get("regime") == "saturated" else "-",
            fmt(acc.get("d")) if acc.get("kind") == "knob" else "-",
            fmt(ref.get("available")) if ref else "-",
            fmt(r.get("reference_used")) if ref else "-",
            stage,
            fmt(r.get("policy_unlock")) if r.get("regime") == "zero" else "-",
            str(r.get("n_search", "-")),
            str(r.get("outcome")),
            str(r.get("reason") or "-"),
            conf_s,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("\n## Correctness gates\n")
    lines.append("| gate | status |")
    lines.append("|---|---|")
    for k, val in gates.items():
        lines.append(
            f"| {k} | {fmt(val) if not isinstance(val, (dict, list)) else json.dumps(val)} |"
        )
    lines.append("\n## Leakage audit (LOW tasks)\n")
    lines.append(
        "| task | reference available | recomputed hash match | reference steps | "
        "reference cuts | post-cut actions independently emitted by the policy | leaks |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for t, a in (audit.get("tasks") or {}).items():
        cells = [
            str(t),
            fmt(a.get("available")),
            fmt(a.get("hash_match")),
            str(a.get("reference_steps", "-")),
            str(a.get("reference_cuts", "-")),
            str(a.get("independent_overlap", "-")),
            str(a.get("leaks", a.get("reason", "-"))),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("\n## Verdicts (pre-registered criteria applied mechanically)\n")
    for k, val in v.items():
        lines.append(f"- {k}: {val}")
    lines.append(
        f"\nSpend (USD, ledgers): {json.dumps(spend)}; "
        f"total {round(sum(spend.values()), 2)} of cap {e6.CAP_USD}."
    )
    lines.append("\n## Designer qualitative audit (descriptive only)\n")
    lines.append("### HIGH\n")
    lines.append(
        "| task | proposal | axis | mechanism summary (LLM's own words) | valid | guard | "
        "leverage |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for t in e6.HIGH_TASKS:
        r = rows.get(str(t), {})
        mech = r.get("mechanisms") or {}
        axes = r.get("axes") or {}
        if isinstance(mech, dict):
            for name, summ in mech.items():
                g: dict[str, Any] = next(
                    (x for x in r.get("guards", []) if x["family"] == name), {}
                )
                cells = [
                    str(t),
                    str(name),
                    str(axes.get(name, "-")),
                    str(summ).replace("|", "/"),
                    "yes",
                    f"{g.get('source', '-')}/{fmt(g.get('ok'))}",
                    fmt(r.get("leverage", {}).get(name)),
                ]
                lines.append("| " + " | ".join(cells) + " |")
        for rej in r.get("rejected", []) or []:
            lines.append(f"| {t} | (rejected) | - | {str(rej).replace('|', '/')} | no | - | - |")
        if not mech and not r.get("rejected"):
            why = f"designer not called or no proposal ({r.get('regime')})"
            lines.append(f"| {t} | - | - | {why} | - | - | - |")
    lines.append("\n### LOW\n")
    lines.append(
        "| task | reference available | source | step | mechanism summary (LLM's own words) | "
        "valid | certified | policy response |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for t in e6.LOW_TASKS:
        r = rows.get(str(t), {})
        ref = r.get("reference") or {}
        avail = fmt(ref.get("available")) if ref else "-"
        mech = r.get("mechanisms") or []
        for i, p in enumerate(r.get("stage_proposals") or []):
            m = mech[i] if isinstance(mech, list) and i < len(mech) else "-"
            pr: dict[str, Any] = next(
                (
                    x
                    for x in r.get("probe", [])
                    if x.get("t") == p["step"] and x.get("source") == p["source"]
                ),
                {},
            )
            certified = any(c == pr.get("id") for c in r.get("certified", []))
            cells = [
                str(t),
                avail,
                str(p["source"]),
                str(p["step"]),
                str(m).replace("|", "/"),
                "yes",
                fmt(certified) if pr else "-",
                f"{pr.get('successes', '-')}/{pr.get('n', '-')} {pr.get('verdict', '')}".strip(),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        for rej in r.get("stage_rejected", []) or []:
            lines.append(
                f"| {t} | {avail} | (rejected) | - | {str(rej).replace('|', '/')} | no | - | - |"
            )
        if not r.get("stage_proposals") and not r.get("stage_rejected"):
            why = f"designer not called or no proposal ({r.get('regime')})"
            lines.append(f"| {t} | {avail} | - | - | {why} | - | - | - |")
    (e6.RESULTS / "e6_smoke.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
