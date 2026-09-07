"""Exception families for aea.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/errors.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; ``BudgetExhausted`` carries the budget name (``search`` / ``confirm`` /
``train`` / ``probe_cert``) and the task id so the controller can record ``budget_cap_hit``.

Two runtime families that are never conflated and are counted separately in ledgers:

* :class:`InfraError` -- the infrastructure failed us: provider 429/5xx, network errors,
  timeouts, missing or corrupt files, a dead ALFWorld engine.
* :class:`TaskFailure` -- the policy or the environment failed the task. :class:`BudgetExhausted`
  is a task-level outcome (part of the estimand), never an infrastructure fault.

:class:`ConfigError` is raised before a run starts (bad config, dirty tree, invalid CLI usage).
"""

from __future__ import annotations


class AeaError(Exception):
    """Base class for all aea exceptions."""


class InfraError(AeaError):
    """Infrastructure failure: provider errors, network, timeouts, missing files."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "infra",
        status_code: int | None = None,
        retryable: bool = False,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable
        self.attempts = attempts

    def __str__(self) -> str:
        base = super().__str__()
        status = f", status={self.status_code}" if self.status_code is not None else ""
        return f"[{self.kind}{status}, attempts={self.attempts}] {base}"


class TaskFailure(AeaError):  # noqa: N818 - name mandated by docs/CONVENTIONS.md
    """The policy or the harness failed the task. Never raised for infrastructure problems."""

    def __init__(self, message: str, *, kind: str = "task_failure") -> None:
        super().__init__(message)
        self.kind = kind


class BudgetExhausted(TaskFailure):
    """A named rollout budget ran out before the task finished (status ``budget_cap_hit``)."""

    def __init__(
        self, message: str, *, budget: str, cap: int, spent: int, task_id: str = ""
    ) -> None:
        super().__init__(message, kind="budget_exhausted")
        self.budget = budget
        self.cap = cap
        self.spent = spent
        self.task_id = task_id


class ConfigError(AeaError):
    """Invalid configuration or refused start (for example a dirty tree on a confirmatory run)."""
