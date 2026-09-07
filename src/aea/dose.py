"""The unified acceptance rule, the leverage test and the sequential dose search (spec section 4).

Any dose, any source: 4 rollouts; 4/4 -> NOEFFECT; 0/4 -> ZERO; 1-3/4 -> top up to 8; accept iff
3-5/8 (B_T); 1-2/8 -> lower the dose; 6-7/8 -> raise it. The leverage test is the same rule at
d = 1: 4/4 -> change family; 0/4 -> search downward from d = 0.5; 3-5/8 -> accept d = 1. Step 0.25,
halved after each evaluation; at most ``max_dose_evals`` evaluations or the budget; non-monotone
responses are recorded, never corrected.

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


def next_dose(history: list[DoseEval], config: AEAConfig) -> float | None:
    """Direction from the last class; step 0.25 then halved per evaluation; None when the search
    ends."""
    if not history:
        return 1.0
    if len(history) >= config.max_dose_evals or history[-1].cls == "IN_BAND":
        return None
    last = history[-1]
    step = config.dose_step / (2 ** (len(history) - 1))
    proposal: float | None
    if last.cls in ("NOEFFECT", "LOW"):
        proposal = last.d + step if last.d < 1.0 else None
    elif last.cls in ("ZERO", "HIGH"):
        proposal = (
            0.5 if (len(history) == 1 and last.d == 1.0 and last.cls == "ZERO") else last.d - step
        )
    else:
        proposal = None
    if proposal is None:
        return None
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


def dose_search(run: BatchFn, config: AEAConfig) -> DoseSearchResult:
    """Leverage test at d = 1, then the sequential search. The caller's ``run`` charges the budget
    and raises ``BudgetExhausted`` when the per-task cap would be exceeded."""
    history: list[DoseEval] = []
    d: float | None = 1.0
    try:
        while d is not None:
            ev = evaluate_dose(d, run, config)
            history.append(ev)
            if ev.cls == "IN_BAND":
                return DoseSearchResult("accepted", history, ev, non_monotone_pairs(history))
            if len(history) == 1 and ev.cls == "NOEFFECT":
                return DoseSearchResult("no_leverage", history, None, 0)
            d = next_dose(history, config)
    except BudgetExhausted:
        return DoseSearchResult("budget_cap_hit", history, None, non_monotone_pairs(history))
    return DoseSearchResult("exhausted", history, None, non_monotone_pairs(history))
