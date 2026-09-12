"""Families: library, proposer validation, leverage table (docs/spec/AEA_v0.2.md)."""

from __future__ import annotations

from typing import Any

from envharness.core.types import Candidate

from aea.families import (
    LIBRARY,
    FamilyContext,
    FooterMask,
    HorizonSqueeze,
    LeverageTable,
    ProposedFamily,
    footer_masked,
    horizon_m,
    parse_proposals,
    validate_rules_template,
)

GOOD = """
class _Rules(Rules):
    DOSE = __DOSE__

    def filter_observation(self, obs, env_state):
        if self.DOSE > 0.5:
            return Observation(text=obs.text.replace("Admissible", "admissible"), data=obs.data)
        return obs
"""


def test_library_makes_runnable_candidates() -> None:
    ctx = FamilyContext(task_id="7", success_lengths=(9, 12, 15))
    fm = FooterMask().make(0.5, ctx)
    hs = HorizonSqueeze().make(1.0, ctx)
    assert fm is not None and "DOSE = 0.5" in fm.rules_code and "TASK_ID = '7'" in fm.rules_code
    assert hs is not None and "M = 9" in hs.rules_code  # d = 1 -> shortest success
    assert HorizonSqueeze().make(0.5, FamilyContext("7")) is None  # no successes: infeasible
    assert [f.name for f in LIBRARY] == ["footer_mask", "horizon_squeeze"]
    assert (
        horizon_m((9, 12, 15), 0.0) == 15
        and sum(footer_masked("7", s, 0.5) for s in range(1000)) > 300
    )


def test_validate_and_parse_proposals() -> None:
    assert validate_rules_template(GOOD).ok
    bad = validate_rules_template("class _Rules(Rules):\n    pass\n")
    assert not bad.ok and any("DOSE" in r for r in bad.reasons)
    families, rejected = parse_proposals(
        {
            "families": [
                {"name": "case_flip", "axis": "O", "rules_code": GOOD},
                {"name": "footer_mask", "axis": "O", "rules_code": GOOD},
                {"name": "broken", "axis": "T", "rules_code": "def x(:"},
                {"name": "third", "axis": "O", "rules_code": GOOD},
            ],
            "ranking": ["case_flip"],
        },
        cap=2,
    )
    assert [f.name for f in families] == ["case_flip"]  # cap 2: the second slot was the duplicate
    assert any("duplicate" in r for r in rejected)
    made = families[0].make(0.75, FamilyContext("3"))
    assert isinstance(made, Candidate) and "DOSE = 0.75" in made.rules_code
    assert isinstance(families[0], ProposedFamily) and families[0].source == "llm"


def test_leverage_table_orders_and_seeds_the_bracket() -> None:
    lt = LeverageTable()
    fams: list[Any] = [FooterMask(), HorizonSqueeze()]
    assert [f.name for f in lt.order(fams)] == ["footer_mask", "horizon_squeeze"]  # cold start
    for _ in range(5):
        lt.record_leverage("footer_mask", False)  # no effect on 5 tasks
        lt.record_leverage("horizon_squeeze", True)
    assert [f.name for f in lt.order(fams)] == ["horizon_squeeze", "footer_mask"]
    assert lt.bracket_seed("horizon_squeeze") == (0.0, 1.0)  # no population data
    # the E3 footer-mask walk on one task: 1.0 too_hard, 0.5 / 0.75 / 0.875 too_easy
    for d, v in ((1.0, "too_hard"), (0.5, "too_easy"), (0.75, "too_easy"), (0.875, "too_easy")):
        lt.record_dose("footer_mask", d, v)
    assert lt.bracket_seed("footer_mask") == (0.875, 1.0)
    lt.record_dose("footer_mask", 0.9375, "in_band")  # in band leaves the seed alone
    assert lt.bracket_seed("footer_mask") == (0.875, 1.0)
    lt.record_dose("footer_mask", 1.0, "too_easy")  # a no-effect d = 1 test is not a lo_pop
    assert lt.bracket_seed("footer_mask") == (0.875, 1.0)
    lt.record_dose("footer_mask", 0.8, "too_hard")  # inconsistent population: back to [0, 1]
    assert lt.bracket_seed("footer_mask") == (0.0, 1.0)
    snap = lt.snapshot()
    assert snap["horizon_squeeze"]["rate"] == 1.0 and snap["footer_mask"]["rate"] == 0.0
    assert snap["footer_mask"]["lo_pop"] == 0.875 and snap["footer_mask"]["hi_pop"] == 0.8
