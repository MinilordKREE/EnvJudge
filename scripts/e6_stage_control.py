"""E6 LOW stage control (experiments/alfworld_e6/PREREG_LOW_STAGE_CONTROL.md): paired
shared-evidence LOW-only comparison on the eight untouched LOW_POOL_2 tasks between arm A =
``llm_v1_refalign`` (one designer call, <= 2 reference-grounded cuts) and arm B =
``llm_v1_stage_control`` (no designer call; closed-loop control over the depth of the same
verified reference prefix, maximum assistance first, inward discrete refinement).

Protocol, machinery and gates are those of ``scripts/e6_refalign.py`` (shared regime estimate
frozen and replayed for both arms, one exact rich reference per task, the same 30-rollout cap,
K = 16 confirmation of accepted Stages, provenance-based leakage audit); this driver only
re-targets that module's run ids, arm versions, task list, prereg and cap.
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
import e6_refalign as er

from aea.errors import ConfigError

TASKS: list[int] = [62, 66, 67, 70, 71, 73, 78, 79]  # the untouched LOW_POOL_2 tasks
PREREG_SHA: str | None = None  # PREREG_LOW_STAGE_CONTROL.md commit (before the first paid call)
METHOD_SHA: str | None = None  # the phase-3.3b implementation commit (src/aea frozen)
CAP_USD = 50.0

er.SHARED_ID = "e6-sc-shared"
er.ARM_IDS = {"A": "e6-sc-A", "B": "e6-sc-B"}
er.ARM_VERSIONS = {"A": "llm_v1_refalign", "B": "llm_v1_stage_control"}
er.CONFIRM_ID = "e6-sc-confirm"
er.PREREG = "PREREG_LOW_STAGE_CONTROL.md"
er.PREREG_SHA = PREREG_SHA
er.METHOD_SHA = METHOD_SHA
er.TASKS = list(TASKS)
er.CAP_USD = CAP_USD
e3.SPEND_GLOB = "e6-sc-*"
e3.CAP_USD = CAP_USD
e3.EXPERIMENT = "E6 LOW stage control (paired shared-evidence comparison, PREREG_LOW_STAGE_CONTROL)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["probe_endpoint", "shared", "arms", "confirm", "tables", "spend"],
    )
    ap.add_argument("--concurrency", type=int, default=e3.ROLLOUT_CONCURRENCY)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe_endpoint":
            return e3.stage_probe()
        if args.stage == "shared":
            er.stage_shared(args.concurrency)
        elif args.stage == "arms":
            er.stage_arms(args.concurrency)
        elif args.stage == "confirm":
            er.stage_confirm(args.concurrency)
        elif args.stage == "tables":
            mt = importlib.import_module("make_tables_e6_stage_control")
            return int(mt.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            p.name: round(e3.dir_spend(p), 2)
                            for p in sorted(er.RUNS.glob("e6-sc-*"))
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
