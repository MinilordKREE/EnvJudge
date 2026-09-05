"""Secrets, paths and pricing for E-obs. Secrets only via pydantic-settings (EnvJudge/.env); never logged."""

from __future__ import annotations

import functools
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EOBS_ROOT = Path(__file__).resolve().parent.parent            # scratch/eobs
REPO_ROOT = EOBS_ROOT.parent.parent                             # EnvJudge
ENVHARNESS_ROOT = REPO_ROOT / "third_party" / "envharness"
RESULTS = EOBS_ROOT / "results" / "eobs"
WORK = EOBS_ROOT / "work"

DEEPSEEK_API_BASE = "https://api.deepseek.com"
MODEL_PRO = "deepseek-v4-pro"                                   # DeepSeek model id
LITELLM_MODEL_PRO = "openai/deepseek-v4-pro"                    # litellm route (OpenAI-compatible)

# USD per 1M tokens; same numbers and version tag as the switchHarness pilot ledger (pricing page read 2026-09-03).
PRICING_VERSION = "deepseek-pricing-2026-09-03"
PRICES = {
    "deepseek-v4-pro": {"peak": {"miss": 1.32, "hit": 0.044, "out": 3.96}, "offpeak": {"miss": 0.66, "hit": 0.022, "out": 1.98}},
    "deepseek-v4-flash": {"peak": {"miss": 0.44, "hit": 0.014, "out": 1.32}, "offpeak": {"miss": 0.22, "hit": 0.007, "out": 0.66}},
}
BUDGET_HARD_USD = 120.0
BUDGET_SOFT_USD = 80.0


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(REPO_ROOT / ".env"),), env_file_encoding="utf-8", extra="ignore")
    deepseek_api_key: SecretStr


@functools.lru_cache(maxsize=1)
def secrets() -> Secrets:
    return Secrets()  # type: ignore[call-arg]


def tariff_at(ts: float) -> str:
    """DeepSeek peak = 01:00-04:00 and 06:00-10:00 UTC, Monday-Friday."""
    import datetime as dt

    t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    if t.weekday() >= 5:
        return "offpeak"
    h = t.hour + t.minute / 60
    return "peak" if (1 <= h < 4) or (6 <= h < 10) else "offpeak"


def usd_for(model: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int, tariff: str) -> float:
    key = model.split("/", 1)[-1]
    p = PRICES.get(key) or PRICES["deepseek-v4-pro"]
    p = p[tariff]
    return (max(prompt_tokens - cached_tokens, 0) * p["miss"] + cached_tokens * p["hit"] + completion_tokens * p["out"]) / 1e6
