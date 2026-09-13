"""Offline replay of three saturated-side search rules on the evidence E3 and E3b left on disk.

No new rollout. For every (task, family) bracket in runs/e3-A (aea v0.2) and runs/e3b-A (v0.3), the
task's OBSERVED local interval is lo_t = the highest dose seen too easy (0 if none) and hi_t = the
lowest dose seen too hard (1 for the d = 1 test). The replay oracle for that task answers
``too_easy`` at or below lo_t, ``too_hard`` at or above hi_t and ``in_band`` strictly inside, i.e.
it treats the task's unexplored gap as its band (a structural stand-in: the true band lies inside
the gap, but the gap is also all the search can know). Tasks are replayed in the run's order with
the bisection budget that task actually had left after its estimate, no-leverage tests and d = 1
test, under three rules:

  v0.2  first interior probe 0.5, task-local [0, 1]
  v0.3  hard population bracket [lo_pop, hi_pop] from the previously replayed tasks (min / max)
  v0.4  soft warm start: first probe = median of >= 3 previous frontiers (lo_t + hi_t) / 2 of the
        replayed tasks, task-local [0, 1]

Reported per family: tasks whose observed region stays reachable, tasks censored (the rule's
interval excludes the observed region), probes to the first in-band dose, and rollouts. The
replay catches structural pathologies only; it does not predict the ALFWorld result.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

FIRST, FULL, CAP, MAX_BISECTIONS = 4, 8, 30, 4


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def evidence(run_dir: Path) -> list[dict[str, Any]]:
    """(task, family, lo_t, hi_t, budget_left, accepted_d) per bracket, in task order."""
    events = jsonl(run_dir / "events.jsonl")
    spent_before: dict[str, int] = defaultdict(int)
    out: list[dict[str, Any]] = []
    for e in events:
        p, k = e.get("payload", {}), e.get("kind")
        t = str(p.get("task_id"))
        if k == "rollouts" and not str(p.get("phase", "")).startswith("dose:"):
            spent_before[t] += int(p.get("n", 0))
        if k == "rollouts" and str(p.get("phase", "")).startswith("dose:"):
            fam = str(p["phase"]).split(":", 1)[1]
            spent_before[f"{t}:{fam}:pre"] += int(p.get("n", 0))
        if k == "bracket":
            hist = p.get("history") or []
            fam = str(p["family"])
            lo = max([0.0] + [h["d"] for h in hist if h["verdict"] == "too_easy"])
            hi = min([1.0] + [h["d"] for h in hist if h["verdict"] == "too_hard"])
            acc = [h["d"] for h in hist if h["verdict"] == "in_band"]
            leverage_cost = sum(h["n"] for h in hist if h["d"] == 1.0)
            # budget left for bisections = cap - everything charged before this family's bracket
            other = spent_before[t] + sum(
                v
                for kk, v in spent_before.items()
                if kk.startswith(f"{t}:") and kk != f"{t}:{fam}:pre"
            )
            left = CAP - other - leverage_cost
            out.append(
                {
                    "task": t,
                    "family": fam,
                    "lo_t": lo,
                    "hi_t": hi,
                    "budget_left": max(left, 0),
                    "accepted_d": acc[0] if acc else None,
                    "observed_history": [(h["d"], h["verdict"]) for h in hist],
                }
            )
    return out


def oracle(lo_t: float, hi_t: float, d: float) -> str:
    if d <= lo_t:
        return "too_easy"
    if d >= hi_t:
        return "too_hard"
    return "in_band"


def simulate(ev: dict[str, Any], start: float, lo0: float, hi0: float) -> dict[str, Any]:
    """Bisect from ``start`` inside [lo0, hi0] with the task's replay oracle and budget."""
    lo, hi = lo0, hi0
    if not lo < start < hi:
        start = (lo + hi) / 2
    d, budget, probes, rollouts = start, ev["budget_left"], 0, 0
    reached = False
    accepted_d: float | None = None
    for _ in range(MAX_BISECTIONS):
        if budget < FIRST:
            break
        v = oracle(ev["lo_t"], ev["hi_t"], d)
        cost = FULL if v == "in_band" else FIRST
        if budget < cost:
            rollouts += FIRST
            probes += 1
            break
        budget -= cost
        rollouts += cost
        probes += 1
        if v == "in_band":
            reached = True
            accepted_d = d
            break
        if v == "too_easy":
            lo = d
        else:
            hi = d
        d = (lo + hi) / 2
    censored = not (
        lo0 < ev["hi_t"] and hi0 > ev["lo_t"] and lo0 < hi0
    )  # region outside the rule's interval
    return {
        "start": start,
        "reached": reached,
        "probes": probes,
        "rollouts": rollouts,
        "final": [lo, hi],
        "accepted_d": accepted_d,
        "censored": censored,
    }


def replay(evs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in evs:
        by_family[e["family"]].append(e)
    report: dict[str, dict[str, Any]] = {}
    for fam, items in by_family.items():
        rows = []
        lo_pop, hi_pop = 0.0, 1.0
        frontiers: list[float] = []
        for ev in items:
            r02 = simulate(ev, 0.5, 0.0, 1.0)
            seed = (lo_pop, hi_pop) if lo_pop < hi_pop else (0.0, 1.0)
            r03 = simulate(ev, (seed[0] + seed[1]) / 2, seed[0], seed[1])
            start = statistics.median(frontiers) if len(frontiers) >= 3 else 0.5
            r04 = simulate(ev, start, 0.0, 1.0)
            rows.append(
                {
                    "task": ev["task"],
                    "lo_t": ev["lo_t"],
                    "hi_t": ev["hi_t"],
                    "budget_left": ev["budget_left"],
                    "v0.2": r02,
                    "v0.3": r03,
                    "v0.4": r04,
                }
            )
            # population updates from the replayed v0.3 walk's observations (its own oracle answers)
            lo_pop = max(lo_pop, r03["final"][0]) if r03["final"][0] < 1.0 else lo_pop
            hi_pop = min(hi_pop, r03["final"][1])
            frontiers.append(
                r04["accepted_d"]
                if r04["accepted_d"] is not None
                else (r04["final"][0] + r04["final"][1]) / 2
            )
        report[fam] = {
            "tasks": len(rows),
            "rows": rows,
            "summary": {
                rule: {
                    "reachable": sum(1 for r in rows if not r[rule]["censored"]),
                    "censored": sum(1 for r in rows if r[rule]["censored"]),
                    "reached_band": sum(1 for r in rows if r[rule]["reached"]),
                    "probes": sum(r[rule]["probes"] for r in rows),
                    "rollouts": sum(r[rule]["rollouts"] for r in rows),
                }
                for rule in ("v0.2", "v0.3", "v0.4")
            },
        }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="/home/kree/work/EnvJudge/runs")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    runs = Path(args.runs)
    # E3 (v0.2) brackets are genuine bisections from 0.5 and give usable per-task intervals; E3b
    # (v0.3) brackets were confined below the collapsed ceiling, so their observed gaps are
    # artifacts of the collapse (e.g. (0.499999, 1.0)) and cannot stand in for a task's band.
    # They are replayed separately for completeness and excluded from the headline counts.
    evs = evidence(runs / "e3-A")
    rep = replay(evs)
    rep_e3b = replay(evidence(runs / "e3b-A"))
    lines = [
        "# Offline replay of the saturated-side search rules on the E3 bracket evidence",
        "",
    ]
    lines.append(
        f"Brackets replayed: {len(evs)} (E3 v0.2 run + E3b v0.3 run), in run order per family. The oracle treats each task's observed gap (lo_t, hi_t) as its band; a rule 'reaches' when a probe lands inside it within that task's remaining budget; 'censored' means the rule's search interval excluded the observed region because of OTHER tasks' observations."  # noqa: E501
    )
    lines += [
        "",
        "| family | tasks | rule | reachable | censored | reached band | probes | rollouts |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fam, r in sorted(rep.items(), key=lambda kv: -kv[1]["tasks"]):
        for rule, s in r["summary"].items():
            lines.append(
                f"| {fam} | {r['tasks']} | {rule} | {s['reachable']} | {s['censored']} | {s['reached_band']} | {s['probes']} | {s['rollouts']} |"  # noqa: E501
            )
    lines += [
        "",
        "## Per task (families with >= 3 tasks)",
        "",
        "| family | task | observed (lo_t, hi_t) | budget left | v0.2 start / reached / probes | v0.3 interval / reached / censored | v0.4 start / reached / probes |",  # noqa: E501
        "|---|---|---|---|---|---|---|",
    ]
    for fam, r in sorted(rep.items(), key=lambda kv: -kv[1]["tasks"]):
        if r["tasks"] < 3:
            continue
        for row in r["rows"]:
            a, b, c = row["v0.2"], row["v0.3"], row["v0.4"]
            lines.append(
                f"| {fam} | {row['task']} | ({row['lo_t']}, {row['hi_t']}) | {row['budget_left']} | {a['start']:.4g} / {a['reached']} / {a['probes']} | [{b['final'][0]:.4g}, {b['final'][1]:.4g}] / {b['reached']} / {b['censored']} | {c['start']:.4g} / {c['reached']} / {c['probes']} |"  # noqa: E501
            )
    lines += [
        "",
        "## E3b (v0.3 run) brackets, replayed but not counted",
        "",
        "| family | tasks | rule | reachable | censored | reached band | probes | rollouts |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fam, r in sorted(rep_e3b.items(), key=lambda kv: -kv[1]["tasks"]):
        for rule, s in r["summary"].items():
            lines.append(
                f"| {fam} | {r['tasks']} | {rule} | {s['reachable']} | {s['censored']} | {s['reached_band']} | {s['probes']} | {s['rollouts']} |"  # noqa: E501
            )
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(
            json.dumps(rep, indent=1, default=str), encoding="utf-8"
        )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
