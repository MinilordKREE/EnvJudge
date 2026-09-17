"""V3 refuses implicit replay and mutable dispatch evidence before accepting results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

from aea.controller import Controller, TaskRef
from aea.errors import ConfigError
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.unit.test_designer_controller_session import CONFIG, TableSubstrate, proposal, run


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("pooled", [False, True])
def test_restart_refuses_before_new_baseline(tmp_path: Path, partial: bool, pooled: bool) -> None:
    _, host, substrate, _, _ = run(
        tmp_path, "HIGH", [proposal("HIGH", "A")], {("A", 1.0): [True, False]}
    )
    if partial:
        path = host.run_dir / "events.jsonl"
        lines = [
            line
            for line in path.read_text().splitlines()
            if json.loads(line)["kind"] != "task_done"
        ]
        path.write_text("\n".join(lines) + "\n")
    before = list(substrate.calls)
    fresh = Controller(CONFIG, substrate, host.run_dir, "restarted")
    task = TaskRef("3", 3)
    if pooled and not partial:
        # Existing completed_tasks behavior skips terminal tasks; it does not buy another run.
        assert fresh.run([task]) == []
    else:
        with pytest.raises(ConfigError, match="already started"):
            fresh.run([task]) if pooled else fresh.run_task(task)
    assert substrate.calls == before


def test_mutated_dispatch_candidate_is_not_accepted(tmp_path: Path) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("No designer after corrupted baseline")

    substrate = TableSubstrate("HIGH", ScriptedDesigner(forbidden), {})
    original = substrate.rollouts

    def mutate(task: TaskRef, candidate: Candidate, n: int, **kwargs: Any) -> list[Trace]:
        result = original(task, candidate, n, **kwargs)
        candidate.rules_code = "# mutated after dispatch"
        return result

    substrate.rollouts = mutate  # type: ignore[method-assign]
    host = Controller(CONFIG, substrate, tmp_path, "mutation")
    with pytest.raises(ConfigError, match="mutated"):
        host.run_task(TaskRef("3", 3))
    assert len(substrate.calls) == 1
    assert not (tmp_path / "corpus.jsonl").exists()
