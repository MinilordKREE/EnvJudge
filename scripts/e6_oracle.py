"""E6 LOW oracle actuator ceiling (experiments/alfworld_e6/PREREG_LOW_ORACLE_ACTUATOR.md,
docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md): the seven phase-3.4 tasks with a verified
reference, the frozen phase-3.4 shared evidence (estimate traces + exact reference, replayed by
the FrozenSubstrate, charged, no API call), the unchanged ``llm_v1_assistive_rules`` controller
with the experiment-side assist provider (one hand-verified, non-privileged family per task,
frozen before the first policy call) instead of the designer. Two arm processes (O1, O2) over
disjoint task subsets, 8 episodes in flight each; rows merged as the single oracle arm O.
Privileged experimental assistance: an oracle ceiling, never a method result.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_refalign as er
import oracle_actuators as oa

from aea.errors import ConfigError

PREREG_SHA: str | None = None  # PREREG_LOW_ORACLE_ACTUATOR.md commit (recorded before the run)
METHOD_SHA: str | None = None  # the actuator-freeze commit (src/aea + dossier frozen)
CAP_USD = 30.0
TASKS: list[int] = [85, 86, 92, 97, 99, 107, 109]
ARM_TASKS: dict[str, list[int]] = {"O1": [85, 86, 92, 97], "O2": [99, 107, 109]}
SHARED_FILES = ("shared.jsonl", "traces.jsonl", "privileged_references.jsonl")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "missing"


def shared_sha() -> dict[str, str]:
    return {name: _sha(er.RUNS / "e6-ar-shared" / name) for name in SHARED_FILES}


def apply() -> None:
    """Re-target the shared-evidence machinery of ``e6_refalign`` (idempotent)."""
    er.SHARED_ID = "e6-ar-shared"  # the frozen phase-3.4 evidence, read only
    er.ARM_IDS = {"O1": "e6-oa-O1", "O2": "e6-oa-O2"}
    er.ARM_VERSIONS = {"O1": "llm_v1_assistive_rules", "O2": "llm_v1_assistive_rules"}
    er.ARM_TASKS = {k: list(v) for k, v in ARM_TASKS.items()}
    er.CONFIRM_ID = "e6-oa-confirm"
    er.PREREG = "PREREG_LOW_ORACLE_ACTUATOR.md"
    er.PREREG_SHA = PREREG_SHA
    er.METHOD_SHA = METHOD_SHA
    er.TASKS = list(TASKS)
    er.CAP_USD = CAP_USD
    er.WITH_DESIGNER = False  # no designer exists in the oracle arm
    er.CONTROLLER_KWARGS = {"assist_provider": oa.provider}
    er.MANIFEST_EXTRA = {
        "experiment": "oracle_actuator_ceiling",
        "oracle_actuators_sha256_16": {
            t: oa.sha(oa.template_path(t).read_text(encoding="utf-8"))
            for t in oa.TASKS
            if oa.template_path(t).exists()
        },
        "shared_evidence_sha256_16": shared_sha(),
        "actuator_freeze_commit": METHOD_SHA,
        "prereg_commit": PREREG_SHA,
    }
    e3.SPEND_GLOB = "e6-oa-*"
    e3.CAP_USD = CAP_USD
    e3.EXPERIMENT = "E6 LOW oracle actuator ceiling (PREREG_LOW_ORACLE_ACTUATOR)"


apply()


def check_frozen() -> None:
    """The dossier on disk equals the registry (no drift after the freeze) and every family
    validates; the shared evidence exists for every task."""
    rendered = {s.task: oa.render(s) for s in oa.SPECS}
    for t, code in rendered.items():
        if oa.template_path(t).read_text(encoding="utf-8") != code:
            raise ConfigError(f"oracle family {t} on disk differs from the registry")
    for t in TASKS:
        if er.shared_estimate(str(t)) is None or er.frozen_reference(str(t)) is None:
            raise ConfigError(f"frozen shared evidence missing for task {t}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["probe_endpoint", "check", "arms", "confirm", "tables", "spend"],
    )
    ap.add_argument("--concurrency", type=int, default=e3.ROLLOUT_CONCURRENCY)
    ap.add_argument("--arm", choices=["O1", "O2"], default=None)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe_endpoint":
            return e3.stage_probe()
        if args.stage == "check":
            check_frozen()
            print(json.dumps({"frozen": True, "shared": shared_sha()}))
            return 0
        if args.stage == "arms":
            check_frozen()
            er.stage_arms(args.concurrency, (args.arm,) if args.arm else ("O1", "O2"))
        elif args.stage == "confirm":
            er.stage_confirm(args.concurrency)
        elif args.stage == "tables":
            mt = importlib.import_module("make_tables_e6_oracle")
            return int(mt.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            p.name: round(e3.dir_spend(p), 2)
                            for p in sorted(er.RUNS.glob("e6-oa-*"))
                            if p.is_dir()
                        },
                        "ts": time.strftime("%FT%TZ", time.gmtime()),
                    }
                )
            )
    except ConfigError as exc:
        print(json.dumps({"stop": str(exc)}), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
