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

REVERSE_RE = re.compile(r"(revers\w*|loosen\w*|unsolv\w*|impossib\w*)", re.IGNORECASE)


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

    # ---- designer calls in order: propose, (decide, refine|propose)* per task. Align by sequence.
    call_idx = 0
    candidates = []
    tasks: dict[int, dict] = {}
    for task_idx in sorted(task_events):
        ev = task_events[task_idx]
        base = next((x for x in ev if x.get("kind") == "baseline_compute_done"), None)
        cache = next((x for x in ev if x.get("kind") == "baseline_cache_hit"), None)
        tasks[task_idx] = {"task_idx": task_idx, "task_id": (base or cache or {}).get("task_id"),
                           "p5": (base or cache or {}).get("sr"), "skipped": any(x.get("kind") == "task_skipped_passthrough" for x in ev),
                           "aborted": next((x.get("error") for x in ev if x.get("kind") == "task_aborted"), None),
                           "n_attempts": sum(1 for x in ev if x.get("kind") == "candidate_evaluated"),
                           "accepted": any(x.get("kind") == "mutator_decision" and x.get("decision") == "accept" for x in ev)}
        # first propose call for this task
        propose_call = calls[call_idx] if call_idx < len(calls) else {}
        if propose_call:
            call_idx += 1
        evals = [x for x in ev if x.get("kind") == "candidate_evaluated"]
        decisions = [x for x in ev if x.get("kind") == "mutator_decision"]
        cur_propose_args = _tool_args(propose_call)[1] if propose_call else {}
        for i, ce in enumerate(evals):
            cid = ce.get("candidate_id")
            ctraces = by_cand.get(cid, [])
            cand = (ctraces[0].get("candidate") if ctraces else None) or {}
            rules_code = cand.get("rules_code", "") or cur_propose_args.get("rules_code", "") or ""
            in_env = cand.get("in_env_actions", []) or []
            dec = decisions[i] if i < len(decisions) else {}
            decide_call = calls[call_idx] if call_idx < len(calls) else {}
            if decide_call:
                call_idx += 1
            dname, dargs = _tool_args(decide_call)
            decision_text = dargs.get("rationale", "") if dname == "decide_on_traces" else (dec.get("rationale") or "")
            next_call, next_text = {}, ""
            if dec.get("decision") in ("refine", "reject") and i < len(evals) - 1:
                next_call = calls[call_idx] if call_idx < len(calls) else {}
                if next_call:
                    call_idx += 1
                nname, nargs = _tool_args(next_call)
                next_text = nargs.get("rationale", "") if nname == "propose_candidate" else ""
                cur_propose_args = nargs if nname == "propose_candidate" else {}
            joined = " ".join([decision_text, next_text, (dargs.get("failure_analysis") or {}).get("description", "") if isinstance(dargs.get("failure_analysis"), dict) else ""])
            m = REVERSE_RE.search(joined)
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
                "rules_code_sha": hashlib.sha256((rules_code or "").encode()).hexdigest()[:16], "rules_code": rules_code,
                "in_env_actions": in_env, "rationale": cand.get("rationale", ""),
                "SR_c": ce.get("success_rate"), "k": ce.get("k"), "n_errors": ce.get("n_errors"), "timeouts": n_timeout,
                "failure_dist": dict(fails), "decision": dec.get("decision"), "decision_text": decision_text,
                "failure_axis": dec.get("failure_axis"), "failure_label": dec.get("failure_label"),
                "next_attempt_text": next_text, "reverse_or_loosen": bool(m), "matched_snippet": (joined[max(m.start() - 60, 0): m.end() + 60] if m else ""),
            })
    return {"candidates": candidates, "validation_rollouts": validation_rollouts, "baseline_rollouts": baseline_rollouts,
            "tasks": tasks, "n_agent_calls": len(calls), "n_events": len(events), "n_traces": len(traces)}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
