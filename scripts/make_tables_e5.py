"""E5 tables (PREREG12) -> experiments/alfworld_e5/results/e5_warm_start.md and
e5_warm_start_data.json: per-task rows for A2 (v0.2 midpoint start) and A4 (v0.4 soft warm start),
aggregates, the pre-registered decision, spend and incidents. Every number comes from
runs/e5-A2, runs/e5-A4 and runs/e5-confirm.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e5

RUNS = e5.RUNS
RESULTS = e5.RESULTS
TASKS = [str(t) for t in e5.TASKS]


def fmt(x: float | None, nd: int = 1) -> str:
    return "-" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def profile(arm: str) -> dict[str, dict[str, Any]]:
    per: dict[str, dict[str, Any]] = {
        t: {
            "outcome": None,
            "reason": None,
            "regime": None,
            "p_hat": None,
            "n_est": 0,
            "n_search": None,
            "brackets": [],
            "no_leverage": [],
            "rollouts": defaultdict(int),
            "infra_errors": 0,
        }
        for t in TASKS
    }
    for e in e3.jsonl(RUNS / f"e5-{arm}" / "events.jsonl"):
        k, p = e.get("kind"), e.get("payload", {})
        t = str(p.get("task_id"))
        if t not in per:
            continue
        v = per[t]
        if k == "estimate":
            v.update({"regime": p.get("regime"), "p_hat": p.get("p_hat"), "n_est": p.get("n")})
        elif k == "bracket":
            v["brackets"].append(p)
        elif k == "no_leverage":
            v["no_leverage"].append(p.get("family"))
        elif k == "rollouts":
            v["rollouts"][str(p.get("phase"))] += int(p.get("n", 0))
        elif k == "rollout_errors":
            v["infra_errors"] += int(p.get("n", 0))
        elif k == "task_done":
            v.update(
                {
                    "outcome": p.get("outcome"),
                    "reason": p.get("reason"),
                    "n_search": p.get("n_search"),
                }
            )
    return per


def charged(arm: str) -> dict[str, int]:
    per: dict[str, int] = defaultdict(int)
    for r in e3.jsonl(RUNS / f"e5-{arm}" / "traces.jsonl"):
        if not r.get("error"):
            per[str(r["rollout_seed"])] += 1
    return dict(per)


def accepted_dose(arm: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in e3.jsonl(RUNS / f"e5-{arm}" / "corpus.jsonl"):
        meta = e.get("aea") or {}
        if meta.get("kind") == "knob":
            key = e3.candidate_key(
                {"rules_code": e.get("rules_code"), "in_env_actions": e.get("in_env_actions")}
            )
            out[str(meta.get("task_id"))] = {
                "d": meta.get("d"),
                "family": meta.get("family"),
                "p8": meta.get("p_hat"),
                "env": f"{meta.get('task_id')}:{key}",
            }
    return out


def bisection_probes(b: dict[str, Any]) -> int:
    """Bracket probes after the d = 1 leverage test."""
    return len([h for h in (b.get("history") or []) if h.get("d") != 1.0])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "e5_warm_start.md"))
    args = ap.parse_args(argv)
    RESULTS.mkdir(parents=True, exist_ok=True)
    prof = {a: profile(a) for a in e5.ARMS}
    rolls = {a: charged(a) for a in e5.ARMS}
    acc = {a: accepted_dose(a) for a in e5.ARMS}
    conf_path = RUNS / "e5-confirm" / "confirm_summary.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.exists() else {}
    lines: list[str] = [
        "# E5 — soft warm start of the saturated-side dose search: v0.2 (A2) vs v0.4 (A4)",
        "",
        f"PREREG12 @ {e5.PREREG_SHA}. Same code (tag aea-v0.4), same policy, families (library only, proposer off), guard, verdict, acceptance, cap 30, task order {', '.join(TASKS)}; the only difference is the first interior probe of a bracket: 0.5 (A2) vs the median of >= 3 previous task frontiers (A4). Tables from scripts/make_tables_e5.py.",  # noqa: E501
        "",
        "## Per task",
        "",
        "| task | arm | estimate (regime, p_hat, n) | outcome:reason | rollouts | families w/o leverage | first interior probe | doses (d: s/n verdict) | accepted d | final local [lo, hi] | warm start | recovered |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    rows: dict[str, dict[str, Any]] = {}
    for t in TASKS:
        per_arm: dict[str, Any] = {}
        for a in e5.ARMS:
            v = prof[a][t]
            b = v["brackets"][0] if v["brackets"] else None
            hist = (b or {}).get("history") or []
            start = (b or {}).get("start")
            local = (b or {}).get("local")
            per_arm[a] = {
                "outcome": f"{v['outcome']}{':' + v['reason'] if v['reason'] else ''}",
                "regime": v["regime"],
                "p_hat": v["p_hat"],
                "n_est": v["n_est"],
                "rollouts": rolls[a].get(t, 0),
                "n_search": v["n_search"],
                "no_leverage": v["no_leverage"],
                "family": (b or {}).get("family"),
                "start": start,
                "history": [(h["d"], h["s"], h["n"], h["verdict"]) for h in hist],
                "probes": bisection_probes(b) if b else None,
                "accepted_d": acc[a].get(t, {}).get("d"),
                "env": acc[a].get(t, {}).get("env"),
                "local": local,
                "status": (b or {}).get("status"),
            }
        a2, a4 = per_arm["A2"], per_arm["A4"]
        # warm start classification (PREREG12): fewer / equal / more bisection probes than A2 on
        # the same task; n/a while A4 had no history (start 0.5) or either arm did not bracket
        if a4["start"] is None or a2["probes"] is None or a4["probes"] is None:
            ws = "n/a"
        elif a4["start"] == 0.5:
            ws = "n/a (no history)"
        elif a4["probes"] < a2["probes"] or (
            a4["accepted_d"] is not None and a2["accepted_d"] is None
        ):
            ws = "helpful"
        elif a4["probes"] == a2["probes"]:
            ws = "neutral"
        else:
            ws = "harmful"
        first = a4["history"][1] if len(a4["history"]) > 1 else None  # after the d = 1 test
        wrong_side = None
        if first is not None and a4["accepted_d"] is not None:
            wrong_side = (first[3] == "too_hard" and a4["accepted_d"] < first[0]) or (
                first[3] == "too_easy" and a4["accepted_d"] > first[0]
            )
        recovered = (
            "yes"
            if ws == "harmful" and a4["accepted_d"] is not None
            else ("wrong side, accepted" if wrong_side else ("-" if ws != "harmful" else "no"))
        )
        rows[t] = {"A2": a2, "A4": a4, "warm_start": ws, "recovered": recovered}
        for a in e5.ARMS:
            x = per_arm[a]
            doses = "/".join(f"{d}:{s}/{n} {v_}" for d, s, n, v_ in x["history"]) or "-"
            lines.append(
                f"| {t} | {a} | {x['regime']}, {fmt(x['p_hat'], 3)}, {x['n_est']} | {x['outcome']} | {x['rollouts']} | {', '.join(x['no_leverage']) or '-'} | {fmt(x['start'], 4) if x['start'] is not None else '-'} | {doses} | {fmt(x['accepted_d'], 4) if x['accepted_d'] is not None else '-'} | {x['local'] if x['local'] else '-'} | {ws if a == 'A4' else '-'} | {recovered if a == 'A4' else '-'} |"  # noqa: E501
            )
    # aggregates
    agg: dict[str, dict[str, Any]] = {}
    for a in e5.ARMS:
        tested = [t for t in TASKS if prof[a][t]["regime"] == "saturated"]
        accepted = [t for t in TASKS if prof[a][t]["outcome"] == "accepted"]
        total = sum(rolls[a].get(t, 0) for t in TASKS)
        sat_rolls = sum(rolls[a].get(t, 0) for t in tested)
        learn = 0
        for t in accepted:
            env = acc[a].get(t, {}).get("env")
            if env and conf.get(env, {}).get("learnable"):
                learn += 1
        agg[a] = {
            "tested_saturated": len(tested),
            "accepted": len(accepted),
            "accepted_tasks": accepted,
            "rollouts_total": total,
            "rollouts_saturated": sat_rolls,
            "rollouts_per_task": total / len(TASKS),
            "rollouts_per_accept": (sat_rolls / len(accepted)) if accepted else None,
            "confirmed_learnable": learn,
            "precision": (learn / len(accepted)) if accepted else None,
        }
    lines += [
        "",
        "## Aggregates",
        "",
        "| arm | saturated tasks tested | accepted in band | charged rollouts (all / saturated) | rollouts per task | rollouts per accepted task | confirmed learnable (K16) | precision |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|",
    ]
    for a in e5.ARMS:
        g = agg[a]
        lines.append(
            f"| {a} | {g['tested_saturated']} | {g['accepted']} ({', '.join(g['accepted_tasks']) or '-'}) | {g['rollouts_total']} / {g['rollouts_saturated']} | {fmt(g['rollouts_per_task'])} | {fmt(g['rollouts_per_accept'])} | {g['confirmed_learnable']} | {fmt(100 * g['precision'], 0) + '%' if g['precision'] is not None else '-'} |"  # noqa: E501
        )
    ws_counts = defaultdict(int)
    for r in rows.values():
        ws_counts[r["warm_start"]] += 1
    harmful = [t for t, r in rows.items() if r["warm_start"] == "harmful"]
    unrecovered = [t for t in harmful if rows[t]["recovered"] == "no"]
    # the pre-registered decision rule
    rpa2, rpa4 = agg["A2"]["rollouts_per_accept"], agg["A4"]["rollouts_per_accept"]
    cond_a = rpa2 is not None and rpa4 is not None and rpa4 <= 0.8 * rpa2
    cond_b = agg["A4"]["confirmed_learnable"] >= agg["A2"]["confirmed_learnable"] + 1
    loss_a = rpa2 is not None and rpa4 is not None and rpa4 > 1.2 * rpa2  # meaningful loss on A
    loss_b = agg["A4"]["confirmed_learnable"] < agg["A2"]["confirmed_learnable"]
    prec_ok = (agg["A4"]["precision"] or 0.0) >= (agg["A2"]["precision"] or 0.0) or agg["A4"][
        "accepted"
    ] == 0
    no_collapse = not unrecovered
    inconclusive = agg["A2"]["accepted"] == 0 and agg["A4"]["accepted"] == 0
    keep = (
        not inconclusive
        and ((cond_a and not loss_b) or (cond_b and not loss_a))
        and no_collapse
        and prec_ok
    )
    lines += [
        "",
        "## Decision (PREREG12 rule, applied as written)",
        "",
        f"- A. rollouts per accepted task: A2 {fmt(rpa2)} vs A4 {fmt(rpa4)} → >= 20% reduction {'yes' if cond_a else 'no'}.",  # noqa: E501
        f"- B. confirmed accepted environments: A2 {agg['A2']['confirmed_learnable']} vs A4 {agg['A4']['confirmed_learnable']} → >= 1 more {'yes' if cond_b else 'no'}.",  # noqa: E501
        f"- warm starts: {dict(ws_counts)}; harmful {len(harmful)} ({', '.join(harmful) or '-'}), of which not recovered {len(unrecovered)} ({', '.join(unrecovered) or '-'}); no irreversible collapse {'yes' if no_collapse else 'NO'}; precision not worse {'yes' if prec_ok else 'NO'}.",  # noqa: E501
        "",
        "**"
        + (
            "INCONCLUSIVE: neither arm accepted an environment; v0.2 stays."
            if inconclusive
            else (
                "KEEP v0.4 soft warm-start."
                if keep
                else "REVERT TO v0.2; cross-task prior not worth the complexity."
            )
        )
        + "**",
    ]
    sp: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for run in sorted(RUNS.glob("e5-*")):
        if run.is_dir():
            for r in e3._ledger_rows(run):
                if r.get("event") == "call":
                    sp[run.name][str(r.get("budget"))] += float(r.get("usd") or 0.0)
    total_usd = sum(sum(v.values()) for v in sp.values())
    retries = sum(
        1
        for run in RUNS.glob("e5-*")
        if run.is_dir()
        for r in e3._ledger_rows(run)
        if r.get("event") == "infra_retry"
    )
    errs = {
        a: sum(1 for r in e3.jsonl(RUNS / f"e5-{a}" / "traces.jsonl") if r.get("error"))
        for a in e5.ARMS
    }
    lines += ["", "## Spend and incidents", "", "| run | budgets | total |", "|---|---|---|"]
    for run, by in sorted(sp.items()):
        lines.append(
            f"| {run} | "
            + ", ".join(f"{k} {v:.2f}" for k, v in sorted(by.items()))
            + f" | {sum(by.values()):.2f} |"
        )
    lines += [
        "",
        f"E5 total USD {total_usd:.2f} (cap {e5.CAP_USD:.0f}); ledgered retries {retries}; errored rollouts "  # noqa: E501
        + ", ".join(f"{a} {n}" for a, n in errs.items())
        + ".",
        "",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "e5_warm_start_data.json").write_text(
        json.dumps(
            {
                "rows": rows,
                "aggregates": agg,
                "decision": {
                    "keep": keep,
                    "inconclusive": inconclusive,
                    "cond_a": cond_a,
                    "cond_b": cond_b,
                    "no_collapse": no_collapse,
                    "precision_ok": prec_ok,
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
