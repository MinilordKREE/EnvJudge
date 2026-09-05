"""Integration tests: one per external dependency. Run with `-m integration` (skipped otherwise)."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("ALFWORLD_DATA"), reason="ALFWORLD_DATA not set")
def test_alfworld_expert_witness_and_midstate():
    from eobs.replay import witness_base
    from eobs.recover import c_at
    w = witness_base(7)
    assert w["W_base"] and w["expert_plan_len"] >= 3
    c, reason = c_at(7, w["expert_actions"][:2] + ["look"])
    assert c == 1 and reason == "pass"


@pytest.mark.skipif(not os.environ.get("EOBS_LLM_TEST"), reason="set EOBS_LLM_TEST=1 to spend one DeepSeek call")
def test_deepseek_nonthinking_ledger(tmp_path):
    from eobs.settings import secrets
    os.environ["OPENAI_API_KEY"] = secrets().deepseek_api_key.get_secret_value()
    from envharness.infra.llm import Message
    from eobs.llm import LedgerLLMClient
    c = LedgerLLMClient("envharness.infra.llm:LiteLLMClient", {"model": "openai/deepseek-v4-pro", "api_base": "https://api.deepseek.com",
                        "extra_body": {"thinking": {"type": "disabled"}}, "drop_params": True}, ledger_path=str(tmp_path / "l.jsonl"), role="test")
    r = c.chat([Message(role="user", content="Say OK.")], temperature=0.5)
    assert r.content and r.raw.usage.completion_tokens < 50


@pytest.mark.skipif(not os.environ.get("ALFWORLD_DATA"), reason="ALFWORLD_DATA not set")
def test_reused_bridge_matches_fresh_instance():
    """open_session reuses one AlfworldEnv per process; a fresh instance must give the same game and observations."""
    from envharness.bridges.alfworld import AlfworldEnv
    from envharness.core.types import Action
    from eobs.replay import RESET_OPTIONS, TASK_LABEL, open_session
    acts = ["look", "go to fridge 1", "open fridge 1", "inventory"]
    s = open_session(None, 5)
    reused = [s.step_text(a)["obs"] for a in acts]
    gf_reused = s.gamefile
    s.close()
    s2 = open_session(None, 9); s2.close()          # switch task in between
    s3 = open_session(None, 5)
    again = [s3.step_text(a)["obs"] for a in acts]
    s3.close()
    fresh = AlfworldEnv()
    r = fresh.reset(seed=5, options={**RESET_OPTIONS, "task_id": TASK_LABEL})
    fresh_obs = [fresh.step(Action(name="do", kwargs={"text": a})).observation.text for a in acts]
    assert r.info.get("extra.gamefile") == gf_reused
    assert reused == fresh_obs == again
    fresh.close()
