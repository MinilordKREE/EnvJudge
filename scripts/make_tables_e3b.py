"""E3b tables (PREREG10) -> experiments/alfworld_e3/results/e3b_layer1.md and e3b_layer1_data.json:
aea v0.3 (runs/e3b-A, runs/e3b-confirm) beside the E3 rows (aea v0.2 in runs/e3-A, G, R, H100, the
shared K16 — all reused, never re-run). Every number comes from the run directories through the
helpers of scripts/make_tables_e3.py, evaluated once per layout.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import make_tables_e3 as mt

RUNS = e3.RUNS
RESULTS = e3.RESULTS
TASKS = mt.TASKS
fmt = mt.fmt
verdict = mt.verdict


def layout(variant: str) -> None:
    if variant == "e3b":
        mt.RUN_DIRS = {"A": RUNS / "e3b-A", "confirm": RUNS / "e3b-confirm"}
        mt.SPEND_GLOB = "e3b-*"
    else:
        mt.RUN_DIRS = {}
        mt.SPEND_GLOB = "e3-*"


def arm_block(arm: str, sh: dict[str, dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    """Every arm-level number of the E3 tables for one arm under the current layout."""
    conf = mt.confirm()
    envs = mt.arm_envs(arm, conf)
    transformed = [e for e in envs if e.get("kind") != "kept"]
    rolls = mt.charged(arm)
    zero = [t for t in TASKS if sh[t]["cls"] == "zero"]
    band = [t for t in TASKS if sh[t]["cls"] == "band"]
    sat = [t for t in TASKS if sh[t]["cls"] == "saturated"]
    return {
        "envs": envs,
        "transformed": transformed,
        "rolls": rolls,
        "primary": mt.rate(envs, rolls, TASKS, rng),
        "secondary": mt.rate(transformed, rolls, TASKS, rng),
        "sat": mt.rate(transformed, rolls, sat, rng),
        "preserved": sorted(
            {str(e["task"]) for e in envs if e.get("learnable") and str(e["task"]) in band},
            key=int,
        ),
        "unlocked": sorted(
            {str(e["task"]) for e in transformed if e.get("learnable") and str(e["task"]) in zero},
            key=int,
        ),
        "precision": (
            sum(int(bool(e.get("learnable"))) for e in transformed),
            len(transformed),
        ),
    }


def a_events(run_dir: Path) -> list[dict[str, Any]]:
    return e3.jsonl(run_dir / "events.jsonl")


def probe_batches(events: list[dict[str, Any]]) -> dict[str, list[list[tuple[int, int]]]]:
    """Per task, the probe rollouts grouped per candidate as [(n, successes), ...]: a batch of 4
    that is 0/4 ends the candidate; any other first batch (mixed, or 4/4 under v0.3) is followed
    by its top-up batch."""
    per: dict[str, list[list[tuple[int, int]]]] = {}
    pending: dict[str, list[tuple[int, int]]] = {}
    for e in events:
        if e.get("kind") != "rollouts" or e["payload"].get("phase") != "probe":
            continue
        t = str(e["payload"]["task_id"])
        n, s = int(e["payload"]["n"]), int(e["payload"]["successes"])
        cur = pending.setdefault(t, [])
        cur.append((n, s))
        if len(cur) == 2 or (len(cur) == 1 and s == 0):
            per.setdefault(t, []).append(cur)
            pending[t] = []
    for t, cur in pending.items():
        if cur:
            per.setdefault(t, []).append(cur)
    return per


def stage_kinds(events: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Per task, candidate id -> kind (v0.3 events carry ``kinds``)."""
    out: dict[str, dict[str, str]] = {}
    for e in events:
        if e.get("kind") == "stage_candidates":
            out[str(e["payload"]["task_id"])] = dict(e["payload"].get("kinds") or {})
    return out


def brackets(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        if e.get("kind") == "bracket":
            out.setdefault(str(e["payload"]["task_id"]), []).append(e["payload"])
    return out


def rate_row(label: str, r: dict[str, Any]) -> str:
    return (
        f"| {label} | {r['envs']} | {r['learnable']} | {r['rollouts']} | {fmt(r['per_1000'])} "
        f"[{fmt(r['ci95'][0])}, {fmt(r['ci95'][1])}] |"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RESULTS / "e3b_layer1.md"))
    ap.add_argument("--seed", type=int, default=20260913)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    RESULTS.mkdir(parents=True, exist_ok=True)
    e3.set_variant("e3b")

    layout("e3b")
    sh = mt.shared_classes()
    zero = [t for t in TASKS if sh[t]["cls"] == "zero"]
    band = [t for t in TASKS if sh[t]["cls"] == "band"]
    sat = [t for t in TASKS if sh[t]["cls"] == "saturated"]
    blocks: dict[str, dict[str, Any]] = {}
    blocks["A_v0.3"] = arm_block("A", sh, rng)
    prof3 = mt.a_profile()
    corpus3 = mt.a_corpus()
    conf3 = mt.confirm()
    sp = mt.spend()
    inc = mt.incidents()
    for arm in ("G", "R"):
        blocks[arm] = arm_block(arm, sh, rng)
    layout("e3")
    blocks["A_v0.2"] = arm_block("A", sh, rng)
    prof2 = mt.a_profile()
    corpus2 = mt.a_corpus()
    conf2 = mt.confirm()
    layout("e3b")
    order = ("A_v0.3", "A_v0.2", "G", "R")

    h100_path = RUNS / "e3-H100" / "h100_summary.json"
    h100 = json.loads(h100_path.read_text(encoding="utf-8")) if h100_path.exists() else {}
    c1 = {k: blocks[k]["primary"]["per_1000"] for k in order}
    s3 = {k: blocks[k]["sat"]["per_1000"] for k in order}
    e3b1 = c1["A_v0.3"] > c1["G"] and c1["A_v0.3"] > c1["R"]
    e3b3 = (s3["A_v0.3"] >= s3["G"]) if s3["A_v0.3"] == s3["A_v0.3"] else False

    lines: list[str] = [
        "# E3b — aea v0.3 on the E3 task set (PREREG10), beside the E3 rows",
        "",
        f"Arm A_v0.3 = docs/spec/AEA_v0.3.md (population-seeded bracket, stage-side 4/4 top-up, quarter-point candidates) on seeds 0-29, Qwen3-8B policy (alibaba pin, reasoning off), DeepSeek V4 Pro proposer, cap 30. Reused from E3 and never re-run: the shared K16, arms G and R, the H100 control, and every confirmation E3 already made (kept tasks reuse the shared K16). A_v0.2 = the E3 arm A. PREREG10 @ {e3.PREREG10_SHA}; tables from scripts/make_tables_e3b.py.",  # noqa: E501
        "",
        f"Task classes (shared K16): zero {len(zero)} ({', '.join(zero)}); band {len(band)} ({', '.join(band)}); saturated {len(sat)}.",  # noqa: E501
        "",
        "## C1 primary — learner-facing learnable environments per 1,000 charged search rollouts",
        "",
        "| arm | learner-facing envs | learnable | charged rollouts | per 1,000 [95% CI, task bootstrap] |",  # noqa: E501
        "|---|---|---|---|---|",
    ]
    lines += [rate_row(k, blocks[k]["primary"]) for k in order]
    lines += [
        "",
        "## C1 secondary — transformed-only",
        "",
        "| arm | transformed envs | learnable | charged rollouts | per 1,000 [95% CI] |",
        "|---|---|---|---|---|",
    ]
    lines += [rate_row(k, blocks[k]["secondary"]) for k in order]
    lines += [
        "",
        f"## Band preservation ({len(band)} originally learnable tasks)",
        "",
        "| arm | preserved | tasks |",
        "|---|---|---|",
    ]
    lines += [
        f"| {k} | {len(blocks[k]['preserved'])} / {len(band)} | {', '.join(blocks[k]['preserved']) or '-'} |"  # noqa: E501
        for k in order
    ]
    lines += [
        "",
        f"## Unlocked zero tasks (zero: {', '.join(zero)}) and precision",
        "",
        "| arm | unlocked | tasks | precision (learnable / accepted transformed) |",
        "|---|---|---|---|",
    ]
    for k in order:
        lp, ap_ = blocks[k]["precision"]
        lines.append(
            f"| {k} | {len(blocks[k]['unlocked'])} | {', '.join(blocks[k]['unlocked']) or '-'} | {lp} / {ap_} ({fmt(100 * lp / ap_ if ap_ else None, 0)}%) |"  # noqa: E501
        )
    lines += [
        "",
        f"## Saturated subset ({len(sat)} tasks) — learnable transformed environments per 1,000",
        "",
        "| arm | transformed envs | learnable | charged rollouts on the subset | per 1,000 [95% CI] |",  # noqa: E501
        "|---|---|---|---|---|",
    ]
    lines += [rate_row(k, blocks[k]["sat"]) for k in order]
    # H100 with both A rows
    lines += [
        "",
        "## H100 control (reused) next to the staged p16 of both A versions",
        "",
        "| task | H100 s/n | H100 p | A_v0.3 staged p16 (t) | A_v0.2 staged p16 (t) | attribution (v0.3) |",  # noqa: E501
        "|---|---|---|---|---|---|",
    ]
    attr3: dict[str, str] = {}
    for t in [str(x) for x in e3.H100_TASKS]:
        h = h100.get(t, {})
        hp = h.get("p16")

        def staged(
            conf: dict[str, dict[str, Any]], arm: str = "A", task: str = t
        ) -> tuple[Any, Any]:
            c = [
                v
                for v in conf.values()
                if str(v.get("task")) == task
                and v.get("kind") == "stage"
                and arm in (v.get("arms") or [])
            ]
            return (c[0].get("p16"), c[0].get("t")) if c else (None, None)

        p3, t3 = staged(conf3)
        p2, t2 = staged(conf2)
        if hp is None or p3 is None:
            attr = "-"
        elif hp >= p3:
            attr = "horizon (H100 >= staged)"
        else:
            attr = "staging (H100 < staged)"
        attr3[t] = attr
        lines.append(
            f"| {t} | {h.get('successes', '-')}/{h.get('n', '-')} | {fmt(hp, 3)} | {fmt(p3, 3)} ({t3 if t3 is not None else '-'}) | {fmt(p2, 3)} ({t2 if t2 is not None else '-'}) | {attr} |"  # noqa: E501
        )
    lines += [
        "",
        "## PREREG10 claims",
        "",
        f"- E3b-1: A_v0.3 {fmt(c1['A_v0.3'])} vs G {fmt(c1['G'])} and R {fmt(c1['R'])} per 1,000 (A_v0.2 {fmt(c1['A_v0.2'])}) → A_v0.3 > G {verdict(c1['A_v0.3'] > c1['G'])}, A_v0.3 > R {verdict(c1['A_v0.3'] > c1['R'])} → **{verdict(e3b1)}**.",  # noqa: E501
        f"- E3b-3: saturated subset A_v0.3 {fmt(s3['A_v0.3'])} vs G {fmt(s3['G'])} per 1,000 (A_v0.2 {fmt(s3['A_v0.2'])}) → **{verdict(e3b3)}**.",  # noqa: E501
        f"- Unlocked zero tasks: A_v0.3 {len(blocks['A_v0.3']['unlocked'])} ({', '.join(blocks['A_v0.3']['unlocked']) or '-'}), A_v0.2 {len(blocks['A_v0.2']['unlocked'])}, G {len(blocks['G']['unlocked'])}; H100 attribution: "  # noqa: E501
        + "; ".join(f"task {t}: {a}" for t, a in attr3.items())
        + ".",
        "",
        "## A per task — v0.3 beside v0.2",
        "",
        "| task | class | v0.3 outcome | v0.3 reason | v0.3 n_search | v0.3 families (order) | v0.3 brackets (family: seed → status, doses) | v0.3 stage (certified/rejected; probes t: s/n verdict) | v0.2 outcome | v0.2 reason | v0.2 n_search | learner-facing envs v0.3 (p16) |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        v, w = prof3[t], prof2[t]
        br = (
            "; ".join(
                f"{b['family']}: {b.get('seed') or 'mid'} → {b['status']}, "
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
            for e in blocks["A_v0.3"]["envs"]
            if str(e["task"]) == t
        )
        lines.append(
            f"| {t} | {sh[t]['cls']} | {v['outcome']} | {v['reason'] or '-'} | {v['n_search'] if v['n_search'] is not None else '-'} | {', '.join(v['families']) or '-'} | {br} | {st} | {w['outcome']} | {w['reason'] or '-'} | {w['n_search'] if w['n_search'] is not None else '-'} | {lf or '-'} |"  # noqa: E501
        )
    oc3 = Counter(
        f"{v['outcome']}{':' + v['reason'] if v['reason'] else ''}" for v in prof3.values()
    )
    oc2 = Counter(
        f"{v['outcome']}{':' + v['reason'] if v['reason'] else ''}" for v in prof2.values()
    )
    lines += [
        "",
        "A_v0.3 outcomes: " + ", ".join(f"{k} {n}" for k, n in sorted(oc3.items())) + ".",
        "A_v0.2 outcomes: " + ", ".join(f"{k} {n}" for k, n in sorted(oc2.items())) + ".",
        "",
        "### Family of origin — A_v0.3's accepted environments",
        "",
        "| task | kind | family | source | axis | dose | t | p8 | confirmed p16 | learnable |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    origin3: Counter[str] = Counter()
    for t in TASKS:
        for c in corpus3.get(t, []):
            if c["kind"] == "kept":
                continue
            src = {"library": "exemplar", "llm": "proposer"}.get(
                str(c.get("source")), c.get("source")
            )
            origin3[f"{c['kind']}:{src or '-'}:{c.get('family') or '-'}"] += 1
            ce = conf3.get(f"{t}:{c['key']}", {})
            lines.append(
                f"| {t} | {c['kind']} | {c.get('family') or '-'} | {src or '-'} | {c.get('axis') or '-'} | {fmt(c.get('d'), 3) if c.get('d') is not None else '-'} | {c.get('t') if c.get('t') is not None else '-'} | {fmt(c.get('p_hat'), 3)} | {fmt(ce.get('p16'), 3)} | {'y' if ce.get('learnable') else '-'} |"  # noqa: E501
            )
    origin2: Counter[str] = Counter()
    for t in TASKS:
        for c in corpus2.get(t, []):
            if c["kind"] != "kept":
                src = {"library": "exemplar", "llm": "proposer"}.get(
                    str(c.get("source")), c.get("source")
                )
                origin2[f"{c['kind']}:{src or '-'}:{c.get('family') or '-'}"] += 1
    lines += [
        "",
        "Origin counts v0.3: "
        + (", ".join(f"{k} {n}" for k, n in sorted(origin3.items())) or "none")
        + ".",
        "Origin counts v0.2: "
        + (", ".join(f"{k} {n}" for k, n in sorted(origin2.items())) or "none")
        + ".",
        "",
        "### A_v0.3 per-task budget (charged search rollouts by phase)",
        "",
        "| task | estimate | dose (harden) | probe (stage) | n_search | v0.2 n_search |",
        "|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        ro = prof3[t]["rollouts"]
        dose = sum(n for ph, n in ro.items() if ph.startswith("dose:"))
        lines.append(
            f"| {t} | {ro.get('estimate', 0)} | {dose} | {ro.get('probe', 0)} | {prof3[t]['n_search'] if prof3[t]['n_search'] is not None else '-'} | {prof2[t]['n_search'] if prof2[t]['n_search'] is not None else '-'} |"  # noqa: E501
        )
    lines += [
        "",
        "## Learner-facing environments of A_v0.3 and their K=16",
        "",
        "| env | task | kind / t | s/n | p16 | learnable | source |",
        "|---|---|---|---|---|---|---|",
    ]
    for env_id, e in sorted(conf3.items(), key=lambda kv: (int(kv[1]["task"]), kv[0])):
        if "A" not in (e.get("arms") or []):
            continue
        lines.append(
            f"| {env_id[:40]} | {e['task']} | {e.get('kind')} {e.get('t') if e.get('t') is not None else ''} | {e.get('successes')}/{e.get('n')} | {fmt(e.get('p16'), 3)} | {'y' if e.get('learnable') else '-'} | {e.get('reused') or 'new'} |"  # noqa: E501
        )
    # ---------------------------------------------------------------- v0.2 -> v0.3 per task
    ev3 = a_events(RUNS / "e3b-A")
    ev2 = a_events(RUNS / "e3-A")
    br3, br2 = brackets(ev3), brackets(ev2)
    pb3 = probe_batches(ev3)
    kinds3 = stage_kinds(ev3)
    acc3 = {t: [c for c in corpus3.get(t, []) if c["kind"] != "kept"] for t in TASKS}
    lines += [
        "",
        "## Per-task diff v0.2 → v0.3 (outcome and reason; saturated tasks: family, seeded bracket, doses visited, accepted dose)",  # noqa: E501
        "",
        "| task | class | v0.2 outcome:reason | v0.3 outcome:reason | changed | v0.3 family | v0.3 seed [lo_pop, hi_pop] | v0.3 doses (d: s/n) | v0.3 accepted d | v0.2 family / doses |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    changed_tasks: list[str] = []
    for t in TASKS:
        v, w = prof3[t], prof2[t]
        o3 = f"{v['outcome']}{':' + v['reason'] if v['reason'] else ''}"
        o2 = f"{w['outcome']}{':' + w['reason'] if w['reason'] else ''}"
        changed = o3 != o2
        if changed:
            changed_tasks.append(t)
        b3 = br3.get(t, [])
        fam3 = ", ".join(b["family"] for b in b3) or "-"
        seed3 = "; ".join(str(b.get("seed")) for b in b3) or "-"
        doses3 = (
            "; ".join(
                "/".join(f"{h['d']}:{h['s']}/{h['n']}" for h in (b.get("history") or []))
                for b in b3
            )
            or "-"
        )
        acc_d = ", ".join(fmt(c.get("d"), 4) for c in acc3[t] if c.get("d") is not None) or "-"
        b2 = br2.get(t, [])
        v2 = (
            "; ".join(
                f"{b['family']}: "
                + "/".join(f"{h['d']}:{h['s']}/{h['n']}" for h in (b.get("history") or []))
                for b in b2
            )
            or "-"
        )
        lines.append(
            f"| {t} | {sh[t]['cls']} | {o2} | {o3} | {'yes' if changed else '-'} | {fam3} | {seed3} | {doses3} | {acc_d} | {v2} |"  # noqa: E501
        )
    # ---------------------------------------------------------------- attribution from events
    seeded = {
        t: [b for b in br3.get(t, []) if list(b.get("seed") or [0, 1]) != [0.0, 1.0]] for t in TASKS
    }
    seeded_accept = [
        t
        for t in TASKS
        if prof3[t]["outcome"] == "accepted"
        and any(b.get("status") == "accepted" for b in seeded[t])
    ]
    topped = {t: [c for c in pb3.get(t, []) if c and c[0] == (4, 4) and len(c) == 2] for t in TASKS}
    topped_tasks = [t for t in TASKS if topped[t]]
    topped_verdicts: Counter[str] = Counter()
    for t in topped_tasks:
        for c in topped[t]:
            s8 = c[0][1] + c[1][1]
            topped_verdicts[
                "in_band" if 3 <= s8 <= 5 else ("too_easy" if s8 > 5 else "too_hard")
            ] += 1
    topped_accept = [
        t
        for t in TASKS
        if prof3[t]["outcome"] == "accepted"
        and prof3[t]["regime"] == "zero"
        and any(3 <= c[0][1] + c[1][1] <= 5 for c in topped[t])
    ]
    quarter_probed = [t for t in TASKS if any(k == "quarter" for k in kinds3.get(t, {}).values())]
    quarter_accept = [
        t
        for t in TASKS
        for c in acc3[t]
        if c["kind"] == "stage" and kinds3.get(t, {}).get(str(c.get("candidate_id"))) == "quarter"
    ]
    v2_out = {t: prof2[t]["outcome"] for t in TASKS}
    by_cause: dict[str, list[str]] = {
        "(1) population-seeded bracket": [t for t in seeded_accept if v2_out[t] != "accepted"],
        "(2) stage-side 4/4 top-up": [t for t in topped_accept if v2_out[t] != "accepted"],
        "(3) quarter-point candidates": [t for t in quarter_accept if v2_out[t] != "accepted"],
    }
    explained = {t for ts in by_cause.values() for t in ts}
    lost = [
        t
        for t in TASKS
        if v2_out[t] in ("accepted", "kept") and prof3[t]["outcome"] not in ("accepted", "kept")
    ]
    unexplained = [t for t in changed_tasks if t not in explained and t not in lost]
    c1_, c2_, c3_ = (
        by_cause["(1) population-seeded bracket"],
        by_cause["(2) stage-side 4/4 top-up"],
        by_cause["(3) quarter-point candidates"],
    )
    lines += [
        "",
        "## Attribution of the three rule changes (counted from runs/e3b-A/events.jsonl)",
        "",
        f"- (1) Population-seeded bracket: {len([t for t in TASKS if seeded[t]])} tasks bracketed from a seed other than [0, 1] ({', '.join(t for t in TASKS if seeded[t]) or '-'}); {len(seeded_accept)} accepted through a seeded bracket ({', '.join(seeded_accept) or '-'}); outcome changed from v0.2 because of it on {len(c1_)} ({', '.join(c1_) or '-'}).",  # noqa: E501
        f"- (2) Stage-side 4/4 top-up: {sum(len(v) for v in topped.values())} staged candidates had a 4/4 first batch and were topped up, on {len(topped_tasks)} tasks ({', '.join(topped_tasks) or '-'}); verdicts after the top-up: "  # noqa: E501
        + (", ".join(f"{k} {n}" for k, n in sorted(topped_verdicts.items())) or "-")
        + f"; accepted through a topped-up 4/4 candidate: {len(topped_accept)} ({', '.join(topped_accept) or '-'}); outcome changed from v0.2 because of it on {len(c2_)} ({', '.join(c2_) or '-'}).",  # noqa: E501
        f"- (3) Quarter-point candidates: a quarter state was certified on {len(quarter_probed)} tasks ({', '.join(quarter_probed) or '-'}); accepted at a quarter state: {len(quarter_accept)} ({', '.join(quarter_accept) or '-'}); outcome changed from v0.2 because of it on {len(c3_)} ({', '.join(c3_) or '-'}).",  # noqa: E501
        f"- Tasks whose outcome:reason differs from v0.2: {len(changed_tasks)} ({', '.join(changed_tasks) or '-'}); explained by a rule change above: {len(explained)}; lost relative to v0.2 (accepted or kept in v0.2, not in v0.3): {len(lost)} ({', '.join(lost) or '-'}); other (estimate regime, proposer families, sampling): {len(unexplained)} ({', '.join(unexplained) or '-'}).",  # noqa: E501
        "",
        "## Charged search rollouts per task (the per-1,000 denominators)",
        "",
        "| task | A_v0.3 | A_v0.2 | G | R |",
        "|---|---|---|---|---|",
    ]
    for t in TASKS:
        lines.append(
            f"| {t} | {blocks['A_v0.3']['rolls'].get(t, 0)} | {blocks['A_v0.2']['rolls'].get(t, 0)} | {blocks['G']['rolls'].get(t, 0)} | {blocks['R']['rolls'].get(t, 0)} |"  # noqa: E501
        )
    lines.append(
        "| **total** | "
        + " | ".join(f"**{sum(blocks[k]['rolls'].values())}**" for k in order)
        + " |"
    )
    lines += [
        "",
        "## Learner-facing set of A_v0.3 (the deferred SL stage's input)",
        "",
        "| task | kind | family | source | dose | t | p8 | p16 | learnable |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t in TASKS:
        for c in corpus3.get(t, []):
            ce = conf3.get(f"{t}:{c['key']}", {})
            src = {"library": "exemplar", "llm": "proposer"}.get(
                str(c.get("source")), c.get("source")
            )
            lines.append(
                f"| {t} | {c['kind']} | {c.get('family') or '-'} | {src or '-'} | {fmt(c.get('d'), 4) if c.get('d') is not None else '-'} | {c.get('t') if c.get('t') is not None else '-'} | {fmt(c.get('p_hat'), 3)} | {fmt(ce.get('p16'), 3)} | {'y' if ce.get('learnable') else '-'} |"  # noqa: E501
            )
    total_usd = sum(sum(v.values()) for v in sp.values())
    lines += [
        "",
        "## Spend (USD by run and budget; E3b runs only)",
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
        f"E3b total USD {total_usd:.2f} (cap {e3.CAP_USD:.0f}).",
        "",
        "## Incidents (UTC timestamps in experiments/alfworld_e3/LOG.md)",
        "",
        f"- Guard incidents {inc['guard_incidents']}; ledgered retries 429 {inc['retries_429']}, other {inc['retries_other']}; errored rollouts {inc['errored_rollouts'].get('A', 0)} (A_v0.3); A tasks ending infra_error: {', '.join(inc['a_infra_error_tasks']) or 'none'}.",  # noqa: E501
        "",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "e3b_layer1_data.json").write_text(
        json.dumps(
            {
                "blocks": {
                    k: {kk: vv for kk, vv in v.items() if kk not in ("envs", "transformed")}
                    for k, v in blocks.items()
                },
                "claims": {"E3b-1": e3b1, "E3b-3": e3b3},
                "attribution": {
                    "by_cause": by_cause,
                    "changed_tasks": changed_tasks,
                    "lost": lost,
                    "unexplained": unexplained,
                    "seeded_brackets": {t: v for t, v in seeded.items() if v},
                    "topped_up": {t: v for t, v in topped.items() if v},
                    "quarter_probed": quarter_probed,
                },
                "h100_attribution": attr3,
                "a_v03_profile": {
                    t: {k: v for k, v in p.items() if k != "rollouts"}
                    | {"rollouts": dict(p["rollouts"])}
                    for t, p in prof3.items()
                },
                "a_v03_corpus": corpus3,
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
