from __future__ import annotations

from envharness.core.types import Action, Candidate

from aea.certs import certify, expert_shortest_success, replay_actions, run_expert, witness_survival
from aea.config import AEAConfig
from tests.fixtures.fake_world import make_open

PLAN = ["go to a", "take x from a", "go to b", "move x to b"]
TRUNCATE_AT_2 = """
class _Rules(Rules):
    def modify_transition(self, action, raw_response, env_state):
        if env_state.step_count >= 2 and not env_state.won:
            return EnvResponse(observation=raw_response.observation, reward=0.0, terminated=False,
                               truncated=True, info=dict(raw_response.info))
        return raw_response
"""


def test_session_done_reads_stack_level_truncation() -> None:
    open_fn = make_open(PLAN)
    sess = open_fn(Candidate(rules_code=TRUNCATE_AT_2))
    r = replay_actions(sess, PLAN)
    assert (
        not r.ok and r.reason == "verifier_fail" and r.n_steps == 2
    )  # stopped when the stack truncated
    assert sess.done and not sess.bridge.state.done  # bridge alone would not know


def test_replay_and_expert() -> None:
    open_fn = make_open(PLAN)
    assert replay_actions(open_fn(None), PLAN).ok
    bad = replay_actions(open_fn(None), ["look", "take x from a"])
    assert not bad.ok and bad.reason == "verifier_fail"
    r = run_expert(open_fn(None), max_steps=50)
    assert r.ok and r.actions == PLAN and r.n_steps == 4
    stuck = run_expert(open_fn(None), max_steps=3)
    assert not stuck.ok and stuck.reason == "verifier_fail"


def test_ladder_orders_and_hint_budget() -> None:
    cfg = AEAConfig()
    open_fn = make_open(PLAN)
    assert certify(Candidate(), open_fn, cfg, by_construction=True).source == "by_construction"
    cert = certify(Candidate(), open_fn, cfg, policy_witness=PLAN)
    assert cert.source == "R_pol" and cert.witness == PLAN
    cert = certify(Candidate(), open_fn, cfg, policy_witness=["look"])
    assert (
        cert.source == "R_exp" and cert.detail["R_pol"] == "verifier_fail" and cert.witness == PLAN
    )
    blocked = (
        "class _Rules(Rules):\n    def filter_action(self, action, env_state):\n"
        "        return Blocked(reason='no')\n"
    )
    hints: list[list[str]] = []

    def hint(plan: list[str]) -> bool:
        hints.append(plan)
        return len(hints) == 2

    cert = certify(Candidate(rules_code=blocked), open_fn, cfg, hint_rollout=hint)
    assert cert.source == "R_hint" and cert.detail["R_hint_attempt"] == 2 and len(hints) == 2
    cert = certify(Candidate(rules_code=blocked), open_fn, cfg)
    assert (
        cert.source == "uncertified" and not cert.certified and cert.detail["R_exp_1"] == "blocked"
    )


def test_expert_shortest_and_witness_survival() -> None:
    cfg = AEAConfig()
    open_fn = make_open(PLAN)
    assert expert_shortest_success(open_fn, cfg) == PLAN
    stage = Candidate(
        in_env_actions=[
            Action(name="do", kwargs={"text": "go to a"}),
            Action(name="do", kwargs={"text": "look"}),
        ]
    )
    omega, ok, n = witness_survival(stage, open_fn, [PLAN, PLAN[1:], ["look"]])
    assert (omega, ok, n) == (
        2 / 3,
        2,
        3,
    )  # after the staged "go to a" both plans still reach the goal
    assert witness_survival(stage, open_fn, []) == (None, 0, 0)
