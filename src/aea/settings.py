"""Secrets, loaded only here, only from the environment or ``.env``.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/settings.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; the secret set is ``OPENROUTER_API_KEY`` (policy / consumer via
OpenRouter) and ``DEEPSEEK_API_KEY`` (induction), both optional so unit tests run with none.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from aea.errors import ConfigError


class Settings(BaseSettings):
    """Secrets and nothing else. Non-secret knobs live in the run config."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    openrouter_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None

    def require(self, name: str) -> SecretStr:
        """Return the named secret or raise :class:`ConfigError` naming the missing variable."""
        value = getattr(self, name, None)
        if not isinstance(value, SecretStr):
            raise ConfigError(
                f"missing secret {name.upper()}. Copy .env.example to .env and fill it in."
            )
        return value


def load_settings(env_file: Path | None = Path(".env")) -> Settings:
    """Load secrets from ``env_file`` (if it exists) and the process environment.

    Raises :class:`ConfigError` on an invalid value; never echoes values. The env file is bound
    through a subclass config because pydantic's dataclass-transform hides the ``_env_file``
    keyword from mypy.
    """

    class _BoundSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=env_file,
            env_file_encoding="utf-8",
            extra="ignore",
            case_sensitive=False,
            populate_by_name=True,
        )

    try:
        return _BoundSettings()
    except ValidationError as exc:
        bad = ", ".join(str(err["loc"][0]).upper() for err in exc.errors())
        raise ConfigError(f"invalid secret(s): {bad}") from exc


def mask_secret(value: str) -> str:
    """Return a display-safe form of a secret: first and last four characters only."""
    if len(value) > 10:
        return f"{value[:4]}***{value[-4:]}"
    return "***"
