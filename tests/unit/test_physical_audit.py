from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from envharness.infra.llm import Message
from pydantic import SecretStr

from aea.core.config import LLMConfig
from aea.errors import ConfigError, InfraError
from aea.llm.attribution import attributed, current_attribution
from aea.llm.client import build_wire_request
from aea.llm.physical_audit import AuditedPolicyClient, AuditedTransport, physical_summary
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from tests.conftest import ClientFactory, FakeTransport, make_completion, status_error


def request() -> ChatRequest:
    return ChatRequest(
        model="qwen/qwen3-8b",
        messages=(ChatMessage(role="user", content="synthetic"),),
        attribution=Attribution(phase="endpoint", budget="search", arm="A", task_id="9"),
    )


def records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for p in sorted(path.glob("attempts.*.jsonl"))
        for line in p.read_text().splitlines()
    ]


def test_exact_private_requests_responses_and_upper_cost(
    tmp_path: Path, pricing_path: Path
) -> None:
    completion = make_completion(cost=0.05)
    inner = FakeTransport([completion])
    audit = tmp_path / "private"
    wrapped = AuditedTransport(
        inner, audit, config=LLMConfig(), pricing_path=pricing_path, run_id="r", episode_uid="e"
    )
    wire = build_wire_request(request(), LLMConfig())
    with attributed(request().attribution, 9):
        assert wrapped(**wire) is completion
    started, returned = records(audit)
    assert started["attempt_id"] == returned["attempt_id"]
    assert started["run_id"] == "r" and started["episode_uid"] == "e"
    assert started["attribution"] == request().attribution.model_dump()
    raw_request = audit / started["raw_request_file"]
    raw_response = audit / returned["raw_response_file"]
    assert hashlib.sha256(raw_request.read_bytes()).hexdigest() == started["raw_request_sha256"]
    assert hashlib.sha256(raw_response.read_bytes()).hexdigest() == returned["raw_response_sha256"]
    raw = json.loads(raw_request.read_text())
    assert raw["wire"] == inner.calls[0] == wire
    assert "timeout" not in raw["body"] and "extra_body" not in raw["body"]
    assert raw["body"]["provider"]["allow_fallbacks"] is False
    assert raw_request.stat().st_mode & 0o777 == 0o600
    assert raw_response.stat().st_mode & 0o777 == 0o600
    summary = physical_summary(audit)
    assert summary["attempts"] == summary["returned"] == 1
    assert summary["inflight"] == 0 and summary["usd_cap"] is None
    assert summary["upstream_reported_usd"] == summary["conservative_total_usd"] == 0.05
    assert summary["returned_upper_rate_usd"] == pytest.approx((10 * 0.117 + 2 * 0.455) / 1e6)
    # Exceeding an estimate is an audit fact, never an added money stop or retry.
    assert summary["estimate_exceeded_count"] == 1
    assert "synthetic" not in json.dumps(summary)


def test_existing_client_retries_once_and_keeps_ambiguous_cost(
    tmp_path: Path,
    pricing_path: Path,
    make_client: ClientFactory,
) -> None:
    bundle = make_client([status_error(429), make_completion()])
    audit = tmp_path / "physical"
    bundle.client._transport = AuditedTransport(
        bundle.transport, audit, config=bundle.client.config, pricing_path=pricing_path
    )
    with attributed(request().attribution, 9):
        bundle.client.complete(request())
    summary = physical_summary(audit)
    assert summary["attempts"] == 2 and summary["returned"] == 1
    assert summary["ambiguous_failures"] == 1 and summary["inflight"] == 0
    assert summary["retained_ambiguous_estimate_usd"] > 0
    assert summary["conservative_total_usd"] > summary["returned_conservative_usd"]
    assert len(bundle.transport.calls) == 2 and bundle.sleeps == [0.5]
    starts = [r for r in records(audit) if r["status"] == "started"]
    assert starts[0]["attempt_id"] != starts[1]["attempt_id"]
    assert starts[0]["request_sha256"] == starts[1]["request_sha256"]


def test_invalid_usage_preserves_existing_client_failure(
    tmp_path: Path,
    pricing_path: Path,
    make_client: ClientFactory,
) -> None:
    bundle = make_client([make_completion(usage=False)])
    audit = tmp_path / "physical"
    bundle.client._transport = AuditedTransport(
        bundle.transport, audit, config=bundle.client.config, pricing_path=pricing_path
    )
    with attributed(request().attribution, 9), pytest.raises(InfraError) as error:
        bundle.client.complete(request())
    assert error.value.kind == "missing_usage"
    summary = physical_summary(audit)
    assert summary["returned"] == summary["invalid_usage"] == 1
    assert summary["invalid_usage_estimate_usd"] > 0
    assert summary["inflight"] == 0


@pytest.mark.parametrize(
    "override",
    [
        {"model": "other-model"},
        {"extra_headers": {"Authorization": "Bearer must-never-be-written"}},
        {"extra_body": {"provider": {"order": ["other"], "allow_fallbacks": True}}},
        {"max_tokens": 0},
    ],
)
def test_denied_wire_never_calls_transport_or_writes_secret(
    override: dict[str, Any],
    tmp_path: Path,
    pricing_path: Path,
) -> None:
    inner = FakeTransport([])
    wrapped = AuditedTransport(inner, tmp_path / "p", config=LLMConfig(), pricing_path=pricing_path)
    wire = build_wire_request(request(), LLMConfig()) | override
    with attributed(request().attribution, 9), pytest.raises(ConfigError):
        wrapped(**wire)
    assert not inner.calls and not records(tmp_path / "p")
    assert list((tmp_path / "p" / "raw").iterdir()) == []


def test_routing_and_unattributed_calls_are_refused(tmp_path: Path, pricing_path: Path) -> None:
    for cfg in (LLMConfig(provider_pin=None), LLMConfig(base_url="https://wrong.example")):
        with pytest.raises(ConfigError):
            AuditedTransport(FakeTransport([]), tmp_path, config=cfg, pricing_path=pricing_path)
    wrapped = AuditedTransport(
        FakeTransport([]), tmp_path, config=LLMConfig(), pricing_path=pricing_path
    )
    with pytest.raises(ConfigError, match="attribution"):
        wrapped(**build_wire_request(request(), LLMConfig()))


def test_deepseek_maximum_frozen_tier_ignores_cache_discount(
    tmp_path: Path,
    pricing_path: Path,
) -> None:
    cfg = LLMConfig(
        provider="deepseek",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        provider_pin=None,
    )
    inner = FakeTransport([make_completion(model=cfg.model, provider=None, cached=10)])
    wrapped = AuditedTransport(inner, tmp_path / "p", config=cfg, pricing_path=pricing_path)
    req = request().model_copy(update={"model": cfg.model})
    with attributed(req.attribution, 9):
        wrapped(**build_wire_request(req, cfg))
    summary = physical_summary(tmp_path / "p")
    assert summary["returned_upper_rate_usd"] == pytest.approx((10 * 0.44 + 2 * 1.32) / 1e6)
    assert summary["upstream_reported_count"] == 0


def test_threaded_instances_keep_unique_attempts_and_attribution(
    tmp_path: Path,
    pricing_path: Path,
) -> None:
    def call(task: int) -> None:
        wrapped = AuditedTransport(
            lambda **kw: make_completion(),
            tmp_path / "p",
            config=LLMConfig(),
            pricing_path=pricing_path,
        )
        attr = request().attribution.model_copy(update={"task_id": str(task)})
        with attributed(attr, task):
            wrapped(**build_wire_request(request(), LLMConfig()))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(call, range(32)))
    summary = physical_summary(tmp_path / "p")
    assert summary["attempts"] == summary["returned"] == 32
    assert summary["inflight"] == 0
    starts = [r for r in records(tmp_path / "p") if r["status"] == "started"]
    assert len({r["attempt_id"] for r in starts}) == 32
    assert all(int(r["attribution"]["task_id"]) == r["seed"] for r in starts)


def test_killed_worker_retains_started_attempt_and_process_journals(
    tmp_path: Path,
    pricing_path: Path,
) -> None:
    audit = tmp_path / "p"

    def child(kill: bool) -> None:
        def transport(**wire: Any) -> Any:
            if kill:
                os._exit(7)
            return make_completion()

        wrapped = AuditedTransport(transport, audit, config=LLMConfig(), pricing_path=pricing_path)
        with attributed(request().attribution, 9):
            wrapped(**build_wire_request(request(), LLMConfig()))

    ctx = multiprocessing.get_context("fork")
    workers = [ctx.Process(target=child, args=(kill,)) for kill in (False, True)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()
    assert {p.exitcode for p in workers} == {0, 7}
    assert len(list(audit.glob("attempts.*.jsonl"))) == 2
    summary = physical_summary(tmp_path, recursive=True)
    assert summary["attempts"] == 2 and summary["returned"] == summary["inflight"] == 1
    assert summary["inflight_estimate_usd"] > 0


def test_policy_factory_binds_overrides_without_changing_chat(
    tmp_path: Path,
    pricing_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aea.llm import envharness_client

    class Settings:
        def require(self, name: str) -> SecretStr:
            return SecretStr("synthetic-key-not-for-network")

    inner = FakeTransport([make_completion()])
    monkeypatch.setattr(envharness_client, "load_settings", lambda: Settings())
    monkeypatch.setattr(envharness_client, "make_openai_transport", lambda **kw: inner)
    monkeypatch.setenv("AEA_RUN_ID", "child-run")
    client = AuditedPolicyClient(
        audit_dir=str(tmp_path / "p"),
        llm=LLMConfig().model_dump(mode="json"),
        ledger_dir=str(tmp_path),
        pricing_path=str(pricing_path),
        phase="confirm",
        budget="eval",
    )
    with attributed(request().attribution, 9):
        response = client.chat([Message(role="user", content="synthetic")])
        assert current_attribution()[0].phase == "endpoint"
    assert response.content == "pong"
    started = records(tmp_path / "p")[0]
    assert started["attribution"]["phase"] == "confirm"
    assert started["attribution"]["budget"] == "eval"
    assert started["run_id"] == "child-run"
    assert all("synthetic-key" not in p.read_text() for p in (tmp_path / "p").rglob("*.json*"))


def test_returned_retry_attempts_are_both_counted(
    tmp_path: Path,
    pricing_path: Path,
    make_client: ClientFactory,
) -> None:
    bundle = make_client(
        [
            make_completion(finish_reason="insufficient_system_resource"),
            make_completion(),
        ]
    )
    audit = tmp_path / "physical"
    bundle.client._transport = AuditedTransport(
        bundle.transport,
        audit,
        config=bundle.client.config,
        pricing_path=pricing_path,
    )
    with attributed(request().attribution, 9):
        bundle.client.complete(request())
    summary = physical_summary(audit)
    assert summary["attempts"] == summary["returned"] == 2
    assert summary["returned_upper_rate_usd"] == pytest.approx(2 * (10 * 0.117 + 2 * 0.455) / 1e6)
    assert len(bundle.sleeps) == 1


def test_invalid_tokens_preserve_known_provider_charge(tmp_path: Path, pricing_path: Path) -> None:
    completion = make_completion(prompt_tokens=-1, cost=0.04)
    wrapped = AuditedTransport(
        FakeTransport([completion]), tmp_path / "p", config=LLMConfig(), pricing_path=pricing_path
    )
    with attributed(request().attribution, 9):
        assert wrapped(**build_wire_request(request(), LLMConfig())) is completion
    summary = physical_summary(tmp_path / "p")
    assert summary["invalid_usage"] == 1
    assert summary["upstream_reported_usd"] == 0.04
    assert summary["conservative_total_usd"] >= 0.04
