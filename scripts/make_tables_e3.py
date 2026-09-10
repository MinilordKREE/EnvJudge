"""E3 layer-1 tables (PREREG9) -> experiments/alfworld_e3/results/e3_layer1.md and
e3_layer1_data.json.

Every number in the report is computed here from the run directories (runs/e3-*, the reused
runs/e2-shared and, for reference, runs/e2v02-Z):
  shared K=16 per task and its class (zero / marginal-low / band / saturated);
  C1 primary  learner-facing learnable environments per 1,000 charged search rollouts, per arm,
              task-level bootstrap CIs (A: kept + accepted; G, R: accepted non-empty candidates);
  C1 secondary transformed-only (the PREREG7 definition);
  band preservation, unlocked zero tasks and precision, the saturated subset, the H100 control;
  per-arm outcome / reason counts, family of origin (exemplar vs proposer, dose), per-task
  budget breakdown, spend by run and budget, incidents; the PREREG9 claims and stop rules.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3  # the driver: run layout, shared K16, candidate keys

ROOT = e3.ROOT
RUNS = e3.RUNS
RESULTS = e3.RESULTS
TASKS = [str(t) for t in e3.TASKS]
ARMS = ("A", "G", "R")
BOOT = 10_000
B_L = (0.2, 0.8)


def fmt(x: float | None, nd: int = 1) -> str:
    if x is None:
        return "-"
    try:
        if x != x:  # nan
            return "-"
    except TypeError:
        return str(x)
    return f"{x:.{nd}f}"


def d(name: str) -> Path:
    return RUNS / f"e3-{name}"


# ---------------------------------------------------------------------------- inputs
def shared_classes() -> dict[str, dict[str, Any]]:
    """task -> {p16, successes, n, cls}; cls in zero / marginal-low / band / saturated / -."""
    out: dict[str, dict[str, Any]] = {}
    shared = e3.shared_p16()
    for t in TASKS:
        s = shared.get(f"{t}:orig", {})
        p, n = s.get("p16"), s.get("n") or 0
        if p is None or n <= 0:
            cls = "-"
        elif s.get("successes") == 0:
            cls = "zero"
        elif p < B_L[0]:
            cls = "marginal-low"
        elif p <= B_L[1]:
            cls = "band"
        else:
            cls = "saturated"
        out[t] = {
            "p16": p,
            "successes": s.get("successes"),
            "n": n,
            "cls": cls,
            "source": s.get("source"),
        }
    return out


def confirm() -> dict[str, dict[str, Any]]:
    p = d("confirm") / "confirm_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def charged(arm: str) -> dict[str, int]:
    """Charged search rollouts per task: every policy episode of the arm's search without an
    error (A: estimate + dose + probe; G, R: baseline + exploration + accepted validation)."""
    per: dict[str, int] = defaultdict(int)
    for r in e3.jsonl(d(arm) / "traces.jsonl"):
        if r.get("error"):
            continue
        per[str(r["rollout_seed"])] += 1
    return dict(per)


def arm_envs(arm: str, conf: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": k, **v} for k, v in conf.items() if arm in (v.get("arms") or [])]


def a_profile() -> dict[str, dict[str, Any]]:
    per: dict[str, dict[str, Any]] = {
        t: {
            "outcome": None,
            "reason": None,
            "regime": None,
            "p_hat": None,
            "n_est": 0,
            "n_search": None,
            "rollouts": defaultdict(int),
            "families": [],
            "proposed": [],
            "proposer_rejected": 0,
            "brackets": [],
            "no_leverage": [],
            "uncertified": [],
            "certified": 0,
            "rejected": 0,
            "probes": [],
            "skipped": [],
            "infra_errors": 0,
        }
        for t in TASKS
    }
    for e in e3.jsonl(d("A") / "events.jsonl"):
        k, p = e.get("kind"), e.get("payload", {})
        t = str(p.get("task_id"))
        if t not in per:
            continue
        v = per[t]
        if k == "estimate":
            v.update({"regime": p.get("regime"), "p_hat": p.get("p_hat"), "n_est": p.get("n")})
        elif k == "families":
            v["families"] = list(p.get("order") or [])
        elif k == "proposer":
            v["proposed"] = list(p.get("proposed") or [])
            v["proposer_rejected"] = len(p.get("rejected") or [])
        elif k == "bracket":
            v["brackets"].append(
                {
                    "family": p.get("family"),
                    "start": p.get("start"),
                    "status": p.get("status"),
                    "history": p.get("history"),
                }
            )
        elif k == "no_leverage":
            v["no_leverage"].append(p.get("family"))
        elif k == "family_skipped" and p.get("reason") == "uncertified":
            v["uncertified"].append(p.get("family"))
        elif k == "stage_candidates":
            v["certified"] = len(p.get("certified") or [])
            v["rejected"] = len(p.get("rejected") or [])
        elif k == "probe":
            v["probes"] = list(p.get("profile") or [])
            v["skipped"] = list(p.get("skipped") or [])
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


def a_corpus() -> dict[str, list[dict[str, Any]]]:
    per: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in e3.jsonl(d("A") / "corpus.jsonl"):
        meta = e.get("aea") or {}
        per[str(meta.get("task_id"))].append(
            {
                "kind": meta.get("kind"),
                "family": meta.get("family"),
                "source": meta.get("source"),
                "axis": meta.get("axis"),
                "d": meta.get("d"),
                "t": meta.get("t"),
                "candidate_id": meta.get("candidate_id"),
                "p_hat": meta.get("p_hat"),
                "key": e3.candidate_key(
                    {"rules_code": e.get("rules_code"), "in_env_actions": e.get("in_env_actions")}
                ),
            }
        )
    return per


def released_per_task(arm: str) -> dict[str, dict[str, Any]]:
    per: dict[str, dict[str, Any]] = {
        t: {
            "baseline": 0,
            "exploration": 0,
            "accepted": 0,
            "errors": 0,
            "attempts": 0,
            "decision": "not_run",
            "accepted_keys": [],
        }
        for t in TASKS
    }
    for r in e3.jsonl(d(arm) / "traces.jsonl"):
        t = str(r["rollout_seed"])
        if t not in per:
            continue
        if r.get("error"):
            per[t]["errors"] += 1
            continue
        kind = str(r.get("kind"))
        per[t][kind] = per[t].get(kind, 0) + 1
        if kind == "accepted" and not e3.is_unchanged(r["candidate"]):
            key = e3.candidate_key(r["candidate"])
            if key not in per[t]["accepted_keys"]:
                per[t]["accepted_keys"].append(key)
    skipped: set[str] = set()
    for e in e3.jsonl(d(arm) / "orchestrator.jsonl"):
        if e.get("kind") == "task_skipped_passthrough":
            skipped.add(str(e.get("task_id")))
    for t, v in per.items():
        v["attempts"] = round((v["exploration"] + v["accepted"]) / 5)
        if v["accepted_keys"]:
            v["decision"] = "accepted"
        elif v["accepted"]:
            v["decision"] = "accepted_empty"
        elif t in skipped or (v["baseline"] and not v["exploration"]):
            v["decision"] = "skipped"
        elif v["exploration"]:
            v["decision"] = "all_rejected"
    return per


# ---------------------------------------------------------------------------- rates
def rate(
    envs: list[dict[str, Any]],
    rolls: dict[str, int],
    tasks: list[str],
    rng: random.Random,
) -> dict[str, Any]:
    """Learnable environments per 1,000 charged rollouts over ``tasks`` with a task bootstrap."""
    learn: dict[str, int] = defaultdict(int)
    n_env: dict[str, int] = defaultdict(int)
    for e in envs:
        t = str(e["task"])
        if t in tasks:
            n_env[t] += 1
            learn[t] += int(bool(e.get("learnable")))
    tl = sum(learn.values())
    tr = sum(rolls.get(t, 0) for t in tasks)
    per = 1000 * tl / tr if tr else float("nan")
    boots: list[float] = []
    if tasks:
        for _ in range(BOOT):
            s = [tasks[rng.randrange(len(tasks))] for _ in tasks]
            lr, rr = sum(learn.get(t, 0) for t in s), sum(rolls.get(t, 0) for t in s)
            boots.append(1000 * lr / rr if rr else 0.0)
        boots.sort()
    return {
        "envs": sum(n_env.values()),
        "learnable": tl,
        "rollouts": tr,
        "tasks": len(tasks),
        "per_1000": per,
        "ci95": [boots[int(0.025 * BOOT)], boots[int(0.975 * BOOT)]] if boots else [None, None],
    }


def spend() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for run in sorted(RUNS.glob("e3-*")):
        if not run.is_dir():
            continue
        for r in e3._ledger_rows(run):
            if r.get("event") == "call":
                out[run.name][str(r.get("budget"))] += float(r.get("usd") or 0.0)
    return {k: dict(v) for k, v in out.items()}


def incidents() -> dict[str, Any]:
    out: dict[str, Any] = {"guard_incidents": 0, "retries_429": 0, "retries_other": 0}
    for run in sorted(RUNS.glob("e3-*")):
        if not run.is_dir():
            continue
        out["guard_incidents"] += len(e3.jsonl(run / "guard_incidents.jsonl"))
        for r in e3._ledger_rows(run):
            if r.get("event") == "infra_retry":
                if r.get("status_code") == 429:
                    out["retries_429"] += 1
                else:
                    out["retries_other"] += 1
    errs: dict[str, int] = {}
    for arm in ARMS:
        errs[arm] = sum(1 for r in e3.jsonl(d(arm) / "traces.jsonl") if r.get("error"))
    out["errored_rollouts"] = errs
    out["a_infra_error_tasks"] = sorted(
        {
            str(e["payload"].get("task_id"))
            for e in e3.jsonl(d("A") / "events.jsonl")
            if e.get("kind") == "task_done" and e["payload"].get("outcome") == "infra_error"
        },
        key=int,
    )
    return out


def verdict(ok: bool) -> str:
    return "holds" if ok else "fails"


# ---------------------------------------------------------------------------- report
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "e3_layer1.md"))
    ap.add_argument("--seed", type=int, default=20260911)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    RESULTS.mkdir(parents=True, exist_ok=True)

    sh = shared_classes()
    conf = confirm()
    rolls = {arm: charged(arm) for arm in ARMS}
    envs = {arm: arm_envs(arm, conf) for arm in ARMS}
    transformed = {arm: [e for e in envs[arm] if e.get("kind") != "kept"] for arm in ARMS}
    zero = [t for t in TASKS if sh[t]["cls"] == "zero"]
    band = [t for t in TASKS if sh[t]["cls"] == "band"]
    sat = [t for t in TASKS if sh[t]["cls"] == "saturated"]
    measured = [t for t in TASKS if sh[t]["cls"] != "-"]

    primary = {arm: rate(envs[arm], rolls[arm], TASKS, rng) for arm in ARMS}
    secondary = {arm: rate(transformed[arm], rolls[arm], TASKS, rng) for arm in ARMS}
    sat_rate = {arm: rate(transformed[arm], rolls[arm], sat, rng) for arm in ARMS}
    preserved = {
        arm: sorted(
            {str(e["task"]) for e in envs[arm] if e.get("learnable") and str(e["task"]) in band},
            key=int,
        )
        for arm in ARMS
    }
    unlocked = {
        arm: sorted(
            {
                str(e["task"])
                for e in transformed[arm]
                if e.get("learnable") and str(e["task"]) in zero
            },
            key=int,
        )
        for arm in ARMS
    }
    precision = {
        arm: (
            sum(int(bool(e.get("learnable"))) for e in transformed[arm]),
            len(transformed[arm]),
        )
        for arm in ARMS
    }
    prof = a_profile()
    corpus = a_corpus()
    rel = {arm: released_per_task(arm) for arm in ("G", "R")}
    h100_path = d("H100") / "h100_summary.json"
    h100 = json.loads(h100_path.read_text(encoding="utf-8")) if h100_path.exists() else {}
    e2v02_path = RUNS / "e2v02-Z" / "confirm_summary.json"
    e2v02 = json.loads(e2v02_path.read_text(encoding="utf-8")) if e2v02_path.exists() else {}
    sp = spend()
    inc = incidents()
    total_usd = sum(sum(v.values()) for v in sp.values())

    lines: list[str] = []
    lines += [
        "# E3 layer 1 — environment production at matched budget, Qwen3-8B, ALFWorld seeds 0-29 (PREREG9)",  # noqa: E501
        "",
        f"Policy Qwen3-8B (OpenRouter, alibaba pin, reasoning off); designer DeepSeek V4 Pro (thinking off) for every arm; cap 30 policy rollouts per task per arm; K = 16 confirmations (budget eval, never written back); B_L = [{B_L[0]}, {B_L[1]}]. Shared original-environment K=16: 10 tasks reused from E2 (runs/e2-shared), 20 new (runs/e3-shared). Tables from scripts/make_tables_e3.py; PREREG9 @ {e3.PREREG_SHA}.",  # noqa: E501
        "",
        "## Shared original-environment K=16 per task",
        "",
        "| task | p16 | s/n | class | source |",
        "|---|---|---|---|---|",
    ]
    for t in TASKS:
        s = sh[t]
        lines.append(
            f"| {t} | {fmt(s['p16'], 3)} | {s['successes'] if s['successes'] is not None else '-'}/{s['n']} | {s['cls']} | {s['source'] or '-'} |"  # noqa: E501
        )
    lines += [
        "",
        f"Classes: zero {len(zero)} ({', '.join(zero) or '-'}); marginal-low {len([t for t in TASKS if sh[t]['cls'] == 'marginal-low'])}; band {len(band)} ({', '.join(band) or '-'}); saturated {len(sat)} ({', '.join(sat) or '-'}); unmeasured {len(TASKS) - len(measured)}.",  # noqa: E501
        "",
        "## C1 primary — learner-facing learnable environments per 1,000 charged search rollouts",
        "",
        "| arm | learner-facing envs | learnable | charged rollouts | per 1,000 [95% CI, task bootstrap] |",  # noqa: E501
        "|---|---|---|---|---|",
    ]
    for arm in ARMS:
        r = primary[arm]
        lines.append(
            f"| {arm} | {r['envs']} | {r['learnable']} | {r['rollouts']} | {fmt(r['per_1000'])} [{fmt(r['ci95'][0])}, {fmt(r['ci95'][1])}] |"  # noqa: E501
        )
    lines += [
        "",
        "## C1 secondary — transformed-only (PREREG7 definition)",
        "",
        "| arm | transformed envs | learnable | charged rollouts | per 1,000 [95% CI] |",
        "|---|---|---|---|---|",
    ]
    for arm in ARMS:
        r = secondary[arm]
        lines.append(
            f"| {arm} | {r['envs']} | {r['learnable']} | {r['rollouts']} | {fmt(r['per_1000'])} [{fmt(r['ci95'][0])}, {fmt(r['ci95'][1])}] |"  # noqa: E501
        )
    lines += [
        "",
        f"## Band preservation — originally learnable tasks ({len(band)}: {', '.join(band) or '-'}) still learnable in the learner-facing set",  # noqa: E501
        "",
        "| arm | preserved | tasks |",
        "|---|---|---|",
    ]
    for arm in ARMS:
        lines.append(
            f"| {arm} | {len(preserved[arm])} / {len(band)} | {', '.join(preserved[arm]) or '-'} |"
        )
    lines += [
        "",
        f"## Unlocked zero tasks (zero: {', '.join(zero) or '-'}) and precision",
        "",
        "| arm | unlocked | tasks | precision (learnable / accepted transformed) |",
        "|---|---|---|---|",
    ]
    for arm in ARMS:
        lp, ap_ = precision[arm]
        lines.append(
            f"| {arm} | {len(unlocked[arm])} | {', '.join(unlocked[arm]) or '-'} | {lp} / {ap_} ({fmt(100 * lp / ap_ if ap_ else None, 0)}%) |"  # noqa: E501
        )
    lines += [
        "",
        f"## Saturated subset (original p16 > 0.8: {len(sat)} tasks) — learnable transformed environments per 1,000",  # noqa: E501
        "",
        "| arm | transformed envs | learnable | charged rollouts on the subset | per 1,000 [95% CI] |",  # noqa: E501
        "|---|---|---|---|---|",
    ]
    for arm in ARMS:
        r = sat_rate[arm]
        lines.append(
            f"| {arm} | {r['envs']} | {r['learnable']} | {r['rollouts']} | {fmt(r['per_1000'])} [{fmt(r['ci95'][0])}, {fmt(r['ci95'][1])}] |"  # noqa: E501
        )
    # H100 control
    lines += [
        "",
        "## H100 control — 100-step success from the original start (tasks 8, 9, 27) next to the staged p16",  # noqa: E501
        "",
        "| task | H100 s/n | H100 p | A staged env p16 (t) | E2 Phase D staged p16 (reference) | attribution |",  # noqa: E501
        "|---|---|---|---|---|---|",
    ]
    h100_attr: dict[str, str] = {}
    for t in [str(x) for x in e3.H100_TASKS]:
        h = h100.get(t, {})
        a_stage = [e for e in envs["A"] if str(e["task"]) == t and e.get("kind") == "stage"]
        a_p = a_stage[0].get("p16") if a_stage else None
        a_t = a_stage[0].get("t") if a_stage else None
        ref = next((v.get("p16") for v in e2v02.values() if str(v.get("task")) == t), None)
        hp = h.get("p16")
        staged = a_p if a_p is not None else ref
        if hp is None or staged is None:
            attr = "-"
        elif hp >= staged:
            attr = "horizon (H100 >= staged)"
        else:
            attr = "staging (H100 < staged)"
        h100_attr[t] = attr
        lines.append(
            f"| {t} | {h.get('successes', '-')}/{h.get('n', '-')}{' (topped up)' if h.get('topped_up') else ''} | {fmt(hp, 3)} | {fmt(a_p, 3)} ({a_t if a_t is not None else '-'}) | {fmt(ref, 3)} | {attr} |"  # noqa: E501
        )
    # claims
    c1 = {arm: primary[arm]["per_1000"] for arm in ARMS}
    e31 = c1["A"] > c1["G"] and c1["A"] > c1["R"]
    e32 = len(preserved["A"]) >= len(preserved["G"]) and len(preserved["A"]) >= len(preserved["R"])
    s3 = {arm: sat_rate[arm]["per_1000"] for arm in ARMS}
    e33 = s3["A"] >= s3["G"] if s3["A"] == s3["A"] and s3["G"] == s3["G"] else False
    e34 = len(unlocked["A"]) >= len(unlocked["G"])
    lines += [
        "",
        "## PREREG9 claims",
        "",
        f"- E3-1 (primary): A {fmt(c1['A'])} vs G {fmt(c1['G'])} and R {fmt(c1['R'])} per 1,000 → A > G {verdict(c1['A'] > c1['G'])}, A > R {verdict(c1['A'] > c1['R'])} → **{verdict(e31)}** (point estimates; CIs above).",  # noqa: E501
        f"- E3-2 (band preservation): A {len(preserved['A'])}, G {len(preserved['G'])}, R {len(preserved['R'])} of {len(band)} → **{verdict(e32)}**.",  # noqa: E501
        f"- E3-3 (saturated subset): A {fmt(s3['A'])} vs G {fmt(s3['G'])} per 1,000 → **{verdict(e33)}**.",  # noqa: E501
        f"- E3-4 (zero subset, reported, not a gate): A {len(unlocked['A'])} vs G {len(unlocked['G'])} unlocked → **{verdict(e34)}** (E2 Phase D anchor: 2 vs 2).",  # noqa: E501
        "- H100 (control): "
        + "; ".join(f"task {t}: {a}" for t, a in h100_attr.items())
        + ". A task whose 100-step original-start success is >= its staged p16 is attributed to horizon, not staging.",  # noqa: E501
        "",
        f"**Stop rule for downstream:** E3-3 {verdict(e33)} → {'the saturated side proceeds' if e33 else 'the saturated side returns to design before any skill or RL evaluation'}; E3-1 {verdict(e31)} → {'the downstream columns may run' if e31 else 'the downstream columns are not run'}.",  # noqa: E501
        "",
    ]
    # A per-task profile
    lines += [
        "## A per task (aea v0.2, proposer on, persistent priors)",
        "",
        "| task | shared p16 (class) | estimate (regime, p_hat, n) | families (order) | brackets (family: start → status, doses) | stage (certified/rejected; probes t: s/n verdict) | outcome | reason | n_search | learner-facing envs (p16) |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        v = prof[t]
        br = (
            "; ".join(
                f"{b['family']}: {fmt(b['start'], 3) if b['start'] is not None else 'mid'} → {b['status']}, "  # noqa: E501
                + "/".join(f"{h['d']}:{h['s']}/{h['n']}" for h in (b.get("history") or []))
                for b in v["brackets"]
            )
            or "-"
        )
        st = (
            f"{v['certified']}/{v['rejected']}; "
            + (
                "; ".join(
                    f"{x.get('t')}: {x.get('successes')}/{x.get('n')} {x.get('verdict')}"
                    for x in v["probes"]
                )
                or "-"
            )
            if v["regime"] == "zero"
            else "-"
        )
        lf = ", ".join(
            f"{e.get('kind')} {fmt(e.get('p16'), 3)}{'*' if e.get('learnable') else ''}"
            for e in envs["A"]
            if str(e["task"]) == t
        )
        lines.append(
            f"| {t} | {fmt(sh[t]['p16'], 3)} ({sh[t]['cls']}) | {v['regime']}, {fmt(v['p_hat'], 3)}, {v['n_est']} | {', '.join(v['families']) or '-'} | {br} | {st} | {v['outcome']} | {v['reason'] or '-'} | {v['n_search'] if v['n_search'] is not None else '-'} | {lf or '-'} |"  # noqa: E501
        )
    oc = Counter(f"{v['outcome']}{':' + v['reason'] if v['reason'] else ''}" for v in prof.values())
    lines += [
        "",
        "A outcomes: " + ", ".join(f"{k} {n}" for k, n in sorted(oc.items())) + ".",
        "",
        "### Family of origin — A's accepted environments",
        "",
        "| task | kind | family | source | axis | dose | t | p8 | confirmed p16 | learnable |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    origin: Counter[str] = Counter()
    for t in TASKS:
        for c in corpus.get(t, []):
            if c["kind"] == "kept":
                continue
            src = {"library": "exemplar", "llm": "proposer"}.get(
                str(c.get("source")), c.get("source")
            )
            origin[f"{c['kind']}:{src or '-'}:{c.get('family') or '-'}"] += 1
            ce = conf.get(f"{t}:{c['key']}", {})
            lines.append(
                f"| {t} | {c['kind']} | {c.get('family') or '-'} | {src or '-'} | {c.get('axis') or '-'} | {fmt(c.get('d'), 3) if c.get('d') is not None else '-'} | {c.get('t') if c.get('t') is not None else '-'} | {fmt(c.get('p_hat'), 3)} | {fmt(ce.get('p16'), 3)} | {'y' if ce.get('learnable') else '-'} |"  # noqa: E501
            )
    lines += [
        "",
        "Origin counts: "
        + (", ".join(f"{k} {n}" for k, n in sorted(origin.items())) or "none")
        + ".",
        "",
        "### A per-task budget (charged search rollouts by phase)",
        "",
        "| task | estimate | dose (harden) | probe (stage) | n_search | infra errors (refunded) |",
        "|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        ro = prof[t]["rollouts"]
        dose = sum(n for ph, n in ro.items() if ph.startswith("dose:"))
        lines.append(
            f"| {t} | {ro.get('estimate', 0)} | {dose} | {ro.get('probe', 0)} | {prof[t]['n_search'] if prof[t]['n_search'] is not None else '-'} | {prof[t]['infra_errors']} |"  # noqa: E501
        )
    # G, R
    lines += [
        "",
        "## G and R per task (released orchestrator; Qwen policy, DeepSeek designer)",
        "",
        "| arm | task | shared class | baseline | candidates tried | accepted (non-empty) | decision | charged | accepted-env p16 |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ("G", "R"):
        for t in TASKS:
            v = rel[arm][t]
            p16s = [
                f"{fmt(e.get('p16'), 3)}{'*' if e.get('learnable') else ''}"
                for e in envs[arm]
                if str(e["task"]) == t
            ]
            lines.append(
                f"| {arm} | {t} | {sh[t]['cls']} | {v['baseline']} | {v['attempts']} | {len(v['accepted_keys'])} | {v['decision']} | {rolls[arm].get(t, 0)} | {', '.join(p16s) or '-'} |"  # noqa: E501
            )
        dc = Counter(v["decision"] for v in rel[arm].values())
        lines.append("")
        lines.append(
            f"{arm} decisions: " + ", ".join(f"{k} {n}" for k, n in sorted(dc.items())) + "."
        )
        lines.append("")
    # confirmations
    lines += [
        "## Learner-facing environments and their K=16 (deduplicated across arms)",
        "",
        "| env | task | kind / t | arms | s/n | p16 | learnable |",
        "|---|---|---|---|---|---|---|",
    ]
    for env_id, e in sorted(conf.items(), key=lambda kv: (int(kv[1]["task"]), kv[0])):
        lines.append(
            f"| {env_id[:40]} | {e['task']} | {e.get('kind')} {e.get('t') if e.get('t') is not None else ''} | {', '.join(e.get('arms') or [])} | {e.get('successes')}/{e.get('n')} | {fmt(e.get('p16'), 3)} | {'y' if e.get('learnable') else '-'} |"  # noqa: E501
        )
    # spend, incidents
    lines += [
        "",
        "## Spend (USD by run and budget)",
        "",
        "| run | budgets | total |",
        "|---|---|---|",
    ]
    for run, budgets in sorted(sp.items()):
        lines.append(
            f"| {run} | "
            + ", ".join(f"{k} {v:.2f}" for k, v in sorted(budgets.items()))
            + f" | {sum(budgets.values()):.2f} |"
        )
    lines += [
        "",
        f"E3 total USD {total_usd:.2f} (hard cap {e3.CAP_USD:.0f}).",
        "",
        "## Incidents (UTC timestamps in experiments/alfworld_e3/LOG.md)",
        "",
        f"- Guard incidents (usage.cost mismatch): {inc['guard_incidents']}. Ledgered retries: 429 {inc['retries_429']}, other {inc['retries_other']}.",  # noqa: E501
        "- Errored rollouts (refunded, not charged): "
        + ", ".join(f"{arm} {n}" for arm, n in inc["errored_rollouts"].items())
        + f". A tasks ending infra_error at the last attempt: {', '.join(inc['a_infra_error_tasks']) or 'none'}.",  # noqa: E501
        "",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "e3_layer1_data.json").write_text(
        json.dumps(
            {
                "shared": sh,
                "classes": {"zero": zero, "band": band, "saturated": sat},
                "primary": primary,
                "secondary": secondary,
                "saturated_subset": sat_rate,
                "preserved": preserved,
                "unlocked": unlocked,
                "precision": precision,
                "h100": h100,
                "h100_attribution": h100_attr,
                "claims": {"E3-1": e31, "E3-2": e32, "E3-3": e33, "E3-4": e34},
                "a_profile": {
                    t: {k: v for k, v in p.items() if k != "rollouts"}
                    | {"rollouts": dict(p["rollouts"])}
                    for t, p in prof.items()
                },
                "a_corpus": corpus,
                "released": rel,
                "spend": sp,
                "incidents": inc,
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
