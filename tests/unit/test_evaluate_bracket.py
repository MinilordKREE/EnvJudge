"""evaluate() (the one 4 -> 8 rule, stage-side top-up) and the population-seeded dose bracket
(docs/spec/AEA_v0.3.md)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from envharness.core.types import Candidate, Trace

from aea.bracket import DoseEval, bracket, order_violated
from aea.config import AEAConfig
from aea.errors import BudgetExhausted
from aea.evaluate import Eval, evaluate, verdict

CFG = AEAConfig()


def _trace(ok: bool) -> Trace:
    return Trace(episode_id="e", iteration_id="i", task_id="t", candidate=Candidate(), success=ok)


def scripted(outcomes: list[int]) -> tuple[list[int], Callable[[int], list[Trace]]]:
    """A run function that hands out the scripted successes in order and counts rollouts."""
    pos = [0]
    spent = [0]

    def run(n: int) -> list[Trace]:
        got = outcomes[pos[0] : pos[0] + n]
        pos[0] += n
        spent[0] += n
        return [_trace(bool(x)) for x in got]

    return spent, run


def test_verdict_matches_the_box() -> None:
    assert verdict(0, 4, CFG) == "too_hard" and verdict(4, 4, CFG) == "too_easy"
    with pytest.raises(ValueError):
        verdict(2, 4, CFG)
    assert [verdict(s, 8, CFG) for s in range(9)] == [
        "too_hard",
        "too_hard",
        "too_hard",
        "in_band",
        "in_band",
        "in_band",
        "too_easy",
        "too_easy",
        "too_easy",
    ]


def test_evaluate_tops_up_unless_extreme() -> None:
    spent, run = scripted([1, 0, 1, 0, 1, 1, 0, 0])
    ev = evaluate(run, CFG)
    assert ev.n == 8 and ev.successes == 4 and ev.verdict == "in_band" and spent[0] == 8
    spent, run = scripted([0, 0, 0, 0])
    ev = evaluate(run, CFG)
    assert ev.n == 4 and ev.verdict == "too_hard" and spent[0] == 4
    spent, run = scripted([1, 1, 1, 1])
    assert evaluate(run, CFG).verdict == "too_easy" and spent[0] == 4
    spent, run = scripted([1, 0, 0, 0, 0, 0, 0, 0])
    assert evaluate(run, CFG).verdict == "too_hard"  # 1/4 is NOT accepted (E2 lesson)


def test_bracket_bisects_and_accepts() -> None:
    """Cliff between 0.5 and 0.75: 0.5 too easy (4/4), 0.75 too hard (0/4), 0.625 in band."""
    table = {0.5: [1, 1, 1, 1], 0.75: [0, 0, 0, 0], 0.625: [1, 0, 1, 0, 1, 1, 0, 0]}
    seen: list[float] = []

    def at(d: float) -> Eval:
        seen.append(d)
        _, run = scripted(table[d])
        return evaluate(run, CFG)

    lev = DoseEval(1.0, Eval(0, 4, "too_hard"))
    r = bracket(at, CFG, leverage=lev)
    assert r.status == "accepted" and r.accepted is not None and r.accepted.d == 0.625
    assert seen == [0.5, 0.75, 0.625] and [h.d for h in r.history] == [1.0, 0.5, 0.75, 0.625]


def test_bracket_population_seed_sets_the_first_bisection() -> None:
    table = {0.9375: [1, 0, 1, 0, 1, 1, 0, 0], 0.5: [1, 0, 1, 0, 1, 1, 0, 0]}
    seen: list[float] = []

    def at(d: float) -> Eval:
        seen.append(d)
        _, run = scripted(table[d])
        return evaluate(run, CFG)

    r = bracket(at, CFG, leverage=DoseEval(1.0, Eval(0, 4, "too_hard")), lo=0.875, hi=1.0)
    assert r.status == "accepted" and seen == [0.9375]
    seen.clear()
    bracket(at, CFG, leverage=DoseEval(1.0, Eval(0, 4, "too_hard")))  # no population data
    assert seen == [0.5]
    seen.clear()
    bracket(at, CFG, leverage=DoseEval(1.0, Eval(0, 4, "too_hard")), lo=0.9, hi=0.9)  # invalid
    assert seen == [0.5]


def _footer_like(lo: float, hi: float) -> tuple[str, int]:
    """A scripted family whose band lies in (0.875, 1.0]: too_easy (4/4) at every dose <= 0.875,
    in band at any dose strictly inside (0.875, 1), too_hard (0/4) at d = 1. Charged against the
    cap of 30 after a 10-rollout estimate; returns (status, rollouts spent)."""
    spent = {"n": 10}

    def charged_run(script: list[int]) -> Callable[[int], list[Trace]]:
        pos = [0]

        def run(n: int) -> list[Trace]:
            if spent["n"] + n > CFG.cap:
                raise BudgetExhausted(
                    "cap", budget="search", cap=CFG.cap, spent=spent["n"], task_id="t"
                )
            spent["n"] += n
            got = script[pos[0] : pos[0] + n]
            pos[0] += n
            return [_trace(bool(x)) for x in got]

        return run

    def at(d: float) -> Eval:
        if d <= 0.875:
            return evaluate(charged_run([1, 1, 1, 1]), CFG)
        if d >= 1.0:
            return evaluate(charged_run([0, 0, 0, 0]), CFG)
        return evaluate(charged_run([1, 0, 1, 0, 1, 1, 0, 0]), CFG)

    lev = at(1.0)  # the d = 1 leverage test always runs first (4 rollouts)
    r = bracket(at, CFG, leverage=DoseEval(1.0, lev), lo=lo, hi=hi)
    return r.status, spent["n"]


def test_population_seed_reaches_a_late_band_within_the_cap() -> None:
    """The E3 footer-mask case: seeded at [0.875, 1] the band is one bisection away
    (10 + 4 + 8 = 22 <= 30); seeded at [0, 1] the walk 0.5 -> 0.75 -> 0.875 exhausts the cap."""
    assert _footer_like(0.875, 1.0) == ("accepted", 22)
    status, spent = _footer_like(0.0, 1.0)
    # 10 + 4 + 4 + 4 + 4 = 26, then the first batch at 0.9375 fits (30) and its top-up cannot
    assert status == "budget" and spent == 30


def test_evaluate_tops_up_a_full_first_batch_on_the_stage_side() -> None:
    spent, run = scripted([1, 1, 1, 1, 1, 1, 1, 0])
    ev = evaluate(run, CFG, top_up_full=True)
    assert (ev.successes, ev.n, ev.verdict) == (7, 8, "too_easy") and spent[0] == 8
    spent, run = scripted([1, 1, 1, 1, 0, 1, 0, 0])
    ev = evaluate(run, CFG, top_up_full=True)
    assert (ev.successes, ev.n, ev.verdict) == (5, 8, "in_band") and spent[0] == 8
    spent, run = scripted([1, 1, 1, 1])  # harden side unchanged: 4/4 decides at 4
    ev = evaluate(run, CFG)
    assert (ev.successes, ev.n, ev.verdict) == (4, 4, "too_easy") and spent[0] == 4
    spent, run = scripted([0, 0, 0, 0])  # 0/4 still decides at 4 on both sides
    ev = evaluate(run, CFG, top_up_full=True)
    assert (ev.successes, ev.n, ev.verdict) == (0, 4, "too_hard") and spent[0] == 4


def test_cap_arithmetic_10_4_8_8() -> None:
    """After a 10-rollout estimate and a 4-rollout leverage test, the cap of 30 admits two full
    bisections (8 + 8); the third raises BudgetExhausted -> status budget."""
    spent = {"n": 14}
    # with the mixed script each bisection costs 8: 14 + 8 + 8 = 30, the third cannot start
    spent["n"] = 14
    calls: list[int] = []

    def at2(d: float) -> Eval:
        def run(n: int) -> list[Trace]:
            if spent["n"] + n > CFG.cap:
                raise BudgetExhausted(
                    "cap", budget="search", cap=CFG.cap, spent=spent["n"], task_id="t"
                )
            spent["n"] += n
            calls.append(n)
            return [
                _trace(x == 1) for x in ([1, 0, 0, 0] if n == 4 else [0, 0, 0, 0])
            ]  # 1/8 too_hard

        return evaluate(run, CFG)

    r = bracket(at2, CFG, leverage=DoseEval(1.0, Eval(0, 4, "too_hard")))
    assert r.status == "budget" and calls == [4, 4, 4, 4] and spent["n"] == 30
    assert [h.d for h in r.history] == [1.0, 0.5, 0.25]


def test_same_verdict_noise_is_not_an_order_violation() -> None:
    """6/8 vs 8/8 (both too easy) and 0/4 vs 2/8 (both too hard) are one batch's sampling noise."""
    tol = CFG.impl.order_tolerance
    assert tol == 0.375
    easy = [DoseEval(0.25, Eval(6, 8, "too_easy")), DoseEval(0.5, Eval(8, 8, "too_easy"))]
    hard = [DoseEval(1.0, Eval(2, 8, "too_hard")), DoseEval(0.5, Eval(0, 4, "too_hard"))]
    assert not order_violated(easy, tol) and not order_violated(hard, tol)
    assert order_violated(
        [DoseEval(0.25, Eval(0, 4, "too_hard")), DoseEval(0.5, Eval(7, 8, "too_easy"))], tol
    )


def test_order_violation_is_diagnostic_only() -> None:
    """A recorded violation never stops the bracket: the search runs to acceptance or exhaustion."""
    table = {0.5: [0, 0, 0, 0], 0.25: [1, 1, 1, 1], 0.375: [1, 0, 1, 0, 1, 1, 0, 0]}

    def at(d: float) -> Eval:
        _, run = scripted(table[d])
        return evaluate(run, CFG)

    r = bracket(at, CFG, leverage=DoseEval(1.0, Eval(2, 8, "too_hard")))
    assert r.status == "accepted" and r.accepted is not None and r.accepted.d == 0.375
    assert [h.d for h in r.history] == [1.0, 0.5, 0.25, 0.375]
    assert not r.order_violated  # a lower dose easier than a higher one is the expected order
