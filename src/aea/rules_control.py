"""LOW assistive-Rules dose control (docs/design/AEA_LOW_ASSISTIVE_RULES.md): the mirrored copy
of the HIGH dose bracket (``aea.bracket``) for a family that gets EASIER with the dose.

The family is an LLM-generated assistive ``Rules`` template W(d), d in [0, 1], with W(0) = the
original environment. The first probe is d = 1 (maximum assistance, the LOW philosophy). The
caller has already measured d = 1: too_hard there means the family has no leverage (no bracket);
in_band accepts; too_easy opens the bracket lo = 0 (the estimate's reset, known inaccessible),
hi = 1 and bisects with the same 4 -> 8 measurement, at most ``impl.max_bisections`` times:
too_hard raises lo, too_easy lowers hi, in_band accepts. The verdict-to-bound mapping is the
HIGH bracket's mirror image; everything else (batches, verdicts, budget, cap) is shared.

Direction is not trusted because the designer declared it: a measured too_easy dose below a
measured too_hard dose is a ``dose_order_violation`` and stops the family (nothing is repaired).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from aea.bracket import DoseEval, EvalAt
from aea.config import AEAConfig
from aea.errors import BudgetExhausted

type AssistStatus = Literal["accepted", "exhausted", "budget", "dose_order_violation"]


@dataclass
class AssistResult:
    status: AssistStatus
    history: list[DoseEval] = field(default_factory=list)
    accepted: DoseEval | None = None
    lo: float = 0.0
    hi: float = 1.0


def dose_order_violation(history: list[DoseEval]) -> bool:
    """A lower dose empirically easier than a higher dose, in the discrete verdict classes."""
    for a in history:
        for b in history:
            if a.d < b.d and a.eval.verdict == "too_easy" and b.eval.verdict == "too_hard":
                return True
    return False


def assist_bracket(evaluate_at: EvalAt, config: AEAConfig, *, leverage: DoseEval) -> AssistResult:
    """Bisect [0, 1] inward after a ``too_easy`` at d = 1 (``leverage``); see the module
    docstring. ``evaluate_at`` runs the charged 4 -> 8 measurement at a dose."""
    res = AssistResult("exhausted", [leverage], lo=0.0, hi=1.0)
    d = 0.5
    try:
        for _ in range(config.impl.max_bisections):
            ev = DoseEval(round(d, 6), evaluate_at(round(d, 6)))
            res.history.append(ev)
            if dose_order_violation(res.history):
                res.status = "dose_order_violation"
                return res
            if ev.eval.verdict == "in_band":
                res.status, res.accepted = "accepted", ev
                return res
            if ev.eval.verdict == "too_hard":
                res.lo = ev.d
            else:
                res.hi = ev.d
            d = (res.lo + res.hi) / 2
    except BudgetExhausted:
        res.status = "budget"
        return res
    return res
