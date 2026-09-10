"""Dose bracketing for the harden operator (docs/spec/AEA_v0.2.md, "Families and leverage").

The d = 1 leverage test is always run by the caller. ``bracket``: ``lo`` = the largest dose known
too easy (starts at 0), ``hi`` = the smallest dose known too hard (starts at 1, the failed leverage
test); each bisection evaluates one dose with the 4 -> 8 rule: ``too_easy`` -> lo = d,
``too_hard`` -> hi = d, ``in_band`` -> accept. The first dose is the midpoint or, when the family's
prior applies, its last accepted dose (clipped into the open bracket). At most
``impl.max_bisections``; an order violation (a higher dose with a success rate more than
``impl.order_tolerance`` above a lower dose's) stops the family for this task. The cap arithmetic
10 + 4 + 8 + 8 = 30 leaves at most two bisections after a full leverage test.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from aea.config import AEAConfig
from aea.errors import BudgetExhausted
from aea.evaluate import Eval

type EvalAt = Callable[[float], Eval]
"""Evaluate the family at dose d (the caller charges the cap and raises BudgetExhausted)."""


@dataclass
class DoseEval:
    d: float
    eval: Eval


@dataclass
class BracketResult:
    status: Literal["accepted", "exhausted", "order_violation", "budget"]
    history: list[DoseEval] = field(default_factory=list)
    accepted: DoseEval | None = None


def order_violated(history: list[DoseEval], tolerance: float) -> bool:
    """A harder dose measurably easier than an easier one."""
    for a in history:
        for b in history:
            if b.d > a.d and b.eval.p_hat > a.eval.p_hat + tolerance:
                return True
    return False


def bracket(
    evaluate_at: EvalAt,
    config: AEAConfig,
    *,
    leverage: DoseEval,
    start: float | None = None,
) -> BracketResult:
    """Bisect on [0, 1] after a failed (``too_hard``) leverage test at d = 1."""
    history = [leverage]
    lo, hi = 0.0, 1.0
    d = start if start is not None and lo < start < hi else 0.5
    try:
        for _ in range(config.impl.max_bisections):
            ev = DoseEval(round(d, 6), evaluate_at(round(d, 6)))
            history.append(ev)
            if ev.eval.verdict == "in_band":
                return BracketResult("accepted", history, ev)
            if order_violated(history, config.impl.order_tolerance):
                return BracketResult("order_violation", history)
            if ev.eval.verdict == "too_easy":
                lo = ev.d
            else:
                hi = ev.d
            d = (lo + hi) / 2
    except BudgetExhausted:
        return BracketResult("budget", history)
    return BracketResult("exhausted", history)
