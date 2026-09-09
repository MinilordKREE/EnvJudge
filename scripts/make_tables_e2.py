"""E2 step-1 tables (PREREG8-Z) -> experiments/alfworld_e2/results/e2_step1.md.

Z1: learnable environments per 1,000 charged search rollouts (Z, G, R; task bootstrap CIs).
Z2: unlocked zero tasks (shared original p16 = 0 this run, accepted environment learnable).
Z3: Z's per-task learnability profile (late-learnable / poisoned / dead / unresolved-budget),
certified-state counts, G's / R's accepted environments with p16; Z-full reference; per-task
budget breakdown for Z;
G/R attempts and decisions; shared p16; spend by arm and budget; incidents; kill rule.
"""

from __future__ import annotations

import argparse
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
RESULTS = ROOT / "experiments" / "alfworld_e2" / "results"
TASKS = ("0", "8", "9", "10", "11", "14", "17", "18", "20", "27")
BOOT = 10_000


def d(arm: str) -> Path:
    return RUNS / f"e2-{arm}"


def confirm(arm: str) -> dict[str, dict[str, Any]]:
    p = d(arm) / "confirm_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def events(arm: str) -> list[dict[str, Any]]:
    return mt.jsonl(d(arm) / "events.jsonl")


def search_rollouts(arm: str) -> dict[str, int]:
    """Charged search rollouts per task from the arm's traces (every policy episode without an
    error, hint episodes excluded). For Z this includes the episodes of tasks re-run after the
    staging crash (the controller's in-memory budget restarted for them), so Z1's denominator is
    the full spend, not the accounting file of the resumed process."""
    per: dict[str, int] = defaultdict(int)
    for r in mt.jsonl(d(arm) / "traces.jsonl"):
        if r.get("error") or str(r.get("candidate_id")) == "hint":
            continue
        per[str(r["rollout_seed"])] += 1
    return dict(per)


def z1(arm: str, rng: random.Random) -> dict[str, Any]:
    conf = confirm(arm)
    learn: dict[str, int] = defaultdict(int)
    for e in conf.values():
        if e.get("learnable"):
            learn[str(e["task"])] += 1
    rolls = search_rollouts(arm)
    tasks = list(TASKS)
    tl, tr = sum(learn.values()), sum(rolls.values())
    rate = 1000 * tl / tr if tr else float("nan")
    boots = []
    for _ in range(BOOT):
        s = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        lr, rr = sum(learn.get(t, 0) for t in s), sum(rolls.get(t, 0) for t in s)
        boots.append(1000 * lr / rr if rr else 0.0)
    boots.sort()
    return {
        "envs": len(conf),
        "learnable": tl,
        "rollouts": tr,
        "per_1000": rate,
        "ci95": [boots[int(0.025 * BOOT)], boots[int(0.975 * BOOT)]],
    }


def unlocked(arm: str, zero_tasks: set[str]) -> list[str]:
    return sorted(
        {
            str(e["task"])
            for e in confirm(arm).values()
            if e.get("learnable") and str(e["task"]) in zero_tasks
        },
        key=int,
    )


def z_profile() -> dict[str, dict[str, Any]]:
    per: dict[str, dict[str, Any]] = {
        t: {
            "status": None,
            "regime": None,
            "p_hat": None,
            "n_est": 0,
            "certified": 0,
            "rejected": 0,
            "probes": [],
            "skipped": [],
            "too_easy": [],
            "n_search": None,
            "rollouts": defaultdict(int),
            "certificates": 0,
        }
        for t in TASKS
    }
    for e in events("Z"):
        k, p = e.get("kind"), e.get("payload", {})
        t = str(p.get("task_id"))
        if t not in per:
            continue
        if k == "estimate":
            per[t].update({"regime": p.get("regime"), "p_hat": p.get("p_hat"), "n_est": p.get("n")})
        elif k == "stage_candidates":
            per[t]["certified"] = len(p.get("certified") or [])
            per[t]["rejected"] = len(p.get("rejected") or [])
            per[t]["certificates"] = per[t]["certified"] + per[t]["rejected"]
        elif k == "probe":
            per[t]["probes"] = list(p.get("profile") or [])
        elif k == "probe_skipped_budget":
            per[t]["skipped"] = list(p.get("skipped") or [])
        elif k == "rollouts":
            per[t]["rollouts"][str(p.get("phase"))] += int(p.get("n", 0))
        elif k == "task_done":
            per[t]["status"] = p.get("status")
            per[t]["n_search"] = p.get("n_search")
            per[t]["too_easy"] = list(p.get("too_easy") or [])
    for v in per.values():
        probes = v["probes"]
        if v["status"] == "accepted_stage":
            v["profile"] = "late-learnable"
        elif (
            v["status"]
            in ("band", "accepted_knob", "frozen_no_leverage", "exhausted", "budget_cap_hit")
            and v["regime"] != "zero"
        ):
            v["profile"] = f"regime drift ({v['regime']})"
        elif probes and all(x.get("cls") == "dead" for x in probes) and not v["skipped"]:
            v["profile"] = "dead"
        elif probes and any(x.get("cls") == "too_easy_stage" for x in probes) and not v["skipped"]:
            v["profile"] = "poisoned"
        elif v["skipped"]:
            v["profile"] = "unresolved (budget)"
        else:
            v["profile"] = v["status"] or "-"
    return per


def released_per_task(arm: str) -> dict[str, dict[str, Any]]:
    per: dict[str, dict[str, Any]] = {
        t: {"baseline": 0, "exploration": 0, "accepted": 0, "attempts": 0, "decision": "skipped"}
        for t in TASKS
    }
    for r in mt.jsonl(d(arm) / "traces.jsonl"):
        t = str(r["rollout_seed"])
        if t in per:
            per[t][str(r.get("kind"))] = per[t].get(str(r.get("kind")), 0) + 1
    for v in per.values():
        v["attempts"] = round((v["exploration"] + v["accepted"]) / 5)
        v["decision"] = (
            "accepted" if v["accepted"] else ("all_rejected" if v["exploration"] else "skipped")
        )
    return per


def spend() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for run in sorted(RUNS.glob("e2-*")):
        for r in mt.jsonl(run / "ledger.jsonl"):
            if r.get("event") == "call":
                out[run.name][str(r.get("budget"))] += float(r.get("usd") or 0.0)
    return {k: dict(v) for k, v in out.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "e2_step1.md"))
    ap.add_argument("--seed", type=int, default=20260909)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    RESULTS.mkdir(parents=True, exist_ok=True)
    shared = confirm("shared")
    zero_tasks = {str(e["task"]) for e in shared.values() if e.get("successes") == 0}
    lines = ["# E2 step 1 — zero side on Qwen3-8B (PREREG8-Z)", ""]
    lines += [
        "## Shared original-environment K=16 (defines zero for this run)",
        "",
        "| task | p16 (shared) | class |",
        "|---|---|---|",
    ]
    for t in TASKS:
        e = shared.get(f"{t}:orig", {})
        p = e.get("p16")
        cls = (
            "-"
            if p is None
            else (
                "zero"
                if p == 0
                else "learnable"
                if 0.2 <= p <= 0.8
                else "marginal-low"
                if p < 0.2
                else "high"
            )
        )
        lines.append(f"| {t} | {mt.fmt(p, 3)} | {cls} |")
    lines += [
        "",
        f"Zero tasks this run: {sorted(zero_tasks, key=int) or 'none'} ({len(zero_tasks)}).",
        "",
    ]

    z1_rows = {arm: z1(arm, rng) for arm in ("Z", "G", "R")}
    lines += [
        "## Z1 — learnable environments per 1,000 charged search rollouts",
        "",
        "| arm | accepted envs | learnable | search rollouts | per 1,000 [95% CI, task bootstrap] |",  # noqa: E501
        "|---|---|---|---|---|",
    ]
    for arm in ("Z", "G", "R"):
        r = z1_rows[arm]
        lines.append(
            f"| {arm} | {r['envs']} | {r['learnable']} | {r['rollouts']} | {mt.fmt(r['per_1000'])} [{mt.fmt(r['ci95'][0])}, {mt.fmt(r['ci95'][1])}] |"  # noqa: E501
        )
    zg = z1_rows["Z"]["per_1000"] > z1_rows["G"]["per_1000"]
    zr = z1_rows["Z"]["per_1000"] > z1_rows["R"]["per_1000"]
    lines += [
        "",
        f"**Z1: Z > G {'holds' if zg else 'fails'}; Z > R {'holds' if zr else 'fails'} (point estimates).**",  # noqa: E501
        "",
    ]

    unl = {arm: unlocked(arm, zero_tasks) for arm in ("Z", "G", "R", "Zfull")}
    lines += ["## Z2 — unlocked zero tasks", "", "| arm | unlocked | tasks |", "|---|---|---|"]
    for arm in ("Z", "G", "R", "Zfull"):
        lines.append(
            f"| {arm}{' (reference)' if arm == 'Zfull' else ''} | {len(unl[arm])} | {', '.join(unl[arm]) or '-'} |"  # noqa: E501
        )
    z2 = len(unl["Z"]) >= 3 and len(unl["Z"]) >= len(unl["G"])
    kill = len(unl["Z"]) <= 1 or len(unl["Z"]) < len(unl["G"])
    lines += [
        "",
        f"**Z2: Z unlocks {len(unl['Z'])} (>= 3: {'yes' if len(unl['Z']) >= 3 else 'no'}); Z >= G: {'yes' if len(unl['Z']) >= len(unl['G']) else 'no'} → {'holds' if z2 else 'fails'}.**",  # noqa: E501
        "",
        f"**Kill rule (Z unlocks <= 1 or fewer than G): {'TRIGGERED — the zero-side claim is dead on this benchmark/agent; E2 stops' if kill else 'not triggered'}.**",  # noqa: E501
        "",
    ]

    prof = z_profile()
    lines += [
        "## Z3 — Z per-task learnability profile",
        "",
        "| task | shared p16 | estimate (regime, p_hat, n) | certified / rejected states | probes (t: s/n cls) | skipped by cap | status | profile |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        v = prof[t]
        probes = (
            "; ".join(
                f"{x.get('t')}: {x.get('successes')}/{x.get('n')} {x.get('cls')}"
                for x in v["probes"]
            )
            or "-"
        )
        lines.append(
            f"| {t} | {mt.fmt(shared.get(f'{t}:orig', {}).get('p16'), 3)} | {v['regime']}, {mt.fmt(v['p_hat'], 3)}, {v['n_est']} | {v['certified']} / {v['rejected']} | {probes} | {len(v['skipped'])} | {v['status']} | {v['profile']} |"  # noqa: E501
        )
    zf = (
        json.loads((d("Zfull") / "zfull_summary.json").read_text(encoding="utf-8"))
        if (d("Zfull") / "zfull_summary.json").exists()
        else {}
    )
    if zf:
        lines += [
            "",
            "Z-full (reference, uncharged): probe walk continued over the skipped candidates.",
            "",
            "| task | probed | profile (t: s/n cls) | status | accepted t | confirmed p16 |",
            "|---|---|---|---|---|---|",
        ]
        zconf = confirm("Zfull")
        for t in sorted(zf, key=int):
            rec = zf[t]
            pr = (
                "; ".join(f"{x['t']}: {x['successes']}/{x['n']} {x['cls']}" for x in rec["profile"])
                or "-"
            )
            acc = rec.get("accepted") or {}
            p16 = next((e["p16"] for e in zconf.values() if str(e["task"]) == t), None)
            lines.append(
                f"| {t} | {len(rec['profile'])} | {pr} | {rec['status']} | {acc.get('t', '-')} | {mt.fmt(p16, 3)} |"  # noqa: E501
            )
    lines += [
        "",
        "### Accepted environments and their p16",
        "",
        "| arm | task | env | kind / t | p16 | learnable |",
        "|---|---|---|---|---|---|",
    ]
    for arm in ("Z", "G", "R", "Zfull"):
        for env_id, e in sorted(confirm(arm).items(), key=lambda kv: int(kv[1]["task"])):
            lines.append(
                f"| {arm} | {e['task']} | {env_id[:40]} | {e.get('kind')} {e.get('t') if e.get('t') is not None else ''} | {mt.fmt(e.get('p16'), 3)} | {'y' if e.get('learnable') else '-'} |"  # noqa: E501
            )

    lines += [
        "",
        "## Z per-task budget breakdown (charged search rollouts by phase; certificates = expert sessions, 0 policy rollouts)",  # noqa: E501
        "",
        "| task | estimate | probes | dose (drift) | hint | n_search | certificate sessions (states certified + rejected) |",  # noqa: E501
        "|---|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        v = prof[t]
        ro = v["rollouts"]
        dose = sum(n for ph, n in ro.items() if ph.startswith("dose:"))
        hint = sum(n for ph, n in ro.items() if ph.startswith("hint:"))
        lines.append(
            f"| {t} | {ro.get('estimate', 0)} | {ro.get('probe', 0)} | {dose} | {hint} | {v['n_search']} | {v['certificates']} |"  # noqa: E501
        )

    lines += [
        "",
        "## G and R per task (released orchestrator; Qwen policy, DeepSeek designer)",
        "",
        "| arm | task | baseline rollouts | candidates tried | accepted | decision | accepted-env p16 |",  # noqa: E501
        "|---|---|---|---|---|---|---|",
    ]
    for arm in ("G", "R"):
        per = released_per_task(arm)
        conf = confirm(arm)
        for t in TASKS:
            v = per[t]
            p16s = [mt.fmt(e["p16"], 3) for e in conf.values() if str(e["task"]) == t]
            lines.append(
                f"| {arm} | {t} | {v['baseline']} | {v['attempts']} | {v['accepted'] // 5 if v['accepted'] else 0} | {v['decision']} | {', '.join(p16s) or '-'} |"  # noqa: E501
            )

    sp = spend()
    lines += ["", "## Spend (USD by run and budget)", "", "| run | budgets |", "|---|---|"]
    total = 0.0
    for run, budgets in sorted(sp.items()):
        total += sum(budgets.values())
        lines.append(
            f"| {run} | " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(budgets.items())) + " |"
        )
    lines += ["", f"E2 step-1 total USD {total:.2f} (cap 90).", ""]
    inc = (
        mt.jsonl(RUNS / "e2-eval" / "guard_incidents.jsonl") if (RUNS / "e2-eval").exists() else []
    )
    lines += [
        "## Incidents",
        "",
        f"Guard incidents: {len(inc)}. See experiments/alfworld_e2/LOG.md for launches, crashes and resumes.",  # noqa: E501
        "",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "e2_step1_data.json").write_text(
        json.dumps(
            {
                "z1": z1_rows,
                "unlocked": unl,
                "zero_tasks": sorted(zero_tasks, key=int),
                "profile": {
                    t: {k: v for k, v in p.items() if k != "rollouts"}
                    | {"rollouts": dict(p["rollouts"])}
                    for t, p in prof.items()
                },
                "spend": sp,
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
