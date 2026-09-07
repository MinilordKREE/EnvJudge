from __future__ import annotations

from pathlib import Path

import pytest

from aea.core.config import LLMConfig, RetryConfig
from aea.errors import ConfigError, InfraError
from aea.llm.client import build_wire_request, check_routing
from aea.llm.ledger import read_ledger
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from tests.conftest import ClientFactory, make_completion, status_error


def _request(**overrides: object) -> ChatRequest:
    base: dict[str, object] = {
        "model": "qwen/qwen3-8b",
        "messages": (ChatMessage(role="user", content="hello there"),),
        "temperature": 0.5,
        "attribution": Attribution(phase="p", budget="search", arm="A", task_id="1"),
    }
    base.update(overrides)
    return ChatRequest.model_validate(base)


def test_routing_guard() -> None:
    check_routing(LLMConfig())
    with pytest.raises(ConfigError):
        check_routing(LLMConfig(base_url="https://evil.example/v1"))
    with pytest.raises(ConfigError):
        check_routing(
            LLMConfig(
                provider="deepseek",
                base_url="https://api.deepseek.com",
                api_key_env="DEEPSEEK_API_KEY",
                model="qwen/qwen3-8b",
            )
        )


def test_wire_request_openrouter_and_deepseek() -> None:
    wire = build_wire_request(_request(), LLMConfig())
    assert wire["extra_body"]["provider"] == {"order": ["alibaba"], "allow_fallbacks": False}
    assert wire["extra_body"]["usage"] == {"include": True}
    assert (
        "reasoning" not in wire["extra_body"]
    )  # ChatRequest.thinking defaults to None: provider default
    assert wire["temperature"] == 0.5 and "reasoning_effort" not in wire
    off = build_wire_request(_request(thinking=False), LLMConfig())
    assert off["extra_body"]["reasoning"] == {"enabled": False}
    on = build_wire_request(_request(thinking=True, reasoning_effort="low"), LLMConfig())
    assert on["extra_body"]["reasoning"] == {"enabled": True} and on["reasoning_effort"] == "low"
    ds = LLMConfig(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        model="deepseek-v4-pro",
        provider_pin=None,
    )
    wire = build_wire_request(
        _request(model="deepseek-v4-pro", thinking=True, reasoning_effort="high"), ds
    )
    assert wire["extra_body"] == {"thinking": {"type": "enabled"}}
    assert wire["reasoning_effort"] == "high" and "temperature" not in wire


def test_success_records_call_with_provider_and_cost(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    usd = (10 * 0.117 + 2 * 0.455) / 1e6
    bundle = make_client([make_completion(cost=usd)])
    response = bundle.client.complete(_request())
    assert response.content == "pong" and response.provider == "Alibaba"
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert [r.event for r in rows] == ["call"]
    assert rows[0].provider == "Alibaba" and abs(rows[0].usd - usd) < 1e-12
    assert rows[0].upstream_cost == usd and rows[0].budget == "search"


def test_provider_and_pricing_guards(make_client: ClientFactory) -> None:
    bundle = make_client([make_completion(provider="DeepInfra")])
    with pytest.raises(InfraError) as info:
        bundle.client.complete(_request())
    assert info.value.kind == "provider_mismatch"
    bundle = make_client([make_completion(cost=0.5)])
    with pytest.raises(InfraError) as bad_price:
        bundle.client.complete(_request())
    assert bad_price.value.kind == "pricing_mismatch"


def test_retries_are_ledgered_and_auth_is_not_retried(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    bundle = make_client([status_error(429), make_completion()])
    bundle.client.complete(_request())
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert [r.event for r in rows] == ["infra_retry", "call"] and rows[1].attempt == 2
    assert bundle.sleeps == [0.5]
    bundle = make_client(
        [status_error(401)], config=LLMConfig(retry=RetryConfig(max_attempts=3, jitter_s=0.0))
    )
    with pytest.raises(InfraError) as info:
        bundle.client.complete(_request())
    assert info.value.kind == "auth" and len(bundle.transport.calls) == 1
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert rows[-1].event == "infra_failure" and rows[-1].error_kind == "auth"


def test_missing_usage_is_infra(make_client: ClientFactory) -> None:
    bundle = make_client([make_completion(usage=False)])
    with pytest.raises(InfraError) as info:
        bundle.client.complete(_request())
    assert info.value.kind == "missing_usage"
