"""Offline unit tests (no env, no LLM). Integration tests live in test_integration.py and are marked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eobs import axis, certs, hooks
from eobs.certs import HintResult, ReplayResult
from eobs.recover import summarize

CODE_A = "class _Rules(Rules):\n    def filter_action(self, action, env_state):\n        if 'open' in action.kwargs.get('text',''):\n            return Blocked(reason='no')\n        return action\n"
CODE_T = "class _Rules(Rules):\n    def modify_transition(self, action, raw_response, env_state):\n        return raw_response\n"
CODE_O = "class _Rules(Rules):\n    def filter_observation(self, obs, env_state):\n        return obs\n"


def test_axis_classifier():
    a = axis.classify(CODE_A, [])
    assert a.axes == {"A"} and a.blocked_possible and a.label == "A"
    assert axis.classify(CODE_T + CODE_O.replace("class _Rules(Rules):\n", ""), []).axes == {"T", "O"}
    s = axis.classify("", [{"name": "do", "kwargs": {"text": "open drawer 1"}}])
    assert s.axes == {"S0"} and s.label == "S0"
    both = axis.classify(CODE_A, [{"name": "do"}])
    assert both.label == "S0+A"
    bad = axis.classify("class _Rules(Rules)\n  pass", [])
    assert bad.parse_error and bad.axes == set()
    assert axis.classify("class Other(Rules):\n    def filter_action(self, a, s): return a\n", []).axes == set()


def test_certificates_logic():
    ok = ReplayResult(ok=True, reason="pass")
    bad = ReplayResult(ok=False, reason="blocked", step=3)
    assert certs.certified(bad, bad, None) is False
    assert certs.certified(bad, ok, None) is True
    assert certs.certified(None, None, HintResult(attempts=2, ok=True)) is True
    assert certs.needs_hint(0.0, ok) and certs.needs_hint(0.4, bad) and not certs.needs_hint(0.4, ok)
    row = certs.certificate_row("c1", "A", bad, bad, HintResult(3, False), None)
    assert row["unresolved"] and not row["certified"] and row["R_old"]["step"] == 3


def test_recover_summary_math():
    rec = {"T_eval": 10, "L": 6, "monotone": 0}
    s = summarize(rec)
    assert s["L_over_T"] == 0.6 and s["L_ge_2"] and s["non_monotone"]
    assert summarize({"T_eval": 4, "L": -1, "monotone": 1})["L_over_T"] == 0.0


class _FakeInner:
    def __init__(self, **kw):
        self.model_id = kw.get("model", "fake")
        self.calls = []

    def chat(self, messages, tools=None, tool_choice="auto", temperature=0.7, max_tokens=None, **kwargs):
        self.calls.append(dict(messages=messages, tools=tools, tool_choice=tool_choice, temperature=temperature, max_tokens=max_tokens, kwargs=kwargs))
        from envharness.infra.llm import ChatResponse

        class U:
            prompt_tokens, completion_tokens = 100, 20
            prompt_tokens_details = type("D", (), {"cached_tokens": 40})()
            completion_tokens_details = None
            prompt_cache_hit_tokens = 40

        class Raw:
            usage = U()
            choices = []
        return ChatResponse(content="<action>look</action>", tool_calls=[], raw=Raw())


def test_ledger_client_is_observe_only(tmp_path, monkeypatch):
    import eobs.llm as L
    monkeypatch.setattr(L, "import_symbol", lambda name: _FakeInner)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = L.LedgerLLMClient("x:Fake", {"model": "openai/deepseek-v4-pro"}, ledger_path=str(tmp_path / "ledger.jsonl"), role="policy")
    msgs = [object()]
    tools = [{"type": "function"}]
    r1 = c.chat(msgs, tools=tools, tool_choice="auto", temperature=0.5, max_tokens=None, foo=1)
    inner_call = c.inner.calls[0]
    assert inner_call["messages"] is msgs and inner_call["tools"] is tools and inner_call["temperature"] == 0.5 and inner_call["kwargs"] == {"foo": 1}
    assert r1.content == "<action>look</action>" and r1.raw is not None
    rows = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["prompt_tokens"] == 100 and rows[0]["cached_tokens"] == 40 and rows[0]["completion_tokens"] == 20
    assert rows[0]["pricing_version"] and rows[0]["usd"] > 0 and rows[0]["role"] == "policy"


def _mk_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    cand = {"rules_code": CODE_A, "in_env_actions": [], "rationale": "block opens"}
    traces = []
    for k in range(2):
        traces.append({"episode_id": f"b{k}", "iteration_id": "baseline-0000", "task_id": "lbl", "candidate": {"rules_code": "", "in_env_actions": [], "rationale": ""},
                       "candidate_id": "baseline", "rollout_idx": k, "rollout_seed": 0, "kind": "baseline", "success": k == 0, "duration_steps": 3,
                       "steps": [{"raw_action": {"name": "do", "kwargs": {"text": "look"}}, "blocked_reason": None}] * 3})
    for k in range(2):
        traces.append({"episode_id": f"v{k}", "iteration_id": "it1", "task_id": "lbl", "candidate": cand, "candidate_id": "cand1", "rollout_idx": k,
                       "rollout_seed": 0, "kind": "exploration", "success": False, "duration_steps": 2,
                       "steps": [{"raw_action": {"name": "do", "kwargs": {"text": "open drawer 1"}}, "blocked_reason": "no"}] * 2})
    (run / "traces.jsonl").write_text("".join(json.dumps(t) + "\n" for t in traces))
    events = [{"kind": "task_start", "task_idx": 0}, {"kind": "baseline_compute_done", "task_idx": 0, "task_id": 0, "sr": 0.5},
              {"kind": "candidate_proposed", "attempt": 0}, {"kind": "candidate_evaluated", "attempt": 1, "candidate_id": "cand1", "k": 2, "success_rate": 0.0, "n_errors": 0},
              {"kind": "mutator_decision", "attempt": 1, "decision": "reject", "rationale": "short", "failure_axis": "A"}, {"kind": "budget_stop"}]
    (run / "orchestrator.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    calls = [{"ts": 1, "role": "harness_agent", "response": {"tool_calls": [{"name": "propose_candidate", "arguments": {"rationale": "block opens", "rules_code": CODE_A}}]}},
             {"ts": 2, "role": "harness_agent", "response": {"tool_calls": [{"name": "decide_on_traces", "arguments": {"decision": "reject", "rationale": "All rollouts blocked; the task is UNSOLVABLE under this ban, reverse it.", "failure_analysis": {"primary_axis": "A"}}}]}}]
    (run / "agent_calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in calls))
    return run


def test_hooks_extract(tmp_path):
    out = hooks.extract(_mk_run(tmp_path))
    assert len(out["baseline_rollouts"]) == 2 and len(out["validation_rollouts"]) == 2
    c = out["candidates"][0]
    assert c["candidate_id"] == "cand1" and c["axis"] == "A" and c["SR_c"] == 0.0 and c["decision"] == "reject"
    assert c["reverse_or_loosen"] and "UNSOLVABLE" in c["matched_snippet"] and c["decision_text"].startswith("All rollouts")
    assert c["failure_dist"] == {"blocked": 2} and out["tasks"][0]["p5"] == 0.5
