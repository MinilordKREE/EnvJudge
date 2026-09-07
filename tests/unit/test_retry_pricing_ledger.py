from __future__ import annotations

from pathlib import Path

import pytest

from aea.core.config import RetryConfig
from aea.errors import BudgetExhausted, InfraError, TaskFailure
from aea.llm.ledger import LEDGER_SCHEMA_VERSION, Ledger, read_ledger, summarize
from aea.llm.pricing import PricingTable
from aea.llm.retry import RetryEvent, classify, run_with_retry
from aea.llm.types import Attribution, ChatMessage, ChatRequest, Usage
from tests.conftest import OFF_PEAK_TS, PEAK_TS, connection_error, status_error, timeout_error

CODES = (408, 409, 425, 429)


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (status_error(429), "rate_limit", True),
        (status_error(500), "server_error", True),
        (status_error(408), "transient", True),
        (status_error(401), "auth", False),
        (status_error(403), "auth", False),
        (status_error(400), "bad_request", False),
        (status_error(404), "client_error", False),
        (connection_error(), "connection", True),
        (timeout_error(), "timeout", True),
    ],
)
def test_classify(exc: Exception, kind: str, retryable: bool) -> None:
    info = classify(exc, retry_status_codes=CODES)
    assert info is not None and info.kind == kind and info.retryable is retryable
    assert classify(ValueError("bug"), retry_status_codes=CODES) is None


def test_retry_then_success_and_exhaustion() -> None:
    outcomes: list[Exception | str] = [status_error(429), status_error(503), "ok"]
    events: list[RetryEvent] = []
    sleeps: list[float] = []

    def fn() -> str:
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    policy = RetryConfig(max_attempts=5, initial_delay_s=1.0, multiplier=2.0, jitter_s=0.0)
    assert run_with_retry(fn, policy=policy, on_retry=events.append, sleep=sleeps.append) == "ok"
    assert [e.attempt for e in events] == [1, 2] and sleeps == [1.0, 2.0]
    with pytest.raises(InfraError) as info:
        run_with_retry(
            lambda: (_ for _ in ()).throw(status_error(401)), policy=policy, sleep=sleeps.append
        )
    assert info.value.kind == "auth" and info.value.attempts == 1
    with pytest.raises(InfraError) as gave_up:
        run_with_retry(
            lambda: (_ for _ in ()).throw(status_error(500)),
            policy=RetryConfig(max_attempts=2, initial_delay_s=0.0, jitter_s=0.0),
            sleep=sleeps.append,
        )
    assert gave_up.value.attempts == 2 and gave_up.value.retryable


def test_pricing_flat_and_peak(pricing: PricingTable) -> None:
    usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000, cached_tokens=500_000)
    flat = pricing.cost("qwen/qwen3-8b", usage, OFF_PEAK_TS)
    assert flat.tier == "flat" and abs(flat.usd - (0.117 + 0.455)) < 1e-9
    peak = pricing.cost("deepseek-v4-flash", usage, PEAK_TS)
    off = pricing.cost("deepseek-v4-flash", usage, OFF_PEAK_TS)
    assert peak.tier == "peak" and off.tier == "off_peak" and abs(peak.usd - 2 * off.usd) < 1e-9
    assert abs(off.usd - (0.5 * 0.007 + 0.5 * 0.22 + 0.66)) < 1e-9
    assert peak.pricing_version == "test-ds.1"
    with pytest.raises(Exception, match="no pricing"):
        pricing.cost("unknown", usage, OFF_PEAK_TS)


def _request() -> ChatRequest:
    return ChatRequest(
        model="m",
        messages=(ChatMessage(role="user", content="x"),),
        seed=5,
        attribution=Attribution(phase="search", budget="search", arm="A", task_id="7"),
    )


def test_ledger_rows_and_summary(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl", "r1")
    request = _request()
    ledger.record_infra_retry(
        request, attempt=1, kind="rate_limit", status_code=429, error="e", request_sha256="s"
    )
    ledger.record_infra_failure(
        request,
        InfraError("gave up", kind="server_error", status_code=500, attempts=3),
        request_sha256="s",
    )
    ledger.record_task_failure(
        attribution=request.attribution,
        seed=5,
        model="m",
        exc=BudgetExhausted("cap", budget="search", cap=30, spent=30, task_id="7"),
    )
    ledger.record_task_failure(
        attribution=request.attribution, seed=5, model="m", exc=TaskFailure("bad", kind="verifier")
    )
    from aea.llm.pricing import CostBreakdown

    ledger.record_rollout(
        attribution=request.attribution,
        seed=5,
        model="m",
        rollout_uid="u1",
        usage=Usage(prompt_tokens=10, completion_tokens=2),
        cost=CostBreakdown(usd=0.01, tier="flat", pricing_version="v"),
        steps=12,
        success=True,
    )
    rows = read_ledger(ledger.path)
    assert [r.event for r in rows] == [
        "infra_retry",
        "infra_failure",
        "task_failure",
        "task_failure",
        "rollout",
    ]
    assert all(r.schema_version == LEDGER_SCHEMA_VERSION for r in rows)
    assert {(r.phase, r.budget, r.arm, r.task_id, r.seed) for r in rows} == {
        ("search", "search", "A", "7", 5)
    }
    summary = summarize(rows)
    assert (
        summary.infra_retries,
        summary.infra_failures,
        summary.task_failures,
        summary.budget_exhausted,
    ) == (1, 1, 1, 1)
    assert summary.rollouts == 1 and summary.rollouts_by_budget == {"search": 1}


def test_per_task_totals_merge_call_and_rollout_rows(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from aea.llm.ledger import per_task_totals
    from aea.llm.pricing import CostBreakdown
    from aea.llm.types import ChatResponse

    ledger = Ledger(tmp_path / "ledger.jsonl", "r1")
    att = Attribution(phase="estimate", budget="search", arm="A", task_id="7")
    request = ChatRequest(
        model="m", messages=(ChatMessage(role="user", content="x"),), seed=7, attribution=att
    )
    for i in range(3):
        response = ChatResponse(
            content="a",
            reasoning=None,
            finish_reason="stop",
            usage=Usage(prompt_tokens=100 * (i + 1), completion_tokens=10),
            model="m",
            provider="Alibaba",
            upstream_cost=None,
            response_id=None,
            request_sha256="s",
            latency_ms=1,
            created_at=datetime.now(UTC),
        )
        ledger.record_call(
            request,
            response,
            cost=CostBreakdown(usd=0.01 * (i + 1), tier="flat", pricing_version="v"),
            attempt=1,
        )
    ledger.record_rollout(
        attribution=att,
        seed=7,
        model="m",
        rollout_uid="u1",
        usage=Usage(prompt_tokens=0, completion_tokens=0),
        cost=CostBreakdown(usd=0.0, tier="flat", pricing_version="rollout"),
        steps=3,
        success=True,
    )
    ledger.record_rollout(
        attribution=Attribution(phase="estimate", budget="search", arm="A", task_id="8"),
        seed=8,
        model="m",
        rollout_uid="u2",
        usage=Usage(prompt_tokens=0, completion_tokens=0),
        cost=CostBreakdown(usd=0.0, tier="flat", pricing_version="rollout"),
        steps=1,
        success=False,
    )
    totals = per_task_totals(read_ledger(ledger.path))
    assert totals["7"].rollouts == 1 and totals["7"].calls == 3
    assert abs(totals["7"].usd - 0.06) < 1e-12 and totals["7"].prompt_tokens == 600
    assert totals["8"].rollouts == 1 and totals["8"].usd == 0.0
