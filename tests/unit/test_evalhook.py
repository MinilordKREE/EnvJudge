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


def test_guard_error_is_never_retried_by_the_released_client() -> None:
    """The released retry sets (envharness/infra/llm.py: completion_with_retry and LiteLLMClient)
    are litellm's transient classes; GuardError must not be one of them."""
    from aea.evalhook import GuardError

    transient = tuple(
        cls
        for name in (
            "APIConnectionError",
            "RateLimitError",
            "ServiceUnavailableError",
            "InternalServerError",
            "Timeout",
        )
        if isinstance(cls := getattr(litellm, name, None), type)
    )
    assert transient and not issubclass(GuardError, transient)
    assert (
        isinstance(GuardError("x"), InfraError)
        and GuardError("x").kind == "guard"
        and not GuardError("x").retryable
    )


def test_wire_request_is_byte_identical_except_routing(
    tmp_path: Path, pricing: PricingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The released path's kwargs (messages, temperature, max_tokens, ...) reach litellm unchanged;
    the hook only adds/replaces the routing keys."""
    import json

    from aea.evalhook import ROUTING_KEYS

    released_kwargs = {
        "model": "openai/qwen/qwen3-8b",
        "messages": [
            {"role": "user", "content": "Step 3 of 50\n\nObservation: x\n\nHistory: a, b"}
        ],
        "temperature": 0.4,
        "max_tokens": 2048,
        "api_key": "released-key",
        "drop_params": True,
    }
    seen: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> Any:
        seen.append(kwargs)
        return _response(cost=(100 * 0.117 + 10 * 0.455) / 1e6)

    monkeypatch.setattr(litellm, "completion", fake_completion)
    original = install(_hook(tmp_path, pricing))
    try:
        litellm.completion(**released_kwargs)
    finally:
        litellm.completion = original
    plain = {k: v for k, v in released_kwargs.items() if k not in ROUTING_KEYS}
    routed = {k: v for k, v in seen[0].items() if k not in ROUTING_KEYS}
    assert json.dumps(routed, sort_keys=True) == json.dumps(plain, sort_keys=True)
    assert set(seen[0]) - set(released_kwargs) <= ROUTING_KEYS


def test_driver_installs_the_hook_for_every_arm(
    tmp_path: Path, pricing: PricingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aea.core.config import LLMConfig
    from aea.evaldriver import run_eval
    from aea.llm.attribution import current_attribution

    calls: list[tuple[str, list[str], bool, str]] = []

    def fake_main(argv: list[str]) -> int:
        wrapped = (
            litellm.completion.__name__ == "completion"
            and litellm.completion.__module__ == "aea.evalhook"
        )
        calls.append((current_attribution()[0].arm, argv, wrapped, current_attribution()[0].budget))
        return 0

    monkeypatch.setattr(litellm, "completion", lambda **kw: _response())
    for arm, banks in (
        ("N", {"nobank": None}),
        ("R", {"rigger": tmp_path / "r.jsonl"}),
        ("A", {"aea": tmp_path / "a.jsonl"}),
    ):
        hook = _hook(tmp_path / arm, pricing)
        rc = run_eval(
            arm=arm,
            conditions=banks,
            config_yaml=tmp_path / "eval.yaml",
            out_dir=tmp_path / arm,
            start_seeds=(0, 1000, 2000),
            concurrency=6,
            llm=LLMConfig(),
            pricing=pricing,
            run_id="r",
            eval_main=fake_main,
            hook=hook,
        )
        assert rc == 0
    assert (
        [c[0] for c in calls] == ["N", "R", "A"]
        and all(c[2] for c in calls)
        and {c[3] for c in calls} == {"eval"}
    )
    assert "--bank-overrides" not in calls[0][1] and f"rigger={tmp_path / 'r.jsonl'}" in calls[1][1]
    assert litellm.completion.__module__ != "aea.evalhook"  # restored after the run
    (tmp_path / "A" / "guard_failure.json").write_text(
        '{"problem": "pricing guard: x"}', encoding="utf-8"
    )
    with pytest.raises(InfraError, match="aborted by a guard"):
        run_eval(
            arm="A",
            conditions={"aea": None},
            config_yaml=tmp_path / "e.yaml",
            out_dir=tmp_path / "A",
            start_seeds=(0,),
            concurrency=1,
            llm=LLMConfig(),
            pricing=pricing,
            run_id="r",
            eval_main=fake_main,
            hook=_hook(tmp_path / "A", pricing),
        )


def test_embedding_is_routed_and_accounted(
    tmp_path: Path, pricing: PricingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from aea.evalhook import EMBED_MODEL
    from aea.llm.pricing import load_pricing

    seen: list[dict[str, Any]] = []

    def fake_embedding(**kwargs: Any) -> Any:
        seen.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=40), data=[{"embedding": [0.0]}])

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    monkeypatch.setattr(litellm, "completion", lambda **kw: _response())
    root = Path(__file__).resolve().parents[2]
    hook = EvalHook(
        config=LLMConfig(),
        ledger=Ledger(tmp_path / "ledger.jsonl", "r"),
        pricing=load_pricing(root / "configs" / "pricing.yaml"),
        run_dir=tmp_path,
        api_key="sk-test",
    )
    original = install(hook)
    try:
        litellm.embedding(model="gemini/gemini-embedding-001", input=["a", "b"])
    finally:
        litellm.completion = original
        monkeypatch.setattr(litellm, "embedding", fake_embedding)
    assert (
        seen[0]["model"] == f"openai/{EMBED_MODEL}"
        and seen[0]["api_base"] == "https://openrouter.ai/api/v1"
    )
    assert os.environ["EH_EMBED_MODEL"] == f"openai/{EMBED_MODEL}"
    row = read_ledger(tmp_path / "ledger.jsonl")[0]
    assert (
        row.model == EMBED_MODEL
        and row.prompt_tokens == 40
        and abs(row.usd - 40 * 0.15 / 1e6) < 1e-15
    )


def test_hook_default_labels_pool_threads(tmp_path: Path, pricing: PricingTable) -> None:
    """The released induction/eval fan out over pools that do not inherit the contextvar: rows
    from such threads carry the hook's default attribution, bound calls keep their own."""
    from concurrent.futures import ThreadPoolExecutor

    default = Attribution(phase="induce", budget="eval", arm="R", task_id="e0")
    hook = EvalHook(
        config=LLMConfig(),
        ledger=Ledger(tmp_path / "ledger.jsonl", "r"),
        pricing=pricing,
        run_dir=tmp_path,
        api_key="sk-test",
        default=(default, 7),
    )
    usd = (20 * 0.117 + 80 * 0.117 + 10 * 0.455) / 1e6
    with attributed(Attribution(phase="eval", budget="eval", arm="A", task_id="3"), seed=1):
        with ThreadPoolExecutor(max_workers=2) as pool:
            pool.submit(hook.account, _response(cost=usd), 1).result()
        hook.account(_response(cost=usd), latency_ms=1)
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert (rows[0].phase, rows[0].arm, rows[0].task_id, rows[0].seed) == ("induce", "R", "e0", 7)
    assert (rows[1].phase, rows[1].arm, rows[1].task_id) == ("eval", "A", "3")


def test_driver_passes_extra_argv(
    tmp_path: Path, pricing: PricingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aea.core.config import LLMConfig
    from aea.evaldriver import run_eval

    seen: list[list[str]] = []

    def record(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(litellm, "completion", lambda **kw: _response())
    run_eval(
        arm="R",
        conditions={"orig_rel": tmp_path / "o.jsonl"},
        config_yaml=tmp_path / "e.yaml",
        out_dir=tmp_path,
        start_seeds=(112,),
        concurrency=2,
        llm=LLMConfig(),
        pricing=pricing,
        run_id="r",
        eval_main=record,
        hook=_hook(tmp_path, pricing),
        extra_argv=("--n-ood", "22"),
    )
    assert seen[0][-2:] == ["--n-ood", "22"] and "--start-seeds" in seen[0]
    assert seen[0][seen[0].index("--start-seeds") + 1] == "112"
