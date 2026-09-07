"""In-memory :class:`Provider` for unit tests and dry runs.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/llm/fake.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; response carries ``provider="fake"`` and no upstream cost.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from aea.core.hashing import sha256_of
from aea.llm.types import ChatRequest, ChatResponse, Usage


class FakeProvider:
    """Deterministic replies; records every request. Never touches a ledger or the network."""

    def __init__(self, reply: str | Callable[[ChatRequest], str] = "ok") -> None:
        self._reply = reply
        self.requests: list[ChatRequest] = []

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        content = self._reply(request) if callable(self._reply) else self._reply
        prompt_tokens = sum(len(m.content.split()) for m in request.messages)
        return ChatResponse(
            content=content,
            reasoning=None,
            finish_reason="stop",
            usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=len(content.split())),
            model=request.model,
            provider="fake",
            upstream_cost=None,
            response_id=None,
            request_sha256=sha256_of({"provider": "fake", "request": request.model_dump()}),
            latency_ms=0,
            created_at=datetime.now(UTC),
        )
