"""solvable(): the one guard, asymmetric (docs/spec/AEA_v0.2.md)."""

from __future__ import annotations

from envharness.core.types import Candidate

from aea.config import AEAConfig
from aea.families import FamilyContext, FooterMask
from aea.witness import solvable
from tests.fixtures.fake_substrate import PLAN
from tests.fixtures.fake_world import make_open

CFG = AEAConfig()
BLOCK_ALL = """
class _Rules(Rules):
    DOSE = 1.0

    def filter_action(self, action, env_state):
        return Blocked(reason="no")
"""
BLOCK_LOOK = """
class _Rules(Rules):
    DOSE = 1.0

    def filter_action(self, action, env_state):
        if action.kwargs.get("text", "") == "look":
            return Blocked(reason="look is closed")
        return action
"""
STALE = ["look", "look", "look", "look", "look"]  # a witness that no longer reaches the goal


def _open(cand: Candidate | None):  # type: ignore[no-untyped-def]
    return make_open(PLAN)(cand, None)


def test_by_construction_skips_the_guard() -> None:
    fm = FooterMask().make(1.0, FamilyContext("1"))
    assert fm is not None
    r = solvable(fm, _open, CFG, policy_success=None, oracle=False, by_construction=True)
    assert r.ok and r.source == "by_construction"


def test_policy_replay_then_oracle_then_uncertified() -> None:
    plain = Candidate()
    r = solvable(plain, _open, CFG, policy_success=list(PLAN), oracle=True)
    assert r.ok and r.source == "policy_replay" and r.witness == list(PLAN)
    # the stale witness fails on a wrapper that closes `look`; the oracle (never looks) recovers
    closed = Candidate(rules_code=BLOCK_LOOK)
    r = solvable(closed, _open, CFG, policy_success=STALE, oracle=True)
    assert r.ok and r.source == "oracle" and r.detail["policy_replay"] == "blocked"
    # everything blocked -> the oracle fails -> uncertified
    r = solvable(
        Candidate(rules_code=BLOCK_ALL), _open, CFG, policy_success=list(PLAN), oracle=True
    )
    assert not r.ok and r.source == "uncertified"


def test_no_oracle_self_certifies_after_a_failed_replay() -> None:
    closed = Candidate(rules_code=BLOCK_LOOK)
    r = solvable(closed, _open, CFG, policy_success=STALE, oracle=False)
    assert r.ok and r.source == "self_certify" and r.detail["policy_replay"] == "blocked"
    # stage side: no policy witness, no oracle -> self-certify without any replay
    r = solvable(Candidate(), _open, CFG, policy_success=None, oracle=False)
    assert r.ok and r.source == "self_certify" and r.detail == {}
