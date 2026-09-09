"""The unified acceptance rule, the leverage test and the sequential dose search (spec section 4).

Any dose, any source: 4 rollouts; 4/4 -> NOEFFECT; 0/4 -> ZERO; 1-3/4 -> top up to 8; accept iff
3-5/8 (B_T); 1-2/8 (too hard) -> lower the dose; 6-7/8 (too easy) -> raise it. The leverage test
is the same rule at d = 1: 4/4 or 6-7/8 -> change family; 0/4 -> search from d = 0.5; 1-2/8 ->
search from 0.75; 3-5/8 -> accept d = 1. Step 0.25, halved after each SEARCH evaluation (the
leverage test is not counted): 0.5 -> 0.75 -> 0.875 -> 0.9375; at most ``max_dose_evals`` search
evaluations or the budget; non-monotone responses are recorded, never corrected.

Pilot oracle: docs/pilots/e1pilot/e1/controller.py (``classify_after4`` / ``classify8``),
lam_search.py (``next_lambda``), p2b_run.py (``run_dose``); fixture
docs/pilots/e1pilot/results/e1pilot/p2b_curves.csv. No reference source copied.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from envharness.core.types import Trace

from aea.config import AEAConfig
from aea.errors import BudgetExhausted

type DoseClass = Literal["NOEFFECT", "ZERO", "IN_BAND", "LOW", "HIGH"]

type BatchFn = Callable[[float, int], list[Trace]]
"""Run ``n`` rollouts at dose ``d`` (charged to search by the caller); returns their traces."""


def classify(successes: int, n: int, config: AEAConfig) -> DoseClass:
    """section 4 classes. At n = k_first only the two extremes are decided; otherwise the 8-rollout
    classes."""
    if n == config.dose_k_first:
        if successes == n:
            return "NOEFFECT"
        if successes == 0:
            return "ZERO"
        raise ValueError("an in-between 4-rollout result must be topped up before classification")
    lo, hi = config.accept_range()
    if lo <= successes <= hi:
        return "IN_BAND"
    if successes < lo:
        return "ZERO" if successes == 0 else "LOW"
    return "NOEFFECT" if successes == n else "HIGH"


@dataclass
class DoseEval:
    d: float
    successes: int
    n: int
    cls: DoseClass
    traces: list[Trace] = field(default_factory=list)

    @property
    def p_hat(self) -> float:
        """The empirical rate s/n (not the posterior mean); the classes are defined on counts."""
        return self.successes / self.n if self.n else 0.0


def evaluate_dose(d: float, run: BatchFn, config: AEAConfig) -> DoseEval:
    """4 rollouts, then 4 more unless the first batch was 0/4 or 4/4."""
    first = run(d, config.dose_k_first)
    s = sum(int(bool(t.success)) for t in first)
    if s in (0, config.dose_k_first):
        return DoseEval(
            d, s, config.dose_k_first, classify(s, config.dose_k_first, config), list(first)
        )
    more = run(d, config.dose_k_full - config.dose_k_first)
    traces = [*first, *more]
    s = sum(int(bool(t.success)) for t in traces)
    return DoseEval(d, s, config.dose_k_full, classify(s, config.dose_k_full, config), traces)


def next_dose(
    history: list[DoseEval], config: AEAConfig, *, leverage_tested: bool = True
) -> float | None:
    """The next dose after ``history`` (leverage test at d = 1 first, then the search).

    Direction: NOEFFECT / HIGH (too easy) -> raise; ZERO / LOW (too hard) -> lower. After the
    leverage test the search starts at the midpoint (0/4 at d = 1 -> 0.5; LOW at d = 1 -> 0.75)
    with step ``dose_step``, halved after every SEARCH evaluation (the leverage test is not
    counted):
    0.5 -> 0.75 -> 0.875 -> 0.9375. At most ``max_dose_evals`` search evaluations; ``None`` ends the
    search."""
    if not history:
        return 1.0 if leverage_tested else None  # a skipped leverage test starts at the prior
    last = history[-1]
    if last.cls == "IN_BAND":
        return None
    # evaluations after the leverage test; with the test skipped (A3.3) every evaluation is search
    searched = len(history) - 1 if leverage_tested else len(history)
    if leverage_tested and searched == 0:  # the leverage test at d = 1 decides the start
        if last.cls == "ZERO":
            return 0.5
        if last.cls == "LOW":
            return round(1.0 - config.dose_step, 6)
        return None  # NOEFFECT / HIGH at d = 1: the family has no leverage here
    if searched >= config.max_dose_evals:
        return None
    step = config.dose_step / (2 ** (searched - 1))
    proposal = last.d + step if last.cls in ("NOEFFECT", "HIGH") else last.d - step
    clipped: float = round(min(max(proposal, 0.0), 1.0), 6)
    if any(abs(clipped - h.d) < 1e-9 for h in history) or clipped <= 0.0:
        return None
    return clipped


def non_monotone_pairs(history: list[DoseEval]) -> int:
    """Pairs (d_a < d_b) whose success rate RISES with the dose — logged, never corrected."""
    count = 0
    for a in history:
        for b in history:
            if a.d < b.d and a.p_hat < b.p_hat:
                count += 1
    return count


@dataclass
class DoseSearchResult:
    status: Literal["accepted", "no_leverage", "exhausted", "budget_cap_hit"]
    history: list[DoseEval]
    accepted: DoseEval | None = None
    non_monotone: int = 0


def dose_search(run: BatchFn, config: AEAConfig, *, start: float | None = None) -> DoseSearchResult:
    """Leverage test at d = 1, then the sequential search. The caller's ``run`` charges the budget
    and raises ``BudgetExhausted`` when the per-task cap would be exceeded. ``start`` (A3.3 prior)
    skips the leverage test: leverage is assumed and the search begins at ``start`` with the same
    halving schedule."""
    history: list[DoseEval] = []
    leverage_tested = start is None
    d: float | None = 1.0 if start is None else start
    try:
        while d is not None:
            ev = evaluate_dose(d, run, config)
            history.append(ev)
            if ev.cls == "IN_BAND":
                return DoseSearchResult("accepted", history, ev, non_monotone_pairs(history))
            if leverage_tested and len(history) == 1 and ev.cls in ("NOEFFECT", "HIGH"):
                return DoseSearchResult("no_leverage", history, None, 0)
            d = next_dose(history, config, leverage_tested=leverage_tested)
    except BudgetExhausted:
        return DoseSearchResult("budget_cap_hit", history, None, non_monotone_pairs(history))
    return DoseSearchResult("exhausted", history, None, non_monotone_pairs(history))
