"""Typed chat request/response records shared by every provider.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/llm/types.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; ``Attribution`` carries the ledger dimensions aea charges by
(``phase``, ``budget``, ``arm``, ``task_id``); the multimodal content form and the cache
payload are dropped (no caches in experiments); ``ChatResponse`` records the upstream
``provider`` and ``upstream_cost`` so a provider pin can be enforced.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from aea.core.config import ReasoningEffort, StrictModel

type Role = Literal["system", "user", "assistant", "tool"]

type BudgetName = Literal["search", "confirm", "train", "probe_cert", "designer", "eval", "none"]
"""Named budgets. ``search`` is capped per task per round; ``confirm`` (K16 post-hoc) and
``train`` are separate ledgers; ``probe_cert`` is the hint certificate; ``designer`` calls are
free of the rollout budget but logged; ``eval`` is the released downstream evaluation."""


class ChatMessage(StrictModel):
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class Attribution(StrictModel):
    """Who is paying for a call in the experiment's terms."""

    phase: str = "none"
    budget: BudgetName = "none"
    arm: str = "none"
    task_id: str = "none"


class ChatRequest(StrictModel):
    """Everything that determines a completion, plus per-call bookkeeping."""

    model: str
    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int = 0
    max_tokens: int = Field(default=2048, ge=1)
    thinking: bool = False
    reasoning_effort: ReasoningEffort | None = None
    timeout_s: float = Field(default=120.0, gt=0.0)
    attribution: Attribution = Attribution()
    tools: tuple[dict[str, object], ...] | None = None
    tool_choice: str | dict[str, object] | None = None


class ToolCall(StrictModel):
    id: str
    name: str
    arguments: dict[str, object]


class Usage(StrictModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

    @property
    def uncached_prompt_tokens(self) -> int:
        return self.prompt_tokens - self.cached_tokens


class ChatResponse(StrictModel):
    content: str
    reasoning: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str
    usage: Usage
    model: str
    provider: str | None
    upstream_cost: float | None
    response_id: str | None
    request_sha256: str
    latency_ms: int
    created_at: datetime
