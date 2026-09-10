"""E3 first-layer main table (PREREG9 @ experiments/alfworld_e3/PREREG9.md): environment production
at matched budget on ALFWorld seeds 0-29, Qwen3-8B policy (OpenRouter, alibaba pin, reasoning off),
DeepSeek V4 Pro designer (thinking off) for every arm. Runs write runs/e3-<stage>/.

Stages (each resumable; the chain runs/e3_chain.sh runs them in the pre-registered order):
  probe     one cheap ledgered call to the policy endpoint (gate before every arm; E2 rule)
  shared    K=16 on the original environment of the 20 tasks E2 did not cover (runs/e3-shared);
            the 10 E2 tasks reuse runs/e2-shared
  A         aea v0.2 (the box) with the proposer on and persistent priors, task pool
            (<= 16 episodes in flight), zero tasks first (ordered by the shared p16)
  G         EnvRigger, App-G config (generic prompt, target band [0.4, 0.6])
  R         EnvRigger, released ALFWorld config (fail-targeted; skips >= 0.8; scaffold-only)
  h100      control: tasks 8, 9, 27 from the original start, underlying cap and policy horizon
            100, 8 rollouts each, topped up to 16 when a task lands in 2-3/8
  confirm   K=16 (budget eval, never written back) on every learner-facing environment,
            deduplicated across arms; A's kept tasks reuse the shared original K=16
  tables    scripts/make_tables_e3.py -> experiments/alfworld_e3/results/e3_layer1.md
  spend     E3 total (every runs/e3-* ledger) against the hard cap USD 330

A watchdog thread prints the interim spend every 10 finished tasks (and every 10 minutes) and
ends the process (exit 3) when the cap is reached; the chain stops on that exit code.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import LLMConfig, RetryConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.hashing import sha256_digest
from aea.core.manifest import load_run_context, write_manifest
from aea.e0config import derive_arm_config, derive_corpus_config, write_corpus_config
from aea.errors import ConfigError, InfraError
from aea.io import AeaMeta, CorpusEntry, TraceWriter, read_corpus
from aea.llm.attribution import attributed
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from aea.runner import AeaSubprocessRunner
from aea.settings import load_settings
from aea.substrate import AeaSubstrate

ROOT = Path(__file__).resolve().parents[1]
ENVHARNESS = ROOT / "third_party" / "envharness"
RUNS = ROOT / "runs"
RESULTS = ROOT / "experiments" / "alfworld_e3" / "results"
PRICING = ROOT / "configs" / "pricing.yaml"
STAGE_CONFIG = ROOT / "configs" / "alfworld_config_100.yaml"

TASKS: tuple[int, ...] = tuple(range(30))
E2_TASKS: tuple[int, ...] = (0, 8, 9, 10, 11, 14, 17, 18, 20, 27)  # shared K16 in runs/e2-shared
NEW_SHARED: tuple[int, ...] = tuple(t for t in TASKS if t not in E2_TASKS)
H100_TASKS: tuple[int, ...] = (8, 9, 27)
PREREG_SHA = "08a09b7"
CAP_USD = 330.0
ROLLOUT_CONCURRENCY = 4  # subprocess episodes per rollout batch (arm A)
MAX_INFLIGHT_EPISODES = 16  # PREREG7 A2.4: total eval concurrency
CONFIRM_K = 16
H100_N = 8
H100_TOPUP = (2, 3)  # successes of 8 that trigger 8 more


# ---------------------------------------------------------------------------- backbones
def policy_qwen() -> LLMConfig:
    return LLMConfig(
        provider="openrouter",
        model="qwen/qwen3-8b",
        provider_pin="alibaba",
        thinking=False,
        temperature=0.5,
        max_tokens=2048,
        retry=RetryConfig(
            max_attempts=10, initial_delay_s=2.0, max_delay_s=90.0, total_timeout_s=900.0
        ),
    )


def designer_deepseek() -> LLMConfig:
    return LLMConfig(
        provider="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        provider_pin=None,
        thinking=False,
        temperature=0.7,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------- spend
def _ledger_rows(d: Path) -> list[dict[str, Any]]:
    files = (
        [d / "ledger.jsonl"] if (d / "ledger.jsonl").exists() else sorted(d.glob("ledger.*.jsonl"))
    )
    rows: list[dict[str, Any]] = []
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def dir_spend(d: Path) -> float:
    return sum(float(r.get("usd") or 0.0) for r in _ledger_rows(d) if r.get("event") == "call")


def e3_spend() -> float:
    return sum(dir_spend(d) for d in RUNS.glob("e3-*") if d.is_dir())


def guard(where: str) -> None:
    total = e3_spend()
    print(
        json.dumps(
            {
                "spend_check": where,
                "usd": round(total, 2),
                "ts": time.strftime("%FT%TZ", time.gmtime()),
            }
        ),
        flush=True,
    )
    if total >= CAP_USD:
        raise ConfigError(f"E3 cap USD {CAP_USD} reached ({total:.2f}); paused at {where}")


def merge(d: Path) -> None:
    rows = [r for r in _ledger_rows_parts(d)]
    rows.sort(key=lambda r: str(r.get("ts", "")))
    (d / "ledger.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
    )


def _ledger_rows_parts(d: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for part in sorted(d.glob("ledger.*.jsonl")):
        for line in part.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def _count_done(events: Path) -> int:
    """Finished tasks in an aea ``events.jsonl`` (task_done) or a released ``orchestrator.jsonl``
    (task_end)."""
    if not events.exists():
        return 0
    n = 0
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"task_done"' in line or '"task_end"' in line:
            n += 1
    return n


def start_watchdog(where: str, events: Path) -> threading.Event:
    """Interim spend every 10 finished tasks and every 10 minutes; exit 3 at the cap."""
    stop = threading.Event()

    def loop() -> None:
        last_print, last_tasks = time.time(), 0
        while not stop.wait(60):
            total = e3_spend()
            tasks = _count_done(events)
            if tasks // 10 > last_tasks // 10 or time.time() - last_print >= 600:
                print(
                    json.dumps(
                        {
                            "spend_interim": where,
                            "usd": round(total, 2),
                            "tasks_done": tasks,
                            "ts": time.strftime("%FT%TZ", time.gmtime()),
                        }
                    ),
                    flush=True,
                )
                last_print, last_tasks = time.time(), tasks
            if total >= CAP_USD:
                print(json.dumps({"CAP_HIT": where, "usd": round(total, 2)}), flush=True)
                os._exit(3)

    threading.Thread(target=loop, name="e3-watchdog", daemon=True).start()
    return stop


# ---------------------------------------------------------------------------- substrate
def substrate(
    d: Path,
    run_id: str,
    *,
    with_designer: bool,
    concurrency: int,
    max_steps: int | None = None,
) -> AeaSubstrate:
    sub = AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=d,
        run_id=run_id,
        policy_llm=policy_qwen(),
        designer_llm=designer_deepseek() if with_designer else None,
        aea_config=AEAConfig(),
        stage_config_path=STAGE_CONFIG,
        pricing_path=PRICING,
        rollout_concurrency=concurrency,
    )
    if max_steps is not None:  # H100: policy horizon 100 (the underlying cap via reset options)
        sub.max_steps = max_steps
    return sub


def _git_sha(path: Path) -> str | None:
    out = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return out or None


def write_arm_manifest(d: Path, arm: str, extra: dict[str, Any]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "arm_manifest.json").write_text(
        json.dumps(
            {
                "experiment": "E3 layer 1",
                "arm": arm,
                "prereg": "experiments/alfworld_e3/PREREG9.md",
                "prereg_sha": PREREG_SHA,
                "tasks": list(TASKS),
                "policy": policy_qwen().model_dump(mode="json"),
                "designer": designer_deepseek().model_dump(mode="json"),
                "aea_config_sha256": aea_config_sha256(AEAConfig()),
                "envharness_sha": _git_sha(ENVHARNESS),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **extra,
            },
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )


def candidate_key(c: dict[str, Any] | Candidate) -> str:
    if isinstance(c, Candidate):
        rules = c.rules_code or ""
        acts = [{"name": a.name, "kwargs": dict(a.kwargs)} for a in c.in_env_actions]
    else:
        rules, acts = c.get("rules_code") or "", list(c.get("in_env_actions") or [])
    return sha256_digest(json.dumps({"r": rules, "a": acts}, sort_keys=True))[:16]


def is_unchanged(c: dict[str, Any]) -> bool:
    return not (c.get("rules_code") or "") and not (c.get("in_env_actions") or [])


def to_candidate(c: dict[str, Any]) -> Candidate:
    return CorpusEntry(
        game_file="x",
        rules_code=c.get("rules_code") or "",
        in_env_actions=list(c.get("in_env_actions") or []),
        aea=AeaMeta(kind="knob", task_id="x", seed=0),
    ).to_candidate()


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------- shared K=16
def shared_p16() -> dict[str, dict[str, Any]]:
    """``<task>:orig`` -> confirmation record for every task: E2's runs/e2-shared (10 tasks) plus
    runs/e3-shared (20 tasks)."""
    out: dict[str, dict[str, Any]] = {}
    for d in (RUNS / "e2-shared", RUNS / "e3-shared"):
        p = d / "confirm_summary.json"
        if p.exists():
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                out[k] = {**v, "source": d.name}
    return out


def _k16(
    sub: AeaSubstrate,
    writer: TraceWriter,
    env_id: str,
    task: TaskRef,
    candidate: Candidate,
    *,
    arm: str,
    n: int = CONFIRM_K,
    reset_options: dict[str, Any] | None = None,
    phase: str = "confirm",
) -> dict[str, Any]:
    cfg = AEAConfig()
    got = sub.rollouts(
        task,
        candidate,
        n,
        attribution=Attribution(phase=phase, budget="eval", arm=arm, task_id=task.task_id),
        reset_options=reset_options,
    )
    for tr in got:
        tr.candidate_id = env_id
        writer.add(tr)
    ok = sum(int(bool(tr.success)) for tr in got)
    errs = sum(1 for tr in got if tr.error)
    n_ok = len(got) - errs
    return {
        "task": task.task_id,
        "successes": ok,
        "n": n_ok,
        "errors": errs,
        "p16": ok / n_ok if n_ok else None,
        "learnable": bool(n_ok and cfg.learnable(ok, n_ok)),
    }


def stage_shared(concurrency: int) -> None:
    guard("shared")
    d = RUNS / "e3-shared"
    d.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub = substrate(d, "e3-shared", with_designer=False, concurrency=concurrency)
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "confirm.jsonl")
    stop = start_watchdog("shared", d / "nothing")
    for i, t in enumerate(NEW_SHARED):
        env_id = f"{t}:orig"
        if env_id in summary:
            continue
        rec = _k16(sub, writer, env_id, TaskRef(str(t), t), Candidate(), arm="shared")
        summary[env_id] = {**rec, "kind": "orig", "t": None, "shared": True}
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"shared": env_id, **rec}), flush=True)
        if (i + 1) % 5 == 0:
            merge(d)
            guard(f"shared after {i + 1} tasks")
    stop.set()
    merge(d)
    write_arm_manifest(
        d,
        "shared",
        {"tasks": list(NEW_SHARED), "reused_from_e2": list(E2_TASKS), "k": CONFIRM_K},
    )
    print(json.dumps({"stage": "shared", "envs": len(summary), "usd": round(dir_spend(d), 2)}))


# ---------------------------------------------------------------------------- arm A
def a_task_order() -> list[TaskRef]:
    """Zero tasks first (ascending shared p16, ties by id) so the long zero episodes overlap in
    the pool and the saturated tasks, whose hardening serializes, come last."""
    shared = shared_p16()
    missing = [t for t in TASKS if f"{t}:orig" not in shared]
    if missing:
        raise ConfigError(f"shared K16 missing for tasks {missing}; run --stage shared first")

    def key(t: int) -> tuple[float, int]:
        p = shared[f"{t}:orig"].get("p16")
        return (float(p) if p is not None else 2.0, t)

    return [TaskRef(str(t), t) for t in sorted(TASKS, key=key)]


def stage_a(task_concurrency: int) -> None:
    guard("A")
    inflight = task_concurrency * ROLLOUT_CONCURRENCY
    if task_concurrency < 1 or inflight > MAX_INFLIGHT_EPISODES:
        raise ConfigError(
            f"task concurrency {task_concurrency} x {ROLLOUT_CONCURRENCY} rollouts = {inflight} "
            f"episodes in flight; the cap is {MAX_INFLIGHT_EPISODES}"
        )
    order = a_task_order()
    policy, designer = policy_qwen(), designer_deepseek()
    run_id = "e3-A"
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=RUNS,
    )
    d = RUNS / run_id
    if (d / "manifest.json").exists():
        ctx, _ = load_run_context(d)
    else:
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
        envharness_sha=_git_sha(ENVHARNESS),
        extra={
            "experiment": "E3 layer 1",
            "arm": "A",
            "prereg_sha": PREREG_SHA,
            "tasks": [int(t.task_id) for t in order],
            "task_order": "zero first (ascending shared p16, ties by id)",
            "policy_endpoint_pin": policy.provider_pin,
            "designer": designer.model,
            "thinking": {"policy": policy.thinking, "designer": designer.thinking},
            "proposer": "on",
            "priors": "persistent (leverage events)",
            "aea_config": AEAConfig().model_dump(mode="json"),
            "concurrency": {
                "tasks": task_concurrency,
                "rollouts": ROLLOUT_CONCURRENCY,
                "inflight_episodes": inflight,
            },
        },
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    ctrl = Controller(
        AEAConfig(),
        substrate(ctx.out_dir, ctx.run_id, with_designer=True, concurrency=ROLLOUT_CONCURRENCY),
        ctx.out_dir,
        ctx.run_id,
        arm="A",
        use_proposer=True,
    )
    stop = start_watchdog("A", ctx.out_dir / "events.jsonl")
    outcomes = ctrl.run(order, concurrency=task_concurrency)
    stop.set()
    merge(ctx.out_dir)
    for o in outcomes:
        print(
            json.dumps(
                {
                    "arm": "A",
                    "task": o.task.task_id,
                    "outcome": o.outcome,
                    "reason": o.reason,
                    "regime": o.regime,
                    "p_hat": o.p_hat,
                    "n_search": o.n_search,
                }
            ),
            flush=True,
        )
    write_arm_manifest(
        ctx.out_dir,
        "A",
        {"run_id": ctx.run_id, "leverage_table": ctrl.leverage.snapshot(), "proposer": "on"},
    )
    print(json.dumps({"stage": "A", "done": True, "usd": round(dir_spend(ctx.out_dir), 2)}))


# ---------------------------------------------------------------------------- arms G, R
def released_done_tasks(d: Path) -> set[int]:
    """Tasks the released orchestrator finished in this directory: ``task_end`` events mapped
    through the explicit id list of their invocation (``invocations.json``)."""
    inv_path = d / "invocations.json"
    if not inv_path.exists():
        return set()
    invocations: list[list[int]] = json.loads(inv_path.read_text(encoding="utf-8"))
    done: set[int] = set()
    idx = -1
    for e in jsonl(d / "orchestrator.jsonl"):
        if e.get("kind") == "run_start":
            idx += 1
        elif e.get("kind") == "task_end" and 0 <= idx < len(invocations):
            ids = invocations[idx]
            ti = int(e.get("task_idx", -1))
            if 0 <= ti < len(ids):
                done.add(ids[ti])
    return done


def stage_released(arm: str) -> None:
    guard(arm)
    policy, designer = policy_qwen(), designer_deepseek()
    run_id = f"e3-{arm}"
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=RUNS,
    )
    d = RUNS / run_id
    if (d / "manifest.json").exists():
        ctx, _ = load_run_context(d)
    else:
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
            pricing_path=PRICING,
            extra_instructions="",
            target_band=(0.4, 0.6),
        )
    else:
        cfg = derive_corpus_config(
            released, run_dir=ctx.out_dir, policy=policy, designer=designer, pricing_path=PRICING
        )
        changed = ["client blocks and storage/logging paths only (derive_corpus_config)"]
    cfg_path = write_corpus_config(cfg, ctx.out_dir / f"corpus_{arm}.yaml")
    done = released_done_tasks(ctx.out_dir)
    ids = [t for t in TASKS if t not in done]
    write_manifest(
        ctx,
        run_config,
        envharness_sha=_git_sha(ENVHARNESS),
        extra={
            "experiment": "E3 layer 1",
            "arm": arm,
            "prereg_sha": PREREG_SHA,
            "tasks": list(TASKS),
            "config_changes_vs_released": [str(c) for c in changed],
            "config_sha256": sha256_digest(cfg_path.read_text(encoding="utf-8")),
            "policy_endpoint_pin": policy.provider_pin,
            "designer": designer.model,
            "thinking": {"policy": policy.thinking, "designer": designer.thinking},
            "concurrency": {
                "tasks": 1,
                "rollouts": int(cfg["orchestrator"].get("rollout_concurrency", 5)),
                "inflight_episodes": int(cfg["orchestrator"].get("rollout_concurrency", 5)),
            },
            "resumed_with_tasks": ids if done else None,
        },
    )
    if not ids:
        print(json.dumps({"stage": arm, "done": True, "resumed": True}))
        return
    inv_path = ctx.out_dir / "invocations.json"
    invocations = json.loads(inv_path.read_text(encoding="utf-8")) if inv_path.exists() else []
    invocations.append(ids)
    inv_path.write_text(json.dumps(invocations), encoding="utf-8")
    sys.path.insert(0, str(ENVHARNESS / "scripts"))
    sys.path.insert(0, str(ENVHARNESS))
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    os.environ["AEA_RUN_ID"] = ctx.run_id
    run_harness = importlib.import_module("run_harness")
    orch = run_harness.build_from_config(
        cfg_path,
        run_id,
        overrides={"n_tasks": len(ids), "n_iterations": len(ids), "explicit_task_ids": ids},
    )
    label = Attribution(phase="corpus", budget="search", arm=arm, task_id="e3")
    orch.runner = AeaSubprocessRunner(
        ctx.run_id,
        default=(label, 0),
        timeout=float(cfg["runner"].get("timeout_seconds", 600)),
        subprocess_log_dir=ctx.out_dir / "subprocess_logs",
    )
    stop = start_watchdog(arm, ctx.out_dir / "orchestrator.jsonl")
    with attributed(label, seed=0):
        orch.run()
    stop.set()
    merge(ctx.out_dir)
    write_arm_manifest(
        ctx.out_dir,
        arm,
        {
            "run_id": ctx.run_id,
            "config_changes_vs_released": [str(c) for c in changed],
            "invocations": invocations,
        },
    )
    print(
        json.dumps(
            {
                "stage": arm,
                "traces": len(orch.trace_store.all()),
                "usd": round(dir_spend(ctx.out_dir), 2),
            }
        )
    )


# ---------------------------------------------------------------------------- H100 control
def stage_h100(concurrency: int) -> None:
    guard("h100")
    d = RUNS / "e3-H100"
    d.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub = substrate(d, "e3-H100", with_designer=False, concurrency=concurrency, max_steps=100)
    summary_path = d / "h100_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "h100.jsonl")
    for t in H100_TASKS:
        task = TaskRef(str(t), t)
        reset = {"config_path": str(STAGE_CONFIG)}  # underlying cap 100; horizon 100 (max_steps)
        rec = summary.get(str(t))
        if rec is None:
            first = _k16(
                sub,
                writer,
                f"{t}:orig:h100",
                task,
                Candidate(),
                arm="H100",
                n=H100_N,
                reset_options=reset,
                phase="h100",
            )
            rec = {**first, "batches": [first["successes"]], "topped_up": False}
            summary[str(t)] = rec
            summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
            print(json.dumps({"h100": t, **first}), flush=True)
        if rec["successes"] in H100_TOPUP and not rec["topped_up"] and rec["n"] == H100_N:
            more = _k16(
                sub,
                writer,
                f"{t}:orig:h100",
                task,
                Candidate(),
                arm="H100",
                n=CONFIRM_K - H100_N,
                reset_options=reset,
                phase="h100",
            )
            ok = rec["successes"] + more["successes"]
            n = rec["n"] + more["n"]
            rec.update(
                {
                    "successes": ok,
                    "n": n,
                    "errors": rec["errors"] + more["errors"],
                    "p16": ok / n if n else None,
                    "learnable": bool(n and AEAConfig().learnable(ok, n)),
                    "batches": rec["batches"] + [more["successes"]],
                    "topped_up": True,
                }
            )
            summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
            print(json.dumps({"h100_topup": t, "successes": ok, "n": n}), flush=True)
    merge(d)
    write_arm_manifest(
        d,
        "H100",
        {
            "control": True,
            "tasks": list(H100_TASKS),
            "policy_horizon": 100,
            "underlying_config": str(STAGE_CONFIG),
            "n_per_task": H100_N,
            "topup_on": list(H100_TOPUP),
        },
    )
    print(json.dumps({"stage": "h100", "tasks": len(summary), "usd": round(dir_spend(d), 2)}))


# ---------------------------------------------------------------------------- confirmations
def learner_facing() -> list[dict[str, Any]]:
    """Every environment an arm hands to the learner, deduplicated across arms by
    (task, candidate): A's kept tasks (reuse the shared K16, no confirmation) and accepted
    transformed environments; G's and R's accepted non-empty candidates."""
    envs: dict[str, dict[str, Any]] = {}

    def put(arm: str, task: str, cand: dict[str, Any], kind: str, t: int | None, ref: str) -> None:
        key = candidate_key(cand)
        env_id = f"{task}:{key}"
        e = envs.setdefault(
            env_id,
            {
                "id": env_id,
                "task": task,
                "key": key,
                "candidate": cand,
                "kind": kind,
                "t": t,
                "arms": [],
                "refs": {},
            },
        )
        if arm not in e["arms"]:
            e["arms"].append(arm)
        e["refs"][arm] = ref

    a_corpus = RUNS / "e3-A" / "corpus.jsonl"
    if a_corpus.exists():
        for e in read_corpus(a_corpus):
            if e.aea.kind == "kept":
                put(
                    "A",
                    e.aea.task_id,
                    {"rules_code": "", "in_env_actions": []},
                    "kept",
                    None,
                    str(e.aea.candidate_id),
                )
                continue
            put(
                "A",
                e.aea.task_id,
                {"rules_code": e.rules_code, "in_env_actions": e.in_env_actions},
                str(e.aea.kind),
                e.aea.t,
                str(e.aea.candidate_id),
            )
    for arm in ("G", "R"):
        for rec in jsonl(RUNS / f"e3-{arm}" / "traces.jsonl"):
            if rec.get("kind") != "accepted" or is_unchanged(rec["candidate"]):
                continue
            put(
                arm,
                str(rec["rollout_seed"]),
                {
                    "rules_code": rec["candidate"].get("rules_code") or "",
                    "in_env_actions": list(rec["candidate"].get("in_env_actions") or []),
                },
                "accepted",
                None,
                str(rec.get("candidate_id") or rec.get("iteration_id") or ""),
            )
    return sorted(envs.values(), key=lambda e: (int(e["task"]), e["id"]))


def stage_confirm(concurrency: int) -> None:
    guard("confirm")
    d = RUNS / "e3-confirm"
    d.mkdir(parents=True, exist_ok=True)
    envs = learner_facing()
    (d / "envs.json").write_text(json.dumps(envs, indent=1), encoding="utf-8")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub = substrate(d, "e3-confirm", with_designer=False, concurrency=concurrency)
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "confirm.jsonl")
    shared = shared_p16()
    stop = start_watchdog("confirm", d / "nothing")
    n_run = 0
    for env in envs:
        if env["id"] in summary:
            summary[env["id"]]["arms"] = env["arms"]
            continue
        task = TaskRef(env["task"], int(env["task"]))
        if env["kind"] == "kept":  # A keeps the original: the shared K16 is its confirmation
            s = shared.get(f"{env['task']}:orig", {})
            summary[env["id"]] = {
                "task": env["task"],
                "kind": "kept",
                "t": None,
                "arms": env["arms"],
                "successes": s.get("successes"),
                "n": s.get("n"),
                "errors": s.get("errors"),
                "p16": s.get("p16"),
                "learnable": bool(s.get("learnable")),
                "reused": "shared",
            }
            summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
            continue
        reset = sub.stage_reset_options(task) if env["kind"] == "stage" else None
        rec = _k16(
            sub,
            writer,
            env["id"],
            task,
            to_candidate(env["candidate"]),
            arm="confirm",
            reset_options=reset,
        )
        summary[env["id"]] = {
            **rec,
            "kind": env["kind"],
            "t": env.get("t"),
            "arms": env["arms"],
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": env["id"], "arms": env["arms"], **rec}), flush=True)
        n_run += 1
        if n_run % 5 == 0:
            merge(d)
            guard(f"confirm after {n_run} envs")
    stop.set()
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    merge(d)
    write_arm_manifest(
        d,
        "confirm",
        {"envs": len(envs), "confirmed": n_run, "k": CONFIRM_K, "dedup": "(task, candidate)"},
    )
    print(json.dumps({"stage": "confirm", "envs": len(envs), "usd": round(dir_spend(d), 2)}))


# ---------------------------------------------------------------------------- probe / main
def stage_probe() -> int:
    """One cheap ledgered call to the policy endpoint: 0 if it answers, 1 on a throttle."""
    policy = policy_qwen().model_copy(
        update={"retry": RetryConfig(max_attempts=1), "max_tokens": 8}
    )
    out = RUNS / "e3-probe"
    out.mkdir(parents=True, exist_ok=True)
    key = load_settings().require(policy.api_key_env.lower())
    client = OpenAICompatibleClient(
        config=policy,
        transport=make_openai_transport(api_key=key, base_url=policy.base_url, timeout_s=60.0),
        ledger=Ledger(out / "ledger.jsonl", "e3-probe"),
        pricing=load_pricing(PRICING),
    )
    req = ChatRequest(
        model=policy.model,
        messages=(ChatMessage(role="user", content="Reply with the single word OK."),),
        max_tokens=8,
        attribution=Attribution(phase="endpoint_probe", budget="none", arm="infra", task_id="e3"),
    )
    try:
        resp = client.complete(req)
    except InfraError as exc:
        print(f"PROBE_FAIL {exc.kind}")
        return 1
    print(f"PROBE_OK provider={resp.provider}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=["probe", "shared", "A", "G", "R", "h100", "confirm", "tables", "spend"],
    )
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe":
            return stage_probe()
        if args.stage == "shared":
            stage_shared(max(args.concurrency, 8))
        elif args.stage == "A":
            stage_a(args.concurrency)
        elif args.stage in ("G", "R"):
            stage_released(args.stage)
        elif args.stage == "h100":
            stage_h100(max(args.concurrency, 8))
        elif args.stage == "confirm":
            stage_confirm(max(args.concurrency, 8))
        elif args.stage == "tables":
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            mte3 = importlib.import_module("make_tables_e3")
            return int(mte3.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            d.name: round(dir_spend(d), 2)
                            for d in sorted(RUNS.glob("e3-*"))
                            if d.is_dir()
                        },
                        "ts": time.strftime("%FT%TZ", time.gmtime()),
                    }
                )
            )
    except ConfigError as exc:
        print(f"CONFIG/GATE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
