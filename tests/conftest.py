"""Shared fixtures. Every unit test runs offline: the transport is scripted, no ALFWorld."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from openai.types.chat import ChatCompletion

from aea.core.config import LLMConfig, RetryConfig, RunConfig
from aea.llm.client import OpenAICompatibleClient
from aea.llm.ledger import Ledger
from aea.llm.pricing import PricingTable, load_pricing

REPO_ROOT = Path(__file__).resolve().parents[1]

PRICING_YAML = """\
currency: USD
unit: per_1m_tokens
models:
  qwen/qwen3-8b:
    pricing_version: "test-qwen.1"
    as_of: 2026-09-07
    source: test
    flat: {input_cache_hit: 0.117, input_cache_miss: 0.117, output: 0.455}
  deepseek-v4-flash:
    pricing_version: "test-ds.1"
    as_of: 2026-09-04
    source: test
    peak:     {input_cache_hit: 0.014, input_cache_miss: 0.44, output: 1.32}
    off_peak: {input_cache_hit: 0.007, input_cache_miss: 0.22, output: 0.66}
    schedule:
      description: "Mon-Fri 01:00-04:00 and 06:00-10:00 UTC"
      weekdays: [0, 1, 2, 3, 4]
      utc_windows: [["01:00", "04:00"], ["06:00", "10:00"]]
"""

OFF_PEAK_TS = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)  # Wednesday noon UTC
PEAK_TS = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)  # Wednesday 02:00 UTC


def make_completion(
    content: str = "pong",
    *,
    prompt_tokens: int = 10,
    completion_tokens: int = 2,
    cached: int = 0,
    reasoning_tokens: int = 0,
    finish_reason: str = "stop",
    model: str = "qwen/qwen3-8b",
    provider: str | None = "Alibaba",
    cost: float | None = None,
    usage: bool = True,
) -> ChatCompletion:
    """Build a ChatCompletion the way the SDK does for a real response (lenient construct)."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    data: dict[str, Any] = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
    }
    if provider is not None:
        data["provider"] = provider
    if usage:
        data["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": cached},
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        }
        if cost is not None:
            data["usage"]["cost"] = cost
    return ChatCompletion.construct(**data)


def _http(status: int) -> httpx.Response:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return httpx.Response(status, request=request)


def status_error(status: int, message: str = "boom") -> openai.APIStatusError:
    if status == 429:
        return openai.RateLimitError(message, response=_http(status), body=None)
    return openai.APIStatusError(message, response=_http(status), body=None)


def connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai"))


def timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://openrouter.ai"))


class FakeTransport:
    """Scripted ``chat.completions.create``: returns or raises each outcome in order."""

    def __init__(self, outcomes: list[ChatCompletion | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> ChatCompletion:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise AssertionError("FakeTransport has no scripted outcomes left")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def pricing_path(tmp_path: Path) -> Path:
    path = tmp_path / "pricing.yaml"
    path.write_text(PRICING_YAML, encoding="utf-8")
    return path


@pytest.fixture
def pricing(pricing_path: Path) -> PricingTable:
    return load_pricing(pricing_path)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh repository with one commit and a clean tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("test\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def run_config(pricing_path: Path, tmp_path: Path) -> RunConfig:
    return RunConfig(
        schema_version=1,
        name="unit",
        kind="exploratory",
        seed=7,
        require_clean_tree=False,
        policy=LLMConfig(retry=RetryConfig(max_attempts=3, initial_delay_s=0.0, jitter_s=0.0)),
        pricing_path=pricing_path,
        runs_root=tmp_path / "runs",
    )


class ClientBundle:
    def __init__(
        self, client: OpenAICompatibleClient, transport: FakeTransport, ledger: Ledger
    ) -> None:
        self.client = client
        self.transport = transport
        self.ledger = ledger
        self.sleeps: list[float] = []


type ClientFactory = Callable[..., ClientBundle]


@pytest.fixture
def make_client(tmp_path: Path, pricing: PricingTable) -> ClientFactory:
    def factory(
        outcomes: list[ChatCompletion | Exception],
        *,
        config: LLMConfig | None = None,
        now: datetime = OFF_PEAK_TS,
    ) -> ClientBundle:
        transport = FakeTransport(outcomes)
        ledger = Ledger(tmp_path / "ledger.jsonl", "run-test")
        sleeps: list[float] = []
        cfg = config or LLMConfig(
            retry=RetryConfig(max_attempts=3, initial_delay_s=0.5, jitter_s=0.0)
        )
        client = OpenAICompatibleClient(
            config=cfg,
            transport=transport,
            ledger=ledger,
            pricing=pricing,
            now=lambda: now,
            sleep=sleeps.append,
        )
        bundle = ClientBundle(client, transport, ledger)
        bundle.sleeps = sleeps
        return bundle

    return factory
