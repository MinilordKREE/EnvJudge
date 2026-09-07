"""Versioned price table (``configs/pricing.yaml``) and usd computation.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/llm/pricing.py (``TierRates``, ``ModelPricing``, ``PeakSchedule``,
``PricingTable``, ``load_pricing``)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; models carry their own ``pricing_version`` and optional peak
schedule (only DeepSeek has one); the web-search section is dropped; cached prompt tokens are
priced at the cache-hit rate.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError

from aea.core.config import StrictModel
from aea.core.io import read_text
from aea.errors import ConfigError
from aea.llm.types import Usage

type PricingTier = Literal["peak", "off_peak", "flat"]


class TierRates(StrictModel):
    """USD per 1M tokens."""

    input_cache_hit: float = Field(ge=0.0)
    input_cache_miss: float = Field(ge=0.0)
    output: float = Field(ge=0.0)


class PeakSchedule(StrictModel):
    description: str
    weekdays: tuple[int, ...]
    utc_windows: tuple[tuple[time, time], ...]

    def is_peak(self, ts: datetime) -> bool:
        """Start inclusive, end exclusive, evaluated in UTC. Naive datetimes are rejected."""
        if ts.tzinfo is None:
            raise ConfigError("pricing needs a timezone-aware timestamp")
        utc = ts.astimezone(UTC)
        if utc.weekday() not in self.weekdays:
            return False
        clock = utc.time()
        return any(start <= clock < end for start, end in self.utc_windows)


class ModelPricing(StrictModel):
    pricing_version: str = Field(min_length=1)
    as_of: date
    source: str
    flat: TierRates | None = None
    peak: TierRates | None = None
    off_peak: TierRates | None = None
    schedule: PeakSchedule | None = None

    def rates_at(self, ts: datetime) -> tuple[PricingTier, TierRates]:
        if self.flat is not None:
            return "flat", self.flat
        if self.peak is None or self.off_peak is None or self.schedule is None:
            raise ConfigError("a model without flat rates needs peak, off_peak and schedule")
        tier: PricingTier = "peak" if self.schedule.is_peak(ts) else "off_peak"
        return tier, self.peak if tier == "peak" else self.off_peak


class CostBreakdown(StrictModel):
    usd: float
    tier: PricingTier
    pricing_version: str


class PricingTable(StrictModel):
    currency: Literal["USD"]
    unit: Literal["per_1m_tokens"]
    models: dict[str, ModelPricing]

    def pricing_for(self, model: str) -> ModelPricing:
        try:
            return self.models[model]
        except KeyError:
            known = ", ".join(sorted(self.models))
            raise ConfigError(f"no pricing for model {model!r}; known: {known}") from None

    def cost(self, model: str, usage: Usage, ts: datetime) -> CostBreakdown:
        """Cached and uncached prompt tokens are priced separately; reasoning tokens are part
        of ``completion_tokens`` and billed as output."""
        pricing = self.pricing_for(model)
        tier, rates = pricing.rates_at(ts)
        usd = (
            usage.cached_tokens * rates.input_cache_hit
            + usage.uncached_prompt_tokens * rates.input_cache_miss
            + usage.completion_tokens * rates.output
        ) / 1_000_000
        return CostBreakdown(usd=usd, tier=tier, pricing_version=pricing.pricing_version)


def load_pricing(path: Path) -> PricingTable:
    text = read_text(path)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in pricing file {path}: {exc}") from exc
    try:
        return PricingTable.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid pricing file {path}:\n{exc}") from exc
