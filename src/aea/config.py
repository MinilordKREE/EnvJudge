"""The method's frozen parameters: one ``AEAConfig`` whose hash goes into every manifest.

Spec: docs/spec/AEA_v2.md section 0 (budgets), section 1 (bands), section 2 (estimation), section 4
(dose rule), section 5 (stage /
probe), section 6 (certificates). No reference source: written fresh for aea.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from aea.core.config import StrictModel, config_sha256
from aea.core.io import read_text
from aea.errors import ConfigError

AEA_CONFIG_SCHEMA_VERSION = 1


class AEAConfig(StrictModel):
    schema_version: Literal[1] = 1
    # section 2 estimation
    confidence: float = Field(default=0.9, gt=0.5, lt=1.0)
    k_max: int = Field(default=16, ge=4)
    batch_first: int = Field(default=4, ge=1)
    batch_next: int = Field(default=2, ge=1)
    # section 1 bands
    band_t: tuple[float, float] = (0.4, 0.6)
    """Controller acceptance band (spec section 1)."""
    accept_successes: tuple[int, int] = (3, 5)
    """B_T expressed at K = dose_k_full: accept iff successes in this closed range (3-5 of 8)."""
    band_l: tuple[float, float] = (0.2, 0.8)
    """Downstream learnability band (spec section 1)."""
    learnable_successes: tuple[int, int] = (4, 12)
    """B_L expressed at K = confirm_k: learnable iff successes in this closed range (4-12 of 16)."""
    # section 0 budgets
    search_cap: int = Field(default=30, ge=1)
    confirm_k: int = Field(default=16, ge=1)
    # section 4 dose search
    dose_k_first: int = Field(default=4, ge=1)
    dose_k_full: int = Field(default=8, ge=2)
    dose_step: float = Field(default=0.25, gt=0.0, le=0.5)
    max_dose_evals: int = Field(default=4, ge=1)
    max_designer_families: int = Field(default=2, ge=0)
    # section 5 stage / probe
    candidate_fractions: tuple[float, ...] = (1.0, 0.75, 0.5, 0.25)
    max_candidates: int = Field(default=6, ge=1)
    n_failed_trajectories: int = Field(default=3, ge=1)
    probe_k: int = Field(default=4, ge=1)
    stage_budget: int = Field(default=100, ge=50)
    # section 6 certificates
    expert_attempts: int = Field(default=3, ge=1)
    hint_attempts: int = Field(default=3, ge=0)
    expert_max_steps: int = Field(default=50, ge=1)
    # runner
    policy_max_steps: int = Field(default=50, ge=1)

    @model_validator(mode="after")
    def _bands(self) -> AEAConfig:
        for name, (lo, hi) in (("band_t", self.band_t), ("band_l", self.band_l)):
            if not 0.0 <= lo < hi <= 1.0:
                raise ValueError(f"{name} must satisfy 0 <= lo < hi <= 1, got {(lo, hi)}")
        if self.dose_k_full < self.dose_k_first:
            raise ValueError("dose_k_full must be >= dose_k_first")
        for name, (lo, hi), k in (
            ("accept_successes", self.accept_successes, self.dose_k_full),
            ("learnable_successes", self.learnable_successes, self.confirm_k),
        ):
            if not 0 < lo <= hi < k:
                raise ValueError(f"{name} must satisfy 0 < lo <= hi < K={k}, got {(lo, hi)}")
        return self

    def accept_range(self) -> tuple[int, int]:
        """Successes out of ``dose_k_full`` that count as in-band (3-5 of 8 by default)."""
        return self.accept_successes

    def learnable_range(self) -> tuple[int, int]:
        """Successes out of ``confirm_k`` that count as learnable (4-12 of 16 by default)."""
        return self.learnable_successes


def aea_config_sha256(config: AEAConfig) -> str:
    return config_sha256(config)


def load_aea_config(path: Path | None = None) -> AEAConfig:
    """Defaults when ``path`` is ``None``; otherwise a strict YAML override."""
    if path is None:
        return AEAConfig()
    text = read_text(path)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    try:
        return AEAConfig.model_validate(raw or {})
    except ValidationError as exc:
        raise ConfigError(f"invalid AEA config {path}:\n{exc}") from exc
