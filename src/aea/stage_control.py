"""LOW Stage control (docs/design/AEA_LOW_STAGE_CONTROL.md): the integer bracket over the depth
of a verified reference prefix, the LOW mirror of the HIGH dose bracket (``aea.bracket``).

The family is E_t = Stage(a_1 .. a_t) of one verified successful reference; the actuator is the
integer depth t in 1..t_max (t_max = the deepest non-terminal, exactly reproducible prefix,
found simulator-side and never charged). The first probe is maximum assistance t_max (the LOW
analogue of d = 1 first). Every probe is the existing 4 -> 8 measurement (``aea.evaluate``);
too_hard raises lo, too_easy lowers hi, in_band accepts; the next depth is floor((lo + hi) / 2);
a depth is never probed twice; hi - lo == 1 without an in-band point is ``resolution_limited``;
a measured too_easy depth below a measured too_hard depth is ``nonmonotonic_profile`` (a
structural invariant under the bracket, kept as a stated check). Reference progress is treated
as an EMPIRICALLY ordered assistance axis (phase 3.3a); no monotonicity is assumed or claimed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from aea.errors import BudgetExhausted
from aea.evaluate import Eval

type Status = Literal[
    "accepted",
    "no_stage_leverage",
    "resolution_limited",
    "nonmonotonic_profile",
    "budget",
    "invalid_stage",
]


class InvalidStageError(Exception):
    """The chosen depth does not compile exactly or fails the existing guard."""


@dataclass
class DepthEval:
    t: int
    eval: Eval


@dataclass
class StageControlResult:
    status: Status
    history: list[DepthEval] = field(default_factory=list)
    accepted: DepthEval | None = None
    lo: int = 0
    hi: int | None = None

    @property
    def unique_cuts(self) -> int:
        return len({h.t for h in self.history})


def ordering_contradiction(history: list[DepthEval]) -> bool:
    """t1 < t2 with t1 too_easy and t2 too_hard: the discrete ordering contradiction."""
    for a in history:
        for b in history:
            if a.t < b.t and a.eval.verdict == "too_easy" and b.eval.verdict == "too_hard":
                return True
    return False


def stage_bracket(evaluate_at: Callable[[int], Eval], t_max: int) -> StageControlResult:
    """Maximum assistance first, then inward discrete refinement (see the module docstring).
    ``evaluate_at`` runs the charged 4 -> 8 measurement at a depth; it may raise
    :class:`aea.errors.BudgetExhausted` or :class:`InvalidStageError`."""
    res = StageControlResult("resolution_limited", lo=0, hi=None)
    measured: set[int] = set()
    t = t_max
    while True:
        if t in measured:  # never probe a depth twice (unreachable under the update rule)
            res.status = "resolution_limited"
            return res
        try:
            ev = DepthEval(t, evaluate_at(t))
        except BudgetExhausted:
            res.status = "budget"
            return res
        except InvalidStageError:
            res.status = "invalid_stage"
            return res
        res.history.append(ev)
        measured.add(t)
        if ordering_contradiction(res.history):
            res.status = "nonmonotonic_profile"
            return res
        if ev.eval.verdict == "in_band":
            res.status, res.accepted = "accepted", ev
            return res
        if ev.eval.verdict == "too_hard":
            if res.hi is None:  # maximum assistance is still inaccessible
                res.status = "no_stage_leverage"
                return res
            res.lo = t
        else:  # too_easy
            res.hi = t
        assert res.hi is not None
        if res.hi - res.lo <= 1:
            res.status = "resolution_limited"
            return res
        t = (res.lo + res.hi) // 2
