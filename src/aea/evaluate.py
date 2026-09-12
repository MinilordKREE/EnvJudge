"""The one acceptance rule (docs/spec/AEA_v0.3.md, "One acceptance rule").

``evaluate``: ``probe[0]`` policy rollouts; 0 of them -> ``too_hard``; all of them -> ``too_easy``
on the harden side (a cheaper next dose exists there) but, on a staged state
(``top_up_full=True``), topped up like a mixed batch; otherwise top up to ``probe[1]`` and read
the count: ``in_band`` iff it lies in ``accept`` (3-5 of 8), below -> ``too_hard``, above ->
``too_easy``. The harden loop reads ``too_easy`` at d = 1 as ``no_effect``. The caller's ``run``
charges the cap and raises ``BudgetExhausted`` when the next batch would exceed it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from envharness.core.types import Trace

from aea.config import AEAConfig

type Verdict = Literal["in_band", "too_easy", "too_hard"]

type RunFn = Callable[[int], list[Trace]]
"""Run ``n`` policy rollouts on the environment under evaluation (the caller charges the cap)."""


@dataclass
class Eval:
    successes: int
    n: int
    verdict: Verdict
    traces: list[Trace] = field(default_factory=list)

    @property
    def p_hat(self) -> float:
        return self.successes / self.n if self.n else 0.0


def verdict(successes: int, n: int, config: AEAConfig) -> Verdict:
    _, full = config.probe
    lo, hi = config.accept
    if n < full:  # the first batch decides only the extremes
        if successes == 0:
            return "too_hard"
        if successes == n:
            return "too_easy"
        raise ValueError("an in-between first batch must be topped up before a verdict")
    if lo <= successes <= hi:
        return "in_band"
    return "too_hard" if successes < lo else "too_easy"


def evaluate(run: RunFn, config: AEAConfig, *, top_up_full: bool = False) -> Eval:
    """``top_up_full``: a first batch of all successes is topped up too (the stage operator;
    P(p > 0.8 | 4/4) is only about 0.67, and no cheaper candidate follows on that side)."""
    first, full = config.probe
    traces = list(run(first))
    s = sum(int(bool(t.success)) for t in traces)
    if s == 0 or (s == len(traces) and not top_up_full):
        return Eval(s, len(traces), verdict(s, len(traces), config), traces)
    traces += list(run(full - first))
    s = sum(int(bool(t.success)) for t in traces)
    return Eval(s, len(traces), verdict(s, len(traces), config), traces)
