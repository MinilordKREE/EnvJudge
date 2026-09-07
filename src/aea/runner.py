"""Episode dispatch on the released runner with attribution and per-process ledgers (spec §0, §9).

Reference (wrapped): third_party/envharness ``envharness/orchestration/runner.py`` —
``SubprocessRunner`` (316-420; ``_child_env`` 397-419 builds the child's environment),
``EpisodeSpec`` / ``EnvSpec`` / ``PolicySpec`` (84-127). The K-rollout dispatch mirrors
``orchestrator.py:986-1046`` (one spec per rollout, same ``reset_seed``, thread pool).
No reference source copied.

Every child writes its own ``ledger.<pid>.jsonl`` (crash-safe: no two processes append to one
file); :func:`merge_ledgers` folds them into ``ledger.jsonl`` by ``run_id`` for reporting.
"""

from __future__ import annotations

import concurrent.futures as cf
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace
from envharness.orchestration.runner import EnvSpec, EpisodeSpec, PolicySpec, SubprocessRunner

from aea.core.io import append_jsonl, read_jsonl
from aea.llm.attribution import attributed, child_environment
from aea.llm.types import Attribution

LEDGER_GLOB = "ledger.*.jsonl"


class AeaSubprocessRunner(SubprocessRunner):  # type: ignore[misc]  # envharness ships no type information
    """The released subprocess runner; the child's environment carries the bound attribution."""

    def __init__(self, run_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.run_id = run_id

    def _child_env(self) -> dict[str, str]:  # released method is static; instance override is fine
        env: dict[str, str] = dict(SubprocessRunner._child_env())
        env.update(child_environment(self.run_id))
        return env


def episode_spec(
    *,
    import_path: str,
    reset_options: dict[str, Any],
    task_seed: int,
    candidate: Candidate,
    policy: PolicySpec,
    iteration_id: str,
    task_label: str,
    max_steps: int = 50,
) -> EpisodeSpec:
    """One rollout spec; ``reset_seed`` selects the ALFWorld game (``runner.py:196-199``)."""
    return EpisodeSpec(
        env=EnvSpec(
            import_path=import_path, reset_options=dict(reset_options), reset_seed=task_seed
        ),
        candidate=candidate,
        policy=policy,
        iteration_id=iteration_id,
        task_id=task_label,
        max_steps=max_steps,
    )


type RunFn = Callable[[EpisodeSpec], Trace]


def dispatch(
    run: RunFn,
    specs: Sequence[EpisodeSpec],
    *,
    attribution: Attribution,
    seed: int,
    concurrency: int,
) -> list[Trace]:
    """Run ``specs`` under one attribution, ``concurrency`` at a time; traces in spec order."""

    def one(index: int) -> tuple[int, Trace]:
        with attributed(attribution, seed):
            return index, run(specs[index])

    results: dict[int, Trace] = {}
    if concurrency <= 1 or len(specs) <= 1:
        for i in range(len(specs)):
            results[i] = one(i)[1]
    else:
        with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
            for i, trace in pool.map(one, range(len(specs))):
                results[i] = trace
    return [results[i] for i in range(len(specs))]


def ledger_path_for_process(run_dir: Path) -> Path:
    return run_dir / f"ledger.{os.getpid()}.jsonl"


def merge_ledgers(run_dir: Path, run_id: str) -> Path:
    """Fold every ``ledger.<pid>.jsonl`` into ``ledger.jsonl`` (this run only, by timestamp)."""
    rows: list[dict[str, Any]] = []
    for part in sorted(run_dir.glob(LEDGER_GLOB)):
        rows.extend(r for r in read_jsonl(part) if r.get("run_id") == run_id)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    target = run_dir / "ledger.jsonl"
    if target.exists():
        target.unlink()
    for row in rows:
        append_jsonl(target, row)
    return target
