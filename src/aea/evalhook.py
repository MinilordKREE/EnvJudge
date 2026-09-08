"""Accounting and guards for the released evaluation (``reasoning_bank_eval.py``).

The released eval calls ``litellm.completion`` directly through ``completion_with_retry``
(``envharness/infra/llm.py``) with kwargs from ``completion_kwargs`` (``infra/model.py:434``),
which carries only model, temperature, max_tokens and the provider's auth — no request extras. The
pilot's approach (docs/pilots/e1pilot/e1/p3a.py ``install_wrappers``) is kept: ``install`` wraps
``litellm.completion`` IN THIS PROCESS (and its worker processes, which inherit the wrapped module)
to (1) route the call to the configured endpoint with the provider pin and the reasoning setting
from an ``LLMConfig``, (2) write one ledger row per call on budget ``eval``, and (3) apply the
provider and price guards: a mismatch writes ``guard_failure.json`` in the run directory, records an
``infra_failure`` row and raises. Because the released eval catches per-episode exceptions, the
driver must treat the marker as an abort (``check_guard`` after ``rbe.main`` returns). The released
code path is otherwise untouched; nothing under third_party changes.

A plain ``litellm.success_callback`` cannot abort (litellm runs it in a thread and swallows
exceptions) and cannot route, which is why the wrapper form is used; it is observe-and-route,
documented here and in docs/reuse/eval_hook.md.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from aea.core.config import LLMConfig
from aea.core.io import atomic_write_json
from aea.errors import InfraError
from aea.llm.attribution import current_attribution
from aea.llm.client import build_wire_request, check_routing
from aea.llm.ledger import Ledger
from aea.llm.pricing import PricingTable
from aea.llm.types import Attribution, ChatMessage, ChatRequest, ChatResponse, Usage
from aea.settings import load_settings

GUARD_MARKER = "guard_failure.json"
ROUTING_KEYS = frozenset(
    {"api_base", "api_key", "extra_body", "reasoning_effort", "model", "drop_params"}
)
"""The only kwargs the hook may add or change; everything else reaches litellm byte-identical."""


class GuardError(InfraError):
    """A provider or price guard failed. Deliberately NOT one of litellm's transient exception
    classes (APIConnectionError, RateLimitError, ServiceUnavailableError, InternalServerError,
    Timeout), so the released ``completion_with_retry`` / ``LiteLLMClient`` never retries it."""

    def __init__(self, message: str) -> None:
        super().__init__(message, kind="guard", retryable=False)


def _int(obj: Any, name: str) -> int:
    value = getattr(obj, name, None) if not isinstance(obj, dict) else obj.get(name)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _cost(usage: Any) -> float | None:
    value = getattr(usage, "cost", None) if not isinstance(usage, dict) else usage.get("cost")
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def parse_litellm_response(response: Any) -> ChatResponse:
    """The fields the ledger needs from a litellm ``ModelResponse`` (usage, provider, cost)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        raise InfraError("eval response carries no usage block", kind="missing_usage")
    details = getattr(usage, "prompt_tokens_details", None)
    cached = _int(details, "cached_tokens") if details is not None else 0
    cdetails = getattr(usage, "completion_tokens_details", None)
    choices = getattr(response, "choices", None) or []
    content = ""
    if choices:
        message = getattr(choices[0], "message", None)
        content = str(getattr(message, "content", "") or "")
    provider = getattr(response, "provider", None)
    if provider is None and isinstance(getattr(response, "_hidden_params", None), dict):
        provider = response._hidden_params.get("provider") or response._hidden_params.get(
            "custom_llm_provider"
        )
    return ChatResponse(
        content=content,
        reasoning=None,
        finish_reason=str(getattr(choices[0], "finish_reason", "stop") if choices else "stop"),
        usage=Usage(
            prompt_tokens=_int(usage, "prompt_tokens"),
            completion_tokens=_int(usage, "completion_tokens"),
            cached_tokens=min(cached, _int(usage, "prompt_tokens")),
            reasoning_tokens=_int(cdetails, "reasoning_tokens") if cdetails is not None else 0,
        ),
        model=str(getattr(response, "model", "") or ""),
        provider=str(provider) if isinstance(provider, str) else None,
        upstream_cost=_cost(usage),
        response_id=getattr(response, "id", None),
        request_sha256="eval",
        latency_ms=0,
        created_at=datetime.now(UTC),
    )


class EvalHook:
    def __init__(
        self,
        *,
        config: LLMConfig,
        ledger: Ledger,
        pricing: PricingTable,
        run_dir: Path,
        api_key: str | None,
    ) -> None:
        check_routing(config)
        self.config = config
        self.ledger = ledger
        self.pricing = pricing
        self.run_dir = run_dir
        self.api_key = api_key
        self.calls = 0

    def route(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """The released kwargs plus endpoint, key, provider pin and reasoning setting."""
        base = ChatRequest(
            model=self.config.model,
            messages=(ChatMessage(role="user", content="x"),),
            temperature=float(kwargs.get("temperature", 0.0) or 0.0),
            max_tokens=int(
                kwargs.get("max_tokens", self.config.max_tokens) or self.config.max_tokens
            ),
        )
        wire = build_wire_request(base, self.config)
        out = dict(kwargs)
        out["model"] = (
            f"openai/{self.config.model}"
            if self.config.provider == "openrouter"
            else self.config.model
        )
        out["api_base"] = self.config.base_url
        if self.api_key:
            out["api_key"] = self.api_key
        if "extra_body" in wire:
            out["extra_body"] = {**(out.get("extra_body") or {}), **wire["extra_body"]}
        if "reasoning_effort" in wire:
            out["reasoning_effort"] = wire["reasoning_effort"]
        out.pop("drop_params", None)
        assert {k for k in out if k not in kwargs or out[k] != kwargs.get(k)} <= ROUTING_KEYS
        return out

    def account(self, response: Any, latency_ms: int) -> ChatResponse:
        parsed = parse_litellm_response(response).model_copy(update={"latency_ms": latency_ms})
        attribution, seed = current_attribution()
        if attribution.budget == "none":
            attribution = Attribution(
                phase="eval", budget="eval", arm=attribution.arm, task_id=attribution.task_id
            )
        request = ChatRequest(
            model=self.config.model,
            messages=(ChatMessage(role="user", content="eval"),),
            seed=seed,
            attribution=attribution,
        )
        cost = self.pricing.cost(self.config.model, parsed.usage, parsed.created_at)
        self.ledger.record_call(request, parsed, cost=cost, attempt=1)
        self.calls += 1
        self._guard(request, parsed, cost.usd)
        return parsed

    def _guard(self, request: ChatRequest, parsed: ChatResponse, usd: float) -> None:
        pin = self.config.provider_pin
        problem: str | None = None
        if (
            pin is not None
            and parsed.provider is not None
            and (parsed.provider.lower().replace(" ", "-") != pin.lower().replace(" ", "-"))
        ):
            problem = f"provider guard: response from {parsed.provider!r}, pinned {pin!r}"
        elif (
            parsed.upstream_cost is not None
            and abs(parsed.upstream_cost - usd) > self.config.cost_tolerance
        ):
            problem = f"pricing guard: upstream cost {parsed.upstream_cost:.8f} != table {usd:.8f}"
        if problem is None:
            return
        exc = GuardError(problem)
        self.ledger.record_infra_failure(request, exc, request_sha256="eval")
        atomic_write_json(
            self.run_dir / GUARD_MARKER, {"problem": problem, "ts": time.time(), "pid": os.getpid()}
        )
        raise exc


def install(hook: EvalHook) -> Callable[..., Any]:
    """Wrap ``litellm.completion`` for this process; returns the original for tests."""
    import litellm

    original = cast(Callable[..., Any], litellm.completion)

    def completion(*args: Any, **kwargs: Any) -> Any:
        routed = hook.route(kwargs)
        t0 = time.perf_counter()
        response = original(*args, **routed)
        hook.account(response, int((time.perf_counter() - t0) * 1000))
        return response

    litellm.completion = completion
    return original


def make_hook(config: LLMConfig, *, run_dir: Path, run_id: str, pricing: PricingTable) -> EvalHook:
    key = None
    if config.provider != "fake":
        key = load_settings().require(config.api_key_env.lower()).get_secret_value()
    return EvalHook(
        config=config,
        ledger=Ledger(run_dir / f"ledger.{os.getpid()}.jsonl", run_id),
        pricing=pricing,
        run_dir=run_dir,
        api_key=key,
    )


def check_guard(run_dir: Path) -> dict[str, Any] | None:
    """The driver's abort check after the released eval returns: the marker, if any guard fired."""
    marker = run_dir / GUARD_MARKER
    if not marker.exists():
        return None
    return dict(json.loads(marker.read_text(encoding="utf-8")))
