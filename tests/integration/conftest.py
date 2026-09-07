"""Integration tests need ALFWorld/TextWorld and the game data (LLM-free). Skipped otherwise."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

DATA = Path(os.environ.get("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data")))


def _available() -> bool:
    return importlib.util.find_spec("alfworld") is not None and DATA.exists()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _available():
        os.environ.setdefault("ALFWORLD_DATA", str(DATA))
        return
    skip = pytest.mark.skip(reason="ALFWorld or its game data is not installed")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
