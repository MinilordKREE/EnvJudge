"""The task pool changes wall clock only (docs/changelog_v0.2.md, "Task pool"): staging and every
other in-process session is serialized while rollouts overlap; corpus, accounting and per-task
charges are byte-for-byte those of the sequential run; the leverage prior sees the sequential
state; attribution survives the pool threads."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace
from envharness.orchestration.runner import PolicySpec, SubprocessRunner

from aea.config import AEAConfig, ImplConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.io import canonicalize_corpus, read_corpus
from aea.llm.types import Attribution
from aea.runner import AeaSubprocessRunner, dispatch, episode_spec
from aea.session import SESSION_LOCK
from tests.fixtures.fake_substrate import FakeSubstrate

# saturated (no leverage), zero (stage), saturated (bracket), zero, coin, saturated (bracket,
# with the prior from task 7 once its rate qualifies)
POLICIES = {"2": "expert", "9": "random", "7": "footer", "11": "random", "1": "coin", "8": "footer"}
CONFIG = AEAConfig(impl=ImplConfig(prior_min_tasks=1))


def _run(
    tmp_path: Path, name: str, concurrency: int, **kw: Any
) -> tuple[Controller, FakeSubstrate, list[Any]]:
    sub = FakeSubstrate(POLICIES, seed=3, **kw)
    ctrl = Controller(CONFIG, sub, tmp_path / name, "r1", arm="A", use_proposer=False)
    outcomes = ctrl.run([TaskRef(t, int(t)) for t in POLICIES], concurrency=concurrency)
    return ctrl, sub, outcomes


def _charges(ctrl: Controller) -> dict[str, tuple[dict[str, int], dict[str, int], int]]:
    return {
        t: (dict(a.charged), dict(a.refunded), a.spent)
        for t, a in ((t, ctrl.budget.account(t)) for t in POLICIES)
    }


def _brackets(run_dir: Path) -> set[str]:
    ev = read_trace(run_dir / "events.jsonl")
    return {json.dumps(e.payload, sort_keys=True) for e in ev if e.kind in ("families", "bracket")}


def test_pool_reproduces_the_sequential_run_byte_for_byte(tmp_path: Path) -> None:
    seq, _, seq_out = _run(tmp_path, "seq", 1)
    pool, sub, pool_out = _run(tmp_path, "pool", 3, rollout_delay_s=0.02, session_delay_s=0.02)
    # outcomes, per-task charging, run files
    key = [(o.task.task_id, o.outcome, o.reason, o.regime, o.n_search) for o in seq_out]
    assert [(o.task.task_id, o.outcome, o.reason, o.regime, o.n_search) for o in pool_out] == key
    assert _charges(pool) == _charges(seq)
    for name in ("corpus.jsonl", "accounting.csv"):
        assert (tmp_path / "pool" / name).read_bytes() == (tmp_path / "seq" / name).read_bytes()
    assert (tmp_path / "seq" / "corpus.jsonl").stat().st_size > 0
    # the leverage table and every bracket (family order, start dose, history) are the same
    assert pool.leverage.snapshot() == seq.leverage.snapshot()
    assert _brackets(tmp_path / "pool") == _brackets(tmp_path / "seq")
    # the pool did run things at once: rollout batches overlapped, sessions never did
    assert sub.max_active_rollouts >= 2
    assert sub.max_active_sessions == 1
    assert sub.rollouts_during_session >= 1  # a rollout ran while another task held a session


def test_pool_orders_harden_after_its_predecessors(tmp_path: Path) -> None:
    """Task 8's families are ordered only after tasks 2, 9, 7, 11 and 1 are done: the prior it
    reads is the sequential one (overlap itself is shown by the byte-for-byte test above)."""
    _, _, _ = _run(tmp_path, "pool", 3, rollout_delay_s=0.02)
    ev = read_trace(tmp_path / "pool" / "events.jsonl")
    assert ev[0].kind == "run_start" and ev[0].payload["concurrency"] == 3
    seq_of = {(e.kind, str(e.payload.get("task_id"))): e.seq for e in ev if "task_id" in e.payload}
    fam8 = seq_of[("families", "8")]
    assert all(seq_of[("task_done", t)] < fam8 for t in ("2", "9", "7", "11", "1"))


def test_controller_sections_take_the_session_lock(tmp_path: Path) -> None:
    """Both the harden guard and the staging section hold aea.session.SESSION_LOCK: a thread
    holding it blocks the controller's in-process sessions but not its rollouts."""
    sub = FakeSubstrate({"9": "random", "7": "footer"}, seed=3)
    ctrl = Controller(CONFIG, sub, tmp_path / "run", "r1", arm="A", use_proposer=False)
    opened: list[str] = []
    original = sub.open_session

    def spy(task: TaskRef, cand: Candidate | None, ro: dict[str, Any] | None) -> Any:
        assert SESSION_LOCK._is_owned()  # type: ignore[attr-defined]
        opened.append(task.task_id)
        return original(task, cand, ro)

    sub.open_session = spy  # type: ignore[method-assign, assignment]
    SESSION_LOCK.acquire()
    worker = threading.Thread(
        target=ctrl.run, args=([TaskRef("9", 9), TaskRef("7", 7)],), kwargs={"concurrency": 2}
    )
    worker.start()
    worker.join(timeout=5.0)
    assert worker.is_alive() and not opened  # rollouts ran; sessions waited for the lock
    assert any(phase == "estimate" for _, phase, _ in sub.calls)
    SESSION_LOCK.release()
    worker.join(timeout=30.0)
    assert not worker.is_alive() and set(opened) == {"9", "7"}


def test_canonicalize_corpus_moves_lines_without_rewriting_them(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    a = '{"game_file": "g", "aea": {"kind": "kept", "task_id": "a", "seed": 1}}'
    b = '{"game_file": "g",  "aea": {"kind": "kept", "task_id": "b", "seed": 2}}'
    path.write_text(f"{b}\n{a}\n", encoding="utf-8")
    canonicalize_corpus(path, ["a", "b"])
    assert path.read_text(encoding="utf-8") == f"{a}\n{b}\n"  # odd spacing preserved
    before = path.read_bytes()
    canonicalize_corpus(path, ["a", "b"])
    assert path.read_bytes() == before
    assert [e.aea.task_id for e in read_corpus(path)] == ["a", "b"]


def test_dispatch_from_pool_threads_keeps_each_task_attribution(monkeypatch: Any) -> None:
    """Two task-pool threads each dispatch a batch of episodes on their own rollout pool; every
    child environment carries its own task id, phase and seed (extends the two-thread test in
    test_attribution_runner)."""
    seen: dict[tuple[str, str], dict[str, str]] = {}
    lock = threading.Lock()
    runner = AeaSubprocessRunner("r9")

    def fake_run(self: Any, spec: Any) -> Trace:
        env = self._child_env()
        with lock:
            seen[(env["AEA_PHASE"], str(spec.env.reset_seed))] = env
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
    barrier = threading.Barrier(2)

    def task_thread(task: str, phase: str) -> None:
        specs = [
            episode_spec(
                import_path="x",
                reset_options={},
                task_seed=int(task),
                candidate=Candidate(),
                policy=policy,
                iteration_id=f"{phase}-{task}-{i}",
                task_label="lbl",
            )
            for i in range(4)
        ]
        barrier.wait()
        dispatch(
            runner.run,
            specs,
            attribution=Attribution(phase=phase, budget="search", arm="A", task_id=task),
            seed=int(task),
            concurrency=2,
        )

    threads = [
        threading.Thread(target=task_thread, args=a) for a in (("3", "estimate"), ("4", "probe"))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(seen) == {("estimate", "3"), ("probe", "4")}
    for (phase, task), env in seen.items():
        assert env["AEA_TASK_ID"] == task and env["AEA_SEED"] == task
        assert env["AEA_PHASE"] == phase and env["AEA_ARM"] == "A"
