"""Per-call attribution in a ``contextvars.ContextVar`` (thread-safe), exported to subprocess
workers as ``AEA_*`` environment variables (spec §0: every rollout charged to a named budget).

No reference source: written fresh for aea (docs/reuse/M0.md). The parent process never writes
``os.environ``: the released orchestrator runs episodes concurrently in threads
(``orchestrator.py:986-1046``), so process-global variables would race and mis-charge the
per-task cap. ``SubprocessRunner._child_env`` (``runner.py:397-419``) is the single place a
child's environment is built; :class:`aea.runner.AeaSubprocessRunner` overrides it to read this
context.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import cast

from aea.llm.types import Attribution, BudgetName

_ATTRIBUTION: ContextVar[tuple[Attribution, int] | None] = ContextVar(
    "aea_attribution", default=None
)

ENV_KEYS = ("AEA_PHASE", "AEA_BUDGET", "AEA_ARM", "AEA_TASK_ID", "AEA_SEED", "AEA_RUN_ID")


@contextmanager
def attributed(attribution: Attribution, seed: int) -> Iterator[None]:
    """Bind an attribution for the calling thread/task; nested bindings restore on exit."""
    token = _ATTRIBUTION.set((attribution, seed))
    try:
        yield
    finally:
        _ATTRIBUTION.reset(token)


def bound_attribution() -> tuple[Attribution, int] | None:
    """The contextvar binding only (None when unbound), without the environment fallback."""
    return _ATTRIBUTION.get()


def current_attribution() -> tuple[Attribution, int]:
    """The bound attribution, else the ``AEA_*`` variables of this process (a subprocess worker)."""
    bound = _ATTRIBUTION.get()
    if bound is not None:
        return bound
    budget = cast(BudgetName, os.environ.get("AEA_BUDGET", "none"))
    return (
        Attribution(
            phase=os.environ.get("AEA_PHASE", "none"),
            budget=budget,
            arm=os.environ.get("AEA_ARM", "none"),
            task_id=os.environ.get("AEA_TASK_ID", "none"),
        ),
        int(os.environ.get("AEA_SEED", "0") or 0),
    )


def child_environment(run_id: str) -> dict[str, str]:
    """The ``AEA_*`` variables a subprocess worker needs to reproduce the bound attribution."""
    attribution, seed = current_attribution()
    return {
        "AEA_PHASE": attribution.phase,
        "AEA_BUDGET": attribution.budget,
        "AEA_ARM": attribution.arm,
        "AEA_TASK_ID": attribution.task_id,
        "AEA_SEED": str(seed),
        "AEA_RUN_ID": run_id,
    }
