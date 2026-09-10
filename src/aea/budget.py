"""The one budget (docs/spec/AEA_v0.2.md, "One budget"): every policy rollout of a task is charged
to ``search`` before it runs; the cap is a hard stop. Errored rollouts are refunded and counted as
infra errors. Confirmations (``eval``) are outside the method and never touch this object.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from aea.errors import BudgetExhausted


@dataclass
class TaskAccount:
    task_id: str
    cap: int
    charged: dict[str, int] = field(default_factory=dict)
    refunded: dict[str, int] = field(default_factory=dict)
    infra_errors: int = 0

    @property
    def spent(self) -> int:
        return sum(self.charged.values()) - sum(self.refunded.values())

    def remaining(self) -> int:
        return max(self.cap - self.spent, 0)


class Budget:
    def __init__(self, cap: int) -> None:
        self.cap = cap
        self._accounts: dict[str, TaskAccount] = {}
        self._lock = threading.Lock()

    def account(self, task_id: str) -> TaskAccount:
        with self._lock:
            return self._accounts.setdefault(task_id, TaskAccount(task_id, self.cap))

    def can_afford(self, task_id: str, n: int) -> bool:
        return self.account(task_id).spent + n <= self.cap

    def charge(self, task_id: str, n: int, *, phase: str) -> None:
        acc = self.account(task_id)
        with self._lock:
            if acc.spent + n > self.cap:
                raise BudgetExhausted(
                    f"cap {self.cap} would be exceeded by {n} rollouts",
                    budget="search",
                    cap=self.cap,
                    spent=acc.spent,
                    task_id=task_id,
                )
            acc.charged[phase] = acc.charged.get(phase, 0) + n

    def refund(self, task_id: str, n: int, *, phase: str) -> None:
        acc = self.account(task_id)
        with self._lock:
            acc.refunded[phase] = acc.refunded.get(phase, 0) + n
            acc.infra_errors += n

    def accounting_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        with self._lock:
            for acc in self._accounts.values():
                for phase, n in sorted(acc.charged.items()):
                    rows.append(
                        {
                            "task_id": acc.task_id,
                            "budget": "search",
                            "phase": phase,
                            "n": n - acc.refunded.get(phase, 0),
                            "refunded": acc.refunded.get(phase, 0),
                        }
                    )
        return rows

    def totals(self) -> dict[str, int]:
        with self._lock:
            return {t: a.spent for t, a in self._accounts.items()}
