"""E6 LOW assistive Rules (experiments/alfworld_e6/PREREG_LOW_ASSISTIVE_RULES.md): paired
shared-evidence LOW-only comparison on the eight smallest LOW_POOL_3 tasks between arm A =
``llm_v1_stage_control`` (frozen, reference-prefix depth + closed-loop integer refinement) and
arm B = ``llm_v1_assistive_rules`` (one designer call, <= 2 easier_with_d Rules families,
maximum dose first, the mirrored dose bracket). Machinery and gates of ``scripts/e6_refalign.py``
re-targeted; the shared stage runs tasks in a pool of 4 and the two arms run as parallel
processes (the owner asked for more parallelism; concurrency never changes charged numbers).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_pool3 as pool3
import e6_refalign as er

from aea.errors import ConfigError

PREREG_SHA: str | None = "4a617fb"  # PREREG_LOW_ASSISTIVE_RULES.md commit
METHOD_SHA: str | None = "09bc8b0"  # the phase-3.4 implementation commit (src/aea frozen)
CAP_USD = 60.0
N_TASKS = 8


def tasks() -> list[int]:
    low = pool3.low_pool3()
    return low[:N_TASKS] if len(low) >= N_TASKS else []


TASKS: list[int] = tasks()


def apply() -> None:
    """Re-target the shared-evidence machinery of ``e6_refalign`` to this experiment (idempotent;
    call again after importing another experiment's tables module, which re-targets it too)."""
    er.SHARED_ID = "e6-ar-shared"
    er.ARM_IDS = {"A": "e6-ar-A", "B": "e6-ar-B"}
    er.ARM_VERSIONS = {"A": "llm_v1_stage_control", "B": "llm_v1_assistive_rules"}
    er.CONFIRM_ID = "e6-ar-confirm"
    er.PREREG = "PREREG_LOW_ASSISTIVE_RULES.md"
    er.PREREG_SHA = PREREG_SHA
    er.METHOD_SHA = METHOD_SHA
    er.TASKS = list(TASKS)
    er.CAP_USD = CAP_USD
    e3.SPEND_GLOB = "e6-ar-*"
    e3.CAP_USD = CAP_USD
    e3.EXPERIMENT = (
        "E6 LOW assistive Rules (paired shared-evidence comparison, PREREG_LOW_ASSISTIVE_RULES)"
    )


apply()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["probe_endpoint", "shared", "arms", "confirm", "tables", "spend"],
    )
    ap.add_argument("--concurrency", type=int, default=e3.ROLLOUT_CONCURRENCY)
    ap.add_argument("--task-concurrency", type=int, default=1)
    ap.add_argument("--arm", choices=["A", "B"], default=None)
    args = ap.parse_args(argv)
    try:
        if not TASKS:
            raise ConfigError("POOL_INSUFFICIENT: fewer than 8 zero tasks in LOW_POOL_3")
        if args.stage == "probe_endpoint":
            return e3.stage_probe()
        if args.stage == "shared":
            er.stage_shared(args.concurrency, args.task_concurrency)
        elif args.stage == "arms":
            er.stage_arms(args.concurrency, (args.arm,) if args.arm else ("A", "B"))
        elif args.stage == "confirm":
            er.stage_confirm(args.concurrency)
        elif args.stage == "tables":
            mt = importlib.import_module("make_tables_e6_assist")
            return int(mt.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            p.name: round(e3.dir_spend(p), 2)
                            for p in sorted(er.RUNS.glob("e6-ar-*"))
                            if p.is_dir()
                        },
                        "ts": time.strftime("%FT%TZ", time.gmtime()),
                    }
                )
            )
    except ConfigError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
