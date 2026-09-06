"""E-obs-F re-analyses F1, F2, F4, F6, F7 on the frozen E-obs artifacts (read-only inputs; outputs to results/eobs/followup)."""

from __future__ import annotations

import ast
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eobs.analyze import boot_rate, fmt, rs  # noqa: E402

RES = ROOT / "results" / "eobs"
OUT = RES / "followup"
BAND = (0.4, 0.6)


def jsonl(p: Path) -> list[dict]:
    """Tolerant reader: one truncated line (a killed process) is skipped, never repaired or dropped from the file."""
    out = []
    if not Path(p).exists():
        return out
    for l in Path(p).read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not rows:
        Path(path).write_text("")
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def cls(sr: float) -> str:
    if sr >= 0.8:
        return "NOEFFECT"
    if 0.4 <= sr <= 0.6:
        return "INBAND"
    if sr == 0.2:
        return "OVERSHOOT"
    return "ZERO"


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


# ------------------------------------------------------------------ F1
def f1() -> dict:
    tasks = list(csv.DictReader(open(RES / "tasks.csv", encoding="utf-8")))
    cands = [c for c in jsonl(RES / "candidates.jsonl") if c["arm"] == "H"]
    certs = {c["candidate_id"]: c for c in jsonl(RES / "certificates.jsonl")}
    out = {}
    for name, thr in (("S_H", 1.0), ("S_H_prime", 0.8)):
        sat = {int(t["task_id"]) for t in tasks if f(t.get("p5_H")) >= thr}
        rows = []
        for c in sorted((c for c in cands if int(c["task_id"]) in sat), key=lambda c: (int(c["task_id"]), int(c["attempt"] or 0))):
            rows.append({"task_id": c["task_id"], "attempt": c["attempt"], "candidate_id": c["candidate_id"], "axis": c["axis"], "SR_c": c["SR_c"],
                         "class": cls(float(c["SR_c"])), "decision": c["decision"], "certified": certs.get(c["candidate_id"], {}).get("certified")})
        by = defaultdict(list)
        for r in rows:
            by[int(r["task_id"])].append(r)
        trows = []
        for tid in sorted(sat):
            rs_ = by.get(tid, [])
            classes = [r["class"] for r in rs_]
            n = len(rs_)
            acc = any(r["decision"] == "accept" for r in rs_)
            inband_rej = any(r["class"] == "INBAND" and r["decision"] != "accept" for r in rs_)
            if n == 0:
                tc = "SKIPPED(no validated attempt)"
            elif classes.count("NOEFFECT") * 2 >= n:
                tc = "NOEFFECT-dominated"
            elif (classes.count("OVERSHOOT") + classes.count("ZERO")) * 2 >= n:
                tc = "OVERSHOOT/ZERO-dominated"
            elif inband_rej:
                tc = "INBAND-REJECTED"
            else:
                tc = "MIXED"
            trows.append({"task_id": tid, "n_attempts": n, "classes": " ".join(classes), "ended_with_accept": acc, "inband_rejected": inband_rej, "task_class": tc})
        # D1 rates on failed attempts (decision != accept), task-resampled
        failed_by = {tid: [r for r in rs_ if r["decision"] != "accept"] for tid, rs_ in by.items()}
        failed_by = {k: v for k, v in failed_by.items() if v}
        a = boot_rate(failed_by, lambda r: r["class"] == "NOEFFECT", lambda r: 1)
        b = boot_rate(failed_by, lambda r: r["class"] in ("OVERSHOOT", "ZERO"), lambda r: 1)
        cc = boot_rate(failed_by, lambda r: r["class"] == "INBAND", lambda r: 1)
        # controllability
        pairs_by = defaultdict(list)
        for tid, rs_ in by.items():
            for x, y in zip(rs_, rs_[1:]):
                pairs_by[tid].append((float(x["SR_c"]), float(y["SR_c"])))
        center = sum(BAND) / 2
        inb = lambda s: BAND[0] <= s <= BAND[1]
        toward = lambda s0, s1: inb(s1) or abs(s1 - center) < abs(s0 - center)
        above = {t: [p for p in ps if p[0] > BAND[1]] for t, ps in pairs_by.items()}
        below = {t: [p for p in ps if p[0] < BAND[0]] for t, ps in pairs_by.items()}
        zo = {t: [p for p in ps if cls(p[0]) in ("ZERO", "OVERSHOOT")] for t, ps in pairs_by.items()}
        ne = {t: [p for p in ps if cls(p[0]) == "NOEFFECT"] for t, ps in pairs_by.items()}
        ctrl = [
            {"rate": "P(toward band | SR_i above band)", **_r(boot_rate({t: v for t, v in above.items() if v}, lambda p: toward(*p), lambda p: 1))},
            {"rate": "P(toward band | SR_i below band)", **_r(boot_rate({t: v for t, v in below.items() if v}, lambda p: toward(*p), lambda p: 1))},
            {"rate": "P(toward band | SR_i outside band)", **_r(boot_rate({t: [p for p in ps if not inb(p[0])] for t, ps in pairs_by.items() if any(not inb(p[0]) for p in ps)}, lambda p: toward(*p), lambda p: 1))},
            {"rate": "P(next milder (SR up) | ZERO or OVERSHOOT)", **_r(boot_rate({t: v for t, v in zo.items() if v}, lambda p: p[1] > p[0], lambda p: 1))},
            {"rate": "P(next harder (SR down) | NOEFFECT)", **_r(boot_rate({t: v for t, v in ne.items() if v}, lambda p: p[1] < p[0], lambda p: 1))},
        ]
        out[name] = {"n_tasks": len(sat), "tasks": sorted(sat), "attempts": rows, "task_rows": trows, "a": a, "b": b, "c": cc, "ctrl": ctrl,
                     "task_class_counts": dict(Counter(r["task_class"] for r in trows))}
    write_csv(OUT / "saturated_attempts.csv", out["S_H"]["attempts"])
    write_csv(OUT / "saturated_tasks.csv", out["S_H"]["task_rows"])
    write_csv(OUT / "saturated_attempts_SHprime.csv", out["S_H_prime"]["attempts"])
    write_csv(OUT / "saturated_tasks_SHprime.csv", out["S_H_prime"]["task_rows"])
    write_csv(OUT / "controllability.csv", [{"set": k, **row} for k in ("S_H", "S_H_prime") for row in out[k]["ctrl"]])
    return out


def _r(r) -> dict:
    return {"rate_point": fmt(r[0]), "ci_lo": fmt(r[1]), "ci_hi": fmt(r[2]), "n": r[3], "tasks": r[4]}


# ------------------------------------------------------------------ F2
def f2() -> dict:
    cands = {c["candidate_id"]: c for c in jsonl(RES / "candidates.jsonl")}
    certs = jsonl(RES / "certificates.jsonl")
    led = jsonl(RES / "ledger.jsonl")
    hint_usd = defaultdict(float)
    for r in led:
        if r.get("phase") == "phase3_hint" and r.get("candidate_id"):
            hint_usd[r["candidate_id"]] += float(r.get("usd") or 0.0)
    rows = []
    groups = defaultdict(list)
    for c in certs:
        groups[(c["arm"], c["axis"])].append(c)
    for (arm, axis), cs in sorted(groups.items()):
        ro = [c for c in cs if (c["R_old"] or {}).get("ok")]
        ro_fail = [c for c in cs if not (c["R_old"] or {}).get("ok")]
        rx_ok_after = [c for c in ro_fail if (c["R_exp"] or {}).get("ok")]
        rx_fail = [c for c in cs if not (c["R_old"] or {}).get("ok") and not (c["R_exp"] or {}).get("ok")]
        hint_run = [c for c in cs if c.get("R_hint")]
        hint_ok_after = [c for c in rx_fail if (c.get("R_hint") or {}).get("ok")]
        hint_cert = [c for c in cs if (c.get("R_hint") or {}).get("ok") and not (c["R_old"] or {}).get("ok") and not (c["R_exp"] or {}).get("ok")]
        usd = sum(hint_usd[c["candidate_id"]] for c in hint_run)
        rows.append({"arm": arm, "axis": axis, "n": len(cs), "R_old_ok": len(ro), "R_old_not_run": sum(1 for c in cs if (c["R_old"] or {}).get("reason") == "not_run"),
                     "R_exp_ok_among_R_old_fail": f"{len(rx_ok_after)}/{len(ro_fail)}", "R_hint_run": len(hint_run), "R_hint_ok_among_R_exp_fail": f"{len(hint_ok_after)}/{len(rx_fail)}",
                     "certified": sum(1 for c in cs if c["certified"]), "unresolved": sum(1 for c in cs if c["unresolved"]),
                     "usd_R_hint_total": round(usd, 4), "usd_R_hint_per_hint_certified": round(usd / len(hint_cert), 4) if hint_cert else ""})
    write_csv(OUT / "cert_sources.csv", rows)
    # O5H detail: certified A/T with R_old=0
    at = [c for c in certs if c["arm"] == "H" and c["certified"] and (set(c["axis"].split("+")) & {"A", "T"}) and not (c["R_old"] or {}).get("ok")]
    src = Counter("R_exp" if (c["R_exp"] or {}).get("ok") else ("R_hint" if (c.get("R_hint") or {}).get("ok") else "?") for c in at)
    r_old_reasons = Counter((c["R_old"] or {}).get("reason") for c in at)
    total_hint_usd = sum(hint_usd.values())
    n_hint_cert = sum(1 for c in certs if (c.get("R_hint") or {}).get("ok") and not (c["R_old"] or {}).get("ok") and not (c["R_exp"] or {}).get("ok"))
    return {"rows": rows, "o5h_sources": dict(src), "o5h_n": len(at), "o5h_r_old_reasons": dict(r_old_reasons), "hint_usd_total": total_hint_usd, "n_hint_certified": n_hint_cert}


# ------------------------------------------------------------------ F4
def f4(run_policy_replay: bool = True) -> dict:
    tasks = list(csv.DictReader(open(RES / "tasks.csv", encoding="utf-8")))
    base = jsonl(RES / "baseline_rollouts.jsonl")
    wit = {int(w["task_id"]): w for w in jsonl(RES / "witness_base.jsonl")}
    cands = [c for c in jsonl(RES / "candidates.jsonl")]
    certs = {c["candidate_id"]: c for c in jsonl(RES / "certificates.jsonl")}
    succ_by = defaultdict(list)
    for b in base:
        if b["success"] and not b.get("error"):
            succ_by[int(b["task_id"])].append(b)
    rows = []
    for t in tasks:
        tid = int(t["task_id"])
        wp = bool(succ_by.get(tid))
        we1 = t["W_base"] in ("True", True)
        we3 = bool(wit.get(tid, {}).get("W_base_any3"))
        rows.append({"task_id": tid, "type": t["type"], "p16": t["p16"], "W_policy": wp, "W_expert1": we1, "W_expert3": we3, "W_any": wp or we3})
    write_csv(OUT / "witness_ladder.csv", rows)
    g = {r["task_id"]: [r] for r in rows}
    cov = {k: boot_rate(g, lambda r, k=k: bool(r[k]), lambda r: 1) for k in ("W_policy", "W_expert1", "W_expert3", "W_any")}
    four = {}
    for tid in (2, 4, 5, 22):
        cs = [c for c in cands if int(c["task_id"]) == tid]
        det = []
        for c in cs:
            ce = certs.get(c["candidate_id"], {})
            src = "R_old" if (ce.get("R_old") or {}).get("ok") else ("R_exp" if (ce.get("R_exp") or {}).get("ok") else ("R_hint" if (ce.get("R_hint") or {}).get("ok") else "unresolved"))
            det.append({"candidate_id": c["candidate_id"], "arm": c["arm"], "axis": c["axis"], "SR_c": c["SR_c"], "decision": c["decision"], "certified": ce.get("certified"), "source": src,
                        "R_old_reason": (ce.get("R_old") or {}).get("reason")})
        four[tid] = {"p16": next(t["p16"] for t in tasks if int(t["task_id"]) == tid), "n_candidates": len(cs), "n_H": sum(1 for c in cs if c["arm"] == "H"),
                     "certified": sum(1 for d in det if d["certified"]), "detail": det, "policy_success_available": bool(succ_by.get(tid))}
    # supplementary R_old_policy: verbatim replay of the shortest successful Pro baseline trajectory in E'_c
    if run_policy_replay:
        from envharness.core.types import Action, Candidate
        from eobs.replay import r_old
        prows = []
        for tid, info in four.items():
            if not succ_by.get(tid):
                continue
            traj = min(succ_by[tid], key=lambda b: b["steps"])
            for c in (c for c in cands if int(c["task_id"]) == tid):
                cand = Candidate(rules_code=c.get("rules_code", "") or "", in_env_actions=[Action(name=a["name"], kwargs=dict(a.get("kwargs") or {})) for a in c.get("in_env_actions", [])])
                try:
                    r = r_old(cand, tid, traj["actions"])
                    prows.append({"task_id": tid, "candidate_id": c["candidate_id"], "arm": c["arm"], "axis": c["axis"], "witness_episode": traj["episode_id"], "witness_len": traj["steps"],
                                  "R_old_policy_ok": r.ok, "reason": r.reason, "step": r.step})
                except Exception as e:  # noqa: BLE001
                    prows.append({"task_id": tid, "candidate_id": c["candidate_id"], "arm": c["arm"], "axis": c["axis"], "witness_episode": traj["episode_id"], "witness_len": traj["steps"],
                                  "R_old_policy_ok": False, "reason": f"env_error:{type(e).__name__}", "step": None})
        write_csv(OUT / "r_old_policy_four_tasks.csv", prows)
        for tid in four:
            four[tid]["R_old_policy"] = [p for p in prows if p["task_id"] == tid]
    return {"rows": rows, "coverage": cov, "four": four}


# ------------------------------------------------------------------ F6
_VERB = lambda s: (s or "").strip().split(" ")[0]


def _func_src(code: str, name: str):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None, None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_Rules":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item, ast.unparse(item)
    return None, None


def _strs(node) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip()]


def _nums(node) -> list:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)]


def f6() -> dict:
    cands = jsonl(RES / "candidates.jsonl")
    rows = []
    for c in cands:
        code = c.get("rules_code", "") or ""
        fa, fa_src = _func_src(code, "filter_action")
        mt, mt_src = _func_src(code, "modify_transition")
        fo, fo_src = _func_src(code, "filter_observation")
        acts = c.get("in_env_actions", []) or []
        a_lits = _strs(fa) if fa else []
        t_nums = _nums(mt) if mt else []
        o_lits = _strs(fo) if fo else []
        all_nums = []
        try:
            tree = ast.parse(code) if code.strip() else None
            all_nums = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)] if tree else []
        except SyntaxError:
            pass
        tunable = [x for x in all_nums if x not in (0, 1)]
        rationale = (c.get("rationale") or "").strip()
        intent = rationale.split(". ")[0][:200] if rationale else ""
        rows.append({
            "arm": c["arm"], "task_id": c["task_id"], "candidate_id": c["candidate_id"], "axis": c["axis"], "hooks": "|".join(c.get("hooks", [])),
            "A_uses_regex": bool(fa_src and "re." in fa_src), "A_blocked_literals": " | ".join(a_lits)[:300], "A_n_literals": len(a_lits), "A_returns_Blocked": bool(fa_src and "Blocked(" in fa_src),
            "T_uses_random": bool(mt_src and "random" in mt_src), "T_numeric_literals": " ".join(str(x) for x in t_nums)[:100], "T_nothing_happens": bool(mt_src and "Nothing happens" in mt_src),
            "T_edits_text": bool(mt_src and ("observation" in mt_src or "text" in mt_src)),
            "O_masked_literals": " | ".join(o_lits)[:300], "O_n_literals": len(o_lits), "O_touches_admissible": bool(fo_src and "admissible" in fo_src), "O_uses_regex": bool(fo_src and "re." in fo_src),
            "S0_n_actions": len(acts), "S0_verbs": " ".join(sorted({_VERB((a.get("kwargs") or {}).get("text", "")) for a in acts})),
            "numeric_params": " ".join(str(x) for x in tunable)[:120], "has_tunable_param": bool(tunable), "SR_c": c["SR_c"], "decision": c["decision"], "intent": intent,
        })
    write_csv(OUT / "candidate_taxonomy.csv", rows)
    H = [r for r in rows if r["arm"] == "H"]
    def optype(r):
        ops = []
        if r["S0_n_actions"]:
            ops.append("S0:setup_actions")
        if "filter_action" in r["hooks"]:
            ops.append("A:block(" + ("regex" if r["A_uses_regex"] else "literal") + ")" if r["A_returns_Blocked"] else "A:rewrite")
        if "modify_transition" in r["hooks"]:
            ops.append("T:" + ("nothing_happens" if r["T_nothing_happens"] else "text_edit") + ("+random" if r["T_uses_random"] else ""))
        if "filter_observation" in r["hooks"]:
            ops.append("O:" + ("admissible" if r["O_touches_admissible"] else "text") + ("+regex" if r["O_uses_regex"] else ""))
        return "+".join(ops) or "none"
    dist = Counter(optype(r) for r in H)
    tun = sum(r["has_tunable_param"] for r in H)
    rnd = random.Random(20260909)
    review = rnd.sample([c for c in cands if c["arm"] == "H"], 15)
    return {"rows": rows, "H_optype_dist": dict(dist.most_common()), "H_tunable": tun, "H_n": len(H), "released_optype_dist": dict(Counter(optype(r) for r in rows if r["arm"] == "released").most_common()),
            "review": [{"candidate_id": c["candidate_id"], "task_id": c["task_id"], "axis": c["axis"], "SR_c": c["SR_c"], "decision": c["decision"], "rationale": (c.get("rationale") or "")[:300],
                        "in_env_actions": [(a.get("kwargs") or {}).get("text") for a in c.get("in_env_actions", [])], "rules_code": c.get("rules_code", "")} for c in review]}


# ------------------------------------------------------------------ F7
def f7() -> dict:
    cands = [c for c in jsonl(RES / "candidates.jsonl") if c["arm"] == "H"]
    acc = [c for c in cands if c["decision"] == "accept"]
    dist = Counter(c["SR_c"] for c in acc)
    outside = [c for c in acc if not (BAND[0] <= float(c["SR_c"]) <= BAND[1])]
    by = defaultdict(list)
    for c in cands:
        by[int(c["task_id"])].append(c)
    trows = []
    for tid, cs in sorted(by.items()):
        n_roll = sum(int(c.get("k") or 0) for c in cs)
        n_acc = sum(1 for c in cs if c["decision"] == "accept")
        best = min(cs, key=lambda c: abs(float(c["SR_c"]) - 0.5))
        trows.append({"task_id": tid, "n_attempts": len(cs), "validation_rollouts": n_roll, "n_accept": n_acc, "rollouts_per_accept": (n_roll / n_acc) if n_acc else "",
                      "best_SR_c_closest_to_band": best["SR_c"], "best_in_band": BAND[0] <= float(best["SR_c"]) <= BAND[1], "accepted_SR_c": " ".join(str(c["SR_c"]) for c in cs if c["decision"] == "accept")})
    rows = [{"stat": "accepted SR_c distribution", "value": json.dumps(dict(sorted(dist.items())))},
            {"stat": "accepted outside [0.4, 0.6]", "value": f"{len(outside)}/{len(acc)}" + (f" = {len(outside) / len(acc):.3f}" if acc else "")},
            {"stat": "accepted SR_c values outside band", "value": " ".join(str(c["SR_c"]) for c in outside)},
            {"stat": "tasks without ACCEPT", "value": str(sum(1 for r in trows if not r["n_accept"]))},
            {"stat": "of which best attempt in band", "value": str(sum(1 for r in trows if not r["n_accept"] and r["best_in_band"]))},
            {"stat": "validation rollouts per ACCEPT (all H validation / accepts)", "value": f"{sum(int(c.get('k') or 0) for c in cands)}/{len(acc)}"}]
    write_csv(OUT / "accept_distribution.csv", rows)
    write_csv(OUT / "accept_per_task.csv", trows)
    g = {int(c["task_id"]): [c] for c in acc}
    r_out = boot_rate(g, lambda c: not (BAND[0] <= float(c["SR_c"]) <= BAND[1]), lambda c: 1)
    return {"rows": rows, "task_rows": trows, "outside_rate": r_out, "n_accept": len(acc)}


if __name__ == "__main__":
    import pickle
    which = sys.argv[1:] or ["f1", "f2", "f6", "f7", "f4"]
    cache = OUT / "_reanalyses_cache.pkl"
    res = pickle.loads(cache.read_bytes()) if cache.exists() else {}   # merge, so partial re-runs keep earlier items
    for w in which:
        res[w] = globals()[w]()
        print("[F]", w, "done", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_reanalyses_cache.pkl").write_bytes(pickle.dumps(res))
