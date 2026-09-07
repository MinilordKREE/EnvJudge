"""Minimal DeepSeek chat client for rollouts (temperature 0.7, thinking disabled, seed).

The pilot's clients hard-code temperature 0 and cannot be changed, so this is a separate
thin client. Every attempt writes one ledger row (results/emin/ledger.jsonl); no response
caching of any kind. Retries only on transient faults (network, timeout, HTTP 429/5xx).
"""

from __future__ import annotations

import datetime as dt
import json
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from emin.settings import config, secrets

_LEDGER_LOCK = threading.Lock()


def tariff_at(ts: float) -> str:
    """DeepSeek peak = 01:00-04:00 and 06:00-10:00 UTC, Monday-Friday; otherwise off-peak."""
    t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    if t.weekday() >= 5:
        return "offpeak"
    h = t.hour + t.minute / 60
    return "peak" if (1 <= h < 4) or (6 <= h < 10) else "offpeak"


def usd_for(model: str, usage: dict, tariff: str) -> float:
    p = config()["prices"][model][tariff]
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    hit = int(usage.get("prompt_cache_hit_tokens", 0) or 0)
    out = int(usage.get("completion_tokens", 0) or 0)
    return (max(prompt - hit, 0) * p["miss"] + hit * p["hit"] + out * p["out"]) / 1e6


class Ledger:
    """Append-only JSONL ledger; also tracks cumulative applicable-tariff spend."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.total_usd = 0.0
        self.total_usd_peak_bound = 0.0
        self.calls = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.total_usd += float(row.get("usd", 0.0))
                    self.total_usd_peak_bound += float(row.get("usd_peak_bound", 0.0))
                    self.calls += 1

    def resync(self) -> None:
        """Re-sum the shared ledger file (cheap; several arm processes may append concurrently)."""
        with _LEDGER_LOCK:
            usd = usd_peak = 0.0
            calls = 0
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        row = json.loads(line)
                        usd += float(row.get("usd", 0.0)); usd_peak += float(row.get("usd_peak_bound", 0.0)); calls += 1
            self.total_usd, self.total_usd_peak_bound, self.calls = usd, usd_peak, calls

    def append(self, row: dict) -> None:
        with _LEDGER_LOCK:
            self.total_usd += float(row.get("usd", 0.0))
            self.total_usd_peak_bound += float(row.get("usd_peak_bound", 0.0))
            self.calls += 1
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class BudgetStop(RuntimeError):
    pass


@dataclass
class Completion:
    ok: bool
    text: str
    usage: dict
    model: str
    http_status: int | None
    failure_class: str | None
    failure: str
    attempts: int
    wall_seconds: float


class Client:
    def __init__(self, ledger: Ledger, *, soft_ok: bool = False):
        cfg = config()
        self.cfg = cfg
        self.base_url = cfg["api"]["base_url"].rstrip("/")
        self.timeout = int(cfg["api"]["timeout_seconds"])
        self.retries = int(cfg["api"]["retries"])
        self.backoff = list(cfg["api"]["backoff_seconds"])
        self.ledger = ledger
        self.soft_ok = soft_ok
        self._key = secrets().deepseek_api_key.get_secret_value()

    def _gate(self) -> None:
        b = self.cfg["budget"]
        self.ledger.resync()   # other arm processes append to the same ledger file
        if self.ledger.total_usd >= float(b["hard_usd"]):
            raise BudgetStop(f"hard budget reached: USD {self.ledger.total_usd:.2f} >= {b['hard_usd']}")
        if self.ledger.total_usd >= float(b["soft_usd"]) and not self.soft_ok:
            raise BudgetStop(f"soft budget reached: USD {self.ledger.total_usd:.2f} >= {b['soft_usd']} (owner approval required)")

    def complete(self, *, model: str, prompt: str, temperature: float, seed: int | None, meta: dict) -> Completion:
        self._gate()
        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "thinking": {"type": "disabled"},
        }
        if seed is not None:
            payload["seed"] = int(seed)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = self.base_url + "/chat/completions"
        t_start = time.time()
        failure_class, failure, status, text, usage = None, "", None, "", {}
        for attempt in range(1, self.retries + 2):
            t0 = time.time()
            failure_class, failure, status, text, usage = None, "", None, "", {}
            try:
                req = Request(url, data=body, method="POST", headers={
                    "Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                    "User-Agent": "envjudge-emin/0.1"})
                with urlopen(req, timeout=self.timeout) as h:
                    status = int(h.status)
                    raw = h.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw)
                content = parsed["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty content")
                text = content
                usage = parsed.get("usage", {}) or {}
            except HTTPError as exc:
                status = exc.code
                failure_class = "provider_http_error"
                failure = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[-300:]}"
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                failure_class = "target_timeout" if isinstance(exc, (TimeoutError, socket.timeout)) else "transport_error"
                failure = f"{type(exc).__name__}: {exc}"[:300]
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                failure_class = "response_schema_error"
                failure = f"{type(exc).__name__}: {exc}"[:300]
            ts = time.time()
            tariff = tariff_at(ts)
            row = {
                "ts": dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                **meta, "model": model, "attempt": attempt, "http_status": status,
                "ok": failure_class is None, "failure_class": failure_class, "failure": failure.replace(self._key, "<redacted>"),
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens", 0) or 0),
                "tariff": tariff,
                "usd": usd_for(model, usage, tariff) if usage else 0.0,
                "usd_peak_bound": usd_for(model, usage, "peak") if usage else 0.0,
                "wall_seconds": round(ts - t0, 3),
            }
            self.ledger.append(row)
            transient = failure_class in ("transport_error", "target_timeout") or (
                failure_class == "provider_http_error" and status is not None and (status == 429 or status >= 500))
            if failure_class is None or not transient or attempt > self.retries:
                break
            time.sleep(self.backoff[min(attempt - 1, len(self.backoff) - 1)])
        return Completion(ok=failure_class is None, text=text.replace(self._key, "<redacted>"), usage=usage, model=model,
                          http_status=status, failure_class=failure_class, failure=failure, attempts=attempt,
                          wall_seconds=round(time.time() - t_start, 3))
