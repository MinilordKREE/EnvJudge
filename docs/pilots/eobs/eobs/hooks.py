"""Observe-only extraction of EnvRigger's own artifacts into the E-obs schema (no control-flow change).

Sources written by the released code (per run dir):
  traces.jsonl        one Trace per rollout: kind (baseline|exploration|accepted), candidate (rules_code,
                      in_env_actions, rationale), candidate_id, rollout_idx, rollout_seed (= task_id), success,
                      duration_steps, steps[] (raw_action.kwargs.text, blocked_reason, raw_observation, info...), error
  orchestrator.jsonl  events: task_start(task_idx) / baseline_compute_done / candidate_proposed(attempt, rationale[:120])
                      / candidate_evaluated(attempt, candidate_id, success_rate) / mutator_decision(attempt, decision,
                      rationale[:200], failure_axis/label) / candidate_refined / candidate_reproposed / budget_stop /
                      task_skipped_passthrough / task_aborted
  agent_calls.jsonl   LoggingLLMClient rows for the designer: messages (truncated 8000 chars), tools, response.tool_calls
                      (decide_on_traces args carry the FULL decision rationale; propose_candidate args carry the full
                      rules_code / in_env_actions / rationale of the NEXT candidate)

The full decision text is taken from agent_calls (tool-call arguments), aligned to orchestrator events by
iteration order (both are appended sequentially per task; rollouts run inside, calls don't interleave across tasks).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from eobs.axis import classify

# Word-boundary version (owner review 2026-09-05): reverse/reversed/reversing/reversal, loosen*, unsolvable,
# impossible/impossibility; "irreversible", "reverse the order" (as a verb phrase about ordering) are NOT the
# target, but only the lexical exclusion of irreversib* is mechanical -- every match is listed in verdict.md for audit.
REVERSE_RE = re.compile(r"(?<![A-Za-z])(?:revers(?:e|ed|es|ing|al)|loosen(?:s|ed|ing)?|unsolvable|impossib(?:le|ility))(?![A-Za-z])", re.IGNORECASE)


def _jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def load_agent_calls(run_dir: Path) -> list[dict]:
    rows = []
    for p in sorted(Path(run_dir).glob("agent_calls*.jsonl")):
        rows += _jsonl(p)
    rows.sort(key=lambda r: r.get("ts", 0))
    return rows


def _tool_args(call: dict) -> tuple[str, dict]:
    tcs = (call.get("response") or {}).get("tool_calls") or []
    if not tcs:
        return "", {}
    return tcs[0].get("name", ""), tcs[0].get("arguments") or {}


def extract(run_dir: Path) -> dict:
    """Return {'candidates': [...], 'validation_rollouts': [...], 'baseline_rollouts': [...], 'tasks': {...}}."""
    run_dir = Path(run_dir)
    traces = _jsonl(run_dir / "traces.jsonl")
    events = _jsonl(run_dir / "orchestrator.jsonl")
    calls = load_agent_calls(run_dir)

    # ---- rollouts
    baseline_rollouts, validation_rollouts = [], []
    by_cand: dict[str, list[dict]] = defaultdict(list)
    for t in traces:
        acts = [(s.get("raw_action") or {}).get("kwargs", {}).get("text", "") for s in t.get("steps", [])]
        blocked = sum(1 for s in t.get("steps", []) if s.get("blocked_reason"))
        row = {"task_id": t.get("rollout_seed"), "candidate_id": t.get("candidate_id"), "seed_idx": t.get("rollout_idx"),
               "success": bool(t.get("success")), "steps": t.get("duration_steps"), "actions": acts, "blocked_count": blocked,
               "timeout": (t.get("error") == "subprocess timeout"), "error": t.get("error"), "kind": t.get("kind"),
               "episode_id": t.get("episode_id")}
        if t.get("kind") == "baseline":
            row["source"] = "rigger"
            baseline_rollouts.append(row)
        else:
            validation_rollouts.append(row)
            by_cand[t.get("candidate_id")].append(t)

    # ---- per task event streams
    task_events: dict[int, list[dict]] = defaultdict(list)
    cur = None
    for e in events:
        if e.get("kind") == "task_start":
            cur = e.get("task_idx")
        if cur is not None:
            task_events[cur].append(e)

    # ---- designer calls: content-matched to candidates (rules_code sha), sequence only as fallback
    def _sha(code: str) -> str:
        return hashlib.sha256((code or "").encode()).hexdigest()[:16]

    propose_calls = [(i, c) for i, c in enumerate(calls) if _tool_args(c)[0] == "propose_candidate"]
    decide_calls = [(i, c) for i, c in enumerate(calls) if _tool_args(c)[0] == "decide_on_traces"]
    used: set[int] = set()
    align_stats = {"propose_content": 0, "propose_sequence": 0, "propose_unmatched": 0,
                   "decide_candidate_id": 0, "decide_sequence": 0, "decide_unmatched": 0}

    def _match_propose(rules_code: str, in_env: list, after_idx: int) -> tuple[int, dict, str]:
        want = _sha(rules_code)
        want_acts = [(a.get("name"), (a.get("kwargs") or {}).get("text")) for a in in_env]
        for i, c in propose_calls:
            if i in used or i < after_idx:
                continue
            _, args = _tool_args(c)
            acts = []
            for a in (args.get("in_env_actions") or []):
                kw = a.get("kwargs")
                if kw is None and isinstance(a.get("kwargs_json"), str):
                    try:
                        kw = json.loads(a["kwargs_json"])
                    except Exception:
                        kw = {}
                acts.append((a.get("name"), (kw or {}).get("text")))
            if _sha(args.get("rules_code", "") or "") == want and acts == want_acts:
                used.add(i)
                return i, args, "content"
        return -1, {}, "none"

    def _match_decide(cid: str, after_idx: int, before_idx: int | None) -> tuple[int, dict, str]:
        for i, c in decide_calls:
            if i in used or i < after_idx or (before_idx is not None and i >= before_idx):
                continue
            _, args = _tool_args(c)
            if cid and args.get("candidate_id") == cid:
                used.add(i)
                return i, args, "candidate_id"
        # fallback: the first unused decide call after the candidate's propose call and before the next task's
        for i, c in decide_calls:
            if i in used or i < after_idx or (before_idx is not None and i >= before_idx):
                continue
            used.add(i)
            return i, _tool_args(c)[1], "sequence"
        return -1, {}, "none"

    candidates = []
    tasks: dict[int, dict] = {}
    # per task, the index range of agent calls: assume tasks consume calls in order (they run sequentially)
    task_call_ranges: dict[int, tuple[int, int | None]] = {}
    cursor = 0
    ordered_tasks = sorted(task_events)
    for ti in ordered_tasks:
        ev = task_events[ti]
        n_prop = 1 + sum(1 for x in ev if x.get("kind") in ("candidate_refined", "candidate_reproposed"))
        n_dec = sum(1 for x in ev if x.get("kind") == "mutator_decision")
        if any(x.get("kind") == "task_skipped_passthrough" for x in ev):
            n_prop, n_dec = 1, 0
        # count calls consumed by this task = n_prop propose + n_dec decide (aborted tasks may have fewer; use events)
        n_calls = n_prop + n_dec
        task_call_ranges[ti] = (cursor, cursor + n_calls)
        cursor += n_calls
    for task_idx in ordered_tasks:
        ev = task_events[task_idx]
        base = next((x for x in ev if x.get("kind") == "baseline_compute_done"), None)
        cache = next((x for x in ev if x.get("kind") == "baseline_cache_hit"), None)
        tasks[task_idx] = {"task_idx": task_idx, "task_id": (base or cache or {}).get("task_id"),
                           "p5": (base or cache or {}).get("sr"), "skipped": any(x.get("kind") == "task_skipped_passthrough" for x in ev),
                           "aborted": next((x.get("error") for x in ev if x.get("kind") == "task_aborted"), None),
                           "n_attempts": sum(1 for x in ev if x.get("kind") == "candidate_evaluated"),
                           "accepted": any(x.get("kind") == "mutator_decision" and x.get("decision") == "accept" for x in ev)}
        lo, hi = task_call_ranges[task_idx]
        evals = [x for x in ev if x.get("kind") == "candidate_evaluated"]
        decisions = [x for x in ev if x.get("kind") == "mutator_decision"]
        for i, ce in enumerate(evals):
            cid = ce.get("candidate_id")
            ctraces = by_cand.get(cid, [])
            cand = (ctraces[0].get("candidate") if ctraces else None) or {}
            rules_code = cand.get("rules_code", "") or ""
            in_env = cand.get("in_env_actions", []) or []
            pi, pargs, pmode = _match_propose(rules_code, in_env, lo)
            if pmode == "content":
                align_stats["propose_content"] += 1
            else:
                # sequence fallback: i-th propose call inside this task's range
                cands_in_range = [(j, c) for j, c in propose_calls if lo <= j < (hi or 10**9) and j not in used]
                if cands_in_range:
                    pi, c = cands_in_range[0]
                    used.add(pi)
                    pargs = _tool_args(c)[1]
                    pmode = "sequence"
                    align_stats["propose_sequence"] += 1
                else:
                    align_stats["propose_unmatched"] += 1
            dec = decisions[i] if i < len(decisions) else {}
            di, dargs, dmode = _match_decide(cid, max(pi, lo) if pi >= 0 else lo, hi)
            align_stats["decide_" + ("candidate_id" if dmode == "candidate_id" else ("sequence" if dmode == "sequence" else "unmatched"))] += 1
            decision_text = dargs.get("rationale", "") if dargs else (dec.get("rationale") or "")
            fa = dargs.get("failure_analysis") if isinstance(dargs.get("failure_analysis"), dict) else {}
            # next-attempt text: the propose/refine call that follows this decide within the task range
            next_text = ""
            if dec.get("decision") in ("refine", "reject") and i < len(evals) - 1 and di >= 0:
                nxt = next(((j, c) for j, c in propose_calls if j > di and (hi is None or j < hi) and j not in used), None)
                if nxt is not None:
                    next_text = _tool_args(nxt[1])[1].get("rationale", "")
            joined = " ".join([decision_text, fa.get("description", "") if fa else "", next_text])
            matches = [(m.group(0), joined[max(m.start() - 60, 0): m.end() + 60]) for m in REVERSE_RE.finditer(joined)]
            axis = classify(rules_code, in_env)
            n_timeout = sum(1 for t in ctraces if t.get("error") == "subprocess timeout")
            fails = defaultdict(int)
            for t in ctraces:
                if t.get("success"):
                    continue
                key = "timeout" if t.get("error") == "subprocess timeout" else ("error" if t.get("error") else ("blocked" if any(s.get("blocked_reason") for s in t.get("steps", [])) else "fail"))
                fails[key] += 1
            candidates.append({
                "task_idx": task_idx, "task_id": tasks[task_idx]["task_id"], "attempt": ce.get("attempt"), "candidate_id": cid,
                "axis": axis.label, "axes": sorted(axis.axes), "hooks": list(axis.hooks), "blocked_possible": axis.blocked_possible,
                "rules_code_sha": _sha(rules_code), "rules_code": rules_code,
                "in_env_actions": in_env, "rationale": cand.get("rationale", ""),
                "SR_c": ce.get("success_rate"), "k": ce.get("k"), "n_errors": ce.get("n_errors"), "timeouts": n_timeout,
                "failure_dist": dict(fails), "decision": dec.get("decision"), "decision_text": decision_text,
                "decision_text_source": dmode, "propose_align": pmode,
                "failure_axis": dec.get("failure_axis"), "failure_label": dec.get("failure_label"),
                "next_attempt_text": next_text, "reverse_or_loosen": bool(matches),
                "matched_snippet": " || ".join(f"[{w}] …{ctx}…" for w, ctx in matches),
            })
    return {"candidates": candidates, "validation_rollouts": validation_rollouts, "baseline_rollouts": baseline_rollouts,
            "tasks": tasks, "n_agent_calls": len(calls), "n_events": len(events), "n_traces": len(traces), "align_stats": align_stats}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
