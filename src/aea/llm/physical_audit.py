"""Private physical-attempt accounting without a USD cap or an additional retry loop.

Wrap the transport *inside* OpenAICompatibleClient: every existing retry receives a
fresh attempt ID. Raw request/response JSON belongs in a gitignored private run
folder. Hashes identify canonical JSON objects, not the SDK's byte serialization.
The frozen price file supplies conservative maximum-tier/cache-miss rates; these
estimates are distinct from provider-reported charges and the logical call ledger.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from aea.core.config import LLMConfig
from aea.errors import ConfigError
from aea.llm.attribution import attributed, current_attribution
from aea.llm.client import check_routing
from aea.llm.envharness_client import AeaLLMClient
from aea.llm.pricing import load_pricing

_ALLOWED = {
    "qwen/qwen3-8b": ("openrouter", "https://openrouter.ai/api/v1", "alibaba"),
    "deepseek-v4-pro": ("deepseek", "https://api.deepseek.com", None),
    "deepseek-v4-flash": ("deepseek", "https://api.deepseek.com", None),
}
_WIRE_KEYS = {
    "model",
    "messages",
    "max_tokens",
    "max_completion_tokens",
    "stream",
    "timeout",
    "temperature",
    "tools",
    "tool_choice",
    "extra_body",
    "reasoning_effort",
    "seed",
    "response_format",
    "top_p",
}
_EXTRA_KEYS = {"thinking", "usage", "provider", "reasoning"}


def _json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _write_private(path: Path, value: Any) -> str:
    data = _json(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return hashlib.sha256(data).hexdigest()


def _journal(path: Path, row: dict[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.write(_json(row) + b"\n")
        out.flush()
        os.fsync(out.fileno())
        fcntl.flock(out, fcntl.LOCK_UN)


def _number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
        and value >= 0
    )


class AuditedTransport:
    """Journal each call once and return/raise the wrapped transport's result unchanged.

    No monetary threshold is enforced. A start without a terminal record is charged
    to ``inflight_estimate_usd`` by physical_summary, including a killed worker.
    ``config`` binds the recipient/model; actual endpoint routing remains enforced
    by the existing client, which must construct the supplied transport from it.
    """

    def __init__(
        self,
        transport: Callable[..., Any],
        audit_dir: Path | str,
        *,
        config: LLMConfig,
        pricing_path: Path | str,
        run_id: str | None = None,
        episode_uid: str | None = None,
    ) -> None:
        check_routing(config)
        route = (config.provider, config.base_url.rstrip("/"), config.provider_pin)
        if _ALLOWED.get(config.model) != route:
            raise ConfigError("physical audit requires an authorized model, recipient and pin")
        self.transport, self.config = transport, config
        self.audit_dir = Path(audit_dir)
        self.raw_dir = self.audit_dir / "raw"
        self.raw_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.run_id, self.episode_uid = run_id, episode_uid
        pricing_path = Path(pricing_path)
        self.pricing_sha256 = hashlib.sha256(pricing_path.read_bytes()).hexdigest()
        price = load_pricing(pricing_path).pricing_for(config.model)
        tiers = [r for r in (price.flat, price.peak, price.off_peak) if r is not None]
        if not tiers:
            raise ConfigError("physical audit requires frozen price tiers")
        self.input_rate = max(max(r.input_cache_hit, r.input_cache_miss) for r in tiers)
        self.output_rate = max(r.output for r in tiers)
        self.pricing_version = price.pricing_version

    def __call__(self, **wire: Any) -> Any:
        # Reject transport headers/options, so authentication never enters raw files.
        if set(wire) - _WIRE_KEYS or wire.get("model") != self.config.model:
            raise ConfigError("physical audit refused unexpected wire options or model")
        extra = wire.get("extra_body") or {}
        if not isinstance(extra, dict) or set(extra) - _EXTRA_KEYS:
            raise ConfigError("physical audit refused unexpected extra request fields")
        if self.config.provider == "openrouter" and extra.get("provider") != {
            "order": ["alibaba"],
            "allow_fallbacks": False,
        }:
            raise ConfigError("physical audit requires the frozen Alibaba provider pin")
        output_bound = wire.get("max_tokens") or wire.get("max_completion_tokens")
        if isinstance(output_bound, bool) or not isinstance(output_bound, int) or output_bound <= 0:
            raise ConfigError("physical audit requires a positive output-token bound")
        attr, seed = current_attribution()
        if any(v == "none" for v in (attr.phase, attr.arm, attr.task_id)):
            raise ConfigError("physical audit requires explicit experiment attribution")
        body = {k: v for k, v in wire.items() if k not in ("timeout", "extra_body")}
        body.update(extra)
        input_bound = len(_json(wire)) + 4096
        estimate = (input_bound * self.input_rate + output_bound * self.output_rate) / 1e6
        attempt = uuid.uuid4().hex
        request_name = f"{attempt}.request.json"
        request_sha = _write_private(self.raw_dir / request_name, {"wire": wire, "body": body})
        meta = {
            "schema_version": 1,
            "attempt_id": attempt,
            "pid": os.getpid(),
            "run_id": self.run_id or os.environ.get("AEA_RUN_ID", "unset"),
            "episode_uid": self.episode_uid or os.environ.get("AEA_EPISODE_UID"),
            "attribution": attr.model_dump(mode="json"),
            "seed": seed,
            "model": self.config.model,
            "recipient": self.config.base_url.rstrip("/"),
            "provider_pin": self.config.provider_pin,
            "request_sha256": _hash(wire),
            "request_body_sha256": _hash(body),
            "raw_request_file": "raw/" + request_name,
            "raw_request_sha256": request_sha,
            "pricing_file_sha256": self.pricing_sha256,
            "pricing_version": self.pricing_version,
            "upper_input_rate_per_million": self.input_rate,
            "upper_output_rate_per_million": self.output_rate,
            "input_token_estimate": input_bound,
            "output_token_bound": output_bound,
            "attempt_estimate_usd": estimate,
        }
        journal = self.audit_dir / f"attempts.{os.getpid()}.jsonl"
        _journal(journal, {**meta, "status": "started", "started_at": time.time()})
        try:
            completion = self.transport(**wire)
        except BaseException as exc:
            _journal(
                journal,
                {
                    **meta,
                    "status": "ambiguous_failure",
                    "finished_at": time.time(),
                    "error_type": type(exc).__name__,
                    "retained_estimate_usd": estimate,
                },
            )
            raise
        # The existing client retains responsibility for malformed response/usage guards.
        raw = completion.model_dump(mode="json")
        response_name = f"{attempt}.response.json"
        response_sha = _write_private(self.raw_dir / response_name, raw)
        terminal: dict[str, Any] = {
            **meta,
            "status": "returned",
            "finished_at": time.time(),
            "response_sha256": _hash(raw),
            "raw_response_file": "raw/" + response_name,
            "raw_response_sha256": response_sha,
        }
        usage = raw.get("usage") or {}
        tokens_in, tokens_out, upstream = (
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("cost"),
        )
        valid_tokens = all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 0
            for v in (tokens_in, tokens_out)
        )
        valid_upstream = upstream is None or _number(upstream)
        terminal["upstream_usd"] = upstream if _number(upstream) else None
        if valid_tokens and valid_upstream:
            tokens_in, tokens_out = cast(int, tokens_in), cast(int, tokens_out)
            upper = (tokens_in * self.input_rate + tokens_out * self.output_rate) / 1e6
            terminal.update(
                {
                    "usage_valid": True,
                    "input_tokens": tokens_in,
                    "output_tokens": tokens_out,
                    "upstream_usd": upstream,
                    "upper_rate_usd": upper,
                    "conservative_usd": max(upstream or 0, upper),
                    "estimate_exceeded": tokens_in > input_bound
                    or tokens_out > output_bound
                    or max(upstream or 0, upper) > estimate,
                }
            )
        else:
            terminal.update(
                {
                    "usage_valid": False,
                    "retained_estimate_usd": max(estimate, terminal["upstream_usd"] or 0),
                }
            )
        _journal(journal, terminal)
        return completion


class AuditedPolicyClient(AeaLLMClient):
    """Serializable envharness client_factory with physical accounting in each worker."""

    def __init__(
        self,
        *,
        audit_dir: str,
        run_id: str | None = None,
        episode_uid: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._client._transport = AuditedTransport(
            self._client._transport,
            audit_dir,
            config=self.config,
            pricing_path=kwargs.get("pricing_path", "configs/pricing.yaml"),
            run_id=run_id,
            episode_uid=episode_uid,
        )

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        attr, seed = current_attribution()
        if self._phase is not None or self._budget is not None:
            attr = attr.model_copy(
                update={"phase": self._phase or attr.phase, "budget": self._budget or attr.budget}
            )
        with attributed(attr, seed):
            return super().chat(*args, **kwargs)


def physical_summary(audit_dir: Path | str, *, recursive: bool = False) -> dict[str, Any]:
    """Allowlisted cost/count summary; raw material is never included.

    Failed and killed attempts retain a conservative estimate, not an asserted
    charge. Missing/invalid usage is tracked separately. The logical ledger's
    time/cache-aware USD must be reported separately by the experiment driver.
    """
    root = Path(audit_dir)
    starts: dict[str, dict[str, Any]] = {}
    terminals: dict[str, dict[str, Any]] = {}
    paths = root.rglob("attempts.*.jsonl") if recursive else root.glob("attempts.*.jsonl")
    incomplete_lines = 0
    for path in sorted(paths):
        data = path.read_bytes()
        lines = data.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if not line.endswith(b"\n") and i == len(lines) - 1:
                incomplete_lines += 1
                continue
            row = json.loads(line)
            dest = starts if row["status"] == "started" else terminals
            if row["attempt_id"] in dest:
                raise ConfigError("duplicate physical attempt journal event")
            dest[row["attempt_id"]] = row
    if set(terminals) - set(starts):
        raise ConfigError("physical attempt terminal event lacks a start")
    result: dict[str, Any] = {
        "attempts": len(starts),
        "returned": 0,
        "ambiguous_failures": 0,
        "invalid_usage": 0,
        "inflight": 0,
        "upstream_reported_count": 0,
        "upstream_reported_usd": 0.0,
        "returned_upper_rate_usd": 0.0,
        "returned_conservative_usd": 0.0,
        "retained_ambiguous_estimate_usd": 0.0,
        "invalid_usage_estimate_usd": 0.0,
        "inflight_estimate_usd": 0.0,
        "estimate_exceeded_count": 0,
        "incomplete_journal_lines": incomplete_lines,
        "pricing_file_sha256": sorted({r["pricing_file_sha256"] for r in starts.values()}),
        "usd_cap": None,
    }
    for attempt, start in starts.items():
        terminal = terminals.get(attempt)
        if terminal is None:
            result["inflight"] += 1
            result["inflight_estimate_usd"] += start["attempt_estimate_usd"]
        elif terminal["status"] == "ambiguous_failure":
            result["ambiguous_failures"] += 1
            result["retained_ambiguous_estimate_usd"] += terminal["retained_estimate_usd"]
        elif terminal["status"] == "returned":
            result["returned"] += 1
            if terminal["upstream_usd"] is not None:
                result["upstream_reported_count"] += 1
                result["upstream_reported_usd"] += terminal["upstream_usd"]
            if not terminal["usage_valid"]:
                result["invalid_usage"] += 1
                result["invalid_usage_estimate_usd"] += terminal["retained_estimate_usd"]
                continue
            result["returned_upper_rate_usd"] += terminal["upper_rate_usd"]
            result["returned_conservative_usd"] += terminal["conservative_usd"]
            result["estimate_exceeded_count"] += int(terminal["estimate_exceeded"])
        else:
            raise ConfigError("unknown physical attempt terminal status")
    result["conservative_total_usd"] = sum(
        result[key]
        for key in (
            "returned_conservative_usd",
            "retained_ambiguous_estimate_usd",
            "invalid_usage_estimate_usd",
            "inflight_estimate_usd",
        )
    )
    return result
