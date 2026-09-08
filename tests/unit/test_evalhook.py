from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import litellm
import pytest

from aea.core.config import LLMConfig
from aea.errors import InfraError
from aea.evalhook import GUARD_MARKER, EvalHook, check_guard, install, parse_litellm_response
from aea.llm.attribution import attributed
from aea.llm.ledger import Ledger, read_ledger
from aea.llm.pricing import PricingTable
from aea.llm.types import Attribution


def _response(
    provider: str = "Alibaba", cost: float | None = None, content: str = "<action>look</action>"
) -> Any:
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=10,
        prompt_tokens_details=SimpleNamespace(cached_tokens=20),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )
    if cost is not None:
        usage.cost = cost
    return SimpleNamespace(
        usage=usage,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        model="qwen/qwen3-8b",
        provider=provider,
        id="r1",
    )


def _hook(tmp_path: Path, pricing: PricingTable, **cfg: Any) -> EvalHook:
    config = LLMConfig(**cfg) if cfg else LLMConfig()
    return EvalHook(
        config=config,
        ledger=Ledger(tmp_path / "ledger.jsonl", "r"),
        pricing=pricing,
        run_dir=tmp_path,
        api_key="sk-test",
    )


def test_route_adds_endpoint_pin_and_reasoning(tmp_path: Path, pricing: PricingTable) -> None:
    hook = _hook(tmp_path, pricing)
    routed = hook.route(
        {
            "model": "openai/qwen/qwen3-8b",
            "temperature": 0.4,
            "max_tokens": 2048,
            "api_key": "ignored",
            "drop_params": True,
        }
    )
    assert routed["api_base"] == "https://openrouter.ai/api/v1" and routed["api_key"] == "sk-test"
    assert routed["extra_body"]["provider"] == {"order": ["alibaba"], "allow_fallbacks": False}
    assert routed["extra_body"]["reasoning"] == {"enabled": False} and routed["temperature"] == 0.4
    silent = _hook(tmp_path, pricing, thinking=None).route({"model": "m"})
    assert "reasoning" not in silent["extra_body"]  # provider default for the Gemini arms


def test_account_writes_eval_rows_and_guards(tmp_path: Path, pricing: PricingTable) -> None:
    hook = _hook(tmp_path, pricing)
    usd = (20 * 0.117 + 80 * 0.117 + 10 * 0.455) / 1e6
    parsed = hook.account(_response(cost=usd), latency_ms=5)
    assert parsed.usage.cached_tokens == 20 and parsed.provider == "Alibaba"
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert rows[0].event == "call" and rows[0].budget == "eval" and rows[0].phase == "eval"
    with attributed(Attribution(phase="eval", budget="eval", arm="R", task_id="12"), seed=1000):
        hook.account(_response(cost=usd), latency_ms=1)
    assert read_ledger(tmp_path / "ledger.jsonl")[1].task_id == "12"
    with pytest.raises(InfraError) as info:
        hook.account(_response(provider="DeepInfra"), latency_ms=1)
    marker = check_guard(tmp_path)
    assert info.value.kind == "guard" and marker is not None
    assert "provider guard" in str(marker["problem"])
    assert read_ledger(tmp_path / "ledger.jsonl")[-1].event == "infra_failure"
    (tmp_path / GUARD_MARKER).unlink()
    with pytest.raises(InfraError):
        hook.account(_response(cost=0.5), latency_ms=1)
    marker = check_guard(tmp_path)
    assert marker is not None and str(marker["problem"]).startswith("pricing guard")


def test_install_wraps_litellm_completion(
    tmp_path: Path, pricing: PricingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return _response(cost=(100 * 0.117 + 10 * 0.455) / 1e6)

    monkeypatch.setattr(litellm, "completion", fake_completion)
    hook = _hook(tmp_path, pricing)
    original = install(hook)
    try:
        out = litellm.completion(
            model="openai/qwen/qwen3-8b",
            messages=[{"role": "user", "content": "x"}],
            temperature=0.4,
            max_tokens=64,
        )
    finally:
        litellm.completion = original
    assert out.choices[0].message.content == "<action>look</action>"
    assert calls[0]["api_base"] == "https://openrouter.ai/api/v1" and calls[0]["extra_body"][
        "provider"
    ]["order"] == ["alibaba"]
    assert hook.calls == 1 and read_ledger(tmp_path / "ledger.jsonl")[0].budget == "eval"


def test_parse_requires_usage() -> None:
    with pytest.raises(InfraError):
        parse_litellm_response(SimpleNamespace(usage=None, choices=[]))
