"""E2 step 1 (PREREG8-Z): zero side on Qwen3-8B, ALFWorld. Runs write runs/e2-<arm>/.

Policy = Qwen3-8B via OpenRouter (alibaba pin, reasoning off); designer = DeepSeek V4 Pro
(thinking off) for every arm. Tasks = the 10 zero / marginal-low tasks of the E1-pilot P1 regime
map.

Stages (in the pre-registered order; each resumable):
  confirm-shared   K=16 on each task's original environment (defines "zero" for this run)
  corpus-Z         the aea controller (Round-1 configuration) on the 10 tasks, cap 30
  zfull            reference: Z's probe walk continued over the candidates the cap skipped (4 each),
                   uncharged to Z (arm Zfull), flagged reference
  corpus-G         released orchestrator, App-G config (generic prompt, band [0.4, 0.6])
  corpus-R         released orchestrator, released fail-targeted config
  confirm <arm>    K=16 on every accepted environment of Z / Zfull / G / R (staged: 100-step config)
  tables           scripts/make_tables_e2.py -> experiments/alfworld_e2/results/e2_step1.md
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
from envharness.orchestration.storage import TraceStore

sys.path.insert(0, str(Path(__file__).resolve().parent))
import round1 as r1

from aea import probe as probe_mod
from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import LLMConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.hashing import sha256_digest
from aea.core.manifest import write_manifest
from aea.core.trace import read_trace
from aea.e0config import derive_arm_config, derive_corpus_config, write_corpus_config
from aea.errors import ConfigError
from aea.io import AeaMeta, TraceWriter, entry_from_candidate, read_corpus, write_corpus_entry
from aea.llm.attribution import attributed
from aea.llm.types import Attribution
from aea.runner import AeaSubprocessRunner
from aea.stage import StagedCandidate, build_stage_candidates, seeded_failures
from aea.substrate import AeaSubstrate

ROOT = r1.ROOT
ENVHARNESS = r1.ENVHARNESS
RUNS = r1.RUNS
TASKS_E2: tuple[int, ...] = (0, 8, 9, 10, 11, 14, 17, 18, 20, 27)
PREREG_SHA = "db1dcc7"
E2_CAP_USD = 90.0


def backbone_e2() -> tuple[LLMConfig, LLMConfig]:
    policy = LLMConfig(
        provider="openrouter",
        model="qwen/qwen3-8b",
        provider_pin="alibaba",
        thinking=False,
        temperature=0.5,
        max_tokens=2048,
    )
    designer = LLMConfig(
        provider="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        provider_pin=None,
        thinking=False,
        temperature=0.7,
        max_tokens=4096,
    )
    return policy, designer


def arm_dir(arm: str) -> Path:
    return RUNS / f"e2-{arm}"


def task_refs() -> list[TaskRef]:
    return [TaskRef(str(t), t) for t in TASKS_E2]


def e2_spend() -> float:
    return sum(r1.dir_spend(d, round1_only=False) for d in RUNS.glob("e2-*") if d.is_dir())


def spend_guard(where: str) -> None:
    total = e2_spend()
    print(json.dumps({"spend_check": where, "e2_usd": round(total, 2)}), flush=True)
    if total >= E2_CAP_USD:
        raise ConfigError(
            f"E2 step-1 cap USD {E2_CAP_USD} reached ({total:.2f}); paused at {where}"
        )


def make_substrate(
    run_dir: Path, run_id: str, *, with_designer: bool, concurrency: int
) -> AeaSubstrate:
    policy, designer = backbone_e2()
    return AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=run_dir,
        run_id=run_id,
        policy_llm=policy,
        designer_llm=designer if with_designer else None,
        aea_config=AEAConfig(),
        stage_config_path=r1.STAGE_CONFIG,
        pricing_path=r1.PRICING,
        rollout_concurrency=concurrency,
    )


def write_arm_manifest(arm: str, extra: dict[str, Any]) -> None:
    out = arm_dir(arm)
    out.mkdir(parents=True, exist_ok=True)
    policy, designer = backbone_e2()
    (out / "arm_manifest.json").write_text(
        json.dumps(
            {
                "experiment": "E2 step 1",
                "arm": arm,
                "prereg": "experiments/alfworld_e2/PREREG8Z.md",
                "prereg_sha": PREREG_SHA,
                "tasks": list(TASKS_E2),
                "policy": policy.model_dump(mode="json"),
                "designer": designer.model_dump(mode="json"),
                "aea_config_sha256": aea_config_sha256(AEAConfig()),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **extra,
            },
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------- confirmations
def transformed_envs(arm: str) -> list[dict[str, Any]]:
    d = arm_dir(arm)
    envs: list[dict[str, Any]] = []
    if arm in ("Z", "Zfull"):
        for e in read_corpus(d / "corpus.jsonl"):
            if e.aea.kind == "band":
                continue
            envs.append(
                {
                    "id": str(e.aea.candidate_id),
                    "task": e.aea.task_id,
                    "candidate": {"rules_code": e.rules_code, "in_env_actions": e.in_env_actions},
                    "kind": e.aea.kind,
                    "t": e.aea.t,
                }
            )
        return envs
    seen: dict[tuple[str, str], int] = {}
    for rec in r1.read_traces(d / "traces.jsonl"):
        if rec.get("kind") != "accepted" or r1.is_unchanged(rec["candidate"]):
            continue
        key = (str(rec["rollout_seed"]), r1.candidate_key(rec["candidate"]))
        if key in seen:
            continue
        seen[key] = len([k for k in seen if k[0] == key[0]])
        envs.append(
            {
                "id": f"{key[0]}:acc{seen[key]}:{key[1]}",
                "task": key[0],
                "candidate": {
                    "rules_code": rec["candidate"].get("rules_code") or "",
                    "in_env_actions": list(rec["candidate"].get("in_env_actions") or []),
                },
                "kind": "accepted",
                "t": None,
            }
        )
    return envs


def stage_confirm(arm: str, concurrency: int) -> None:
    spend_guard(f"confirm-{arm}")
    cfg = AEAConfig()
    out = arm_dir(arm)
    out.mkdir(parents=True, exist_ok=True)
    envs = (
        [
            {"id": f"{t}:orig", "task": str(t), "candidate": {}, "kind": "orig", "t": None}
            for t in TASKS_E2
        ]
        if arm == "shared"
        else transformed_envs(arm)
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(
        out, f"e2-{arm}-confirm", with_designer=False, concurrency=concurrency
    )
    summary_path = out / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(out / "confirm.jsonl")
    lo, hi = cfg.learnable_successes
    for i, env in enumerate(envs):
        if env["id"] in summary:
            continue
        task = TaskRef(env["task"], int(env["task"]))
        reset = substrate.stage_reset_options(task) if env["kind"] == "stage" else None
        got = substrate.rollouts(
            task,
            r1.to_candidate(env["candidate"]),
            cfg.confirm_k,
            attribution=Attribution(
                phase="confirm", budget="confirm", arm=arm, task_id=task.task_id
            ),
            reset_options=reset,
        )
        for tr in got:
            tr.candidate_id = env["id"]
            writer.add(tr)
        ok = sum(int(bool(tr.success)) for tr in got)
        errs = sum(1 for tr in got if tr.error)
        n = len(got) - errs
        summary[env["id"]] = {
            "task": env["task"],
            "kind": env["kind"],
            "t": env.get("t"),
            "successes": ok,
            "n": n,
            "errors": errs,
            "p16": ok / n if n else None,
            "learnable": bool(n and lo <= ok <= hi),
            "shared": arm == "shared",
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": arm, "env": env["id"], "successes": ok, "n": n}), flush=True)
        if (i + 1) % 5 == 0:
            r1.merge_all(out)
            spend_guard(f"confirm-{arm} after {i + 1} envs")
    r1.merge_all(out)
    if arm == "shared":
        write_arm_manifest("shared", {"stage": "confirm-shared", "envs": len(envs)})
    print(json.dumps({"stage": f"confirm-{arm}", "envs": len(envs)}))


# ---------------------------------------------------------------------------- Z
def stage_corpus_z(task_concurrency: int) -> None:
    spend_guard("corpus-Z")
    policy, designer = backbone_e2()
    run_id = "e2-Z"
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=RUNS,
    )
    ctx = create_run_context(
        run_config,
        runs_root=RUNS,
        run_id=run_id,
        repo_dir=ROOT,
        aea_config_sha256=aea_config_sha256(AEAConfig()),
    )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=r1._git_sha(ENVHARNESS),
        extra={
            "experiment": "E2 step 1",
            "arm": "Z",
            "prereg_sha": PREREG_SHA,
            "tasks": list(TASKS_E2),
            "policy_endpoint_pin": policy.provider_pin,
            "designer": designer.model,
            "thinking": {"policy": policy.thinking, "designer": designer.thinking},
        },
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(ctx.out_dir, ctx.run_id, with_designer=True, concurrency=4)
    controller = Controller(
        AEAConfig(), substrate, ctx.out_dir, ctx.run_id, arm="Z", use_designer=True
    )
    outcomes = controller.run(task_refs(), concurrency=task_concurrency)
    r1.merge_all(ctx.out_dir)
    for o in outcomes:
        print(
            json.dumps(
                {
                    "arm": "Z",
                    "task": o.task.task_id,
                    "status": o.status,
                    "regime": o.regime,
                    "p_hat": o.p_hat,
                    "n_search": o.n_search,
                }
            ),
            flush=True,
        )
    write_arm_manifest("Z", {"run_id": ctx.run_id})
    print(
        json.dumps(
            {
                "stage": "corpus-Z",
                "done": True,
                "usd": round(r1.dir_spend(ctx.out_dir, round1_only=False), 2),
            }
        )
    )


def stage_zfull(concurrency: int) -> None:
    """Continue Z's probe walk over the candidates the cap skipped: 4 rollouts each, latest-first,
    uncharged to Z (arm Zfull, budget search, phase probe_full), flagged reference."""
    spend_guard("zfull")
    cfg = AEAConfig()
    src, out = arm_dir("Z"), arm_dir("Zfull")
    out.mkdir(parents=True, exist_ok=True)
    events = read_trace(src / "events.jsonl")
    skipped: dict[str, list[str]] = {}
    estimates: dict[str, dict[str, Any]] = {}
    for e in events:
        payload: dict[str, Any] = dict(e.payload)
        if e.kind == "probe_skipped_budget":
            raw = payload.get("skipped")
            skipped[str(payload["task_id"])] = [
                str(x) for x in (raw if isinstance(raw, list) else [])
            ]
        elif e.kind == "estimate":
            estimates[str(payload["task_id"])] = payload
    done_path = out / "zfull_summary.json"
    summary: dict[str, Any] = (
        json.loads(done_path.read_text(encoding="utf-8")) if done_path.exists() else {}
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(out, "e2-Zfull", with_designer=False, concurrency=concurrency)
    writer = TraceWriter(out / "traces.jsonl")
    all_traces = TraceStore(src / "traces.jsonl").all()
    for task_id, ids in sorted(skipped.items(), key=lambda kv: int(kv[0])):
        if task_id in summary:
            continue
        task = TaskRef(task_id, int(task_id))
        est_traces = [
            t
            for t in all_traces
            if str(t.rollout_seed) == task_id and t.iteration_id.startswith("estimate-")
        ]
        failures = seeded_failures(est_traces, cfg.n_failed_trajectories, seed=task.seed)
        opts = substrate.stage_reset_options(task)

        def open_fn(c: Candidate | None, ro: dict[str, Any] | None, task: TaskRef = task) -> Any:
            return substrate.open_session(task, c, ro)

        staged = build_stage_candidates(
            open_fn,
            task_id,
            failures,
            opts,
            cfg,
        )
        rebuilt = {c.id: c for c in staged.candidates}
        walk = [rebuilt[i] for i in ids if i in rebuilt]
        missing = [i for i in ids if i not in rebuilt]

        def run(
            c: StagedCandidate, n: int, task: TaskRef = task, opts: dict[str, Any] = opts
        ) -> list[Any]:
            got = substrate.rollouts(
                task,
                c.candidate,
                n,
                attribution=Attribution(
                    phase="probe_full", budget="search", arm="Zfull", task_id=task.task_id
                ),
                reset_options=opts,
            )
            for tr in got:
                tr.candidate_id = c.id
                writer.add(tr)
            return got

        result = probe_mod.probe(walk, run, cfg)
        profile = [
            {
                "id": ev.candidate.id,
                "t": ev.candidate.t,
                "successes": ev.successes,
                "n": ev.n,
                "cls": ev.cls,
            }
            for ev in result.profile
        ]
        rec: dict[str, Any] = {
            "task": task_id,
            "skipped_by_cap": ids,
            "rebuilt": sorted(rebuilt),
            "missing_after_rebuild": missing,
            "profile": profile,
            "status": result.status,
            "accepted": None,
            "reference": True,
        }
        if result.status == "accepted" and result.accepted is not None:
            c = result.accepted.candidate
            meta = AeaMeta(
                kind="stage",
                task_id=task_id,
                seed=task.seed,
                regime="zero",
                t=c.t,
                prefix_sha=c.id.split(":", 1)[1],
                profile=profile,
                stage_budget=cfg.stage_budget,
                candidate_id=c.id,
                certificate=c.certificate.source,
                p8=result.accepted.p_hat,
            )
            write_corpus_entry(
                out / "corpus.jsonl",
                entry_from_candidate(substrate.game_file(task), c.candidate, meta),
            )
            rec["accepted"] = {"id": c.id, "t": c.t, "p4": result.accepted.p_hat}
        summary[task_id] = rec
        done_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(
            json.dumps(
                {"arm": "Zfull", "task": task_id, "probed": len(profile), "status": result.status}
            ),
            flush=True,
        )
        r1.merge_all(out)
        spend_guard(f"zfull after task {task_id}")
    write_arm_manifest(
        "Zfull",
        {
            "run_id": "e2-Zfull",
            "reference": True,
            "tasks_with_skipped_candidates": sorted(skipped, key=int),
        },
    )
    print(json.dumps({"stage": "zfull", "tasks": len(summary)}))


# ---------------------------------------------------------------------------- released arms G, R
def stage_corpus_released(arm: str) -> None:
    spend_guard(f"corpus-{arm}")
    policy, designer = backbone_e2()
    run_id = f"e2-{arm}"
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=RUNS,
    )
    ctx = create_run_context(
        run_config,
        runs_root=RUNS,
        run_id=run_id,
        repo_dir=ROOT,
        aea_config_sha256=aea_config_sha256(AEAConfig()),
    )
    released = ENVHARNESS / "experiments" / "alfworld" / "corpus.yaml"
    if arm == "G":
        cfg, changed = derive_arm_config(
            released,
            run_dir=ctx.out_dir,
            policy=policy,
            designer=designer,
            pricing_path=r1.PRICING,
            extra_instructions="",
            target_band=(0.4, 0.6),
        )
    else:
        cfg = derive_corpus_config(
            released, run_dir=ctx.out_dir, policy=policy, designer=designer, pricing_path=r1.PRICING
        )
        changed = ["client blocks and storage/logging paths only (derive_corpus_config)"]
    cfg_path = write_corpus_config(cfg, ctx.out_dir / f"corpus_{arm}.yaml")
    write_manifest(
        ctx,
        run_config,
        envharness_sha=r1._git_sha(ENVHARNESS),
        extra={
            "experiment": "E2 step 1",
            "arm": arm,
            "prereg_sha": PREREG_SHA,
            "tasks": list(TASKS_E2),
            "config_changes_vs_released": [str(c) for c in changed],
            "config_sha256": sha256_digest(cfg_path.read_text(encoding="utf-8")),
            "policy_endpoint_pin": policy.provider_pin,
            "designer": designer.model,
            "thinking": {"policy": policy.thinking, "designer": designer.thinking},
        },
    )
    sys.path.insert(0, str(ENVHARNESS / "scripts"))
    sys.path.insert(0, str(ENVHARNESS))
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    os.environ["AEA_RUN_ID"] = ctx.run_id
    run_harness = importlib.import_module("run_harness")
    ids = list(TASKS_E2)
    orch = run_harness.build_from_config(
        cfg_path,
        run_id,
        overrides={"n_tasks": len(ids), "n_iterations": len(ids), "explicit_task_ids": ids},
    )
    label = Attribution(phase="corpus", budget="search", arm=arm, task_id="e2")
    orch.runner = AeaSubprocessRunner(
        ctx.run_id,
        default=(label, 0),
        timeout=float(cfg["runner"].get("timeout_seconds", 600)),
        subprocess_log_dir=ctx.out_dir / "subprocess_logs",
    )
    with attributed(label, seed=0):
        orch.run()
    r1.merge_all(ctx.out_dir)
    write_arm_manifest(
        arm, {"run_id": ctx.run_id, "config_changes_vs_released": [str(c) for c in changed]}
    )
    print(
        json.dumps(
            {
                "stage": f"corpus-{arm}",
                "traces": len(orch.trace_store.all()),
                "usd": round(r1.dir_spend(ctx.out_dir, round1_only=False), 2),
            }
        )
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["confirm-shared", "corpus-Z", "zfull", "corpus-G", "corpus-R", "confirm", "spend"],
    )
    ap.add_argument("--arm", default="")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args(argv)
    try:
        if args.stage == "confirm-shared":
            stage_confirm("shared", args.concurrency)
        elif args.stage == "corpus-Z":
            stage_corpus_z(args.concurrency)
        elif args.stage == "zfull":
            stage_zfull(args.concurrency)
        elif args.stage in ("corpus-G", "corpus-R"):
            stage_corpus_released(args.stage.split("-", 1)[1])
        elif args.stage == "confirm":
            stage_confirm(args.arm, args.concurrency)
        else:
            print(json.dumps({"e2_usd": round(e2_spend(), 2), "cap": E2_CAP_USD}))
    except ConfigError as exc:
        print(f"CONFIG/GATE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
