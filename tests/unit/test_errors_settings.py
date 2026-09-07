from __future__ import annotations

import os
from pathlib import Path

import pytest

from aea.errors import BudgetExhausted, ConfigError, InfraError, TaskFailure
from aea.settings import load_settings, mask_secret


def test_error_families_are_distinct() -> None:
    infra = InfraError("x", kind="rate_limit", status_code=429, retryable=True, attempts=2)
    assert "rate_limit" in str(infra) and "429" in str(infra)
    exhausted = BudgetExhausted("cap", budget="search", cap=30, spent=30, task_id="7")
    assert isinstance(exhausted, TaskFailure) and not isinstance(exhausted, InfraError)
    assert exhausted.kind == "budget_exhausted" and exhausted.budget == "search"
    assert not issubclass(ConfigError, TaskFailure)


def test_settings_optional_and_require(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = load_settings(tmp_path / "absent.env")
    assert settings.openrouter_api_key is None
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        settings.require("openrouter_api_key")
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-or-test-1234567890\n", encoding="utf-8")
    loaded = load_settings(env)
    assert loaded.require("openrouter_api_key").get_secret_value().endswith("7890")
    assert "sk-or" not in repr(loaded)
    assert os.environ.get("OPENROUTER_API_KEY") is None


def test_mask_secret() -> None:
    assert mask_secret("sk-abcdefghijkl") == "sk-a***ijkl"
    assert mask_secret("short") == "***"
