"""Cross-task family priors for the A' arm (PREREG7 Amendment 3, A3.3).

Within one round, every family (exemplar or designer proposal, keyed by name) accumulates:
the doses at which it was accepted, how often its d = 1 leverage test returned ZERO, and how often
it showed no leverage (NOEFFECT / HIGH at d = 1). The controller consults the priors per task:

- start dose = median of the family's accepted doses so far (0.5 before any acceptance);
- the d = 1 leverage test is skipped once the family returned ZERO at d = 1 on >= ``skip_after``
  tasks (leverage assumed; the search starts at the start dose);
- a family with no leverage on >= ``demote_after`` tasks is moved to the end of the order.

Everything else (dose contract, acceptance rule, cap, certificates) is the A controller's. The
priors are shared across concurrently running tasks (a lock guards the counters), so "so far" is
in completion order. Provenance: docs/reuse/controller.md; no reference source.
"""

from __future__ import annotations

import statistics
import threading
from dataclasses import dataclass, field

from aea.dose import DoseSearchResult


@dataclass
class FamilyStats:
    accepted_doses: list[float] = field(default_factory=list)
    zero_at_d1: int = 0
    no_leverage: int = 0
    tasks_seen: int = 0


class FamilyPriors:
    def __init__(self, *, skip_after: int = 5, demote_after: int = 5, initial: float = 0.5) -> None:
        self.skip_after = skip_after
        self.demote_after = demote_after
        self.initial = initial
        self._stats: dict[str, FamilyStats] = {}
        self._lock = threading.Lock()

    def stats(self, family: str) -> FamilyStats:
        with self._lock:
            return self._stats.setdefault(family, FamilyStats())

    def start_dose(self, family: str) -> float:
        s = self.stats(family)
        with self._lock:
            return float(statistics.median(s.accepted_doses)) if s.accepted_doses else self.initial

    def skip_leverage(self, family: str) -> bool:
        with self._lock:
            return self._stats.get(family, FamilyStats()).zero_at_d1 >= self.skip_after

    def demoted(self, family: str) -> bool:
        with self._lock:
            return self._stats.get(family, FamilyStats()).no_leverage >= self.demote_after

    def record(self, family: str, result: DoseSearchResult, *, leverage_tested: bool) -> None:
        s = self.stats(family)
        with self._lock:
            s.tasks_seen += 1
            if leverage_tested and result.history and result.history[0].d == 1.0:
                first = result.history[0]
                if first.cls == "ZERO":
                    s.zero_at_d1 += 1
            if result.status == "no_leverage":
                s.no_leverage += 1
            if result.status == "accepted" and result.accepted is not None:
                s.accepted_doses.append(result.accepted.d)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                k: {
                    "accepted_doses": list(v.accepted_doses),
                    "zero_at_d1": v.zero_at_d1,
                    "no_leverage": v.no_leverage,
                    "tasks_seen": v.tasks_seen,
                }
                for k, v in self._stats.items()
            }
