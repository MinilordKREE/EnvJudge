"""Phase 3.4 part A (experiments/alfworld_e6/PREREG_LOW_POOL3.md): K = 16 original-environment
classification of the 50 fresh tasks 80..129, with the machinery of ``e6_pool2.py`` re-targeted
(run id, frozen file, prereg). Same policy, environment, K, error handling, 16 in flight."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_pool2 as pool

USED: frozenset[int] = frozenset(range(80))  # USED_TASKS_AUDIT_POOL3.md (derived programmatically)
TASKS: tuple[int, ...] = tuple(t for t in range(80, 80 + 200) if t not in USED)[:50]
PREREG_SHA: str | None = "fea12f9"  # PREREG_LOW_POOL3.md commit (pre-paid-call)

pool.RUN_ID = "e6-pool3-k16"
pool.FROZEN_NAME = "low_pool3_k16.jsonl"
pool.USED = USED
pool.TASKS = TASKS
pool.PREREG_SHA = PREREG_SHA
pool.PREREG_NAME = "PREREG_LOW_POOL3.md"
e3.SPEND_GLOB = "e6-pool3-*"
e3.CAP_USD = pool.CAP_USD
e3.EXPERIMENT = "E6 pool 3 (fresh K16 behavioural classification, PREREG_LOW_POOL3)"


def low_pool3() -> list[int]:
    return pool.low_pool2()


if __name__ == "__main__":
    sys.exit(pool.main())
