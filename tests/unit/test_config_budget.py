"""AEAConfig (six method constants + impl) and the one budget (docs/spec/AEA_v0.2.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aea.budget import Budget
from aea.config import AEAConfig, ImplConfig, aea_config_sha256, load_aea_config
from aea.errors import BudgetExhausted, ConfigError


def test_aea_config_six_constants_and_impl() -> None:
    cfg = AEAConfig()
    assert cfg.band_t == (0.4, 0.6) and cfg.band_l == (0.2, 0.8) and cfg.k == 16
    assert cfg.accept == (3, 5) and cfg.probe == (4, 8) and cfg.cap == 30
    assert cfg.learnable_range() == (4, 12) and cfg.learnable(4) and not cfg.learnable(13)
    assert set(AEAConfig.model_fields) == {
        "schema_version",
        "band_t",
        "band_l",
        "k",
        "accept",
        "probe",
        "cap",
        "impl",
    }
    assert cfg.impl.max_bisections == 4 and cfg.impl.proposer_cap == 2
    assert aea_config_sha256(cfg) == aea_config_sha256(AEAConfig())
    assert aea_config_sha256(cfg) != aea_config_sha256(AEAConfig(cap=31))
    assert aea_config_sha256(cfg) != aea_config_sha256(AEAConfig(impl=ImplConfig(max_bisections=3)))
    with pytest.raises(ValueError):
        AEAConfig(band_t=(0.6, 0.4))
    with pytest.raises(ValueError):
        AEAConfig(accept=(0, 5))


def test_load_aea_config(tmp_path: Path) -> None:
    path = tmp_path / "aea.yaml"
    path.write_text("cap: 20\nimpl:\n  proposer_cap: 0\n", encoding="utf-8")
    cfg = load_aea_config(path)
    assert cfg.cap == 20 and cfg.impl.proposer_cap == 0
    path.write_text("search_cap: 20\n", encoding="utf-8")  # a v0.1 field name is rejected
    with pytest.raises(ConfigError):
        load_aea_config(path)


def test_budget_cap_is_hard_and_per_task() -> None:
    budget = Budget(cap=30)
    budget.charge("t1", 10, phase="estimate")
    budget.charge("t1", 16, phase="dose:footer_mask")
    assert budget.can_afford("t1", 4) and not budget.can_afford("t1", 5)
    with pytest.raises(BudgetExhausted) as info:
        budget.charge("t1", 8, phase="dose:footer_mask")
    assert info.value.spent == 26 and info.value.cap == 30 and info.value.task_id == "t1"
    assert budget.account("t1").spent == 26  # nothing charged past the cap
    budget.charge("t2", 30, phase="estimate")  # no reallocation across tasks
    budget.refund("t2", 2, phase="estimate")  # errored rollouts come back
    assert budget.totals() == {"t1": 26, "t2": 28} and budget.account("t2").infra_errors == 2
    rows = budget.accounting_rows()
    assert {r["budget"] for r in rows} == {"search"}
    assert sum(int(r["n"]) for r in rows if r["task_id"] == "t2") == 28  # type: ignore[call-overload]
