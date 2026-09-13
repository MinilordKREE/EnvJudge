"""Stage candidates: end + midpoint of three failed rollouts, dedupe, cap, latest first."""

from __future__ import annotations

from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea.config import AEAConfig
from aea.stage import build_stage_candidates, candidate_states, seeded_failures
from tests.fixtures.fake_substrate import PLAN
from tests.fixtures.fake_world import make_open

CFG = AEAConfig()


def test_candidate_states_end_and_midpoint() -> None:
    got = candidate_states({"a": 40, "b": 30, "c": 10}, cap=6)
    assert got == [
        ("a", 40, "end"),
        ("b", 30, "end"),
        ("a", 20, "mid"),
        ("b", 15, "mid"),
        ("c", 10, "end"),
        ("c", 5, "mid"),
    ]
    capped = candidate_states({"a": 40, "b": 30, "c": 10, "d": 12}, cap=6)
    assert len(capped) == 6 and capped[0] == ("a", 40, "end")  # the latest never drops
    assert candidate_states({"z": 0}, cap=6) == []


def _failed_trace(eid: str, actions: list[str]) -> Trace:
    steps = []
    for a in actions:
        act = Action(name="do", kwargs={"text": a})
        steps.append(
            Step(
                raw_action=act,
                filtered_action=act,
                raw_observation=Observation(text="x"),
                filtered_observation=Observation(text="x"),
            )
        )
    return Trace(
        episode_id=eid,
        iteration_id="estimate-1-0",
        task_id="t",
        candidate=Candidate(),
        success=False,
        steps=steps,
        duration_steps=len(steps),
    )


def test_build_stage_candidates_dedupes_and_guards() -> None:
    # three failed rollouts that walk the plan's first actions then wander
    fails = [
        _failed_trace("e1", [PLAN[0], "look", "look", "look"]),
        _failed_trace("e2", [PLAN[0], "look", "look", "look"]),
        _failed_trace("e3", ["look", "look"]),
    ]
    assert len(seeded_failures(fails, 3, seed=1)) == 3
    open_fn = make_open(PLAN)
    res = build_stage_candidates(open_fn, "1", fails, {}, CFG, oracle=True)
    ids = [c.id for c in res.candidates]
    assert len(ids) == len(set(ids)) and all(c.guard.ok for c in res.candidates)
    assert res.fidelity_checked and res.candidates == sorted(res.candidates, key=lambda c: -c.t)
    # e1 and e2 compile to the same state at t=4 and at t=2 -> deduped; e3's states are 'look'-only
    assert len(res.candidates) <= 4
    res2 = build_stage_candidates(open_fn, "1", fails, {}, CFG, oracle=False)
    assert res2.candidates and all(c.guard.source == "self_certify" for c in res2.candidates)
