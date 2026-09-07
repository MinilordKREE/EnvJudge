from __future__ import annotations

from pathlib import Path

import pytest

from aea.budget import Budget
from aea.config import AEAConfig, aea_config_sha256, load_aea_config
from aea.errors import BudgetExhausted, ConfigError


def test_aea_config_defaults_and_ranges() -> None:
    cfg = AEAConfig()
    assert cfg.accept_range() == (3, 5) and cfg.learnable_range() == (4, 12)
    assert cfg.search_cap == 30 and cfg.k_max == 16 and cfg.stage_budget == 100
    assert aea_config_sha256(cfg) == aea_config_sha256(AEAConfig())
    assert aea_config_sha256(cfg) != aea_config_sha256(AEAConfig(search_cap=31))
    with pytest.raises(ValueError):
        AEAConfig(band_t=(0.6, 0.4))


def test_load_aea_config(tmp_path: Path) -> None:
    assert load_aea_config(None) == AEAConfig()
    path = tmp_path / "aea.yaml"
    path.write_text("search_cap: 20\n", encoding="utf-8")
    assert load_aea_config(path).search_cap == 20
    path.write_text("bogus: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_aea_config(path)


def test_budget_cap_is_hard_and_per_task() -> None:
    budget = Budget(search_cap=30)
    budget.charge("t1", 10, budget="search", phase="estimate")
    budget.charge("t1", 16, budget="search", phase="dose")
    assert budget.can_afford("t1", 4) and not budget.can_afford("t1", 5)
    with pytest.raises(BudgetExhausted) as info:
        budget.charge("t1", 8, budget="search", phase="dose")
    assert info.value.spent == 26 and info.value.cap == 30 and info.value.task_id == "t1"
    assert budget.account("t1").search_spent == 26  # nothing charged past the cap
    assert budget.account("t1").status == "budget_cap_hit"
    budget.charge("t1", 16, budget="confirm", phase="confirm")  # separate ledger, never capped
    budget.charge("t2", 30, budget="search", phase="estimate")  # no reallocation across tasks
    assert budget.totals() == {"search": 56, "confirm": 16}
    rows = budget.accounting_rows()
    assert {(r["task_id"], r["budget"], r["phase"]) for r in rows} == {
        ("t1", "search", "estimate"),
        ("t1", "search", "dose"),
        ("t1", "confirm", "confirm"),
        ("t2", "search", "estimate"),
    }
