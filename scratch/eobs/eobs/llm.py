"""LedgerLLMClient: observe-only wrapper around envharness's LiteLLMClient.

Why a wrapper: envharness's LoggingLLMClient records messages/response but not token usage, and
the ledger rule requires one row per LLM call with tokens and USD. This class calls the inner
client, reads `resp.raw.usage`, appends a ledger row, and returns the SAME ChatResponse object.
It never changes messages, tools, temperature or any other argument (unit-tested in tests/).

DeepSeek routing (non-thinking): litellm model `openai/deepseek-v4-pro`, `api_base=https://api.deepseek.com`,
`extra_body={"thinking": {"type": "disabled"}}`. The API key is exported by the launcher as
OPENAI_API_KEY (litellm's openai provider reads it), loaded via pydantic-settings; the YAML never holds it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from envharness.infra.llm import LLMClient
from envharness.infra.utils import import_symbol

from eobs.settings import PRICING_VERSION, tariff_at, usd_for

_LOCK = threading.Lock()


def _usage_from_raw(raw) -> dict:
    u = getattr(raw, "usage", None)
    if u is None and isinstance(raw, dict):
        u = raw.get("usage")
    if u is None:
        return {}
    get = (lambda k: getattr(u, k, None)) if not isinstance(u, dict) else (lambda k: u.get(k))
    details = get("prompt_tokens_details")
    cached = None
    if details is not None:
        cached = getattr(details, "cached_tokens", None) if not isinstance(details, dict) else details.get("cached_tokens")
    if cached is None:
        cached = get("prompt_cache_hit_tokens")
    comp_details = get("completion_tokens_details")
    reasoning = None
    if comp_details is not None:
        reasoning = getattr(comp_details, "reasoning_tokens", None) if not isinstance(comp_details, dict) else comp_details.get("reasoning_tokens")
    return {
        "prompt_tokens": int(get("prompt_tokens") or 0),
        "completion_tokens": int(get("completion_tokens") or 0),
        "cached_tokens": int(cached or 0),
        "reasoning_tokens": int(reasoning or 0),
    }


def _reasoning_content_present(raw) -> bool:
    try:
        msg = raw.choices[0].message
    except Exception:
        return False
    rc = getattr(msg, "reasoning_content", None)
    if rc is None and hasattr(msg, "get"):
        rc = msg.get("reasoning_content")
    if rc is None:
        extra = getattr(msg, "provider_specific_fields", None) or {}
        rc = extra.get("reasoning_content") if isinstance(extra, dict) else None
    return bool(rc)


PROVIDER_ALLOWLIST = {
    # api_key_env -> (allowed api_base values, required model prefix). Refuse construction otherwise: the key for one
    # provider must never be sent to another endpoint (E1-pilot extension, 2026-09-06; backward-compatible).
    "DEEPSEEK_API_KEY": ({"https://api.deepseek.com"}, "openai/deepseek"),
    "DASHSCOPE_API_KEY": ({"https://dashscope.aliyuncs.com/compatible-mode/v1", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"}, "openai/qwen"),
}


def _secret_for(api_key_env: str) -> str:
    from eobs.settings import secrets
    s = secrets()
    val = getattr(s, api_key_env.lower(), None)
    if val is None:
        raise ValueError(f"LedgerLLMClient: secret {api_key_env} is not configured")
    return val.get_secret_value()


class LedgerLLMClient(LLMClient):
    def __init__(self, inner_factory: str, inner_kwargs: dict, ledger_path: str, role: str = "",
                 run_id: str = "", phase: str = "", arm: str = "", api_key_env: str | None = None):
        cls = import_symbol(inner_factory)
        kw = dict(inner_kwargs)
        model, base = str(kw.get("model", "")), kw.get("api_base")
        if api_key_env is None:
            # Legacy path (E-obs): the DeepSeek key travels as OPENAI_API_KEY exported by the launcher.
            if base != "https://api.deepseek.com" or not model.startswith("openai/deepseek"):
                raise ValueError(f"LedgerLLMClient: refusing model/api_base {model!r} / {base!r}; expected openai/deepseek-* at https://api.deepseek.com")
            if "api_key" not in kw and os.environ.get("OPENAI_API_KEY"):
                kw["api_key"] = os.environ["OPENAI_API_KEY"]
        else:
            if api_key_env not in PROVIDER_ALLOWLIST:
                raise ValueError(f"LedgerLLMClient: unknown api_key_env {api_key_env!r}")
            bases, prefix = PROVIDER_ALLOWLIST[api_key_env]
            if base not in bases or not model.startswith(prefix):
                raise ValueError(f"LedgerLLMClient: refusing {api_key_env} with model/api_base {model!r} / {base!r}; allowed bases {sorted(bases)}, model prefix {prefix!r}")
            kw["api_key"] = _secret_for(api_key_env)     # per-call key for litellm; never from YAML, never logged
        self.inner: LLMClient = cls(**kw)
        self.model_id = getattr(self.inner, "model_id", kw.get("model", ""))
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.role, self.run_id, self.phase, self.arm = role, run_id, phase, arm
        self.api_key_env = api_key_env

    def chat(self, messages, tools=None, tool_choice="auto", temperature=0.7, max_tokens=None, **kwargs):
        t0 = time.time()
        error = None
        try:
            resp = self.inner.chat(messages, tools=tools, tool_choice=tool_choice, temperature=temperature,
                                   max_tokens=max_tokens, **kwargs)
        except Exception as e:  # log then re-raise unchanged
            error = f"{type(e).__name__}: {e}"[:300]
            self._append({"ok": False, "error": error, "latency_ms": int((time.time() - t0) * 1000)})
            raise
        usage = _usage_from_raw(getattr(resp, "raw", None))
        ts = time.time()
        tariff = tariff_at(ts)
        self._append({
            "ok": True, "latency_ms": int((ts - t0) * 1000), **usage,
            "reasoning_content_present": _reasoning_content_present(getattr(resp, "raw", None)),
            "tariff": tariff,
            "usd": usd_for(self.model_id, usage.get("prompt_tokens", 0), usage.get("cached_tokens", 0), usage.get("completion_tokens", 0), tariff),
            "usd_peak_bound": usd_for(self.model_id, usage.get("prompt_tokens", 0), usage.get("cached_tokens", 0), usage.get("completion_tokens", 0), "peak"),
            "n_messages": len(messages), "has_tools": bool(tools), "temperature": temperature,
        })
        return resp

    def _append(self, fields: dict) -> None:
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": self.run_id or os.environ.get("EOBS_RUN_ID", ""),
            "phase": self.phase or os.environ.get("EOBS_PHASE", ""),
            "arm": self.arm or os.environ.get("EOBS_ARM", ""),
            "task_id": os.environ.get("EOBS_TASK_ID", ""),
            "candidate_id": os.environ.get("EOBS_CANDIDATE_ID", ""),
            "seed": os.environ.get("EOBS_SEED", ""),
            "role": self.role, "model": self.model_id, "pid": os.getpid(),
            "pricing_version": (__import__("eobs.settings", fromlist=["PRICING_VERSION_QWEN"]).PRICING_VERSION_QWEN if "qwen" in str(self.model_id) else PRICING_VERSION), **fields,
        }
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with _LOCK:
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(line)


def ledger_totals(path: Path) -> dict:
    usd = usd_peak = 0.0
    calls = 0
    by_phase: dict[str, float] = {}
    bad = 0
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:   # a process killed mid-write leaves one truncated line; count, never drop the file
                bad += 1
                continue
            calls += 1
            usd += float(r.get("usd", 0.0) or 0.0)
            usd_peak += float(r.get("usd_peak_bound", 0.0) or 0.0)
            by_phase[r.get("phase", "")] = by_phase.get(r.get("phase", ""), 0.0) + float(r.get("usd", 0.0) or 0.0)
    return {"calls": calls, "usd": usd, "usd_peak_bound": usd_peak, "by_phase": by_phase, "bad_lines": bad}
