"""Phase 3.3a part B (experiments/alfworld_e6/PREREG_STAGE_PROFILE.md): the response surface
t -> p_pi(E_t) of the current policy along ONE verified rich expert reference per task, at fixed
normalised anchors (0, 25, 50, 75, 100 % of the reference length), K = 8 fixed rollouts per valid
non-terminal anchor. LLM-free after reference construction: no designer, no diagnosis, no
adaptive rule, no acceptance. Only the existing Stage machinery (prefix compilation on the
100-step staged configuration, the released Setup harness) and the substrate's rollouts.

Stages: ``refs`` (one expert reference per task, in-process, privileged, frozen) -> ``stages``
(anchor cuts, prefix compilation, replay validity, terminal check) -> ``probe`` (8 rollouts per
valid non-terminal anchor; errored episodes re-run once) -> ``tables``
(scripts/make_tables_e6_profile.py). Runs: runs/e6-profile.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate

from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.designer import Reference, ReferenceStep
from aea.errors import ConfigError
from aea.io import TraceWriter
from aea.llm.types import Attribution
from aea.session import SESSION_LOCK
from aea.stage import compile_prefix, stage_candidate

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_pool2 as pool
import e6_refalign as er
import e6_smoke as e6

RUNS = e6.RUNS
RESULTS = e6.RESULTS
RUN_ID = "e6-profile"
PREREG_SHA: str | None = "d782c8c"  # PREREG_STAGE_PROFILE.md commit (before the first probe)
METHOD_SHA = "48dc028"  # src/aea frozen (no method code path is exercised beyond Stage machinery)
CAP_USD = 35.0
K = 8
N_TASKS = 6
ANCHORS = (0.0, 0.25, 0.5, 0.75, 1.0)

e3.SPEND_GLOB = "e6-profile*"
e3.CAP_USD = CAP_USD
e3.EXPERIMENT = "E6 stage profile (LOW response surface along the reference, PREREG_STAGE_PROFILE)"


def characterization_tasks() -> list[int]:
    """The six smallest ids of LOW_POOL_2 (frozen/low_pool2_k16.jsonl); [] before the pool."""
    low = pool.low_pool2()
    return low[:N_TASKS] if len(low) >= N_TASKS else []


TASKS: list[int] = characterization_tasks()


def anchor_cuts(n_actions: int) -> list[int]:
    """Deterministic normalised anchors, deduplicated, never extended."""
    return sorted({min(n_actions, max(0, round(a * n_actions))) for a in ANCHORS})


# ---------------------------------------------------------------------------- files
def run_dir() -> Path:
    return RUNS / RUN_ID


def references() -> dict[str, dict[str, Any]]:
    return {str(r["task_id"]): r for r in e3.jsonl(run_dir() / "privileged_references.jsonl")}


def reference_of(task: str) -> Reference | None:
    r = references().get(task)
    if r is None:
        return None
    if not r.get("success"):
        return Reference(False, str(r.get("reason", "unavailable")))
    steps = tuple(
        ReferenceStep(
            int(s["step"]), str(s["observation"]), tuple(s["admissible"]), str(s["action"])
        )
        for s in r.get("steps", [])
    )
    return Reference(True, "pass", tuple(r["actions"]), steps)


def stages_file() -> Path:
    return run_dir() / "stages.jsonl"


def profile_file() -> Path:
    return run_dir() / "profile.jsonl"


def _ready(*, paid: bool = True) -> None:
    """References and anchor stages are in-process and free and precede the prereg (it lists
    them); the probes are paid and need the recorded prereg commit."""
    if paid and PREREG_SHA is None:
        raise ConfigError("PREREG_SHA not recorded: commit PREREG_STAGE_PROFILE.md first")
    if not TASKS:
        raise ConfigError("POOL_INSUFFICIENT: fewer than 6 zero tasks in LOW_POOL_2")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))


def _substrate(concurrency: int) -> Any:
    cfg = AEAConfig.model_validate({"method_version": "llm_v1"})  # only for the reference provider
    sub, _ = er.build(cfg, run_dir(), RUN_ID, concurrency=concurrency, with_designer=False)
    return sub


# ---------------------------------------------------------------------------- refs
def stage_refs() -> None:
    """ONE rich expert reference per task (in-process, free, verified by the simulator)."""
    _ready(paid=False)
    er._manifest(
        run_dir(),
        RUN_ID,
        AEAConfig(),
        {
            "stage": "profile",
            "prereg": "experiments/alfworld_e6/PREREG_STAGE_PROFILE.md",
            "prereg_sha_profile": PREREG_SHA,
            "tasks": list(TASKS),
            "anchors": list(ANCHORS),
            "k": K,
        },
    )
    sub = _substrate(1)
    provider = sub.reference_provider(AEAConfig.model_validate({"method_version": "llm_v1"}))
    assert provider is not None
    have = references()
    for t in TASKS:
        task = TaskRef(str(t), t)
        if task.task_id in have:
            continue
        ref = provider(task)
        row = {
            "task_id": task.task_id,
            **ref.as_record(),
            "ts": time.strftime("%FT%TZ", time.gmtime()),
        }
        with (run_dir() / "privileged_references.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(
            json.dumps(
                {
                    "task": task.task_id,
                    "reference": "ok" if ref.ok else f"REFERENCE_UNAVAILABLE ({ref.reason})",
                    "n_steps": ref.n_steps,
                    "reference_id": row["reference_id"],
                }
            ),
            flush=True,
        )


# ---------------------------------------------------------------------------- stages
def _opener(sub: Any, task: TaskRef) -> Any:
    def open_fn(candidate: Candidate | None, reset_options: dict[str, Any] | None) -> Any:
        return sub.open_session(task, candidate, reset_options)

    return open_fn


def stage_stages() -> None:
    """For every anchor: compile the reference prefix with the existing Stage machinery on the
    staged configuration, require exact reproduction (every expert action admissible and
    effective), and check whether the staged state is terminal (won / done)."""
    _ready(paid=False)
    sub = _substrate(1)
    done = {(str(r["task_id"]), int(r["t"])) for r in e3.jsonl(stages_file())}
    for t in TASKS:
        task = TaskRef(str(t), t)
        ref = reference_of(task.task_id)
        if ref is None or not ref.ok:
            continue
        opts = sub.stage_reset_options(task)
        for cut in anchor_cuts(ref.n_steps):
            if (task.task_id, cut) in done:
                continue
            row: dict[str, Any] = {
                "task_id": task.task_id,
                "t": cut,
                "T": ref.n_steps,
                "frac": cut / ref.n_steps,
            }
            prefix = list(ref.actions[:cut])
            with SESSION_LOCK:
                try:
                    if cut == 0:
                        compiled: list[str] = []
                        candidate = Candidate()
                    else:
                        compiled = compile_prefix(_opener(sub, task), prefix, opts)
                        candidate = stage_candidate(compiled)
                    body = (
                        compiled[:-1]
                        if compiled and compiled[-1] == "look" and prefix[-1:] != ["look"]
                        else compiled
                    )
                    row["compiled"] = compiled
                    row["replay_exact"] = body == prefix
                    sess = sub.open_session(task, candidate if cut else None, opts)
                    try:
                        row["terminal_reference_state"] = bool(sess.won or sess.done)
                        row["won_after_replay"] = bool(sess.won)
                    finally:
                        sess.close()
                    row["environment_error"] = None
                except Exception as exc:  # replay infrastructure error: the anchor is invalid
                    row["environment_error"] = f"{type(exc).__name__}: {exc}"
                    row["replay_exact"] = False
                    row["terminal_reference_state"] = None
            row["valid"] = bool(row.get("replay_exact")) and row.get("environment_error") is None
            row["probeable"] = row["valid"] and not row.get("terminal_reference_state")
            row["candidate"] = {
                "rules_code": "",
                "in_env_actions": [
                    {"name": "do", "kwargs": {"text": a}} for a in (row.get("compiled") or [])
                ],
            }
            with stages_file().open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            print(
                json.dumps({k: v for k, v in row.items() if k not in ("candidate", "compiled")}),
                flush=True,
            )


# ---------------------------------------------------------------------------- probe
def stage_probe(concurrency: int) -> None:
    """K = 8 fixed rollouts per valid non-terminal anchor (no early stop, no acceptance);
    errored episodes re-run once. Resumable per (task, anchor)."""
    _ready()
    e3.guard("profile probe")
    sub = _substrate(concurrency)
    writer = TraceWriter(run_dir() / "traces.jsonl")
    done = {(str(r["task_id"]), int(r["t"])) for r in e3.jsonl(profile_file())}
    for row in e3.jsonl(stages_file()):
        task_id, cut = str(row["task_id"]), int(row["t"])
        if (task_id, cut) in done or not row.get("probeable"):
            continue
        e3.guard(f"profile task {task_id} t={cut}")
        task = TaskRef(task_id, int(task_id))
        opts = sub.stage_reset_options(task)
        candidate = e3.to_candidate(row["candidate"])
        attr = Attribution(phase="profile", budget="eval", arm="profile", task_id=task_id)
        traces = sub.rollouts(task, candidate, K, attribution=attr, reset_options=opts)
        errored = [tr for tr in traces if tr.error]
        if errored:  # one re-run of the errored episodes
            traces = [tr for tr in traces if not tr.error]
            traces += sub.rollouts(
                task, candidate, len(errored), attribution=attr, reset_options=opts
            )
        for tr in traces:
            tr.candidate_id = f"{task_id}:t{cut}"
            writer.add(tr)
        valid = [tr for tr in traces if not tr.error]
        rec = {
            "task_id": task_id,
            "t": cut,
            "T": row["T"],
            "frac": row["frac"],
            "successes": sum(int(bool(tr.success)) for tr in valid),
            "n": len(valid),
            "errors": len(traces) - len(valid),
            "reruns": len(errored),
        }
        with profile_file().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)
        e3.merge(run_dir())
    e3.merge(run_dir())
    print(json.dumps({"stage": "probe", "usd": round(e3.dir_spend(run_dir()), 2)}))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["probe_endpoint", "refs", "stages", "probe", "tables", "spend"],
    )
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe_endpoint":
            return e3.stage_probe()
        if args.stage == "refs":
            stage_refs()
        elif args.stage == "stages":
            stage_stages()
        elif args.stage == "probe":
            stage_probe(args.concurrency)
        elif args.stage == "tables":
            mt = importlib.import_module("make_tables_e6_profile")
            return int(mt.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
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
