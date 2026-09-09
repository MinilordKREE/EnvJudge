"""E1-SL Round 1 driver (PREREG7 + Amendments 1-2; owner brief of 2026-09-08).

Policy_1 = the backbone with no bank. Train tasks: seeds 0-29. Every arm writes runs/r1-<arm>/.

Stages (each resumable; run in this order):
  r-reuse     R = E0 tasks 0-19 + D1 tasks 20-29 (identical released config; no paid episode
              re-rolled)
  corpus-G    released orchestrator, generic designer prompt (App-G: _DEFAULT_SYSTEM alone),
              objective.target_band [0.4, 0.6]
  corpus-Gplus  G plus the three exemplars appended to the designer prompt (text only)
  corpus-A    aea controller, designer = Flash-Lite under the dose contract + exemplars
              (<= 2 families)
  corpus-Aex  aea controller, designer off (exemplar families only)
  aplush      A's corpus plus expert hand-off demonstrations for A's exhaustive-unresolved zero
              tasks
  corpus-O    policy_1 on the 30 original tasks, 30 rollouts each (budget search)
  confirm     K=16 policy rollouts (budget confirm, never written back): original environment
              once per task (shared by every arm), then every transformed environment of the arm
  banks       T2 / U single-success banks for every arm (Amendment 1 definitions), released Stage 2
              verbatim for A and R (Amendment 2 A2.3)
  evals       released reasoning_bank_eval through the eval hook, one job per (condition, seed),
              6 seeds for A / R / O / N conditions and 3 for the ablations (A2.2), <= 16 episodes
              in flight (A2.4); N seeds 0/1000/2000 reused from E0
Tables: scripts/make_tables.py -> experiments/alfworld_sl/results/round1.md
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from envharness.core.types import Candidate

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import LLMConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.hashing import sha256_digest
from aea.core.io import append_jsonl, read_jsonl
from aea.core.manifest import write_manifest
from aea.core.trace import read_trace
from aea.e0config import derive_arm_config, write_corpus_config
from aea.errors import ConfigError
from aea.evaldriver import run_eval
from aea.evalhook import GUARD_MARKER, install, make_hook
from aea.exemplars import prompt_text
from aea.handoff import handoff
from aea.io import AeaMeta, CorpusEntry, TraceWriter, read_corpus
from aea.llm.attribution import attributed
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution
from aea.runner import AeaSubprocessRunner, merge_ledgers
from aea.substrate import AeaSubstrate

ROOT = Path(__file__).resolve().parents[1]
ENVHARNESS = ROOT / "third_party" / "envharness"
RUNS = ROOT / "runs"
TASKS: tuple[int, ...] = tuple(range(30))
AMENDMENT2_SHA = "81f64c7"
PHASE0_USD = 99.08
SOFT_GATE_USD = 600.0  # Amendment 3 A3.4
HARD_CAP_USD = 650.0  # Amendment 3 A3.4
E0_RUN = "e0-20260907"
D1_RUN = "e0d1-20260908"
ARMS_ADAPT = ("R", "G", "Gplus", "A", "Aex", "AplusH")
PRIMARY_ARMS = {"A", "R", "O", "N"}
SEEDS_PRIMARY = (0, 1000, 2000, 3000, 4000, 5000)
SEEDS_ABLATION = (0, 1000, 2000)
SPLITS = {"in_distribution": 140, "out_of_distribution": 134}
STAGE_CONFIG = ROOT / "configs" / "alfworld_config_100.yaml"
PRICING = ROOT / "configs" / "pricing.yaml"


# ---------------------------------------------------------------------------- common
def backbone() -> tuple[LLMConfig, LLMConfig]:
    policy = LLMConfig(
        provider="openrouter",
        model="google/gemini-3.1-flash-lite",
        provider_pin="google-ai-studio",
        thinking=None,
        temperature=0.5,
    )
    designer = LLMConfig(
        provider="openrouter",
        model="google/gemini-3.1-flash-lite",
        provider_pin="google-ai-studio",
        thinking=None,
        temperature=0.7,
        max_tokens=4096,
    )
    return policy, designer


def arm_dir(arm: str) -> Path:
    return RUNS / f"r1-{arm}"


def dir_spend(d: Path, *, round1_only: bool = True) -> float:
    """USD of call rows under ``d`` (merged ledger if present, else the per-process files);
    ``round1_only`` keeps rows whose run id starts with ``r1-`` (R's reused rows carry the Phase-0
    run ids and are counted there)."""
    files = (
        [d / "ledger.jsonl"] if (d / "ledger.jsonl").exists() else sorted(d.glob("ledger.*.jsonl"))
    )
    usd = 0.0
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("event") == "call" and (
                not round1_only or str(r.get("run_id", "")).startswith("r1-")
            ):
                usd += float(r.get("usd") or 0.0)
    return usd


def merge_all(d: Path) -> Path:
    """Fold every per-process ledger part in ``d`` (any run id: corpus and confirmation stages
    share an arm directory) plus ``ledger_reuse.jsonl`` (R) into ``ledger.jsonl``."""
    rows: list[dict[str, Any]] = []
    parts = sorted(d.glob("ledger.*.jsonl"))
    if (d / "ledger_reuse.jsonl").exists():
        parts.insert(0, d / "ledger_reuse.jsonl")
    for part in parts:
        for line in part.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    rows.sort(key=lambda r: str(r.get("ts", "")))
    target = d / "ledger.jsonl"
    target.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    return target


def round1_spend() -> float:
    """Round-1 USD: every r1-* run and its eval dirs (rows with an r1- run id)."""
    total = 0.0
    for d in RUNS.glob("r1-*"):
        if d.is_dir():
            total += dir_spend(d)
            for sub in d.glob("*-seeds-*"):  # eval job dirs under runs/r1-eval/
                if sub.is_dir():
                    total += dir_spend(sub)
    return total


def spend_guard(where: str) -> None:
    total = PHASE0_USD + round1_spend()
    print(json.dumps({"spend_check": where, "e1sl_total_usd": round(total, 2)}), flush=True)
    if total >= SOFT_GATE_USD:
        raise ConfigError(f"soft gate USD {SOFT_GATE_USD} reached ({total:.2f}); paused at {where}")


def write_arm_manifest(arm: str, extra: dict[str, Any]) -> None:
    out = arm_dir(arm)
    out.mkdir(parents=True, exist_ok=True)
    (out / "arm_manifest.json").write_text(
        json.dumps(
            {
                "arm": arm,
                "round": 1,
                "amendment2_sha": AMENDMENT2_SHA,
                "aea_config_sha256": aea_config_sha256(AEAConfig()),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **extra,
            },
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )


def task_refs() -> list[TaskRef]:
    return [TaskRef(str(t), t) for t in TASKS]


def read_traces(path: Path) -> list[dict[str, Any]]:
    return [r for r in read_jsonl(path)] if path.exists() else []


def candidate_key(c: dict[str, Any] | Candidate) -> str:
    if isinstance(c, Candidate):
        rules, acts = (
            c.rules_code or "",
            [{"name": a.name, "kwargs": dict(a.kwargs)} for a in c.in_env_actions],
        )
    else:
        rules, acts = c.get("rules_code") or "", list(c.get("in_env_actions") or [])
    return sha256_digest(json.dumps({"r": rules, "a": acts}, sort_keys=True))[:16]


def is_unchanged(c: dict[str, Any] | Candidate) -> bool:
    if isinstance(c, Candidate):
        return not (c.rules_code or "") and not c.in_env_actions
    return not (c.get("rules_code") or "") and not (c.get("in_env_actions") or [])


# ---------------------------------------------------------------------------- R reuse
def stage_r_reuse() -> None:
    out = arm_dir("R")
    out.mkdir(parents=True, exist_ok=True)
    sources = {E0_RUN: range(0, 20), D1_RUN: range(20, 30)}
    n_traces = 0
    with (out / "traces.jsonl").open("w", encoding="utf-8") as fh:
        for run, rng in sources.items():
            for line in (RUNS / run / "traces.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip() and int(json.loads(line)["rollout_seed"]) in rng:
                    fh.write(line + "\n")
                    n_traces += 1
    # ledger rows: policy rows by task id; designer rows by the orchestrator's task windows
    rows: list[dict[str, Any]] = []
    for run, rng in sources.items():
        ids = {str(i) for i in rng}
        events = read_jsonl(RUNS / run / "orchestrator.jsonl")
        ends = [e for e in events if e.get("kind") == "task_end"]
        last_idx = len(rng) - 1 if run == D1_RUN else len(ends) - 1
        cutoff = float(ends[last_idx]["ts"])
        for r in read_jsonl(RUNS / run / "ledger.jsonl"):
            if r.get("task_id") in ids:
                rows.append(r)
            elif r.get("budget") == "designer":
                ts = r["ts"].replace("Z", "+00:00")
                from datetime import datetime

                if datetime.fromisoformat(ts).timestamp() <= cutoff:
                    rows.append(r)
    rows.sort(key=lambda r: str(r["ts"]))
    with (out / "ledger_reuse.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    merge_all(out)
    shas = {
        run: sha256_digest((RUNS / run / "corpus_e0.yaml").read_text(encoding="utf-8"))
        for run in sources
    }
    write_arm_manifest(
        "R",
        {
            "reused_from": {run: [rng.start, rng.stop - 1] for run, rng in sources.items()},
            "source_config_sha256": shas,
            "note": "released corpus.yaml, identical modulo storage paths (diff checked); no paid "
            "episode re-rolled; designer rows of D1 assigned to tasks 20-29 by the orchestrator's "
            "task_end timestamps",
            "traces": n_traces,
            "ledger_rows": len(rows),
        },
    )
    print(json.dumps({"stage": "r-reuse", "traces": n_traces, "ledger_rows": len(rows)}))


# ---------------------------------------------------------------------------- released arms
def exemplar_text() -> str:
    parts = [
        "Reference perturbation families (illustrative code from a different method; adapt "
        "freely or ignore; there is no dose requirement here):",
        "--- footer_mask ---",
        prompt_text("footer_mask"),
        "--- horizon_squeeze ---",
        prompt_text("horizon_squeeze"),
        "--- displacement ---",
        prompt_text("displacement"),
    ]
    return "\n".join(parts)


def stage_corpus_released(arm: str, task_ids: tuple[int, int] | None) -> None:
    spend_guard(f"corpus-{arm}")
    policy, designer = backbone()
    run_id = f"r1-{arm}"
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
    cfg, changed = derive_arm_config(
        ENVHARNESS / "experiments" / "alfworld" / "corpus.yaml",
        run_dir=ctx.out_dir,
        policy=policy,
        designer=designer,
        pricing_path=PRICING,
        extra_instructions="" if arm == "G" else exemplar_text(),
        target_band=(0.4, 0.6),
    )
    cfg_path = write_corpus_config(cfg, ctx.out_dir / f"corpus_{arm}.yaml")
    ids = list(range(*task_ids)) if task_ids else list(TASKS)
    write_manifest(
        ctx,
        run_config,
        envharness_sha=_git_sha(ENVHARNESS),
        extra={
            "phase": "round1",
            "arm": arm,
            "config_changes_vs_released": [str(c) for c in changed],
            "config_sha256": sha256_digest(cfg_path.read_text(encoding="utf-8")),
            "task_ids": [ids[0], ids[-1]],
            "amendment2_sha": AMENDMENT2_SHA,
            "policy_endpoint_pin": policy.provider_pin,
            "designer_endpoint_pin": designer.provider_pin,
            "thinking": policy.thinking,
        },
    )
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
    label = Attribution(phase="corpus", budget="search", arm=arm, task_id="r1")
    orch.runner = AeaSubprocessRunner(
        ctx.run_id,
        default=(label, 0),
        timeout=float(cfg["runner"].get("timeout_seconds", 600)),
        subprocess_log_dir=ctx.out_dir / "subprocess_logs",
    )
    with attributed(label, seed=0):
        orch.run()
    merge_all(ctx.out_dir)
    write_arm_manifest(arm, {"run_id": ctx.run_id, "config_changes_vs_released": changed})
    print(json.dumps({"stage": f"corpus-{arm}", "traces": len(orch.trace_store.all())}))


def _git_sha(path: Path) -> str | None:
    return (
        subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or None
    )


# ---------------------------------------------------------------------------- aea arms
def make_substrate(
    run_dir: Path, run_id: str, *, with_designer: bool, concurrency: int
) -> AeaSubstrate:
    policy, designer = backbone()
    return AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=run_dir,
        run_id=run_id,
        policy_llm=policy,
        designer_llm=designer if with_designer else None,
        aea_config=AEAConfig(),
        stage_config_path=STAGE_CONFIG,
        pricing_path=PRICING,
        rollout_concurrency=concurrency,
    )


def stage_corpus_aea(arm: str, task_concurrency: int) -> None:
    spend_guard(f"corpus-{arm}")
    policy, designer = backbone()
    run_id = f"r1-{arm}"
    use_designer = arm == "A"
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,  # provenance only; the substrate gets none when use_designer is off
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
        envharness_sha=_git_sha(ENVHARNESS),
        extra={
            "phase": "round1",
            "arm": arm,
            "use_designer": use_designer,
            "task_ids": [TASKS[0], TASKS[-1]],
            "amendment2_sha": AMENDMENT2_SHA,
            "policy_endpoint_pin": policy.provider_pin,
            "designer_endpoint_pin": designer.provider_pin if use_designer else None,
            "thinking": policy.thinking,
        },
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(ctx.out_dir, ctx.run_id, with_designer=use_designer, concurrency=4)
    controller = Controller(
        AEAConfig(), substrate, ctx.out_dir, ctx.run_id, arm=arm, use_designer=use_designer
    )
    refs = task_refs()
    for start in range(0, len(refs), 10):
        chunk = refs[start : start + 10]
        outcomes = controller.run(chunk, concurrency=task_concurrency)
        merge_all(ctx.out_dir)
        for o in outcomes:
            print(
                json.dumps(
                    {
                        "arm": arm,
                        "task": o.task.task_id,
                        "status": o.status,
                        "regime": o.regime,
                        "p_hat": o.p_hat,
                        "n_search": o.n_search,
                    }
                ),
                flush=True,
            )
        print(
            json.dumps(
                {
                    "arm": arm,
                    "tasks_done": start + len(chunk),
                    "usd": round(dir_spend(ctx.out_dir), 2),
                }
            ),
            flush=True,
        )
        spend_guard(f"corpus-{arm} after {start + len(chunk)} tasks")
    write_arm_manifest(arm, {"run_id": ctx.run_id, "use_designer": use_designer})
    print(json.dumps({"stage": f"corpus-{arm}", "done": True}))


def task_statuses(run_dir: Path) -> dict[str, dict[str, Any]]:
    """task_id -> the task_done payload (last wins) from the controller's events.jsonl."""
    out: dict[str, dict[str, Any]] = {}
    path = run_dir / "events.jsonl"
    if path.exists():
        for e in read_trace(path):
            if e.kind == "task_done":
                out[str(e.payload["task_id"])] = dict(e.payload)
    return out


def stage_aplush() -> None:
    """A+H = A's outputs plus expert hand-off demonstrations for A's exhaustive-unresolved tasks."""
    src, out = arm_dir("A"), arm_dir("AplusH")
    out.mkdir(parents=True, exist_ok=True)
    for name in (
        "corpus.jsonl",
        "traces.jsonl",
        "events.jsonl",
        "accounting.csv",
        "designer_calls.jsonl",
    ):  # A's ledger is not copied: its USD is A's (run id r1-A), not spent twice
        if (src / name).exists():
            shutil.copy(src / name, out / name)
    statuses = task_statuses(src)
    unresolved = sorted(
        (t for t, p in statuses.items() if p.get("status") == "unresolved"), key=int
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(out, "r1-AplusH", with_designer=False, concurrency=1)
    demos = TraceWriter(out / "handoff.jsonl")
    done = {str(r.get("rollout_seed")) for r in read_traces(out / "handoff.jsonl")}
    record: dict[str, Any] = {"unresolved": unresolved, "demos": {}}
    for t in unresolved:
        if t in done:
            record["demos"][t] = "existing"
            continue
        task = TaskRef(t, int(t))

        def open_fn(c: Candidate | None, task: TaskRef = task) -> Any:
            return substrate.open_session(task, c, None)

        demo = handoff(open_fn, AEAConfig(), task_label=task.label, task_seed=task.seed)
        if demo is None:
            record["demos"][t] = None
            continue
        demos.add(demo)
        record["demos"][t] = demo.duration_steps
        print(json.dumps({"arm": "AplusH", "handoff": t, "steps": demo.duration_steps}), flush=True)
    write_arm_manifest(
        "AplusH",
        {
            "derived_from": "r1-A",
            "note": "corpus, traces, events, accounting and ledger copied from A (no extra "
            "search); "
            "hand-off demonstrations are expert runs (0 policy rollouts, budget probe_cert)",
            **record,
        },
    )
    print(json.dumps({"stage": "aplush", **record}))


def stage_corpus_o() -> None:
    spend_guard("corpus-O")
    out = arm_dir("O")
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(out, "r1-O", with_designer=False, concurrency=8)
    traces = TraceWriter(out / "traces.jsonl")
    done_path = out / "events.jsonl"
    done = {str(e["task_id"]) for e in read_jsonl(done_path)} if done_path.exists() else set()
    cap = AEAConfig().search_cap
    for i, task in enumerate(task_refs()):
        if task.task_id in done:
            continue
        got = substrate.rollouts(
            task,
            Candidate(),
            cap,
            attribution=Attribution(phase="o", budget="search", arm="O", task_id=task.task_id),
        )
        for t in got:
            traces.add(t)
        ok = sum(int(bool(t.success)) for t in got)
        append_jsonl(
            done_path,
            {
                "task_id": task.task_id,
                "n": len(got),
                "successes": ok,
                "errors": sum(1 for t in got if t.error),
            },
        )
        print(
            json.dumps({"arm": "O", "task": task.task_id, "successes": ok, "n": len(got)}),
            flush=True,
        )
        if (i + 1) % 10 == 0:
            merge_all(out)
            spend_guard(f"corpus-O after {i + 1} tasks")
    merge_all(out)
    write_arm_manifest("O", {"run_id": "r1-O", "rollouts_per_task": cap, "budget": "search"})
    print(json.dumps({"stage": "corpus-O", "done": True}))


# ---------------------------------------------------------------------------- confirmations
def transformed_envs(arm: str) -> list[dict[str, Any]]:
    """The arm's transformed environments: id, task, candidate dict, kind (knob | stage |
    accepted)."""
    envs: list[dict[str, Any]] = []
    d = arm_dir(arm)
    if arm in ("A", "Aex", "AplusH"):
        for e in read_corpus(d / "corpus.jsonl"):
            if e.aea.kind == "band":
                continue
            envs.append(
                {
                    "id": str(e.aea.candidate_id),
                    "task": e.aea.task_id,
                    "candidate": {"rules_code": e.rules_code, "in_env_actions": e.in_env_actions},
                    "kind": e.aea.kind,
                    "family": e.aea.family,
                    "source": e.aea.source,
                }
            )
        return envs
    seen: dict[tuple[str, str], int] = {}
    for r in read_traces(d / "traces.jsonl"):
        if r.get("kind") != "accepted" or is_unchanged(r["candidate"]):
            continue
        key = (str(r["rollout_seed"]), candidate_key(r["candidate"]))
        if key in seen:
            continue
        seen[key] = len([k for k in seen if k[0] == key[0]])
        envs.append(
            {
                "id": f"{key[0]}:acc{seen[key]}:{key[1]}",
                "task": key[0],
                "candidate": {
                    "rules_code": r["candidate"].get("rules_code") or "",
                    "in_env_actions": list(r["candidate"].get("in_env_actions") or []),
                },
                "kind": "accepted",
                "family": None,
                "source": "released",
            }
        )
    return envs


def to_candidate(c: dict[str, Any]) -> Candidate:
    return CorpusEntry(
        game_file="x",
        rules_code=c.get("rules_code") or "",
        in_env_actions=list(c.get("in_env_actions") or []),
        aea=AeaMeta(kind="knob", task_id="x", seed=0),
    ).to_candidate()


def stage_confirm(arm: str, concurrency: int) -> None:
    """K=16 per environment; ``shared`` = the original environment of every task (once, shared)."""
    spend_guard(f"confirm-{arm}")
    cfg = AEAConfig()
    out = arm_dir(arm) if arm != "shared" else RUNS / "r1-shared"
    out.mkdir(parents=True, exist_ok=True)
    if arm == "AplusH":  # same transformed environments as A: reuse A's confirmations
        shutil.copy(arm_dir("A") / "confirm_summary.json", out / "confirm_summary.json")
        shutil.copy(arm_dir("A") / "confirm.jsonl", out / "confirm.jsonl")
        print(json.dumps({"stage": "confirm-AplusH", "reused_from": "r1-A"}))
        return
    envs = (
        [{"id": f"{t}:orig", "task": str(t), "candidate": {}, "kind": "orig"} for t in TASKS]
        if arm == "shared"
        else transformed_envs(arm)
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = make_substrate(
        out, f"r1-{arm}-confirm", with_designer=False, concurrency=concurrency
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
            to_candidate(env["candidate"]),
            cfg.confirm_k,
            attribution=Attribution(
                phase="confirm", budget="confirm", arm=arm, task_id=task.task_id
            ),
            reset_options=reset,
        )
        for t in got:
            t.candidate_id = env["id"]
            writer.add(t)
        ok = sum(int(bool(t.success)) for t in got)
        errs = sum(1 for t in got if t.error)
        n = len(got) - errs
        p16 = ok / n if n else None
        summary[env["id"]] = {
            "task": env["task"],
            "kind": env["kind"],
            "family": env.get("family"),
            "source": env.get("source"),
            "successes": ok,
            "n": n,
            "errors": errs,
            "p16": p16,
            "learnable": bool(n and lo <= ok <= hi),
            "in_band_t": bool(n and cfg.band_t[0] <= ok / n <= cfg.band_t[1]),
            "shared": arm == "shared",
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": arm, "env": env["id"], "successes": ok, "n": n}), flush=True)
        if (i + 1) % 10 == 0:
            merge_all(out)
            spend_guard(f"confirm-{arm} after {i + 1} envs")
    merge_all(out)
    print(json.dumps({"stage": f"confirm-{arm}", "envs": len(envs)}))


# ---------------------------------------------------------------------------- banks
def _success_traces(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in records
        if r.get("success")
        and not r.get("error")
        and r.get("steps")
        and not (
            str(r.get("candidate_id")) == "hint"
            or str(r.get("iteration_id", "")).startswith("hint:")
        )
    ]


def bank_inputs(arm: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """{protocol: {task: [success traces]}} for T2 and U (Amendment 1 definitions)."""
    d = arm_dir(arm)
    records = read_traces(d / "traces.jsonl")
    t2: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unchanged: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if arm == "O":
        for r in _success_traces(records):
            unchanged[str(r["rollout_seed"])].append(r)
        return {"T2": {}, "U": dict(unchanged)}
    if arm in ("A", "Aex", "AplusH"):
        keys = {candidate_key(e["candidate"]): e["task"] for e in transformed_envs(arm)}
        statuses = task_statuses(d)
        for r in _success_traces(records):
            task = str(r["rollout_seed"])
            k = candidate_key(r["candidate"])
            if k in keys and keys[k] == task:
                t2[task].append(r)
            elif is_unchanged(r["candidate"]) and statuses.get(task, {}).get("status") in (
                "band",
                "frozen_no_leverage",
                "exhausted",
            ):
                unchanged[task].append(r)
        if arm == "AplusH":
            for r in read_traces(d / "handoff.jsonl"):
                t2[str(r["rollout_seed"])].append(r)
    else:  # R / G / G+: accepted candidates; unchanged = tasks without an accepted candidate
        accepted_tasks = {str(r["rollout_seed"]) for r in records if r.get("kind") == "accepted"}
        for r in _success_traces(records):
            task = str(r["rollout_seed"])
            if r.get("kind") == "accepted" and not is_unchanged(r["candidate"]):
                t2[task].append(r)
            elif r.get("kind") == "baseline" and task not in accepted_tasks:
                unchanged[task].append(r)
    u: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task, rs in t2.items():
        u[task].extend(rs)
    for task, rs in unchanged.items():
        u[task].extend(rs)
    return {"T2": dict(t2), "U": dict(u)}


def _load_released(name: str, rel: str) -> Any:
    sys.path.insert(0, str(ENVHARNESS))
    spec = importlib.util.spec_from_file_location(name, ENVHARNESS / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def released_traces_for(arm: str) -> Path:
    """R: its released traces as they are. A: kinds remapped for the released Stage 2 (estimate
    rollouts -> baseline; rollouts on an accepted corpus environment -> accepted; else
    exploration)."""
    d = arm_dir(arm)
    if arm == "R":
        return d / "traces.jsonl"
    keys = {candidate_key(e["candidate"]): e["task"] for e in transformed_envs(arm)}
    out = d / "traces_released.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in read_traces(d / "traces.jsonl"):
            if str(r.get("candidate_id")) == "hint" or str(r.get("iteration_id", "")).startswith(
                "hint:"
            ):
                continue
            task = str(r["rollout_seed"])
            if str(r.get("iteration_id", "")).startswith("estimate-"):
                r["kind"] = "baseline"
            elif keys.get(candidate_key(r["candidate"])) == task:
                r["kind"] = "accepted"
            else:
                r["kind"] = "exploration"
            fh.write(json.dumps(r) + "\n")
    return out


def stage_banks() -> None:
    policy, _ = backbone()
    pricing = load_pricing(PRICING)
    out = RUNS / "r1-banks"
    out.mkdir(parents=True, exist_ok=True)
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    ip = _load_released("induce_pair", "scripts/induce_pair.py")
    meta_path = out / "banks_r1.json"
    meta: dict[str, Any] = (
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    )
    arms = [*ARMS_ADAPT, "O"]
    for arm in arms:
        label = Attribution(phase="induce", budget="eval", arm=arm, task_id="r1")
        install(
            make_hook(policy, run_dir=out, run_id="r1-banks", pricing=pricing, default=(label, 0))
        )
        inputs = bank_inputs(arm)
        for protocol, by_task in inputs.items():
            name = f"{arm}_{protocol}"
            path = out / f"{name}.jsonl"
            if name in meta and path.exists():
                continue
            if not by_task:
                meta[name] = {"items": 0, "tasks": [], "trajectories": {}, "induction": {}}
                path.write_text("", encoding="utf-8")
                continue
            with attributed(label, seed=0):
                n = ip._build_bank(
                    condition=name,
                    traces_by_task=by_task,
                    llm_model=f"openai/{policy.model}",
                    concurrency=4,
                    embed_model="openai/google/gemini-embedding-001",
                    out_path=path,
                )
            meta[name] = {
                "items": n,
                "tasks": sorted(by_task, key=int),
                "trajectories": {k: len(v) for k, v in by_task.items()},
                "induction": _induction_mix(path),
            }
            meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
            print(json.dumps({"bank": name, "items": n, "tasks": len(by_task)}), flush=True)
        if arm in ("A", "R"):  # A2.3 released-protocol row
            name = f"{arm}_rel"
            if name in meta and (out / f"{name}.jsonl").exists():
                continue
            rel_dir = out / f"released-{arm}"
            rel_dir.mkdir(exist_ok=True)
            with attributed(label, seed=0):
                rc = ip.main(
                    [
                        "--traces",
                        str(released_traces_for(arm)),
                        "--out-dir",
                        str(rel_dir),
                        "--llm-model",
                        f"openai/{policy.model}",
                        "--embed-model",
                        "openai/google/gemini-embedding-001",
                        "--concurrency",
                        "4",
                    ]
                )
            if rc:
                raise ConfigError(f"released induce_pair exited {rc} for {arm}")
            shutil.copy(rel_dir / "ours_full.jsonl", out / f"{name}.jsonl")
            items = [r for r in read_jsonl(out / f"{name}.jsonl")]
            meta[name] = {
                "items": len(items),
                "tasks": sorted(
                    {str((it.get("source") or {}).get("task_id")) for it in items},
                    key=lambda x: int(x) if x.isdigit() else -1,
                ),
                "induction": _induction_mix(out / f"{name}.jsonl"),
                "note": "released Stage 2 verbatim (per-task cascade, automatic mode)",
            }
            meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
            print(json.dumps({"bank": name, "items": len(items)}), flush=True)
    merge_ledgers(out, "r1-banks")
    print(json.dumps({"stage": "banks", "banks": sorted(meta)}))


def _induction_mix(path: Path) -> dict[str, int]:
    mix: dict[str, int] = defaultdict(int)
    for it in read_jsonl(path):
        mix[str((it.get("source") or {}).get("induction"))] += 1
    return dict(mix)


# ---------------------------------------------------------------------------- evals
def conditions() -> dict[str, tuple[str, Path | None]]:
    """condition -> (arm label, bank path or None)."""
    b = RUNS / "r1-banks"
    out: dict[str, tuple[str, Path | None]] = {"N": ("N", None), "O_U": ("O", b / "O_U.jsonl")}
    for arm in ARMS_ADAPT:
        for proto in ("T2", "U"):
            out[f"{arm}_{proto}"] = (arm, b / f"{arm}_{proto}.jsonl")
    out["A_rel"] = ("A", b / "A_rel.jsonl")
    out["R_rel"] = ("R", b / "R_rel.jsonl")
    extra = b / "extra_conditions.json"  # Round 1b: corrected U, placebo, matched, A'
    if extra.exists():
        for name, (arm, path) in json.loads(extra.read_text(encoding="utf-8")).items():
            out[name] = (arm, Path(path) if path else None)
    return out


def eval_jobs() -> list[tuple[str, int]]:
    jobs: list[tuple[str, int]] = []
    for cond, (arm, _) in conditions().items():
        seeds = SEEDS_PRIMARY if arm in PRIMARY_ARMS else SEEDS_ABLATION
        for s in seeds:
            jobs.append((cond, s))
    return jobs


def eval_dir(cond: str, seed: int) -> Path:
    return RUNS / "r1-eval" / f"{cond}-seeds-{seed}"


def cell_files(d: Path, cond: str, split: str) -> list[Path]:
    files = sorted(d.glob(f"round*/{cond}_eval_{split}.jsonl"))
    files += sorted(d.parent.glob(f"{d.name}-resume-*/round*/{cond}_eval_{split}.jsonl"))
    return files


def cell_records(d: Path, cond: str, split: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in cell_files(d, cond, split):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def cell_count(d: Path, cond: str, split: str) -> int:
    """Complete (non-errored) records of the cell across the job dir and its resume dirs."""
    return sum(1 for r in cell_records(d, cond, split) if not r.get("error"))


def drop_errored(d: Path, cond: str, split: str) -> list[int]:
    """Remove errored episode records (a guard abort inside a worker, an env error) from the cell
    files so the missing seeds are re-run; the original file is kept as ``.with_errors``."""
    dropped: list[int] = []
    for f in cell_files(d, cond, split):
        recs = []
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("error"):
                dropped.append(int(r["seed"]))
            else:
                recs.append(r)
        if dropped:
            shutil.copy(f, f.with_suffix(".jsonl.with_errors"))
            f.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return dropped


def missing_runs(d: Path, cond: str, split: str, seed: int, n: int) -> list[tuple[int, int]]:
    """Contiguous runs (start, length) of episode seeds not yet recorded for the cell."""
    have = {int(r["seed"]) for r in cell_records(d, cond, split) if not r.get("error")}
    missing = [s for s in range(seed, seed + n) if s not in have]
    runs: list[tuple[int, int]] = []
    for s in missing:
        if runs and runs[-1][0] + runs[-1][1] == s:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((s, 1))
    return runs


def reuse_n_from_e0() -> None:
    for s in SEEDS_ABLATION:
        src = RUNS / E0_RUN / "eval" / f"seeds-{s}" / "round1"
        dst = eval_dir("N", s) / "round1"
        if dst.exists():
            continue
        dst.mkdir(parents=True)
        for split in SPLITS:
            shutil.copy(src / f"nobank_eval_{split}.jsonl", dst / f"N_eval_{split}.jsonl")
        (eval_dir("N", s) / "REUSED_FROM.json").write_text(
            json.dumps(
                {
                    "run": E0_RUN,
                    "condition": "nobank",
                    "seed": s,
                    "note": "policy_1 = backbone, no bank; identical eval config",
                }
            ),
            encoding="utf-8",
        )


def stage_eval_job(cond: str, seed: int, concurrency: int) -> None:
    """One (condition, seed): both splits fresh, or exactly the missing episode seeds after a
    crash / guard abort (one released invocation per contiguous run of missing seeds)."""
    arm, bank = conditions()[cond]
    if bank is not None and (not bank.exists() or bank.stat().st_size == 0):
        print(json.dumps({"eval_job": cond, "seed": seed, "skipped": "empty bank"}))
        return
    policy, _ = backbone()
    pricing = load_pricing(PRICING)
    base = eval_dir(cond, seed)
    for split in SPLITS:
        dropped = drop_errored(base, cond, split)
        if dropped:
            print(
                json.dumps(
                    {"eval_job": cond, "seed": seed, "split": split, "dropped_errored": dropped}
                )
            )
    plan: list[tuple[str, int, int]] = []  # (split, start, n)
    for split, n in SPLITS.items():
        plan += [(split, st, k) for st, k in missing_runs(base, cond, split, seed, n)]
    if not plan:
        print(json.dumps({"eval_job": cond, "seed": seed, "complete": True}))
        return
    fresh = plan == [(split, seed, n) for split, n in SPLITS.items()]
    eval_yaml = ENVHARNESS / "experiments" / "alfworld" / "reasoning_bank_eval.yaml"
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    invocations = [(None, seed, SPLITS)] if fresh else [(sp, st, {sp: k}) for sp, st, k in plan]
    for only_split, start_seed, splits in invocations:
        cfg = yaml.safe_load(eval_yaml.read_text(encoding="utf-8"))
        cfg["model"]["name"] = f"openai/{policy.model}"
        cfg["eval"]["concurrency"] = concurrency
        cfg["eval"]["splits"] = {f"eval_{k}": v for k, v in splits.items()}
        out_dir = base if fresh else base.parent / f"{base.name}-resume-{int(time.time() * 1000)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved = out_dir / "reasoning_bank_eval_r1.yaml"
        resolved.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        rc = run_eval(
            arm=arm,
            conditions={cond: bank},
            config_yaml=resolved,
            out_dir=out_dir,
            start_seeds=(start_seed,),
            concurrency=concurrency,
            llm=policy,
            pricing=pricing,
            run_id="r1-eval",
            envharness_root=ENVHARNESS,
        )
        merge_ledgers(out_dir, "r1-eval")
        print(
            json.dumps(
                {
                    "eval_job": cond,
                    "seed": seed,
                    "split": only_split,
                    "start": start_seed,
                    "n": sum(splits.values()),
                    "rc": rc,
                    "out_dir": str(out_dir),
                }
            ),
            flush=True,
        )


def stage_evals(workers: int, per_job: int, jobs: list[tuple[str, int]] | None = None) -> None:
    spend_guard("evals")
    reuse_n_from_e0()
    jobs = jobs if jobs is not None else eval_jobs()
    pending = [
        (c, s)
        for c, s in jobs
        if any(cell_count(eval_dir(c, s), c, split) < n for split, n in SPLITS.items())
    ]
    print(json.dumps({"stage": "evals", "jobs": len(jobs), "pending": len(pending)}), flush=True)
    log_dir = RUNS / "r1-eval" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    def run_job(job: tuple[str, int]) -> int:
        cond, seed = job
        log = log_dir / f"{cond}-{seed}.log"
        with log.open("a", encoding="utf-8") as fh:
            return subprocess.call(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "round1.py"),
                    "--stage",
                    "eval-job",
                    "--cond",
                    cond,
                    "--seed",
                    str(seed),
                    "--concurrency",
                    str(per_job),
                ],
                stdout=fh,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
            )

    def guard_incidents(job: tuple[str, int]) -> list[dict[str, Any]]:
        """Guard markers of the job's dir and resume dirs (each = one aborted episode)."""
        base = eval_dir(*job)
        found = []
        for d in [base, *base.parent.glob(f"{base.name}-resume-*")]:
            m = d / GUARD_MARKER
            if m.exists():
                found.append({"job": list(job), "dir": d.name, **json.loads(m.read_text())})
                m.rename(d / "guard_failure.handled.json")
        return found

    def run_with_resume(job: tuple[str, int]) -> int:
        """The abort-and-resume rule: a guard abort ends the affected episode (recorded with an
        error); the job is resumed for its missing episodes, at most 3 times."""
        rc = 0
        for attempt in range(4):
            rc = run_job(job)
            incidents = guard_incidents(job)
            for inc in incidents:
                append_jsonl(
                    RUNS / "r1-eval" / "guard_incidents.jsonl", {**inc, "attempt": attempt}
                )
                print(json.dumps({"guard_incident": inc}), flush=True)
            if rc == 0 or not incidents:
                return rc
        return rc

    done = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for job, rc in zip(pending, pool.map(run_with_resume, pending), strict=True):
            done += 1
            print(
                json.dumps(
                    {
                        "eval_done": job,
                        "rc": rc,
                        "done": done,
                        "of": len(pending),
                        "usd": round(round1_spend(), 2),
                    }
                ),
                flush=True,
            )
            if rc:
                raise ConfigError(f"eval job {job} failed rc={rc}; see {log_dir}")
            if done % 5 == 0:
                spend_guard(f"evals after {done} jobs")
    print(json.dumps({"stage": "evals", "done": True}))


# ---------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=[
            "r-reuse",
            "corpus-G",
            "corpus-Gplus",
            "corpus-A",
            "corpus-Aex",
            "aplush",
            "corpus-O",
            "confirm",
            "banks",
            "evals",
            "eval-job",
            "spend",
            "remerge",
        ],
    )
    ap.add_argument("--arm", default="")
    ap.add_argument("--task-ids", type=int, nargs=2, default=None)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--cond", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jobs-file", default="", help="evals: JSON list of [condition, seed]")
    args = ap.parse_args(argv)
    try:
        if args.stage == "r-reuse":
            stage_r_reuse()
        elif args.stage in ("corpus-G", "corpus-Gplus"):
            stage_corpus_released(
                args.stage.split("-", 1)[1], tuple(args.task_ids) if args.task_ids else None
            )
        elif args.stage in ("corpus-A", "corpus-Aex"):
            stage_corpus_aea(args.stage.split("-", 1)[1], args.concurrency)
        elif args.stage == "aplush":
            stage_aplush()
        elif args.stage == "corpus-O":
            stage_corpus_o()
        elif args.stage == "confirm":
            stage_confirm(args.arm, args.concurrency)
        elif args.stage == "banks":
            stage_banks()
        elif args.stage == "evals":
            jobs = (
                [(str(c), int(s)) for c, s in json.loads(Path(args.jobs_file).read_text())]
                if args.jobs_file
                else None
            )
            stage_evals(args.workers, args.concurrency, jobs)
        elif args.stage == "eval-job":
            stage_eval_job(args.cond, args.seed, args.concurrency)
        elif args.stage == "remerge":
            for d in sorted(RUNS.glob("r1-*")):
                if d.is_dir() and list(d.glob("ledger.*.jsonl")):
                    merge_all(d)
                    print(json.dumps({"remerged": d.name, "usd_r1": round(dir_spend(d), 3)}))
        else:
            print(
                json.dumps(
                    {
                        "phase0_usd": PHASE0_USD,
                        "round1_usd": round(round1_spend(), 2),
                        "total": round(PHASE0_USD + round1_spend(), 2),
                    }
                )
            )
    except ConfigError as exc:
        print(f"CONFIG/GATE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
