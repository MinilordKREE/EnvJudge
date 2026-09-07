"""Secrets and configuration.

Secrets come ONLY through pydantic-settings (env var or EnvJudge/.env). The key is a
SecretStr and is never written to any log, ledger or result file.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EMIN_ROOT = Path(__file__).resolve().parent.parent          # scratch/emin
REPO_ROOT = EMIN_ROOT.parent.parent                          # EnvJudge


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(EMIN_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    deepseek_api_key: SecretStr


@functools.lru_cache(maxsize=1)
def secrets() -> Secrets:
    return Secrets()  # type: ignore[call-arg]


@functools.lru_cache(maxsize=1)
def config() -> dict:
    with open(EMIN_ROOT / "configs" / "emin.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    for key in ("results_dir", "work_dir", "parent_minus_skill"):
        cfg[key] = str((EMIN_ROOT / cfg[key]).resolve())
    return cfg


def ensure_pilot_importable() -> None:
    """Make `pilot.*`, `rethinkskill*` importable (switchHarness venv + repo root)."""
    import sys

    root = config()["switchharness_root"]
    if root not in sys.path:
        sys.path.insert(0, root)
