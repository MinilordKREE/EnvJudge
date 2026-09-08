"""The one evaluation driver every arm uses (N, R, G, G+, A, A-ex, A+H, O): the released
``reasoning_bank_eval.main`` under the accounting hook. The hook is shared pipeline, not part of
AEA: every arm's held-out numbers come from the same routed endpoint, the same reasoning setting
and the same ledger. After the released main returns, ``guard_failure.json`` aborts the run.

Reference (wrapped): third_party/envharness ``experiments/alfworld/reasoning_bank_eval.py``
(``main(argv)``: ``--config --out-dir --start-seeds --conditions --bank-overrides --concurrency``).
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aea.core.config import LLMConfig
from aea.errors import InfraError
from aea.evalhook import EvalHook, check_guard, install, make_hook
from aea.llm.attribution import attributed
from aea.llm.pricing import PricingTable
from aea.llm.types import Attribution

type EvalMain = Callable[[list[str]], int]


def released_eval_main(envharness_root: Path) -> EvalMain:
    """Import the released eval script as a module (its own directory on the path, as released)."""
    sys.path.insert(0, str(envharness_root / "experiments" / "alfworld"))
    sys.path.insert(0, str(envharness_root))
    module = importlib.import_module("reasoning_bank_eval")
    return module.main  # type: ignore[no-any-return]


def run_eval(
    *,
    arm: str,
    conditions: Mapping[str, Path | None],
    config_yaml: Path,
    out_dir: Path,
    start_seeds: tuple[int, ...],
    concurrency: int,
    llm: LLMConfig,
    pricing: PricingTable,
    run_id: str,
    eval_main: EvalMain | None = None,
    envharness_root: Path | None = None,
    hook: EvalHook | None = None,
) -> int:
    """Run the released eval for ``conditions`` ({name: bank path or None}) under the hook.

    Every arm calls this with its own bank; ``arm`` only labels the ledger rows. Raises
    ``InfraError(kind="guard")`` if any guard fired during the run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    label = Attribution(phase="eval", budget="eval", arm=arm, task_id="heldout")
    active = hook or make_hook(
        llm, run_dir=out_dir, run_id=run_id, pricing=pricing, default=(label, start_seeds[0])
    )
    main = eval_main or released_eval_main(envharness_root or Path("third_party/envharness"))
    argv = [
        "--config",
        str(config_yaml),
        "--out-dir",
        str(out_dir),
        "--start-seeds",
        ",".join(str(s) for s in start_seeds),
        "--conditions",
        ",".join(conditions),
        "--concurrency",
        str(concurrency),
    ]
    overrides = [f"{name}={path}" for name, path in conditions.items() if path is not None]
    if overrides:
        argv += ["--bank-overrides", ",".join(overrides)]
    os.environ.setdefault("OPENAI_API_KEY", "routed-by-aea-evalhook")  # the released key check only
    original = install(active)
    try:
        with attributed(label, seed=start_seeds[0]):
            rc = int(main(argv))
    finally:
        import litellm

        litellm.completion = original
    problem = check_guard(out_dir)
    if problem is not None:
        raise InfraError(f"evaluation aborted by a guard: {problem['problem']}", kind="guard")
    return rc


def eval_cost_summary(rows: list[Any]) -> dict[str, float]:
    """Spend and call count of the ``eval`` budget (for the Phase-0b cost table)."""
    calls = [r for r in rows if r.event == "call" and r.budget == "eval"]
    return {"calls": float(len(calls)), "usd": float(sum(r.usd for r in calls))}
