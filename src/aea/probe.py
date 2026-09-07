"""Learnability probes over staged candidates (spec section 5).

Latest-first; ``probe_k`` (4) policy rollouts per candidate, charged to ``search``: 1-3/4 -> accept
this Stage (the latest learnable) and stop; 0/4 -> next earlier; 4/4 -> ``too_easy_stage``
(recorded, not accepted by the main method) and continue earlier. All candidates non-learnable ->
``unresolved``. Pilot oracle: docs/pilots/e1pilot/p5/p5/chs100.py (``probe``); the P5.1 profiles
(``docs/pilots/e1pilot/p5/results/chs_profile.csv``) are the fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from envharness.core.types import Trace

from aea.config import AEAConfig
from aea.errors import BudgetExhausted
from aea.stage import StagedCandidate

type ProbeClass = Literal["dead", "learnable", "too_easy_stage"]
type ProbeRun = Callable[[StagedCandidate, int], list[Trace]]
"""Run ``n`` policy rollouts on the staged candidate (charged to search by the caller)."""


@dataclass
class ProbeEval:
    candidate: StagedCandidate
    successes: int
    n: int
    cls: ProbeClass
    traces: list[Trace] = field(default_factory=list)

    @property
    def p_hat(self) -> float:
        return self.successes / self.n if self.n else 0.0


@dataclass
class ProbeResult:
    status: Literal["accepted", "unresolved", "budget_cap_hit", "no_candidate"]
    profile: list[ProbeEval] = field(default_factory=list)
    accepted: ProbeEval | None = None
    too_easy: list[ProbeEval] = field(default_factory=list)


def classify(successes: int, n: int) -> ProbeClass:
    if successes == 0:
        return "dead"
    if successes == n:
        return "too_easy_stage"
    return "learnable"


def probe(candidates: list[StagedCandidate], run: ProbeRun, config: AEAConfig) -> ProbeResult:
    """Walk the certified candidates latest-first; stop at the first learnable one."""
    if not candidates:
        return ProbeResult("no_candidate")
    ordered = sorted(candidates, key=lambda c: -c.t)
    result = ProbeResult("unresolved")
    try:
        for cand in ordered:
            traces = run(cand, config.probe_k)
            s = sum(int(bool(t.success)) for t in traces)
            ev = ProbeEval(cand, s, len(traces), classify(s, len(traces)), traces)
            result.profile.append(ev)
            if ev.cls == "learnable":
                result.status = "accepted"
                result.accepted = ev
                return result
            if ev.cls == "too_easy_stage":
                result.too_easy.append(ev)
    except BudgetExhausted:
        result.status = "budget_cap_hit"
    return result
