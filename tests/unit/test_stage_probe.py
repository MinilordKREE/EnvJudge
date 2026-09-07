from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea.config import AEAConfig
from aea.errors import BudgetExhausted
from aea.probe import ProbeResult, classify, probe
from aea.stage import (
    StagedCandidate,
    build_stage_candidates,
    candidate_id,
    compile_prefix,
    fidelity_check,
    select_candidates,
    stage_reset_options,
)
from tests.fixtures.fake_world import make_open

PLAN = ["go to a", "take x from a", "go to b", "move x to b"]
CFG = AEAConfig()
CHS_PROFILE = Path(__file__).resolve().parents[2] / "docs/pilots/e1pilot/p5/results/chs_profile.csv"


def _open_with_options(plan: list[str] = PLAN):  # type: ignore[no-untyped-def]
    inner = make_open(plan)
    calls: list[dict[str, Any] | None] = []

    def open_fn(candidate: Candidate | None, reset_options: dict[str, Any] | None = None):  # type: ignore[no-untyped-def]
        calls.append(reset_options)
        return inner(candidate, reset_options)

    return open_fn, calls


def _failed_trace(actions: list[str], eid: str = "ep1") -> Trace:
    steps = []
    for a in actions:
        obs = Observation(text=f"Task: put x in b\n\nYou {a}.\n\nAdmissible commands: look")
        steps.append(
            Step(
                raw_action=Action(name="do", kwargs={"text": a}),
                filtered_action=Action(name="do", kwargs={"text": a}),
                raw_observation=obs,
                filtered_observation=obs,
            )
        )
    return Trace(
        episode_id=eid,
        iteration_id="i",
        task_id="t",
        candidate=Candidate(),
        steps=steps,
        success=False,
    )


def test_compile_prefix_drops_ineffective_and_ends_with_look() -> None:
    open_fn, calls = _open_with_options()
    opts = stage_reset_options({"split": "train"}, "cfg100.yaml")
    compiled = compile_prefix(open_fn, ["go to a", "fly", "take x from a", "look"], opts)
    assert compiled == ["go to a", "take x from a", "look"]  # "fly" is not admissible
    assert calls[-1] == {"split": "train", "config_path": "cfg100.yaml"}
    assert compile_prefix(open_fn, [], opts) == ["look"]
    assert candidate_id("7", compiled) == candidate_id("7", list(compiled)) and candidate_id(
        "7", compiled
    ) != candidate_id("8", compiled)


def test_select_candidates_rule_and_cap() -> None:
    out = select_candidates(
        {"a": [3, 5, 10, 20, 30, 40], "b": [2, 4, 8, 12, 16], "c": [1, 2]},
        (1.0, 0.75, 0.5, 0.25),
        6,
    )
    assert len(out) == 6 and out[0] == ("a", 40, "L") and out == sorted(out, key=lambda x: -x[1])
    assert ("a", 20, "0.5L") in out and ("b", 16, "L") in out
    assert select_candidates({"a": [8]}, (1.0, 0.5), 6) == [("a", 8, "L")]
    assert select_candidates({"a": [], "b": [0]}, (1.0,), 6) == []


def test_build_and_certify_and_fidelity() -> None:
    open_fn, _ = _open_with_options()
    opts = stage_reset_options({}, "cfg100.yaml")
    trace = _failed_trace(["go to a", "look", "fly", "take x from a"])
    states = {"ep1": [1, 2, 4]}
    result = build_stage_candidates(open_fn, "7", [trace], opts, CFG, certified_states=states)
    # t=1 and t=2 compile to the same staged state ("go to a", "look"): one candidate
    assert [c.t for c in result.candidates] == [4, 2] and all(
        c.certified for c in result.candidates
    )
    assert result.candidates[0].compiled == [
        "go to a",
        "look",
        "take x from a",
        "look",
    ]  # "fly" dropped
    assert result.fidelity_checked and result.candidates[0].fidelity_ok is not None
    # a prefix that solves the task cannot be certified as a stage start? it can (expert idles): the
    # id differs
    assert len({c.id for c in result.candidates}) == 2


def test_fidelity_check_compares_observations() -> None:
    open_fn, _ = _open_with_options()
    trace = _failed_trace(["go to a"])
    assert (
        fidelity_check(open_fn, trace, 1, ["go to a", "look"], {}) is False
    )  # archived text differs (fake obs)
    sess = open_fn(Candidate(in_env_actions=[Action(name="do", kwargs={"text": "go to a"})]), {})
    real = sess.stack.observe()
    trace2 = _failed_trace(["go to a"])
    trace2.steps[0].filtered_observation = real
    assert fidelity_check(open_fn, trace2, 1, ["go to a", "look"], {}) is True


def _staged(t: int, eid: str = "e") -> StagedCandidate:
    from aea.certs import Certificate

    return StagedCandidate(
        id=f"7:{t}",
        episode_id=eid,
        t=t,
        kind="L",
        compiled=["look"],
        candidate=Candidate(),
        certificate=Certificate("R_exp"),
    )


def _trace(success: bool) -> Trace:
    return Trace(
        episode_id="e", iteration_id="i", task_id="t", candidate=Candidate(), success=success
    )


def test_probe_latest_first_accepts_first_learnable() -> None:
    script = {30: [0, 0, 0, 0], 25: [1, 1, 1, 1], 20: [1, 0, 0, 1], 10: [1, 1, 0, 0]}
    seen: list[int] = []

    def run(c: StagedCandidate, n: int) -> list[Trace]:
        seen.append(c.t)
        return [_trace(bool(x)) for x in script[c.t][:n]]

    result = probe([_staged(10), _staged(30), _staged(20), _staged(25)], run, CFG)
    assert (
        result.status == "accepted"
        and result.accepted is not None
        and result.accepted.candidate.t == 20
    )
    assert seen == [30, 25, 20] and [e.cls for e in result.profile] == [
        "dead",
        "too_easy_stage",
        "learnable",
    ]
    assert [e.candidate.t for e in result.too_easy] == [25]
    assert classify(4, 4) == "too_easy_stage" and classify(0, 4) == "dead"


def test_probe_unresolved_budget_and_empty() -> None:
    result = probe([_staged(5), _staged(3)], lambda c, n: [_trace(False)] * n, CFG)
    assert result.status == "unresolved" and result.accepted is None and len(result.profile) == 2
    assert probe([], lambda c, n: [], CFG).status == "no_candidate"

    def broke(c: StagedCandidate, n: int) -> list[Trace]:
        raise BudgetExhausted("cap", budget="search", cap=30, spent=30)

    assert probe([_staged(5)], broke, CFG).status == "budget_cap_hit"
    assert isinstance(ProbeResult("unresolved"), ProbeResult)


@pytest.mark.skipif(not CHS_PROFILE.exists(), reason="pilot fixture not present")
def test_p5_profiles_reproduce_selection() -> None:
    """The archived P5.1 profiles (all candidates probed) through the latest-first walk give the
    archived selected states (chs_selected.csv: tasks 8, 9, 27 selected at t = 50; 11/14/17
    unresolved;
    20 dead-then-too-easy -> unresolved for the main method)."""
    with CHS_PROFILE.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)
    expected = {
        "8": 50,
        "9": 50,
        "27": 50,
        "10": 50,
        "11": None,
        "14": None,
        "17": None,
        "20": None,
    }
    for task, want in expected.items():
        cands = [_staged(int(r["t"]), r["episode_id"]) for r in by_task[task]]
        for c, r in zip(cands, by_task[task], strict=True):
            c.id = f"{task}:{r['episode_id']}:{r['t']}"
        table = {c.id: int(r["probe_successes"]) for c, r in zip(cands, by_task[task], strict=True)}

        def run(c: StagedCandidate, n: int, table: dict[str, int] = table) -> list[Trace]:
            s = table[c.id]
            return [_trace(i < s) for i in range(n)]

        result = probe(cands, run, CFG)
        got = result.accepted.candidate.t if result.accepted else None
        assert got == want, (task, got, want)
