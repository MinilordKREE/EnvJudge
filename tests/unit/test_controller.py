"""The box end to end on the fake world: kept / accepted / dropped with reasons, the cap, resume."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import TraceWriter as EventWriter
from aea.core.trace import read_trace
from aea.io import read_corpus
from tests.fixtures.fake_substrate import FakeSubstrate


def _run(tmp_path: Path, policies: dict[str, str], **kw: Any) -> tuple[Controller, list[Any]]:
    sub = FakeSubstrate(policies, seed=3)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r1", arm="A", use_proposer=False, **kw)
    outcomes = ctrl.run([TaskRef(t, int(t)) for t in policies], concurrency=1)
    return ctrl, outcomes


def _events(tmp_path: Path) -> list[Any]:
    return read_trace(tmp_path / "run" / "events.jsonl")


def test_kept_or_accepted_on_a_coin_policy(tmp_path: Path) -> None:
    ctrl, outcomes = _run(tmp_path, {"1": "coin"})
    o = outcomes[0]
    assert o.outcome in ("kept", "accepted", "dropped")
    assert ctrl.budget.account("1").spent <= AEAConfig().cap
    ev = [e.kind for e in _events(tmp_path)]
    assert ev[0] == "task_start" and ev[-1] == "task_done"
    if o.outcome == "kept":
        entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
        assert entry.aea.kind == "kept" and entry.rules_code == "" and not entry.in_env_actions


def test_expert_policy_is_dropped_for_no_leverage(tmp_path: Path) -> None:
    """The expert ignores the footer and the horizon: every family is too_easy at d = 1."""
    _, outcomes = _run(tmp_path, {"2": "expert"})
    o = outcomes[0]
    assert o.regime == "saturated" and o.outcome == "dropped" and o.reason == "no_leverage"
    assert o.n_search == 10 + 4 + 4  # estimate 10, two leverage tests of 4
    ev = _events(tmp_path)
    assert [e.payload["family"] for e in ev if e.kind == "no_leverage"] == [
        "footer_mask",
        "horizon_squeeze",
    ]
    assert not (tmp_path / "run" / "corpus.jsonl").exists()


def test_footer_policy_brackets_the_footer_dose(tmp_path: Path) -> None:
    """'footer' follows the plan only while the footer is visible: 0/4 at d = 1, then a bracket."""
    _, outcomes = _run(tmp_path, {"7": "footer"})
    o = outcomes[0]
    assert o.regime == "saturated" and o.outcome in ("accepted", "dropped")
    ev = _events(tmp_path)
    br = next(e for e in ev if e.kind == "bracket")
    hist = cast(list[dict[str, Any]], br.payload["history"])
    assert (
        br.payload["family"] == "footer_mask"
        and hist[0]["d"] == 1.0
        and hist[0]["verdict"] == "too_hard"
    )
    assert hist[1]["d"] == 0.5  # midpoint start (no prior)
    assert o.n_search <= AEAConfig().cap
    if o.outcome == "accepted":
        entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
        assert entry.aea.kind == "knob" and entry.aea.family == "footer_mask"
        assert entry.aea.p_hat is not None and 3 / 8 <= entry.aea.p_hat <= 5 / 8
    else:
        assert o.reason in ("exhausted", "budget")


def test_random_policy_stages_or_drops_with_a_reason(tmp_path: Path) -> None:
    _, outcomes = _run(tmp_path, {"9": "random"})
    o = outcomes[0]
    assert o.regime == "zero" and o.outcome in ("accepted", "dropped")
    if o.outcome == "dropped":
        assert o.reason in ("dead", "too_easy", "budget", "uncertified", "no_failed_rollout")
    else:
        entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
        assert entry.aea.kind == "stage" and entry.aea.state_hash and entry.stage_budget == 100
    ev = _events(tmp_path)
    assert any(e.kind == "stage_candidates" for e in ev)


def test_budget_invariant_and_resume(tmp_path: Path) -> None:
    ctrl, outcomes = _run(tmp_path, {"1": "coin", "2": "expert", "7": "footer"})
    for o in outcomes:
        assert ctrl.budget.account(o.task.task_id).spent == o.n_search <= AEAConfig().cap
    rows = [r for r in ctrl.budget.accounting_rows() if r["budget"] == "search"]
    assert rows and all(int(cast(int, r["n"])) >= 0 for r in rows)
    sub = FakeSubstrate({"1": "coin", "2": "expert", "7": "footer"}, seed=3)
    ctrl2 = Controller(AEAConfig(), sub, tmp_path / "run", "r1", arm="A", use_proposer=False)
    assert ctrl2.completed_tasks() == {"1", "2", "7"}
    assert ctrl2.run([TaskRef("1", 1), TaskRef("2", 2)], concurrency=1) == []


def test_resume_reruns_infra_error_tasks(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    ev = EventWriter(run / "events.jsonl", "r9")
    ev.write("task_done", {"task_id": "1", "outcome": "kept"})
    ev.write("task_done", {"task_id": "2", "outcome": "infra_error", "error": "429"})
    ev.write("task_done", {"task_id": "3", "outcome": "infra_error"})
    ev.write("task_done", {"task_id": "3", "outcome": "accepted"})
    sub = FakeSubstrate({"1": "coin", "2": "coin", "3": "coin"}, seed=3)
    ctrl = Controller(AEAConfig(), sub, run, "r9", arm="A", use_proposer=False)
    assert ctrl.completed_tasks() == {"1", "3"}


def test_errored_rollouts_are_refunded(tmp_path: Path) -> None:
    sub = FakeSubstrate({"5": "coin"}, seed=3)
    original = sub.rollouts

    def flaky(*args: Any, **kwargs: Any) -> list[Any]:
        traces = original(*args, **kwargs)
        traces[0].error = "boom"
        return traces

    sub.rollouts = flaky  # type: ignore[method-assign]
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r3", arm="A", use_proposer=False)
    ctrl.run([TaskRef("5", 5)], concurrency=1)
    acc = ctrl.budget.account("5")
    assert acc.infra_errors > 0 and acc.spent == sum(acc.charged.values()) - sum(
        acc.refunded.values()
    )
