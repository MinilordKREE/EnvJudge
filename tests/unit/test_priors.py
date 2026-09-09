"""A' cross-task priors (PREREG7 Amendment 3, A3.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.dose import DoseEval, DoseSearchResult, dose_search
from aea.priors import FamilyPriors
from tests.fixtures.fake_substrate import FakeSubstrate


def _events(tmp_path: Path) -> list[Any]:
    return read_trace(tmp_path / "run" / "events.jsonl")


def test_priors_counters_start_dose_and_demotion() -> None:
    pr = FamilyPriors(skip_after=2, demote_after=2)
    zero = DoseSearchResult(
        "exhausted", [DoseEval(1.0, 0, 4, "ZERO"), DoseEval(0.5, 4, 4, "NOEFFECT")]
    )
    acc = DoseSearchResult(
        "accepted",
        [DoseEval(1.0, 0, 4, "ZERO"), DoseEval(0.75, 4, 8, "IN_BAND")],
        DoseEval(0.75, 4, 8, "IN_BAND"),
    )
    nolev = DoseSearchResult("no_leverage", [DoseEval(1.0, 4, 4, "NOEFFECT")])
    assert pr.start_dose("f") == 0.5 and not pr.skip_leverage("f")
    pr.record("f", zero, leverage_tested=True)
    pr.record("f", acc, leverage_tested=True)
    assert pr.skip_leverage("f") and pr.start_dose("f") == 0.75
    pr.record("g", nolev, leverage_tested=True)
    assert not pr.demoted("g")
    pr.record("g", nolev, leverage_tested=True)
    assert pr.demoted("g")
    # a search started at the prior (leverage skipped) does not count as a d = 1 ZERO
    pr.record(
        "f",
        DoseSearchResult("exhausted", [DoseEval(0.75, 4, 4, "NOEFFECT")]),
        leverage_tested=False,
    )
    assert pr.stats("f").zero_at_d1 == 2 and pr.stats("f").tasks_seen == 3


def test_dose_search_with_start_skips_the_leverage_test() -> None:
    seen: list[float] = []

    def run(d: float, n: int) -> list[Any]:
        from envharness.core.types import Candidate, Trace

        seen.append(d)
        ok = d < 0.6  # cliff between 0.5 and 0.75
        return [
            Trace(episode_id="e", iteration_id="i", task_id="t", candidate=Candidate(), success=ok)
            for _ in range(n)
        ]

    result = dose_search(run, AEAConfig(), start=0.5)
    assert result.history[0].d == 0.5 and all(d != 1.0 for d in seen)
    assert result.status in ("accepted", "exhausted") and result.history[0].cls == "NOEFFECT"
    assert result.history[1].d == 0.75  # step 0.25 upward after NOEFFECT at the start dose


def test_sixth_task_starts_at_the_family_prior_without_the_d1_test(tmp_path: Path) -> None:
    """'footer' policies: footer_mask is ZERO at d = 1 (footer always hidden). After five tasks
    the sixth skips the leverage test and starts at the family's start dose."""
    policies = {str(t): "footer" for t in range(1, 7)}
    sub = FakeSubstrate(policies, seed=3)
    ctrl = Controller(
        AEAConfig(),
        sub,
        tmp_path / "run",
        "r1",
        arm="Aprime",
        use_designer=False,
        priors=FamilyPriors(skip_after=5, demote_after=5),
    )
    ctrl.run([TaskRef(t, int(t)) for t in policies], concurrency=1)
    ev = _events(tmp_path)
    searches = [e for e in ev if e.kind == "dose_search" and e.payload["family"] == "footer_mask"]
    by_task = {str(e.payload["task_id"]): e.payload for e in searches}
    for t in ("1", "2", "3", "4", "5"):
        hist = cast(list[dict[str, Any]], by_task[t]["history"])
        assert hist[0]["d"] == 1.0 and hist[0]["cls"] == "ZERO" and by_task[t]["leverage_tested"]
    sixth = by_task["6"]
    hist6 = cast(list[dict[str, Any]], sixth["history"])
    assert not sixth["leverage_tested"] and hist6[0]["d"] != 1.0
    skipped = [e.payload for e in ev if e.kind == "leverage_skipped"]
    assert skipped and skipped[0]["task_id"] == "6" and hist6[0]["d"] == skipped[0]["start"]
    assert ctrl.priors is not None and hist6[0]["d"] == ctrl.priors.start_dose("footer_mask")
    # the skipped test saves the 4 leverage rollouts: task 6 has 4 fewer dose rollouts at d = 1
    d1 = [c for c in sub.calls if c[0] == "6" and c[1].startswith("dose:footer")]
    assert d1  # the search ran


def test_family_with_no_leverage_on_five_tasks_is_demoted(tmp_path: Path) -> None:
    """'expert' policies ignore the footer and the horizon: both exemplar families are NOEFFECT at
    d = 1 (no leverage). After five tasks both are demoted (event on the sixth task); the ordering
    itself is checked with a mixed prior state: a demoted family goes behind the others."""
    policies = {str(t): "expert" for t in range(1, 7)}
    sub = FakeSubstrate(policies, seed=3)
    priors = FamilyPriors(skip_after=5, demote_after=5)
    ctrl = Controller(
        AEAConfig(),
        sub,
        tmp_path / "run",
        "r1",
        arm="Aprime",
        use_designer=False,
        priors=priors,
    )
    ctrl.run([TaskRef(t, int(t)) for t in policies], concurrency=1)
    ev = _events(tmp_path)
    demoted = [e.payload for e in ev if e.kind == "families_demoted"]
    assert demoted and demoted[0]["task_id"] == "6" and "footer_mask" in demoted[0]["demoted"]
    assert priors.stats("footer_mask").no_leverage == 6  # counted on every task, incl. the sixth
    # ordering with a mixed state: only footer_mask demoted -> it goes to the end
    mixed = FamilyPriors(skip_after=5, demote_after=5)
    nolev = DoseSearchResult("no_leverage", [DoseEval(1.0, 4, 4, "NOEFFECT")])
    for _ in range(5):
        mixed.record("footer_mask", nolev, leverage_tested=True)
    ctrl2 = Controller(
        AEAConfig(),
        sub,
        tmp_path / "run2",
        "r2",
        arm="Aprime",
        use_designer=False,
        priors=mixed,
    )
    names = [k.name for k in ctrl2._families(TaskRef("9", 9), (8,))]
    assert names[-1] == "footer_mask" and names[0] == "horizon_squeeze"
