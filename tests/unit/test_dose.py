from __future__ import annotations

import csv
import random
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import pytest
from envharness.core.types import Candidate, Trace

from aea.config import AEAConfig
from aea.dose import DoseEval, classify, dose_search, next_dose, non_monotone_pairs
from aea.errors import BudgetExhausted

CFG = AEAConfig()
P2B = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "pilots"
    / "e1pilot"
    / "results"
    / "e1pilot"
    / "p2b_curves.csv"
)


def _trace(success: bool) -> Trace:
    return Trace(
        episode_id="e", iteration_id="i", task_id="t", candidate=Candidate(), success=success
    )


def curve_runner(
    p_of_d: Callable[[float], float], seed: int = 1
) -> tuple[Callable[[float, int], list[Trace]], list[tuple[float, int]]]:
    rng = random.Random(seed)
    calls: list[tuple[float, int]] = []

    def run(d: float, n: int) -> list[Trace]:
        calls.append((d, n))
        return [_trace(rng.random() < p_of_d(d)) for _ in range(n)]

    return run, calls


def test_classify_matches_spec() -> None:
    assert classify(4, 4, CFG) == "NOEFFECT" and classify(0, 4, CFG) == "ZERO"
    with pytest.raises(ValueError):
        classify(2, 4, CFG)
    assert [classify(s, 8, CFG) for s in range(9)] == [
        "ZERO",
        "LOW",
        "LOW",
        "IN_BAND",
        "IN_BAND",
        "IN_BAND",
        "HIGH",
        "HIGH",
        "NOEFFECT",
    ]


def test_next_dose_directions_and_halving() -> None:
    assert next_dose([DoseEval(1.0, 8, 8, "NOEFFECT")], CFG) is None  # cannot raise above 1
    assert (
        next_dose([DoseEval(1.0, 0, 4, "ZERO")], CFG) == 0.5
    )  # 0/4 at d=1 -> search down from 0.5
    h = [DoseEval(1.0, 0, 4, "ZERO"), DoseEval(0.5, 7, 8, "HIGH")]
    assert next_dose(h, CFG) == 0.375  # step halves: 0.25 -> 0.125
    h.append(DoseEval(0.375, 1, 8, "LOW"))
    assert next_dose(h, CFG) == 0.4375
    h.append(DoseEval(0.4375, 4, 8, "IN_BAND"))
    assert next_dose(h, CFG) is None
    assert next_dose([DoseEval(1.0, 0, 4, "ZERO")] * 4, CFG) is None  # <= 4 evaluations


def test_cliff_curve_accepts_on_the_cliff() -> None:
    run, calls = curve_runner(lambda d: 1.0 if d < 0.45 else (0.5 if d < 0.55 else 0.0), seed=3)
    result = dose_search(run, CFG)
    assert (
        result.status == "accepted"
        and result.accepted is not None
        and 0.45 <= result.accepted.d < 0.55
    )
    assert [c[0] for c in calls][:3] == [1.0, 0.5, 0.5]  # leverage at 1 (0/4), then 0.5 topped up


def test_linear_curve_and_no_leverage() -> None:
    run, _ = curve_runner(lambda d: 1.0 - 0.6 * d, seed=5)
    result = dose_search(run, CFG)
    assert result.status in ("accepted", "exhausted") and len(result.history) <= 4
    run, calls = curve_runner(lambda d: 1.0, seed=7)
    result = dose_search(run, CFG)
    assert result.status == "no_leverage" and calls == [(1.0, 4)]


def test_non_monotone_is_recorded_not_corrected() -> None:
    h = [
        DoseEval(0.25, 0, 4, "ZERO"),
        DoseEval(0.5, 4, 4, "NOEFFECT"),
        DoseEval(1.0, 8, 8, "NOEFFECT"),
    ]
    assert non_monotone_pairs(h) == 2
    script = {1.0: [0, 0, 0, 0], 0.5: [1, 0, 0, 0, 1, 0, 0, 0], 0.625: [1, 1, 0, 0, 1, 1, 0, 1]}
    pos = {d: 0 for d in script}

    def run(d: float, n: int) -> list[Trace]:
        out = script[d][pos[d] : pos[d] + n]
        pos[d] += n
        return [_trace(bool(x)) for x in out]

    result = dose_search(
        run, CFG
    )  # 0/4 -> 2/8 LOW at 0.5 -> raise by 0.125 -> 5/8 IN_BAND at 0.625
    assert (
        result.status == "accepted" and result.accepted is not None and result.accepted.d == 0.625
    )
    assert (
        result.non_monotone == 1
    )  # p_hat(0.5)=0.25 < p_hat(0.625)=0.625: recorded, the acceptance stands


def test_budget_exhaustion_stops_the_search() -> None:
    spent = {"n": 0}

    def run(d: float, n: int) -> list[Trace]:
        if spent["n"] + n > 6:
            raise BudgetExhausted("cap", budget="search", cap=6, spent=spent["n"], task_id="t")
        spent["n"] += n
        return [_trace(i % 2 == 0) for i in range(n)]

    result = dose_search(run, CFG)
    assert result.status == "budget_cap_hit" and spent["n"] == 4


@pytest.mark.skipif(not P2B.exists(), reason="pilot fixture not present")
def test_p2b_fixture_classes_reproduce() -> None:
    """Replaying the recorded successes through the ported rule reproduces the recorded classes
    (the pilot labelled 2/8 and 6/8 NEAR and >6/8 NOEFFECT / <2/8 OVERSHOOT; mapped below)."""
    mapping = {
        "IN-BAND": "IN_BAND",
        "NEAR": {2: "LOW", 6: "HIGH"},
        "NOEFFECT": "NOEFFECT",
        "ZERO": "ZERO",
        "OVERSHOOT": "LOW",
    }
    with P2B.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    checked = 0
    for r in rows:
        n, s = int(r["rollouts"]), int(r["successes"])
        if n not in (4, 8):
            continue
        got = classify(s, n, CFG)
        expected = mapping[r["class"]]
        if isinstance(expected, dict):
            expected = expected[s]
        if r["class"] == "OVERSHOOT":
            expected = "LOW" if s in (1, 2) else ("ZERO" if s == 0 else "HIGH")
        if r["class"] == "NOEFFECT" and n == 8 and s == 7:
            expected = "HIGH"
        assert got == expected, (r, got)
        checked += 1
    assert checked >= 30
    by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_task[r["task_id"] + r["family"]].append(r)
    assert by_task
