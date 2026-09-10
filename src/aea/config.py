"""The method's constants (docs/spec/AEA_v0.2.md, "Six method constants") and the implementation
block.

``AEAConfig`` carries exactly the six constants of the box — B_T, B_L, K, the accept range, the
probe (first batch, full batch) and the cap — plus ``impl``, the implementation details the method
section does not mention (estimator batch schedule and stopping confidence, bisection limit,
proposer cap, candidate-state construction, oracle limits, the staged-session step budget). The
hash of the whole config goes into every run manifest.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from aea.core.config import StrictModel, config_sha256
from aea.core.io import read_text
from aea.errors import ConfigError

AEA_CONFIG_SCHEMA_VERSION = 2


class ImplConfig(StrictModel):
    """Implementation constants (not method constants)."""

    batch_first: int = Field(default=4, ge=1)
    batch_next: int = Field(default=2, ge=1)
    confidence: float = Field(default=0.9, gt=0.5, lt=1.0)
    """Estimator: first batch, then batches of ``batch_next`` until P(regime) >= confidence or K."""
    max_bisections: int = Field(default=4, ge=1)
    order_tolerance: float = Field(default=0.2, ge=0.0, le=1.0)
    """Bracket: a higher dose whose success rate exceeds a lower dose's by more than this stops the
    family for the task (order violation); 0.2 is below one rollout in four, so a 2/8 at d = 1
    against a 0/4 at a lower dose already counts."""
    prior_min_tasks: int = Field(default=5, ge=1)
    prior_min_rate: float = Field(default=0.9, ge=0.0, le=1.0)
    """A family with leverage rate >= prior_min_rate over >= prior_min_tasks starts its bracket at
    its last accepted dose instead of the midpoint."""
    proposer_cap: int = Field(default=2, ge=0)
    n_failed_rollouts: int = Field(default=3, ge=1)
    max_candidates: int = Field(default=6, ge=1)
    stage_budget: int = Field(default=100, ge=50)
    oracle_attempts: int = Field(default=3, ge=1)
    oracle_max_steps: int = Field(default=50, ge=1)
    policy_max_steps: int = Field(default=50, ge=1)


class AEAConfig(StrictModel):
    schema_version: Literal[2] = 2
    band_t: tuple[float, float] = (0.4, 0.6)
    """Target band B_T: the accept range is B_T expressed at ``probe[1]`` rollouts."""
    band_l: tuple[float, float] = (0.2, 0.8)
    """Learnable band B_L, read at K confirmation rollouts (outside the method's decisions)."""
    k: int = Field(default=16, ge=4)
    """Rollouts per task for the estimate (early stop) and for a confirmation."""
    accept: tuple[int, int] = (3, 5)
    """Accept iff successes in this closed range out of ``probe[1]``."""
    probe: tuple[int, int] = (4, 8)
    """The 4 -> 8 rule: first batch, full batch."""
    cap: int = Field(default=30, ge=1)
    """Policy rollouts per task, all budgets of the method."""
    impl: ImplConfig = ImplConfig()

    @model_validator(mode="after")
    def _consistent(self) -> AEAConfig:
        lo, hi = self.band_t
        if not 0.0 <= lo < hi <= 1.0:
            raise ValueError("band_t must satisfy 0 <= lo < hi <= 1")
        lo_l, hi_l = self.band_l
        if not 0.0 <= lo_l < hi_l <= 1.0:
            raise ValueError("band_l must satisfy 0 <= lo < hi <= 1")
        first, full = self.probe
        if not 1 <= first < full:
            raise ValueError("probe must be (first, full) with 1 <= first < full")
        a, b = self.accept
        if not 1 <= a <= b < full:
            raise ValueError("accept must lie strictly inside (0, full)")
        return self

    def learnable_range(self) -> tuple[int, int]:
        """Successes out of K that count as learnable (4-12 of 16 by default)."""
        lo, hi = self.band_l
        return math.ceil(lo * self.k), math.floor(hi * self.k)

    def learnable(self, successes: int, n: int | None = None) -> bool:
        n = self.k if n is None else n
        lo, hi = self.band_l
        return n > 0 and lo <= successes / n <= hi


def aea_config_sha256(config: AEAConfig) -> str:
    return config_sha256(config)


def load_aea_config(path: Path) -> AEAConfig:
    try:
        raw = yaml.safe_load(read_text(path)) or {}
        return AEAConfig.model_validate(raw)
    except (ValidationError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid aea config {path}: {exc}") from exc
