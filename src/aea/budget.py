"""Named rollout budgets and the per-task hard cap (spec section 0).

``search`` is capped at ``search_cap`` policy rollouts per task per round and is the only budget
the controller spends; ``confirm`` (K16, never changes controller output) and ``train`` are
separate ledgers that never touch it. No cross-task reallocation: a task that hits the cap stops
with status ``budget_cap_hit`` (``BudgetExhausted``). Designer calls, expert sessions and verbatim
replays are recorded but not charged. No reference source: written fresh for aea.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field

from aea.errors import BudgetExhausted
from aea.llm.types import BudgetName

type Phase = str


@dataclass
class TaskAccount:
    task_id: str
    round_index: int
    cap: int
    charged: dict[BudgetName, int] = field(default_factory=lambda: defaultdict(int))
    by_phase: dict[tuple[BudgetName, Phase], int] = field(default_factory=lambda: defaultdict(int))
    infra_errors: int = 0
    """Rollouts that ended in an environment/infrastructure error: refunded, never counted."""
    status: str = "open"

    @property
    def search_spent(self) -> int:
        return self.charged["search"]

    def remaining(self) -> int:
        return max(self.cap - self.search_spent, 0)


class Budget:
    """Thread-safe accounting for one run: charge rollouts by (task, round, budget, phase)."""

    def __init__(self, search_cap: int) -> None:
        self.search_cap = search_cap
        self._accounts: dict[tuple[str, int], TaskAccount] = {}
        self._lock = threading.Lock()

    def account(self, task_id: str, round_index: int = 0) -> TaskAccount:
        key = (task_id, round_index)
        with self._lock:
            if key not in self._accounts:
                self._accounts[key] = TaskAccount(task_id, round_index, self.search_cap)
            return self._accounts[key]

    def can_afford(self, task_id: str, n: int, *, round_index: int = 0) -> bool:
        return self.account(task_id, round_index).remaining() >= n

    def charge(
        self, task_id: str, n: int, *, budget: BudgetName, phase: Phase, round_index: int = 0
    ) -> TaskAccount:
        """Charge ``n`` rollouts; on ``search`` the cap is a hard stop (nothing charged past it)."""
        if n < 0:
            raise ValueError("cannot charge a negative number of rollouts")
        acct = self.account(task_id, round_index)
        with self._lock:
            if budget == "search" and acct.search_spent + n > acct.cap:
                acct.status = "budget_cap_hit"
                raise BudgetExhausted(
                    f"task {task_id}: search cap {acct.cap} would be exceeded "
                    f"({acct.search_spent} spent, {n} requested)",
                    budget="search",
                    cap=acct.cap,
                    spent=acct.search_spent,
                    task_id=task_id,
                )
            acct.charged[budget] += n
            acct.by_phase[(budget, phase)] += n
        return acct

    def refund(
        self, task_id: str, n: int, *, budget: BudgetName, phase: Phase, round_index: int = 0
    ) -> TaskAccount:
        """Give back ``n`` rollouts that errored (spec section 2: errors are never counted) and
        count them as infrastructure errors in the accounting."""
        acct = self.account(task_id, round_index)
        with self._lock:
            acct.charged[budget] = max(acct.charged[budget] - n, 0)
            acct.by_phase[(budget, phase)] = max(acct.by_phase[(budget, phase)] - n, 0)
            acct.infra_errors += n
        return acct

    def accounting_rows(self) -> list[dict[str, object]]:
        """One row per (task, round, budget, phase) for ``accounting.csv``."""
        rows: list[dict[str, object]] = []
        with self._lock:
            for (task_id, round_index), acct in sorted(self._accounts.items()):
                for (budget, phase), n in sorted(acct.by_phase.items()):
                    rows.append(
                        {
                            "task_id": task_id,
                            "round": round_index,
                            "budget": budget,
                            "phase": phase,
                            "rollouts": n,
                            "search_total": acct.search_spent,
                            "cap": acct.cap,
                            "infra_errors": acct.infra_errors,
                            "status": acct.status,
                        }
                    )
        return rows

    def totals(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        with self._lock:
            for acct in self._accounts.values():
                for budget, n in acct.charged.items():
                    out[budget] += n
        return dict(out)
