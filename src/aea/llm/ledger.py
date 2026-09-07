"""Append-only JSONL cost ledger, one row per LLM call, policy rollout or infra/task event.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/llm/ledger.py (``LedgerRow``, ``Ledger``, ``read_ledger``, ``summarize``)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; row schema restarted at v1 with the columns the AEA prompt requires
(``run_id, phase, budget, arm, task_id, seed, model, provider, prompt_tokens,
completion_tokens, cached_tokens, latency_ms, usd, pricing_version, upstream_cost``); the
``rollout`` event charges one policy episode to a named budget; web-search rows are dropped.

Event kinds are counted separately by :func:`summarize`: ``call``, ``rollout``,
``infra_retry``, ``infra_failure``, ``task_failure`` (with ``error_kind == budget_exhausted``
counted on its own). Infra and task rows are never merged.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from aea.core.config import StrictModel
from aea.core.io import append_jsonl, read_jsonl
from aea.errors import InfraError, TaskFailure
from aea.llm.pricing import CostBreakdown, PricingTier
from aea.llm.types import Attribution, BudgetName, ChatRequest, ChatResponse, Usage

LEDGER_SCHEMA_VERSION = 1
LEDGER_FILENAME = "ledger.jsonl"
BUDGET_EXHAUSTED_KIND = "budget_exhausted"

type LedgerEvent = Literal["call", "rollout", "infra_retry", "infra_failure", "task_failure"]


class LedgerRow(StrictModel):
    schema_version: int
    ts: datetime
    run_id: str
    event: LedgerEvent
    phase: str
    budget: BudgetName
    arm: str
    task_id: str
    seed: int
    model: str
    provider: str | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0.0)
    pricing_version: str | None = None
    pricing_tier: PricingTier | None = None
    upstream_cost: float | None = None
    attempt: int | None = None
    status_code: int | None = None
    error_kind: str | None = None
    error: str | None = None
    request_sha256: str | None = None
    rollout_uid: str | None = None
    steps: int | None = None
    success: bool | None = None


class LedgerSummary(StrictModel):
    calls: int = 0
    rollouts: int = 0
    infra_retries: int = 0
    infra_failures: int = 0
    task_failures: int = 0
    budget_exhausted: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd: float = 0.0
    rollouts_by_budget: dict[str, int] = {}
    usd_by_budget: dict[str, float] = {}


class Ledger:
    """Writes rows for one run. Each append opens, writes one line and closes (crash-safe)."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._lock = threading.Lock()

    def append(self, row: LedgerRow) -> None:
        with self._lock:
            append_jsonl(self.path, row.model_dump(mode="json"))

    def _fields(
        self, *, event: LedgerEvent, attribution: Attribution, seed: int, model: str
    ) -> dict[str, object]:
        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "ts": datetime.now(UTC),
            "run_id": self.run_id,
            "event": event,
            "phase": attribution.phase,
            "budget": attribution.budget,
            "arm": attribution.arm,
            "task_id": attribution.task_id,
            "seed": seed,
            "model": model,
        }

    def _base(self, request: ChatRequest, event: LedgerEvent) -> dict[str, object]:
        return self._fields(
            event=event, attribution=request.attribution, seed=request.seed, model=request.model
        )

    def record_call(
        self, request: ChatRequest, response: ChatResponse, *, cost: CostBreakdown, attempt: int
    ) -> LedgerRow:
        row = LedgerRow.model_validate(
            {
                **self._base(request, "call"),
                "provider": response.provider,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "cached_tokens": response.usage.cached_tokens,
                "reasoning_tokens": response.usage.reasoning_tokens,
                "latency_ms": response.latency_ms,
                "usd": cost.usd,
                "pricing_version": cost.pricing_version,
                "pricing_tier": cost.tier,
                "upstream_cost": response.upstream_cost,
                "attempt": attempt,
                "request_sha256": response.request_sha256,
            }
        )
        self.append(row)
        return row

    def record_infra_retry(
        self,
        request: ChatRequest,
        *,
        attempt: int,
        kind: str,
        status_code: int | None,
        error: str,
        request_sha256: str,
    ) -> LedgerRow:
        row = LedgerRow.model_validate(
            {
                **self._base(request, "infra_retry"),
                "attempt": attempt,
                "status_code": status_code,
                "error_kind": kind,
                "error": error,
                "request_sha256": request_sha256,
            }
        )
        self.append(row)
        return row

    def record_infra_failure(
        self, request: ChatRequest, exc: InfraError, *, request_sha256: str
    ) -> LedgerRow:
        row = LedgerRow.model_validate(
            {
                **self._base(request, "infra_failure"),
                "attempt": exc.attempts,
                "status_code": exc.status_code,
                "error_kind": exc.kind,
                "error": str(exc),
                "request_sha256": request_sha256,
            }
        )
        self.append(row)
        return row

    def record_task_failure(
        self,
        *,
        attribution: Attribution,
        seed: int,
        model: str,
        exc: TaskFailure,
        rollout_uid: str | None = None,
    ) -> LedgerRow:
        """A task-level failure (including ``BudgetExhausted``) not tied to one chat request."""
        row = LedgerRow.model_validate(
            {
                **self._fields(
                    event="task_failure", attribution=attribution, seed=seed, model=model
                ),
                "error_kind": exc.kind,
                "error": str(exc),
                "rollout_uid": rollout_uid,
            }
        )
        self.append(row)
        return row

    def record_rollout(
        self,
        *,
        attribution: Attribution,
        seed: int,
        model: str,
        rollout_uid: str,
        usage: Usage,
        cost: CostBreakdown,
        steps: int,
        success: bool,
        latency_ms: int = 0,
    ) -> LedgerRow:
        """One policy rollout charged to ``attribution.budget``; tokens summed over its calls."""
        row = LedgerRow.model_validate(
            {
                **self._fields(event="rollout", attribution=attribution, seed=seed, model=model),
                "rollout_uid": rollout_uid,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cached_tokens": usage.cached_tokens,
                "reasoning_tokens": usage.reasoning_tokens,
                "usd": cost.usd,
                "pricing_version": cost.pricing_version,
                "pricing_tier": cost.tier,
                "steps": steps,
                "success": success,
                "latency_ms": latency_ms,
            }
        )
        self.append(row)
        return row


def read_ledger(path: Path) -> list[LedgerRow]:
    rows: list[LedgerRow] = []
    for index, raw in enumerate(read_jsonl(path), start=1):
        try:
            rows.append(LedgerRow.model_validate(raw))
        except ValidationError as exc:
            raise InfraError(
                f"invalid ledger row at line {index} in {path}:\n{exc}", kind="corrupt_file"
            ) from exc
    return rows


def summarize(rows: list[LedgerRow]) -> LedgerSummary:
    counts: dict[str, int] = {
        "calls": 0,
        "rollouts": 0,
        "infra_retries": 0,
        "infra_failures": 0,
        "task_failures": 0,
        "budget_exhausted": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    usd = 0.0
    by_budget: dict[str, int] = {}
    usd_by_budget: dict[str, float] = {}
    for row in rows:
        match row.event:
            case "call":
                counts["calls"] += 1
                counts["prompt_tokens"] += row.prompt_tokens
                counts["completion_tokens"] += row.completion_tokens
                usd += row.usd
                usd_by_budget[row.budget] = usd_by_budget.get(row.budget, 0.0) + row.usd
            case "rollout":
                counts["rollouts"] += 1
                by_budget[row.budget] = by_budget.get(row.budget, 0) + 1
            case "infra_retry":
                counts["infra_retries"] += 1
            case "infra_failure":
                counts["infra_failures"] += 1
            case "task_failure":
                if row.error_kind == BUDGET_EXHAUSTED_KIND:
                    counts["budget_exhausted"] += 1
                else:
                    counts["task_failures"] += 1
    return LedgerSummary(
        **counts, usd=usd, rollouts_by_budget=by_budget, usd_by_budget=usd_by_budget
    )


class TaskTotals(StrictModel):
    rollouts: int = 0
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd: float = 0.0


def per_task_totals(rows: list[LedgerRow]) -> dict[str, TaskTotals]:
    """Merge ``rollout`` rows (episode counts, no tokens) with ``call`` rows (tokens and cost) per
    task: the cost of a task is the sum of its call rows, the rollout count the number of rollout
    rows. Analysis scripts use this instead of reading either row kind alone."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        acc = out.setdefault(
            row.task_id,
            {"rollouts": 0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0},
        )
        if row.event == "rollout":
            acc["rollouts"] += 1
        elif row.event == "call":
            acc["calls"] += 1
            acc["prompt_tokens"] += row.prompt_tokens
            acc["completion_tokens"] += row.completion_tokens
            acc["usd"] += row.usd
    return {
        k: TaskTotals(
            rollouts=int(v["rollouts"]),
            calls=int(v["calls"]),
            prompt_tokens=int(v["prompt_tokens"]),
            completion_tokens=int(v["completion_tokens"]),
            usd=v["usd"],
        )
        for k, v in out.items()
    }
