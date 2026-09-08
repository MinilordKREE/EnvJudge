from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace
from envharness.orchestration.runner import PolicySpec

from aea.llm.attribution import attributed, child_environment, current_attribution
from aea.llm.ledger import read_ledger
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from aea.runner import AeaSubprocessRunner, dispatch, episode_spec, merge_ledgers
from tests.conftest import ClientFactory, make_completion


def _attr(task: str) -> Attribution:
    return Attribution(phase="search", budget="search", arm="A", task_id=task)


def test_contextvar_is_thread_local_and_never_touches_environ(monkeypatch: Any) -> None:
    monkeypatch.delenv("AEA_TASK_ID", raising=False)
    seen: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def worker(task: str) -> None:
        with attributed(_attr(task), seed=int(task)):
            barrier.wait()
            seen[task] = current_attribution()[0].task_id

    threads = [threading.Thread(target=worker, args=(t,)) for t in ("7", "9")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen == {"7": "7", "9": "9"}
    assert current_attribution()[0].task_id == "none"  # nothing leaked to the process


def test_interleaved_episodes_charge_the_right_task(
    make_client: ClientFactory, tmp_path: Path
) -> None:
    """Two tasks' calls interleave on threads; every ledger row carries its own task_id."""
    bundle = make_client([make_completion() for _ in range(20)])
    barrier = threading.Barrier(2)

    def episode(task: str) -> None:
        with attributed(_attr(task), seed=int(task)):
            for _ in range(10):
                barrier.wait()
                attribution, seed = current_attribution()
                bundle.client.complete(
                    ChatRequest(
                        model="qwen/qwen3-8b",
                        messages=(ChatMessage(role="user", content="x"),),
                        seed=seed,
                        attribution=attribution,
                    )
                )

    threads = [threading.Thread(target=episode, args=(t,)) for t in ("7", "9")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = read_ledger(tmp_path / "ledger.jsonl")
    assert len(rows) == 20 and {r.task_id for r in rows} == {"7", "9"}
    assert all(r.seed == int(r.task_id) for r in rows)


def test_child_env_carries_attribution() -> None:
    runner = AeaSubprocessRunner(run_id="r1")
    with attributed(_attr("3"), seed=3):
        env = runner._child_env()
    assert env["AEA_TASK_ID"] == "3" and env["AEA_BUDGET"] == "search" and env["AEA_RUN_ID"] == "r1"
    assert "PYTHONPATH" in env
    assert child_environment("r1")["AEA_TASK_ID"] == "none"


def test_dispatch_keeps_order_and_binds_attribution() -> None:
    seen: list[str] = []

    def fake_run(spec: Any) -> Trace:
        seen.append(current_attribution()[0].task_id)
        return Trace(
            episode_id=spec.iteration_id,
            iteration_id=spec.iteration_id,
            task_id="t",
            candidate=spec.candidate,
            rollout_idx=int(spec.iteration_id[-1]),
        )

    policy = PolicySpec(
        client_factory="f",
        client_kwargs={},
        action_format="think_action",
        task_prompt="p",
        max_history=200,
        temperature=0.5,
    )
    specs = [
        episode_spec(
            import_path="x",
            reset_options={},
            task_seed=5,
            candidate=Candidate(),
            policy=policy,
            iteration_id=f"e{i}",
            task_label="lbl",
        )
        for i in range(4)
    ]
    traces = dispatch(fake_run, specs, attribution=_attr("5"), seed=5, concurrency=2)
    assert [t.rollout_idx for t in traces] == [0, 1, 2, 3] and seen == ["5"] * 4


def test_merge_ledgers(tmp_path: Path) -> None:
    from aea.core.io import append_jsonl

    append_jsonl(tmp_path / "ledger.11.jsonl", {"run_id": "r", "ts": "2", "v": 1})
    append_jsonl(tmp_path / "ledger.12.jsonl", {"run_id": "r", "ts": "1", "v": 2})
    append_jsonl(tmp_path / "ledger.13.jsonl", {"run_id": "other", "ts": "0", "v": 3})
    merged = merge_ledgers(tmp_path, "r")
    from aea.core.io import read_jsonl

    assert [r["v"] for r in read_jsonl(merged)] == [2, 1]


def test_runner_default_attribution_reaches_threads_and_tasks(monkeypatch: Any) -> None:
    """The released orchestrator runs episodes from ThreadPoolExecutor threads (no contextvars):
    the runner's default attribution, with the spec's task seed, must be what the child sees."""
    import threading

    from envharness.orchestration.runner import SubprocessRunner

    seen: dict[str, dict[str, str]] = {}
    runner = AeaSubprocessRunner("r9", default=(_attr("default"), 0))

    def fake_run(self: Any, spec: Any) -> Trace:
        seen[str(spec.env.reset_seed)] = self._child_env()
        return Trace(episode_id="e", iteration_id="i", task_id="t", candidate=spec.candidate)

    monkeypatch.setattr(SubprocessRunner, "run", fake_run)
    policy = PolicySpec(
        client_factory="f",
        client_kwargs={},
        action_format="think_action",
        task_prompt="p",
        max_history=200,
        temperature=0.5,
    )
    specs = [
        episode_spec(
            import_path="x",
            reset_options={},
            task_seed=s,
            candidate=Candidate(),
            policy=policy,
            iteration_id="e",
            task_label="lbl",
        )
        for s in (3, 4)
    ]
    threads = [threading.Thread(target=runner.run, args=(sp,)) for sp in specs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen["3"]["AEA_TASK_ID"] == "3" and seen["4"]["AEA_TASK_ID"] == "4"
    assert (
        seen["3"]["AEA_BUDGET"] == "search"
        and seen["3"]["AEA_ARM"] == "A"
        and seen["3"]["AEA_SEED"] == "3"
    )
