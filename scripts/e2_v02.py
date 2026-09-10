"""E2 step 1 under aea v0.2 (Phase D of the distillation): the zero side re-run on the E2 step-1
task set with the v0.2 controller; the shared original-environment K=16 of v0.1 (runs/e2-shared)
is reused; the proposer is off on this side (PREREG8-Z, arm Z). Writes runs/e2v02-Z/ and
experiments/alfworld_e2/results/e2_step1_v02.md (v0.2 next to the v0.1 numbers).

Stages: corpus (the controller on the 10 tasks, cap 30; ``--concurrency`` = task pool size, the
Phase-D run used 1) -> confirm (K=16 on every accepted environment, staged sessions under the
100-step config) -> tables. The manifest records the task pool size, the rollout concurrency and
their product (episodes in flight, kept <= 16 per PREREG7 A2.4); every invocation also logs it in
``events.jsonl`` (``run_start``), so a resumed run keeps the history of pool sizes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import LLMConfig, RetryConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import load_run_context, write_manifest
from aea.errors import ConfigError, InfraError
from aea.io import TraceWriter, read_corpus
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.ledger import Ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from aea.settings import load_settings
from aea.substrate import AeaSubstrate

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_tables as mt
import make_tables_e2 as mte

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
RESULTS = ROOT / "experiments" / "alfworld_e2" / "results"
TASKS: tuple[int, ...] = (0, 8, 9, 10, 11, 14, 17, 18, 20, 27)
RUN_ID = "e2v02-Z"
ROLLOUT_CONCURRENCY = 4  # subprocess episodes per rollout batch (corpus stage)
MAX_INFLIGHT_EPISODES = 16  # PREREG7 A2.4: total eval concurrency
CAP_USD = 30.0
PRICING = ROOT / "configs" / "pricing.yaml"
STAGE_CONFIG = ROOT / "configs" / "alfworld_config_100.yaml"


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


def run_dir() -> Path:
    return RUNS / RUN_ID


def spend() -> float:
    usd = 0.0
    d = run_dir()
    files = (
        [d / "ledger.jsonl"] if (d / "ledger.jsonl").exists() else list(d.glob("ledger.*.jsonl"))
    )
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if line:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("event") == "call":
                    usd += float(r.get("usd") or 0.0)
    return usd


def guard(where: str) -> None:
    total = spend()
    print(json.dumps({"spend_check": where, "usd": round(total, 2)}), flush=True)
    if total >= CAP_USD:
        raise ConfigError(f"Phase-D cap USD {CAP_USD} reached ({total:.2f}); paused at {where}")


def merge(d: Path) -> None:
    rows: list[dict[str, Any]] = []
    for part in sorted(d.glob("ledger.*.jsonl")):
        for line in part.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip("\0")
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    rows.sort(key=lambda r: str(r.get("ts", "")))
    (d / "ledger.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def substrate(d: Path, run_id: str, concurrency: int) -> AeaSubstrate:
    return AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=d,
        run_id=run_id,
        policy_llm=policy_qwen(),
        designer_llm=None,
        aea_config=AEAConfig(),
        stage_config_path=STAGE_CONFIG,
        pricing_path=PRICING,
        rollout_concurrency=concurrency,
    )


def stage_corpus(task_concurrency: int) -> None:
    guard("corpus")
    inflight = task_concurrency * ROLLOUT_CONCURRENCY
    if task_concurrency < 1 or inflight > MAX_INFLIGHT_EPISODES:
        raise ConfigError(
            f"task concurrency {task_concurrency} x {ROLLOUT_CONCURRENCY} rollouts = {inflight} "
            f"episodes in flight; the cap is {MAX_INFLIGHT_EPISODES}"
        )
    policy = policy_qwen()
    run_config = RunConfig(
        schema_version=1,
        name=RUN_ID,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=policy,  # RunConfig needs one; the proposer is OFF (manifest extra 'proposer')
        runs_root=RUNS,
    )
    d = run_dir()
    if (d / "manifest.json").exists():
        ctx, _ = load_run_context(d)
    else:
        ctx = create_run_context(
            run_config,
            runs_root=RUNS,
            run_id=RUN_ID,
            repo_dir=ROOT,
            aea_config_sha256=aea_config_sha256(AEAConfig()),
        )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=None,
        extra={
            "experiment": "E2 step 1 under aea v0.2 (Phase D)",
            "arm": "Z",
            "tasks": list(TASKS),
            "shared_k16_reused_from": "runs/e2-shared",
            "policy_endpoint_pin": policy.provider_pin,
            "proposer": "off",
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
        substrate(ctx.out_dir, ctx.run_id, ROLLOUT_CONCURRENCY),
        ctx.out_dir,
        ctx.run_id,
        arm="Z",
        use_proposer=False,
    )
    outcomes = ctrl.run([TaskRef(str(t), t) for t in TASKS], concurrency=task_concurrency)
    merge(ctx.out_dir)
    for o in outcomes:
        print(
            json.dumps(
                {
                    "arm": "Z",
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
    print(json.dumps({"stage": "corpus", "done": True, "usd": round(spend(), 2)}))


def stage_confirm(concurrency: int) -> None:
    guard("confirm")
    cfg = AEAConfig()
    d = run_dir()
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub = substrate(d, f"{RUN_ID}-confirm", concurrency)
    entries = read_corpus(d / "corpus.jsonl") if (d / "corpus.jsonl").exists() else []
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    writer = TraceWriter(d / "confirm.jsonl")
    for e in entries:
        if e.aea.kind == "kept" or str(e.aea.candidate_id) in summary:
            continue
        task = TaskRef(e.aea.task_id, e.aea.seed)
        reset = sub.stage_reset_options(task) if e.aea.kind == "stage" else None
        got = sub.rollouts(
            task,
            e.to_candidate(),
            cfg.k,
            attribution=Attribution(phase="confirm", budget="eval", arm="Z", task_id=task.task_id),
            reset_options=reset,
        )
        for tr in got:
            tr.candidate_id = str(e.aea.candidate_id)
            writer.add(tr)
        ok = sum(int(bool(tr.success)) for tr in got)
        errs = sum(1 for tr in got if tr.error)
        n = len(got) - errs
        summary[str(e.aea.candidate_id)] = {
            "task": e.aea.task_id,
            "kind": e.aea.kind,
            "t": e.aea.t,
            "successes": ok,
            "n": n,
            "errors": errs,
            "p16": ok / n if n else None,
            "learnable": bool(n and cfg.learnable(ok, n)),
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": e.aea.candidate_id, "successes": ok, "n": n}), flush=True)
    merge(d)
    print(json.dumps({"stage": "confirm", "envs": len(summary), "usd": round(spend(), 2)}))


# ---------------------------------------------------------------------------- tables
def v02_profile() -> dict[str, dict[str, Any]]:
    per: dict[str, dict[str, Any]] = {
        t: {
            "outcome": None,
            "reason": None,
            "regime": None,
            "p_hat": None,
            "n_est": 0,
            "certified": 0,
            "rejected": 0,
            "probes": [],
            "n_search": None,
            "rollouts": defaultdict(int),
        }
        for t in mte.TASKS
    }
    for e in mt.jsonl(run_dir() / "events.jsonl"):
        k, p = e.get("kind"), e.get("payload", {})
        t = str(p.get("task_id"))
        if t not in per:
            continue
        if k == "estimate":
            per[t].update({"regime": p.get("regime"), "p_hat": p.get("p_hat"), "n_est": p.get("n")})
        elif k == "stage_candidates":
            per[t]["certified"] = len(p.get("certified") or [])
            per[t]["rejected"] = len(p.get("rejected") or [])
        elif k == "probe":
            per[t]["probes"] = list(p.get("profile") or [])
            per[t]["skipped"] = list(p.get("skipped") or [])
        elif k == "rollouts":
            per[t]["rollouts"][str(p.get("phase"))] += int(p.get("n", 0))
        elif k == "task_done":
            per[t].update(
                {
                    "outcome": p.get("outcome"),
                    "reason": p.get("reason"),
                    "n_search": p.get("n_search"),
                }
            )
    return per


def stage_tables() -> None:
    rng = random.Random(20260910)
    shared = mte.confirm("shared")
    zero_tasks = {
        str(e["task"]) for e in shared.values() if e.get("successes") == 0 and (e.get("n") or 0) > 0
    }
    conf = (
        json.loads((run_dir() / "confirm_summary.json").read_text())
        if (run_dir() / "confirm_summary.json").exists()
        else {}
    )
    learn: dict[str, int] = defaultdict(int)
    for e in conf.values():
        if e.get("learnable"):
            learn[str(e["task"])] += 1
    rolls: dict[str, int] = defaultdict(int)
    for r in mt.jsonl(run_dir() / "traces.jsonl"):
        if not r.get("error"):
            rolls[str(r["rollout_seed"])] += 1
    tasks = list(mte.TASKS)
    tl, tr_ = sum(learn.values()), sum(rolls.values())
    boots = []
    for _ in range(mt.BOOT):
        s = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        lr, rr = sum(learn.get(t, 0) for t in s), sum(rolls.get(t, 0) for t in s)
        boots.append(1000 * lr / rr if rr else 0.0)
    boots.sort()
    z02: dict[str, Any] = {
        "envs": len(conf),
        "learnable": tl,
        "rollouts": tr_,
        "per_1000": 1000 * tl / tr_ if tr_ else float("nan"),
        "ci95": [boots[int(0.025 * mt.BOOT)], boots[int(0.975 * mt.BOOT)]],
    }
    unl02 = sorted(
        {
            str(e["task"])
            for e in conf.values()
            if e.get("learnable") and str(e["task"]) in zero_tasks
        },
        key=int,
    )
    v01 = {arm: mte.z1(arm, rng) for arm in ("Z", "G", "R")}
    unl01 = {arm: mte.unlocked(arm, zero_tasks) for arm in ("Z", "G", "R")}
    lines = [
        "# E2 step 1 under aea v0.2 (Phase D) — next to the v0.1 numbers",
        "",
        "Same 10 tasks, same policy (Qwen3-8B, alibaba pin), same cap 30; the shared original-environment K=16 of the v0.1 run is reused.",  # noqa: E501
        "v0.2 Z runs the box of docs/spec/AEA_v0.2.md (one 4 → 8 rule on the stage side, end + midpoint states, oracle guard).",  # noqa: E501
        "",
        "## Z1 — learnable environments per 1,000 charged search rollouts",
        "",
        "| arm | accepted envs | learnable | search rollouts | per 1,000 [95% CI] |",
        "|---|---|---|---|---|",
        f"| Z (v0.2) | {z02['envs']} | {z02['learnable']} | {z02['rollouts']} | {mt.fmt(z02['per_1000'])} [{mt.fmt(z02['ci95'][0])}, {mt.fmt(z02['ci95'][1])}] |",  # noqa: E501
    ]
    for arm in ("Z", "G", "R"):
        r = v01[arm]
        lines.append(
            f"| {arm} (v0.1) | {r['envs']} | {r['learnable']} | {r['rollouts']} | {mt.fmt(r['per_1000'])} [{mt.fmt(r['ci95'][0])}, {mt.fmt(r['ci95'][1])}] |"  # noqa: E501
        )
    lines += [
        "",
        "## Z2 — unlocked zero tasks",
        "",
        "| arm | unlocked | tasks |",
        "|---|---|---|",
        f"| Z (v0.2) | {len(unl02)} | {', '.join(unl02) or '-'} |",
    ]
    for arm in ("Z", "G", "R"):
        lines.append(f"| {arm} (v0.1) | {len(unl01[arm])} | {', '.join(unl01[arm]) or '-'} |")
    z2 = len(unl02) >= 3 and len(unl02) >= len(unl01["G"])
    kill = len(unl02) <= 1 or len(unl02) < len(unl01["G"])
    lines += [
        "",
        f"**v0.2: Z1 Z > G {'holds' if z02['per_1000'] > v01['G']['per_1000'] else 'fails'}, Z > R {'holds' if z02['per_1000'] > v01['R']['per_1000'] else 'fails'}; Z2 {'holds' if z2 else 'fails'}; kill rule {'TRIGGERED' if kill else 'not triggered'}.**",  # noqa: E501
        "",
        "## Z3 — v0.2 per-task profile",
        "",
        "| task | shared p16 | estimate (regime, p_hat, n) | guarded / rejected states | probes (t: s/n verdict) | outcome | reason | n_search |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|",
    ]
    prof = v02_profile()
    for t in mte.TASKS:
        v = prof[t]
        probes = (
            "; ".join(
                f"{x.get('t')}: {x.get('successes')}/{x.get('n')} {x.get('verdict')}"
                for x in v["probes"]
            )
            or "-"
        )
        lines.append(
            f"| {t} | {mt.fmt(shared.get(f'{t}:orig', {}).get('p16'), 3)} | {v['regime']}, {mt.fmt(v['p_hat'], 3)}, {v['n_est']} | {v['certified']} / {v['rejected']} | {probes} | {v['outcome']} | {v['reason'] or '-'} | {v['n_search']} |"  # noqa: E501
        )
    lines += [
        "",
        "### Accepted environments and their p16 (v0.2)",
        "",
        "| task | env | t | p16 | learnable |",
        "|---|---|---|---|---|",
    ]
    for env_id, e in sorted(conf.items(), key=lambda kv: int(kv[1]["task"])):
        lines.append(
            f"| {e['task']} | {env_id[:40]} | {e.get('t')} | {mt.fmt(e.get('p16'), 3)} | {'y' if e.get('learnable') else '-'} |"  # noqa: E501
        )
    lines += [
        "",
        f"Spend (v0.2 Z run, search + confirm): USD {spend():.2f} (Phase-D cap {CAP_USD}).",
        "",
    ]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e2_step1_v02.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def stage_probe() -> int:
    """One cheap ledgered call to the policy endpoint: 0 if it answers, 1 on a throttle."""
    policy = policy_qwen().model_copy(
        update={"retry": RetryConfig(max_attempts=1), "max_tokens": 8}
    )
    out = RUNS / "e2-probe"
    out.mkdir(parents=True, exist_ok=True)
    key = load_settings().require(policy.api_key_env.lower())
    client = OpenAICompatibleClient(
        config=policy,
        transport=make_openai_transport(api_key=key, base_url=policy.base_url, timeout_s=60.0),
        ledger=Ledger(out / "ledger.jsonl", "e2-probe"),
        pricing=load_pricing(PRICING),
    )
    req = ChatRequest(
        model=policy.model,
        messages=(ChatMessage(role="user", content="Reply with the single word OK."),),
        max_tokens=8,
        attribution=Attribution(phase="endpoint_probe", budget="none", arm="infra", task_id="e2"),
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
        "--stage", required=True, choices=["probe", "corpus", "confirm", "tables", "spend"]
    )
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe":
            return stage_probe()
        if args.stage == "corpus":
            stage_corpus(args.concurrency)
        elif args.stage == "confirm":
            stage_confirm(max(args.concurrency, 6))
        elif args.stage == "tables":
            stage_tables()
        else:
            print(
                json.dumps(
                    {
                        "usd": round(spend(), 2),
                        "cap": CAP_USD,
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
