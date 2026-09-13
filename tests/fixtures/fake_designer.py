"""A scripted designer for controller tests: replies to every request with one fixed tool call
(or a caller-supplied function of the request) and records the requests it saw. No network."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aea.core.hashing import sha256_of
from aea.llm.types import ChatRequest, ChatResponse, ToolCall, Usage


def tool_response(request: ChatRequest, name: str, arguments: dict[str, Any]) -> ChatResponse:
    return ChatResponse(
        content="",
        reasoning=None,
        tool_calls=(ToolCall(id="call_0", name=name, arguments=arguments),),
        finish_reason="tool_calls",
        usage=Usage(prompt_tokens=1, completion_tokens=1),
        model=request.model,
        provider="fake",
        upstream_cost=None,
        response_id=None,
        request_sha256=sha256_of({"provider": "fake", "request": request.model_dump()}),
        latency_ms=0,
        created_at=datetime.now(UTC),
    )


class ScriptedDesigner:
    """``reply(request) -> (tool name, arguments)`` or a fixed pair; ``requests`` keeps every
    request (the evidence the designer saw)."""

    def __init__(
        self,
        reply: tuple[str, dict[str, Any]] | Callable[[ChatRequest], tuple[str, dict[str, Any]]],
    ) -> None:
        self._reply = reply
        self.requests: list[ChatRequest] = []

    def __call__(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        name, args = self._reply(request) if callable(self._reply) else self._reply
        return tool_response(request, name, args)

    @property
    def calls(self) -> int:
        return len(self.requests)
