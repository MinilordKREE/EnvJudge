"""The leverage prior survives a kill (E3 pre-flight 1): a resumed run rebuilds the table from
``events.jsonl`` and ends with the same table and the same corpus bytes as an uninterrupted run;
an interrupted attempt's leverage events are discarded with the attempt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aea.config import AEAConfig, ImplConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from tests.fixtures.fake_substrate import FakeSubstrate

POLICIES = {"7": "footer", "2": "expert", "8": "footer", "1": "coin"}  # 1: kept or accepted
CONFIG = AEAConfig(impl=ImplConfig(prior_min_tasks=1))
TASKS = [TaskRef(t, int(t)) for t in POLICIES]


class Killed(BaseException):
    """Stands in for the process dying (never caught by the controller)."""


def _controller(tmp_path: Path, name: str) -> tuple[Controller, FakeSubstrate]:
    sub = FakeSubstrate(POLICIES, seed=3)
    return Controller(CONFIG, sub, tmp_path / name, "r1", arm="A", use_proposer=False), sub


def test_resume_rebuilds_the_prior_and_the_corpus(tmp_path: Path) -> None:
    full, _ = _controller(tmp_path, "full")
    full_out = full.run(TASKS)
    first_two, _ = _controller(tmp_path, "two")
    first_two.run(TASKS[:2])

    killed, sub = _controller(tmp_path, "killed")
    original = sub.rollouts

    def dying(task: TaskRef, *args: Any, **kwargs: Any) -> Any:
        if task.task_id == "8":  # the third task dies in its first rollout batch
            raise Killed
        return original(task, *args, **kwargs)

    sub.rollouts = dying  # type: ignore[method-assign]
    with pytest.raises(Killed):
        killed.run(TASKS)
    assert killed.completed_tasks() == {"7", "2"}

    resumed, _ = _controller(tmp_path, "killed")  # a new process on the same run directory
    assert resumed.leverage.snapshot() == first_two.leverage.snapshot()  # rebuilt, not empty
    assert resumed.leverage.snapshot()["footer_mask"]["tested"] == 2  # tasks 7 and 2 tested it
    out = resumed.run(TASKS)
    assert [o.task.task_id for o in out] == ["8", "1"]
    assert resumed.leverage.snapshot() == full.leverage.snapshot()
    assert (tmp_path / "full" / "corpus.jsonl").stat().st_size > 0
    assert (tmp_path / "killed" / "corpus.jsonl").read_bytes() == (
        tmp_path / "full" / "corpus.jsonl"
    ).read_bytes()
    key = [(o.task.task_id, o.outcome, o.reason, o.n_search) for o in full_out[2:]]
    assert [(o.task.task_id, o.outcome, o.reason, o.n_search) for o in out] == key
    ev = read_trace(tmp_path / "killed" / "events.jsonl")
    assert any(e.kind == "leverage_restored" for e in ev)


def test_interrupted_attempts_do_not_count(tmp_path: Path) -> None:
    """A task that recorded leverage and then failed (infra_error) is re-run; only the completed
    attempt's events are replayed, so nothing is counted twice."""
    from aea.core.trace import TraceWriter as EventWriter

    run = tmp_path / "run"
    run.mkdir()
    ev = EventWriter(run / "events.jsonl", "r1")
    ev.write("task_start", {"task_id": "7"})
    ev.write("leverage", {"task_id": "7", "family": "footer_mask", "has_leverage": True})
    ev.write("task_done", {"task_id": "7", "outcome": "infra_error"})
    ev.write("task_start", {"task_id": "7"})
    ev.write("leverage", {"task_id": "7", "family": "footer_mask", "has_leverage": False})
    ev.write("leverage", {"task_id": "7", "family": "footer_mask", "accepted_dose": 0.5})
    ev.write("task_done", {"task_id": "7", "outcome": "accepted"})
    ev.write("task_start", {"task_id": "8"})
    ev.write("leverage", {"task_id": "8", "family": "footer_mask", "has_leverage": True})
    ev.close()
    ctrl, _ = _controller(tmp_path, "run")
    snap = ctrl.leverage.snapshot()["footer_mask"]
    assert snap == {"tested": 1, "with_leverage": 0, "rate": 0.0, "last_accepted_dose": 0.5}
