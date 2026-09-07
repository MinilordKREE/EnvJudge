"""OpenAI-compatible chat client (OpenRouter / DeepSeek) with retry, ledger and provider guard.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/llm/deepseek.py (``make_openai_transport``, ``build_wire_request``,
``parse_completion``, ``DeepSeekClient``)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; generalised to any OpenAI-compatible endpoint; the response cache is
removed (no caches in experiments); OpenRouter extras are sent when a ``provider_pin`` is set
(``provider.order`` + ``allow_fallbacks=false`` and ``usage.include``); the upstream provider
name and ``usage.cost`` are read back and a mismatch with the pin or the price table aborts the
call (the pilot's guard, docs/pilots/eobs/eobs/llm.py). ``reasoning_effort`` is a top-level
parameter; DeepSeek thinking is toggled through ``extra_body.thinking``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import openai
from openai.types.chat import ChatCompletion
from pydantic import SecretStr

from aea.core.config import LLMConfig
from aea.core.hashing import sha256_of
from aea.errors import ConfigError, InfraError
from aea.llm.ledger import Ledger
from aea.llm.pricing import PricingTable
from aea.llm.retry import RetryEvent, run_with_retry
from aea.llm.types import ChatMessage, ChatRequest, ChatResponse, ToolCall, Usage

logger = logging.getLogger(__name__)

INSUFFICIENT_RESOURCE = "insufficient_system_resource"

type Transport = Callable[..., ChatCompletion]
"""``chat.completions.create``-shaped callable returning a non-streamed completion."""

ALLOWED_PAIRS: dict[str, tuple[str, str]] = {
    "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1", ""),
    "DEEPSEEK_API_KEY": ("https://api.deepseek.com", "deepseek"),
}
"""``api_key_env -> (base_url, required model prefix)``: a key is only ever sent to its own host."""


def check_routing(config: LLMConfig) -> None:
    """Refuse a config that would send a key to a foreign host or an unexpected model."""
    if config.provider == "fake":
        return
    base, prefix = ALLOWED_PAIRS[config.api_key_env]
    if config.base_url.rstrip("/") != base:
        raise ConfigError(f"{config.api_key_env} may only be sent to {base}, not {config.base_url}")
    if prefix and not config.model.startswith(prefix):
        raise ConfigError(f"{config.api_key_env} is bound to models starting with {prefix!r}")


def make_openai_transport(*, api_key: SecretStr, base_url: str, timeout_s: float) -> Transport:
    client = openai.OpenAI(
        api_key=api_key.get_secret_value(), base_url=base_url, max_retries=0, timeout=timeout_s
    )

    def create(**kwargs: Any) -> ChatCompletion:
        result = client.chat.completions.create(**kwargs)
        if not isinstance(result, ChatCompletion):
            raise InfraError("provider returned a streaming response", kind="protocol")
        return result

    return create


def build_wire_request(request: ChatRequest, config: LLMConfig) -> dict[str, Any]:
    """Translate a :class:`ChatRequest` into ``chat.completions.create`` keyword arguments."""
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [_wire_message(message) for message in request.messages],
        "max_tokens": request.max_tokens,
        "stream": False,
        "timeout": request.timeout_s,
    }
    extra: dict[str, Any] = {}
    if config.provider == "deepseek":
        extra["thinking"] = {"type": "enabled" if request.thinking else "disabled"}
    if config.provider == "openrouter":
        extra["usage"] = {"include": True}
        if config.provider_pin is not None:
            extra["provider"] = {"order": [config.provider_pin], "allow_fallbacks": False}
        if not request.thinking and request.reasoning_effort is None:
            extra["reasoning"] = {"enabled": False}
    if request.reasoning_effort is not None:
        body["reasoning_effort"] = request.reasoning_effort
    if not (config.provider == "deepseek" and request.thinking):
        body["temperature"] = request.temperature
    if request.tools:
        body["tools"] = [dict(t) for t in request.tools]
        if request.tool_choice is not None:
            body["tool_choice"] = request.tool_choice
    if extra:
        body["extra_body"] = extra
    return body


def _int_attr(obj: object, name: str) -> int:
    value = getattr(obj, name, None)
    return value if isinstance(value, int) else 0


def _float_attr(obj: object, name: str) -> float | None:
    value = getattr(obj, name, None)
    if isinstance(value, bool) or value is None:
        return None
    return float(value) if isinstance(value, int | float) else None


def parse_completion(
    completion: ChatCompletion, *, request_sha256: str, latency_ms: int, created_at: datetime
) -> ChatResponse:
    if not completion.choices:
        raise InfraError("provider returned no choices", kind="empty_response")
    choice = completion.choices[0]
    if completion.usage is None:
        raise InfraError("provider returned no usage block", kind="missing_usage")
    usage_raw = completion.usage
    details = usage_raw.completion_tokens_details
    prompt_details = usage_raw.prompt_tokens_details
    cached = _int_attr(prompt_details, "cached_tokens") if prompt_details is not None else 0
    cached = cached or _int_attr(usage_raw, "prompt_cache_hit_tokens")
    usage = Usage(
        prompt_tokens=usage_raw.prompt_tokens,
        completion_tokens=usage_raw.completion_tokens,
        cached_tokens=min(cached, usage_raw.prompt_tokens),
        reasoning_tokens=_int_attr(details, "reasoning_tokens") if details is not None else 0,
    )
    reasoning = getattr(choice.message, "reasoning_content", None) or getattr(
        choice.message, "reasoning", None
    )
    calls: list[ToolCall] = []
    for tc in choice.message.tool_calls or []:
        function = getattr(tc, "function", None)
        if function is None:
            continue
        arguments = function.arguments
        parsed: dict[str, object]
        if isinstance(arguments, str):
            import json

            try:
                loaded = json.loads(arguments)
            except json.JSONDecodeError:
                loaded = {"_raw": arguments}
            parsed = loaded if isinstance(loaded, dict) else {"_raw": arguments}
        else:
            parsed = dict(arguments) if isinstance(arguments, dict) else {}
        calls.append(ToolCall(id=tc.id, name=function.name, arguments=parsed))
    provider = getattr(completion, "provider", None)
    return ChatResponse(
        content=choice.message.content or "",
        reasoning=reasoning if isinstance(reasoning, str) else None,
        tool_calls=tuple(calls),
        finish_reason=str(choice.finish_reason),
        usage=usage,
        model=completion.model,
        provider=provider if isinstance(provider, str) else None,
        upstream_cost=_float_attr(usage_raw, "cost"),
        response_id=completion.id or None,
        request_sha256=request_sha256,
        latency_ms=latency_ms,
        created_at=created_at,
    )


class OpenAICompatibleClient:
    """Implements :class:`aea.llm.provider.Provider` with retry, ledger and the provider guard."""

    def __init__(
        self,
        *,
        config: LLMConfig,
        transport: Transport,
        ledger: Ledger,
        pricing: PricingTable,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        check_routing(config)
        self._config = config
        self._transport = transport
        self._ledger = ledger
        self._pricing = pricing
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep

    @property
    def config(self) -> LLMConfig:
        return self._config

    def request_sha256(self, request: ChatRequest) -> str:
        return sha256_of({"provider": self._config.provider, "request": request.model_dump()})

    def _call_once(self, wire: dict[str, Any]) -> ChatCompletion:
        completion = self._transport(**wire)
        if completion.choices and completion.choices[0].finish_reason == INSUFFICIENT_RESOURCE:
            raise InfraError(
                "provider reported insufficient system resources",
                kind=INSUFFICIENT_RESOURCE,
                retryable=True,
            )
        return completion

    def _guard(self, response: ChatResponse, usd: float) -> None:
        """Abort on a provider other than the pin or on a price disagreement with the table."""
        pin = self._config.provider_pin
        if (
            pin is not None
            and response.provider is not None
            and (response.provider.lower().replace(" ", "-") != pin.lower().replace(" ", "-"))
        ):
            raise InfraError(
                f"provider guard: response from {response.provider!r}, pinned {pin!r}",
                kind="provider_mismatch",
            )
        if response.upstream_cost is not None and (
            abs(response.upstream_cost - usd) > self._config.cost_tolerance
        ):
            raise InfraError(
                f"pricing guard: upstream cost {response.upstream_cost:.8f} != table {usd:.8f}",
                kind="pricing_mismatch",
            )

    def complete(self, request: ChatRequest) -> ChatResponse:
        request_sha = self.request_sha256(request)
        retries = 0

        def on_retry(event: RetryEvent) -> None:
            nonlocal retries
            retries += 1
            self._ledger.record_infra_retry(
                request,
                attempt=event.attempt,
                kind=event.kind,
                status_code=event.status_code,
                error=event.error,
                request_sha256=request_sha,
            )

        wire = build_wire_request(request, self._config)
        started_at = self._now()
        t0 = time.perf_counter()
        try:
            completion = run_with_retry(
                lambda: self._call_once(wire),
                policy=self._config.retry,
                on_retry=on_retry,
                sleep=self._sleep,
            )
        except InfraError as exc:
            self._ledger.record_infra_failure(request, exc, request_sha256=request_sha)
            logger.error("infra failure: %s", exc, extra={"error_kind": exc.kind})
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        response = parse_completion(
            completion, request_sha256=request_sha, latency_ms=latency_ms, created_at=started_at
        )
        cost = self._pricing.cost(request.model, response.usage, started_at)
        self._ledger.record_call(request, response, cost=cost, attempt=retries + 1)
        self._guard(response, cost.usd)
        return response


def _wire_message(message: ChatMessage) -> dict[str, object]:
    body: dict[str, object] = {"role": message.role, "content": message.content}
    if message.name is not None:
        body["name"] = message.name
    if message.tool_call_id is not None:
        body["tool_call_id"] = message.tool_call_id
    return body
