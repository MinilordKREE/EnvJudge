"""Strict config base and the run-level configuration loaded from YAML.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/core/config.py (``StrictModel``, ``RetryConfig``, ``RunConfig``,
``load_run_config``, ``config_sha256``); ``StrictModel`` itself from scaleapi/vero @
0b0e86764d836c456aee5b8dff80d765fdbba77c (vero/src/vero/models.py lines 8-16; MIT)
License: MIT -- see THIRD_PARTY_NOTICES.md
Changes: package rename; the task-substrate models are dropped; ``LLMConfig`` describes an
OpenAI-compatible endpoint (OpenRouter or DeepSeek) with a provider pin instead of DeepSeek only.
The method's own frozen parameters live in :mod:`aea.config` (``AEAConfig``), not here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from aea.core.hashing import sha256_of
from aea.core.io import read_text
from aea.errors import ConfigError

CONFIG_SCHEMA_VERSION = 1

type RunKind = Literal["exploratory", "confirmatory"]
type ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and is immutable once built."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetryConfig(StrictModel):
    """Exponential backoff with jitter and a total wall-clock cap.

    Status codes 408, 409, 425, 429 and every 5xx are retried, as are connection errors and
    timeouts. 400, 401 and 403 are never retried. See :mod:`aea.llm.retry`.
    """

    max_attempts: int = Field(default=5, ge=1)
    initial_delay_s: float = Field(default=1.0, ge=0.0)
    max_delay_s: float = Field(default=30.0, ge=0.0)
    multiplier: float = Field(default=2.0, ge=1.0)
    jitter_s: float = Field(default=1.0, ge=0.0)
    total_timeout_s: float = Field(default=300.0, ge=0.0)
    retry_status_codes: tuple[int, ...] = (408, 409, 425, 429)


class LLMConfig(StrictModel):
    """One OpenAI-compatible endpoint. ``provider_pin`` is enforced on every response."""

    provider: Literal["openrouter", "deepseek", "fake"] = "openrouter"
    model: str = "qwen/qwen3-8b"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: Literal["OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"] = "OPENROUTER_API_KEY"
    provider_pin: str | None = "alibaba"
    """OpenRouter upstream provider slug (``provider.order`` with ``allow_fallbacks=false``); a
    response from any other provider aborts the call. ``None`` for endpoints without routing."""
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)
    thinking: bool | None = False
    """Three-state: ``None`` = send no reasoning parameter (provider default, identical for all
    arms); ``False`` = explicitly off (required on the Qwen path); ``True`` = on."""
    reasoning_effort: ReasoningEffort | None = None
    timeout_s: float = Field(default=120.0, gt=0.0)
    cost_tolerance: float = Field(default=1e-6, ge=0.0)
    """Maximum |upstream_cost - usd| before a pricing mismatch aborts the call (only when the
    endpoint reports ``usage.cost``)."""
    retry: RetryConfig = RetryConfig()


class RunConfig(StrictModel):
    schema_version: Literal[1]
    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    kind: RunKind = "exploratory"
    seed: int = 0
    require_clean_tree: bool
    policy: LLMConfig = LLMConfig()
    designer: LLMConfig = LLMConfig(
        provider="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        provider_pin=None,
        temperature=0.7,
        max_tokens=4096,
    )
    pricing_path: Path = Path("configs/pricing.yaml")
    runs_root: Path = Path("runs")

    @model_validator(mode="before")
    @classmethod
    def _default_require_clean_tree(cls, data: Any) -> Any:
        """Confirmatory runs require a clean tree unless the config says otherwise."""
        if isinstance(data, dict) and data.get("require_clean_tree") is None:
            data = dict(data)
            data["require_clean_tree"] = data.get("kind", "exploratory") == "confirmatory"
        return data


def load_run_config(path: Path) -> RunConfig:
    """Parse and validate a YAML run config.

    A missing file is an :class:`~aea.errors.InfraError`; bad YAML or a failed validation is a
    :class:`~aea.errors.ConfigError`.
    """
    text = read_text(path)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"run config {path} must be a mapping at top level")
    try:
        return RunConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid run config {path}:\n{exc}") from exc


def config_sha256(config: BaseModel) -> str:
    """Hash of a resolved config (post-validation, defaults applied), not of the file text."""
    return sha256_of(config.model_dump(mode="json"))
