from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.io import read_corpus
from tests.fixtures.fake_substrate import FakeSubstrate


def _run(tmp_path: Path, policies: dict[str, str], **kw: object) -> tuple[Controller, list]:  # type: ignore[type-arg]
    sub = FakeSubstrate(policies, seed=3)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r1", arm="A", use_designer=False, **kw)  # type: ignore[arg-type]
    outcomes = ctrl.run([TaskRef(t, int(t)) for t in policies], concurrency=1)
    return ctrl, outcomes


def test_band_task_goes_to_corpus_unchanged(tmp_path: Path) -> None:
    ctrl, outcomes = _run(tmp_path, {"1": "coin"})
    assert outcomes[0].status in (
        "band",
        "accepted_knob",
        "frozen_no_leverage",
        "unresolved",
        "accepted_stage",
        "exhausted",
    )
    events = [e.kind for e in read_trace(tmp_path / "run" / "events.jsonl")]
    assert events[0] == "task_start" and events[-1] == "task_done"
    assert ctrl.budget.account("1").search_spent <= 30


def test_saturated_expert_freezes_without_leverage(tmp_path: Path) -> None:
    _, outcomes = _run(tmp_path, {"2": "expert"})
    out = outcomes[0]
    assert out.regime == "saturated" and out.status == "frozen_no_leverage"
    assert out.n_search == 10 + 4 + 4
    # estimate 10, footer_mask leverage 4/4, horizon_squeeze leverage 4/4; displacement infeasible
    events = read_trace(tmp_path / "run" / "events.jsonl")
    fams = [e.payload["family"] for e in events if e.kind == "dose_search"]
    assert fams == ["footer_mask", "horizon_squeeze"]
    certs = {e.payload["family"]: e.payload["source"] for e in events if e.kind == "certificate"}
    assert (
        certs["footer_mask"] == "by_construction" and certs["horizon_squeeze"] == "by_construction"
    )
    assert not (tmp_path / "run" / "corpus.jsonl").exists()


def test_saturated_footer_policy_searches_the_footer_dose(tmp_path: Path) -> None:
    _, outcomes = _run(tmp_path, {"7": "footer"})
    out = outcomes[0]
    assert out.regime == "saturated" and out.status in (
        "accepted_knob",
        "exhausted",
        "frozen_no_leverage",
        "budget_cap_hit",  # 10 + 4 + 8 + 8 = 30: a third search dose cannot start
    )
    events = read_trace(tmp_path / "run" / "events.jsonl")
    ds = next(e for e in events if e.kind == "dose_search")
    history = cast(list[dict[str, Any]], ds.payload["history"])
    assert ds.payload["family"] == "footer_mask" and history[0]["d"] == 1.0
    assert out.n_search <= 30
    if out.status == "accepted_knob":
        entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
        assert (
            entry.aea.kind == "knob"
            and entry.aea.family == "footer_mask"
            and entry.rules_code.startswith("import hashlib")
        )
        assert entry.aea.p8 is not None and 3 / 8 <= entry.aea.p8 <= 5 / 8


def test_zero_random_policy_unresolved_and_handoff(tmp_path: Path) -> None:
    _, outcomes = _run(tmp_path, {"9": "random"}, with_handoff=True)
    out = outcomes[0]
    assert out.regime == "zero" and out.status in ("unresolved", "accepted_stage")
    events = read_trace(tmp_path / "run" / "events.jsonl")
    kinds = [e.kind for e in events]
    assert "stage_candidates" in kinds and "probe" in kinds
    if out.status == "unresolved":
        assert "handoff" in kinds and (tmp_path / "run" / "handoff.jsonl").exists()
    assert out.n_search <= 30


def test_budget_invariants_and_resume(tmp_path: Path) -> None:
    policies = {"2": "expert", "9": "random", "5": "coin"}
    _, outcomes = _run(tmp_path, policies)
    traces = (tmp_path / "run" / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(traces) == sum(o.n_search for o in outcomes)  # every charged rollout is a trace
    assert all(o.n_search <= 30 for o in outcomes)
    rows = (tmp_path / "run" / "accounting.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("task_id,round,budget,phase,rollouts") and len(rows) > 3
    # resume: a second controller on the same run dir skips completed tasks
    ctrl2 = Controller(
        AEAConfig(), FakeSubstrate(policies), tmp_path / "run", "r1", arm="A", use_designer=False
    )
    assert ctrl2.completed_tasks() == set(policies)
    assert ctrl2.run([TaskRef(t, int(t)) for t in policies]) == []


def test_concurrency_keeps_per_task_accounts(tmp_path: Path) -> None:
    sub = FakeSubstrate({"2": "expert", "3": "expert", "9": "random"}, seed=5)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r2", arm="A", use_designer=False)
    outcomes = ctrl.run([TaskRef("2", 2), TaskRef("3", 3), TaskRef("9", 9)], concurrency=3)
    assert {o.task.task_id: o.n_search for o in outcomes}["2"] == 18
    for task_id in ("2", "3", "9"):
        assert ctrl.budget.account(task_id).search_spent <= 30
    events = read_trace(tmp_path / "run" / "events.jsonl")
    assert len([e for e in events if e.kind == "task_done"]) == 3


def test_errored_rollouts_are_refunded_and_hint_traces_marked(tmp_path: Path) -> None:
    from envharness.core.types import Candidate, Trace

    from aea.io import is_hint_trace, training_traces

    sub = FakeSubstrate({"2": "expert"}, seed=1)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r3", arm="A", use_designer=False)
    task = TaskRef("2", 2)
    real = sub.rollouts

    def flaky(task_ref: TaskRef, candidate: Candidate, n: int, **kw: Any) -> list[Trace]:
        traces = real(task_ref, candidate, n, **kw)
        traces[0] = traces[0].model_copy(update={"error": "subprocess timeout", "success": False})
        return traces

    setattr(sub, "rollouts", flaky)  # noqa: B010 - scripted fault injection
    traces = ctrl._charged_rollouts(task, Candidate(), 4, "estimate")
    assert len(traces) == 4 and ctrl.budget.account("2").search_spent == 3
    assert ctrl.budget.account("2").infra_errors == 1
    setattr(sub, "rollouts", real)  # noqa: B010
    hinted = ctrl._charged_rollouts(task, Candidate(), 1, "hint:footer_mask", hint=["go to a"])
    assert is_hint_trace(hinted[0])
    kept = training_traces(tmp_path / "run" / "traces.jsonl")
    assert len(kept) == 4 and not any(is_hint_trace(t) for t in kept)


def test_exhausted_family_does_not_end_the_task(tmp_path: Path) -> None:
    from aea import controller as ctl

    sub = FakeSubstrate({"2": "expert"}, seed=1)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r4", arm="A", use_designer=False)
    seen: list[str] = []
    real = ctrl._try_family

    def spy(task: TaskRef, knob: Any, ctx: Any, witnesses: Any, est: Any) -> Any:
        seen.append(knob.name)
        if knob.name == "footer_mask":
            return ctl.TaskOutcome(
                task, "exhausted", "saturated", 1.0, detail={"family": "footer_mask"}
            )
        return real(task, knob, ctx, witnesses, est)

    ctrl._try_family = spy  # type: ignore[method-assign]
    out = ctrl.run([TaskRef("2", 2)])[0]
    assert seen == ["footer_mask", "horizon_squeeze", "displacement"]  # the loop continued
    assert out.status == "exhausted" and out.detail["exhausted"] == ["footer_mask"]


def test_budget_limited_probes_get_their_own_status_and_no_handoff(tmp_path: Path) -> None:
    cfg = AEAConfig(
        search_cap=14
    )  # estimate 10 + one probe of 4: candidates beyond that are skipped
    sub = FakeSubstrate({"9": "random"}, seed=2)
    ctrl = Controller(
        cfg, sub, tmp_path / "run", "r5", arm="A", use_designer=False, with_handoff=True
    )
    out = ctrl.run([TaskRef("9", 9)])[0]
    assert out.status == "unresolved_budget_limited" and out.detail["skipped"]
    assert not (tmp_path / "run" / "handoff.jsonl").exists()
    events = read_trace(tmp_path / "run" / "events.jsonl")
    assert any(e.kind == "probe_skipped_budget" for e in events) and not any(
        e.kind == "handoff" for e in events
    )


def test_resume_reruns_infra_error_tasks(tmp_path: Path) -> None:
    """A task_done with status infra_error is not an outcome: the task is re-run on resume."""
    from aea.core.trace import TraceWriter as EventWriter

    run = tmp_path / "run"
    run.mkdir()
    ev = EventWriter(run / "events.jsonl", "r9")
    ev.write("task_done", {"task_id": "1", "status": "band"})
    ev.write("task_done", {"task_id": "2", "status": "infra_error", "error": "429"})
    ev.write("task_done", {"task_id": "3", "status": "infra_error"})
    ev.write("task_done", {"task_id": "3", "status": "accepted_knob"})  # re-run succeeded
    sub = FakeSubstrate({"1": "coin", "2": "coin", "3": "coin"}, seed=3)
    ctrl = Controller(AEAConfig(), sub, run, "r9", arm="A", use_designer=False)
    assert ctrl.completed_tasks() == {"1", "3"}
