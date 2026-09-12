"""Stage candidates: end + midpoint of three failed rollouts, dedupe, cap, latest first."""

from __future__ import annotations

from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea.config import AEAConfig
from aea.stage import build_stage_candidates, candidate_states, cap_by_priority, seeded_failures
from tests.fixtures.fake_substrate import PLAN
from tests.fixtures.fake_world import make_open

CFG = AEAConfig()


def test_candidate_states_end_mid_quarter_and_priority_cap() -> None:
    got = candidate_states({"a": 40, "b": 30, "c": 10})
    assert got == [
        ("a", 40, "end"),
        ("b", 30, "end"),
        ("a", 20, "mid"),
        ("b", 15, "mid"),
        ("a", 10, "quarter"),
        ("c", 10, "end"),
        ("b", 7, "quarter"),
        ("c", 5, "mid"),
        ("c", 2, "quarter"),
    ]
    capped = candidate_states({"a": 40, "b": 30, "c": 10}, cap=6)
    assert [k for _, _, k in capped] == ["end", "end", "mid", "mid", "end", "mid"]  # quarters first
    assert capped[0] == ("a", 40, "end")  # the latest never drops
    # when ends and midpoints collapse, quarters fill the slots
    kept = cap_by_priority([("a", 50, "end"), ("a", 25, "mid"), ("a", 12, "quarter")], cap=6)
    assert [k for _, _, k in kept] == ["end", "mid", "quarter"]
    assert candidate_states({"z": 0}) == []
    assert candidate_states({"s": 3}) == [
        ("s", 3, "end"),
        ("s", 1, "mid"),
    ]  # quarter == mid deduped


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
    # e1 and e2 compile to the same state at t=4, t=2 and t=1 -> deduped; e3's states are
    # 'look'-only; quarter candidates were generated and survive the dedupe only when distinct
    assert len(res.candidates) <= 6 and len({c.id for c in res.candidates}) == len(res.candidates)
    kinds = {c.kind for c in res.candidates}
    assert kinds <= {"end", "mid", "quarter"}
    long = [_failed_trace(f"f{i}", ["look"] * 40 + [PLAN[0]] + ["look"] * 9) for i in range(3)]
    res3 = build_stage_candidates(open_fn, "1", long, {}, CFG, oracle=False)
    # three identical rollouts: end, mid and quarter each collapse to one state -> 3 candidates,
    # the quarter one among them (a state before the plan's first action)
    assert len(res3.candidates) == 3 and {c.kind for c in res3.candidates} == {
        "end",
        "mid",
        "quarter",
    }
    res2 = build_stage_candidates(open_fn, "1", fails, {}, CFG, oracle=False)
    assert res2.candidates and all(c.guard.source == "self_certify" for c in res2.candidates)
