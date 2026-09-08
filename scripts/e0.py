"""Phase 0b E0: EnvRigger released on seeds 0-19 with the E1-SL backbone, single-success banks,
released eval on the full splits x 3 seeds, cost per episode and the rounds projection.

Stages (resumable, each writes into runs/<run-id>/):
  corpus  released orchestrator (scripts/run_harness.build_from_config) with both clients routed
          through AeaLLMClient (designer rows budget=designer, policy rows budget=search, arm R)
  banks   N (none) / orig (baseline successes) / R (accepted successes), single-success induction
          through the released _build_bank under the eval hook (Flash-Lite as consumer, embeddings
          via OpenRouter)
  eval    aea.evaldriver.run_eval for N / orig / R, full ID + OOD, start seeds 0/1000/2000
  report  table next to EnvHarness Table 2, USD per corpus episode and per eval episode, projection
  regime  per-task baseline success of the corpus (Flash-Lite regime map; no LLM call)
  banks_released  the released Stage 2 + Stage 3 verbatim (scripts/induce_pair.py main: per-task
          cascade, paired-diff wherever a failure exists; scripts/subset.py) into banks_released/
          -- the Phase 0b diagnosis banks (owner decision 1)
Run: uv run python scripts/e0.py --stage corpus|banks|banks_released|eval|regime|report --run-id ...
     eval takes --tag <name> and --conditions name=path,... to evaluate other banks
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from aea.config import AEAConfig, aea_config_sha256
from aea.core.config import LLMConfig, RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import load_run_context, write_manifest
from aea.e0config import derive_corpus_config, write_corpus_config
from aea.errors import ConfigError
from aea.evaldriver import run_eval
from aea.evalhook import install, make_hook
from aea.io import training_traces
from aea.llm.attribution import attributed
from aea.llm.ledger import read_ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution
from aea.runner import AeaSubprocessRunner, merge_ledgers

ROOT = Path(__file__).resolve().parents[1]
ENVHARNESS = ROOT / "third_party" / "envharness"
TABLE2 = {"N": (62.6, 60.7), "orig": (63.3, 61.4), "EnvHarness": (66.2, 70.4)}


def backbone(fallback: bool) -> tuple[LLMConfig, LLMConfig]:
    if fallback:
        policy = LLMConfig(
            provider="openrouter",
            model="qwen/qwen3-8b",
            provider_pin="alibaba",
            thinking=False,
            temperature=0.5,
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
    policy = LLMConfig(
        provider="openrouter",
        model="google/gemini-3.1-flash-lite",
        provider_pin="google-ai-studio",
        thinking=None,
        temperature=0.5,
        max_tokens=2048,
    )
    return policy, policy.model_copy(update={"temperature": 0.7, "max_tokens": 4096})


def run_dir_for(run_id: str) -> Path:
    return ROOT / "runs" / run_id


def stage_corpus(run_id: str, n_tasks: int, fallback: bool) -> None:
    policy, designer = backbone(fallback)
    run_config = RunConfig(
        schema_version=1,
        name="e0-corpus",
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=ROOT / "runs",
    )
    ctx = create_run_context(
        run_config,
        runs_root=ROOT / "runs",
        run_id=run_id,
        repo_dir=ROOT,
        aea_config_sha256=aea_config_sha256(AEAConfig()),
    )
    env_sha = (
        subprocess.run(
            ["git", "-C", str(ENVHARNESS), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or None
    )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=env_sha,
        extra={
            "phase": "0b-E0",
            "stage": "corpus",
            "arm": "R",
            "n_tasks": n_tasks,
            "policy_endpoint_pin": policy.provider_pin,
            "designer_endpoint_pin": designer.provider_pin,
            "thinking": policy.thinking,
            "prereg": "experiments/alfworld_sl/PREREG7.md",
        },
    )
    cfg = derive_corpus_config(
        ENVHARNESS / "experiments" / "alfworld" / "corpus.yaml",
        run_dir=ctx.out_dir,
        policy=policy,
        designer=designer,
        pricing_path=ROOT / "configs" / "pricing.yaml",
    )
    cfg_path = write_corpus_config(cfg, ctx.out_dir / "corpus_e0.yaml")
    sys.path.insert(0, str(ENVHARNESS / "scripts"))
    sys.path.insert(0, str(ENVHARNESS))
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"  # the released key presence check only
    os.environ["AEA_RUN_ID"] = ctx.run_id
    run_harness = importlib.import_module("run_harness")
    orch = run_harness.build_from_config(
        cfg_path, run_id, overrides={"n_tasks": n_tasks, "n_iterations": n_tasks}
    )
    orch.runner = AeaSubprocessRunner(
        ctx.run_id,
        default=(Attribution(phase="corpus", budget="search", arm="R", task_id="e0"), 0),
        timeout=float(cfg["runner"].get("timeout_seconds", 600)),
        subprocess_log_dir=ctx.out_dir / "subprocess_logs",
    )
    with attributed(Attribution(phase="corpus", budget="search", arm="R", task_id="e0"), seed=0):
        orch.run()
    merge_ledgers(ctx.out_dir, ctx.run_id)
    print(
        json.dumps(
            {"stage": "corpus", "run_dir": str(ctx.out_dir), "traces": len(orch.trace_store.all())}
        ),
        flush=True,
    )


def stage_banks(run_id: str, fallback: bool) -> None:
    run_dir = run_dir_for(run_id)
    ctx, _manifest = load_run_context(run_dir)
    policy, _ = backbone(fallback)
    pricing = load_pricing(ROOT / "configs" / "pricing.yaml")
    induce = Attribution(phase="induce", budget="eval", arm="R", task_id="e0")
    # the released induction fans out over a ThreadPoolExecutor (induce_pair.py:153), which does
    # not inherit the contextvar binding: the hook's default labels those rows
    hook = make_hook(
        policy, run_dir=run_dir, run_id=ctx.run_id, pricing=pricing, default=(induce, 0)
    )
    install(hook)
    sys.path.insert(0, str(ENVHARNESS))
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    spec = importlib.util.spec_from_file_location(
        "induce_pair", ENVHARNESS / "scripts" / "induce_pair.py"
    )
    assert spec and spec.loader
    ip = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ip)
    traces = training_traces(run_dir / "traces.jsonl")
    by_kind: dict[str, dict[str, list[dict[str, Any]]]] = {
        "orig": defaultdict(list),
        "R": defaultdict(list),
    }
    for t in traces:
        if t.error or not t.success:
            continue  # single-success induction: successes only
        task = str(t.rollout_seed)
        if t.kind == "baseline":
            by_kind["orig"][task].append(t.model_dump())
        elif t.kind == "accepted":
            by_kind["R"][task].append(t.model_dump())
    meta: dict[str, Any] = {}
    banks_dir = run_dir / "banks"
    banks_dir.mkdir(exist_ok=True)
    with attributed(induce, seed=0):
        for cond, by_task in by_kind.items():
            out = banks_dir / f"{cond}.jsonl"
            n = (
                ip._build_bank(
                    condition=cond,
                    traces_by_task=dict(by_task),
                    llm_model=f"openai/{policy.model}",
                    concurrency=4,
                    embed_model="openai/google/gemini-embedding-001",
                    out_path=out,
                )
                if by_task
                else 0
            )
            meta[cond] = {
                "tasks": sorted(by_task),
                "items": n,
                "trajectories": {k: len(v) for k, v in by_task.items()},
            }
            print(
                json.dumps(
                    {"stage": "banks", "condition": cond, "items": n, "tasks": len(by_task)}
                ),
                flush=True,
            )
    (run_dir / "banks.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    merge_ledgers(run_dir, ctx.run_id)


def _load_released(name: str, rel: str) -> Any:
    sys.path.insert(0, str(ENVHARNESS))
    spec = importlib.util.spec_from_file_location(name, ENVHARNESS / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stage_banks_released(run_id: str, fallback: bool) -> None:
    """Owner decision 1 (Phase 0b gate): the released Stage 2 and Stage 3 exactly as
    experiments/alfworld/reproduce.py runs them, on this run's traces.jsonl. Stage 2 (induce_pair
    main) builds orig_full from the baseline rollouts and ours_full by per-task cascade (accepted
    rollouts where the task has them, else its baseline rollouts), paired-diff wherever a task has
    both a success and a failure, single-success otherwise. Stage 3 (subset.py) samples one item
    per shared task. The headline eval of reproduce.py uses the FULL banks."""
    run_dir = run_dir_for(run_id)
    ctx, _manifest = load_run_context(run_dir)
    policy, _ = backbone(fallback)
    pricing = load_pricing(ROOT / "configs" / "pricing.yaml")
    induce = Attribution(phase="induce_released", budget="eval", arm="R", task_id="e0")
    hook = make_hook(
        policy, run_dir=run_dir, run_id=ctx.run_id, pricing=pricing, default=(induce, 0)
    )
    install(hook)
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    ip = _load_released("induce_pair", "scripts/induce_pair.py")
    sub = _load_released("subset", "scripts/subset.py")
    out = run_dir / "banks_released"
    out.mkdir(exist_ok=True)
    with attributed(induce, seed=0):
        rc = ip.main(
            [
                "--traces",
                str(run_dir / "traces.jsonl"),
                "--out-dir",
                str(out),
                "--llm-model",
                f"openai/{policy.model}",
                "--embed-model",
                "openai/google/gemini-embedding-001",
                "--concurrency",
                "4",
            ]
        )
        if rc:
            raise ConfigError(f"released induce_pair exited {rc}")
        rc = sub.main(
            [
                "--orig",
                str(out / "orig_full.jsonl"),
                "--ours",
                str(out / "ours_full.jsonl"),
                "--out-dir",
                str(out),
            ]
        )
        if rc:
            raise ConfigError(f"released subset exited {rc}")
    merge_ledgers(run_dir, ctx.run_id)
    meta: dict[str, Any] = {}
    for name in ("orig_full", "ours_full", "orig_subset", "ours_subset_matched"):
        items = [
            json.loads(line)
            for line in (out / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        modes: dict[str, int] = defaultdict(int)
        tasks: set[str] = set()
        for it in items:
            src = it.get("source") or {}
            modes[str(src.get("induction"))] += 1
            tasks.add(str(src.get("task_id")))
        meta[name] = {"items": len(items), "tasks": sorted(tasks), "induction": dict(modes)}
    (run_dir / "banks_released.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps({"stage": "banks_released", **{k: v["items"] for k, v in meta.items()}}))


def stage_regime(run_id: str) -> None:
    """Per-task baseline success of the corpus (5 rollouts per task in the released config) and
    what the released designer did on each task; no LLM call."""
    run_dir = run_dir_for(run_id)
    traces = [
        json.loads(line)
        for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    per: dict[str, dict[str, Any]] = {}
    for t in traces:
        tid = str(t.get("rollout_seed"))
        row = per.setdefault(
            tid,
            {
                "base_s": 0,
                "base_n": 0,
                "acc_s": 0,
                "acc_n": 0,
                "accepted": set(),
                "rejected": set(),
            },
        )
        kind, cid, ok = t.get("kind"), str(t.get("candidate_id")), bool(t.get("success"))
        if kind == "baseline":
            row["base_n"] += 1
            row["base_s"] += int(ok)
        elif kind == "accepted":
            row["acc_n"] += 1
            row["acc_s"] += int(ok)
            row["accepted"].add(cid)
        elif kind == "exploration":
            row["rejected"].add(cid)

    def cls(s: int, n: int) -> str:
        if s == 0:
            return "zero"
        if s == 1:
            return "marginal-low"
        if s == n:
            return "saturated"
        return "mid" if s <= n // 2 + (n % 2) else "high"

    lines = [
        f"# Corpus regime map ({run_id}; released EnvRigger corpus, baseline rollouts per task)",
        "",
        "| task | baseline s/n | class | accepted candidates | rejected | accepted-env s/n |",
        "|---|---|---|---|---|---|",
    ]
    counts: dict[str, int] = defaultdict(int)
    for tid in sorted(per, key=int):
        r = per[tid]
        c = cls(r["base_s"], r["base_n"])
        counts[c] += 1
        lines.append(
            f"| {tid} | {r['base_s']}/{r['base_n']} | {c} | {len(r['accepted'])} | "
            f"{len(r['rejected'])} | {r['acc_s']}/{r['acc_n']} |"
        )
    n_tasks = len(per)
    thin = counts["zero"] + counts["marginal-low"]
    lines += [
        "",
        "Classes on the baseline rollouts: zero = 0/n; marginal-low = 1/n; mid = 2-3/5; "
        "high = 4/5; "
        "saturated = n/n.",
        "Counts: "
        + ", ".join(
            f"{k} {counts[k]}" for k in ("zero", "marginal-low", "mid", "high", "saturated")
        )
        + f" (of {n_tasks}).",
        f"Zero + marginal-low: {thin}/{n_tasks} = {100 * thin / n_tasks:.0f}% "
        f"({'below' if thin < 0.1 * n_tasks else 'at or above'} the owner's 10% "
        "thin-evidence line).",
        f"Designer: {sum(1 for r in per.values() if r['accepted'])}/{n_tasks} tasks with an "
        "accepted "
        f"candidate ({sum(len(r['accepted']) for r in per.values())} accepted, "
        f"{sum(len(r['rejected']) for r in per.values())} rejected).",
    ]
    (run_dir / "regime.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def stage_eval(
    run_id: str,
    fallback: bool,
    seeds: tuple[int, ...],
    concurrency: int,
    tag: str = "",
    conditions_arg: str = "",
    only_split: str = "",
    extra_argv: tuple[str, ...] = (),
) -> None:
    run_dir = run_dir_for(run_id)
    ctx, _ = load_run_context(run_dir)
    policy, _ = backbone(fallback)
    pricing = load_pricing(ROOT / "configs" / "pricing.yaml")
    eval_yaml = ENVHARNESS / "experiments" / "alfworld" / "reasoning_bank_eval.yaml"
    cfg = yaml.safe_load(eval_yaml.read_text(encoding="utf-8"))
    cfg["model"]["name"] = f"openai/{policy.model}"
    cfg["eval"]["concurrency"] = concurrency
    if only_split:  # resume of one crashed cell: the released loop runs every split in the config
        cfg["eval"]["splits"] = {f"eval_{only_split}": cfg["eval"]["splits"][f"eval_{only_split}"]}
    resolved = run_dir / (
        f"reasoning_bank_eval_e0_{only_split}.yaml" if only_split else "reasoning_bank_eval_e0.yaml"
    )
    resolved.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    banks_dir = run_dir / "banks"
    conditions: dict[str, Path | None]
    if conditions_arg:  # name=path[,name=path]; paths relative to the run dir
        conditions = {}
        for kv in conditions_arg.split(","):
            name, _, path = kv.partition("=")
            conditions[name.strip()] = run_dir / path.strip() if path.strip() else None
    else:
        conditions = {"nobank": None, "orig": banks_dir / "orig.jsonl", "R": banks_dir / "R.jsonl"}
    missing = [k for k, v in conditions.items() if v is not None and not v.exists()]
    if missing:
        raise ConfigError(f"bank file missing for {missing}")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    # one directory per invocation: the released eval names rounds round1.. per call, so seeds
    # run in separate invocations (Phase-0 cap pacing) must not overwrite each other
    prefix = f"{tag}-" if tag else ""
    out_dir = run_dir / "eval" / (prefix + "seeds-" + "-".join(str(s) for s in seeds))
    rc = run_eval(
        arm="R",
        conditions=conditions,
        config_yaml=resolved,
        out_dir=out_dir,
        start_seeds=seeds,
        concurrency=concurrency,
        llm=policy,
        pricing=pricing,
        run_id=ctx.run_id,
        envharness_root=ENVHARNESS,
        extra_argv=extra_argv,
    )
    merge_ledgers(out_dir, ctx.run_id)
    print(
        json.dumps(
            {"stage": "eval", "rc": rc, "conditions": list(conditions), "out_dir": str(out_dir)}
        ),
        flush=True,
    )


type Cells = dict[str, dict[str, dict[str, tuple[int, int]]]]


def _cells(eval_root: Path, dir_glob: str) -> Cells:
    """{condition: {split: {seed_block: (won, n)}}} from
    <dir_glob>/round*/<cond>_eval_<split>.jsonl. A cell resumed after a crash lives in a second
    directory whose start seed is inside the same 1,000-seed block (released rounds start at
    0 / 1000 / 2000); its records are added to that block's cell."""
    results: Cells = {}
    for p in (
        sorted(eval_root.glob(f"{dir_glob}/round*/*_eval_*.jsonl")) if eval_root.exists() else []
    ):
        cond, split = p.stem.rsplit("_eval_", 1)
        m = re.search(r"seeds-(\d+)", p.parents[1].name)
        block = f"seeds-{(int(m.group(1)) // 1000) * 1000}" if m else p.parents[1].name
        recs = [
            json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        won = sum(1 for r in recs if r.get("success"))
        cell = results.setdefault(cond, {}).setdefault(split, {})
        prev = cell.get(block, (0, 0))
        cell[block] = (prev[0] + won, prev[1] + len(recs))
    return results


def _rate(cells: Cells, cond: str, split: str) -> tuple[float, int]:
    c = cells.get(cond, {}).get(split, {})
    won, n = sum(w for w, _ in c.values()), sum(k for _, k in c.values())
    return (100 * won / n if n else float("nan")), n


def _per_seed(cells: Cells, cond: str, split: str, seed_dirs: list[str]) -> str:
    c = cells.get(cond, {}).get(split, {})
    return " / ".join(
        f"{100 * c[sd][0] / c[sd][1]:.1f}" if sd in c and c[sd][1] else "-" for sd in seed_dirs
    )


def _gap_se(cells: Cells, a: str, b: str, split: str) -> str:
    """Difference of pooled success rates with a normal-approximation SE (points)."""
    (pa, na), (pb, nb) = _rate(cells, a, split), _rate(cells, b, split)
    if not na or not nb:
        return "n/a"
    return f"{pa - pb:+.1f} ± {(pa * (100 - pa) / na + pb * (100 - pb) / nb) ** 0.5:.1f}"


def _table(cells: Cells, rows: list[tuple[str, str]]) -> list[str]:
    seed_dirs = sorted({sd for c in cells.values() for sp in c.values() for sd in sp})
    lines = [
        f"Seeds: {', '.join(seed_dirs) or 'none'}; success % pooled (per-seed values in brackets).",
        "",
        "| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |",
        "|---|---|---|---|---|",
    ]
    for cond, label in rows:
        (i, idn), (o, oodn) = (
            _rate(cells, cond, "in_distribution"),
            _rate(cells, cond, "out_of_distribution"),
        )
        t2 = TABLE2[label]
        lines.append(
            f"| {cond} ({label}) | {i:.1f} (n={idn}) "
            f"[{_per_seed(cells, cond, 'in_distribution', seed_dirs)}] "
            f"| {o:.1f} (n={oodn}) [{_per_seed(cells, cond, 'out_of_distribution', seed_dirs)}] "
            f"| {t2[0]} | {t2[1]} |"
        )
    return lines


def _signs(cells: Cells, n: str, orig: str, r: str) -> list[str]:
    t2n, t2o, t2r = TABLE2["N"], TABLE2["orig"], TABLE2["EnvHarness"]
    n_id, o_id, r_id = (_rate(cells, c, "in_distribution")[0] for c in (n, orig, r))
    n_ood, o_ood, r_ood = (_rate(cells, c, "out_of_distribution")[0] for c in (n, orig, r))

    def verdict(ok: bool) -> str:
        return "REPRODUCED" if ok else "NOT reproduced"

    return [
        "Sign check (PREREG7 reproduction sanity):",
        f"- orig > N on ID: ours {o_id - n_id:+.1f} pts (Table 2 {t2o[0] - t2n[0]:+.1f}) "
        f"-> {verdict(o_id > n_id)}",
        f"- EnvRigger > orig on OOD: ours {r_ood - o_ood:+.1f} pts "
        f"(Table 2 {t2r[1] - t2o[1]:+.1f}) "
        f"-> {verdict(r_ood > o_ood)}",
        f"- (reported, not a gate) EnvRigger vs N: ID {r_id - n_id:+.1f}, OOD {r_ood - n_ood:+.1f} "
        f"(Table 2 {t2r[0] - t2n[0]:+.1f} / {t2r[1] - t2n[1]:+.1f})",
        "",
        "Pooled gaps with normal-approximation SE (points):",
        f"- {orig} minus {n}: ID {_gap_se(cells, orig, n, 'in_distribution')}, "
        f"OOD {_gap_se(cells, orig, n, 'out_of_distribution')}",
        f"- {r} minus {orig}: ID {_gap_se(cells, r, orig, 'in_distribution')}, "
        f"OOD {_gap_se(cells, r, orig, 'out_of_distribution')}",
        f"- {r} minus {n}: ID {_gap_se(cells, r, n, 'in_distribution')}, "
        f"OOD {_gap_se(cells, r, n, 'out_of_distribution')}",
    ]


def stage_report(run_id: str) -> None:
    run_dir = run_dir_for(run_id)
    rows = read_ledger(run_dir / "ledger.jsonl") if (run_dir / "ledger.jsonl").exists() else []
    eval_root = run_dir / "eval"
    erows = [
        r
        for p in sorted(eval_root.glob("*seeds-*/ledger.jsonl"))
        if eval_root.exists()
        for r in read_ledger(p)
    ]
    traces = (
        training_traces(run_dir / "traces.jsonl") if (run_dir / "traces.jsonl").exists() else []
    )
    corpus_usd = sum(r.usd for r in rows if r.event == "call" and r.budget == "search")
    designer_usd = sum(r.usd for r in rows if r.event == "call" and r.budget == "designer")
    # every `eval`-budget row in the run ledger is induction (the eval ledgers live under eval/);
    # the first banks run labelled its completions phase=eval (thread pool, see LOG), so the
    # budget, not the phase, selects them; the released-pipeline banks carry phase=induce_released
    induce_usd = sum(
        r.usd
        for r in rows
        if r.event == "call" and r.budget == "eval" and r.phase != "induce_released"
    )
    induce_rel_usd = sum(r.usd for r in rows if r.event == "call" and r.phase == "induce_released")
    eval_usd = sum(r.usd for r in erows if r.event == "call" and r.budget == "eval")
    episodes = len(traces)

    e0 = _cells(eval_root, "seeds-*")  # E0: single-success banks, transformed environments only
    rel = _cells(eval_root, "released-*")  # diagnosis: released Stage 2 full banks
    for cond in ("nobank",):  # N is shared by both protocols
        if cond in e0:
            rel[cond] = e0[cond]
    e0_episodes = sum(n for c in e0.values() for sp in c.values() for _, n in sp.values())
    rel_episodes = sum(
        n for k, c in rel.items() if k != "nobank" for sp in c.values() for _, n in sp.values()
    )
    eval_episodes = e0_episodes + rel_episodes
    lines = [
        f"# E0 reproduction ({run_id})",
        "",
        "## E0 protocol (PREREG7): single-success banks, ID n=140 / OOD n=134 per seed",
        "",
        *_table(e0, [("nobank", "N"), ("orig", "orig"), ("R", "EnvHarness")]),
        "",
        *_signs(e0, "nobank", "orig", "R"),
    ]
    if any(k != "nobank" for k in rel):
        lines += [
            "",
            "## Diagnosis (owner decision 1): released Stage 2 banks (per-task cascade, "
            "paired-diff "
            "where a failure exists), full banks as in reproduce.py's headline eval",
            "",
            *_table(rel, [("nobank", "N"), ("orig_rel", "orig"), ("R_rel", "EnvHarness")]),
            "",
            *_signs(rel, "nobank", "orig_rel", "R_rel"),
        ]
    per_corpus = corpus_usd / episodes if episodes else float("nan")
    per_eval = eval_usd / eval_episodes if eval_episodes else float("nan")
    lines += [
        "",
        f"Corpus: {episodes} policy episodes, USD {corpus_usd:.2f} (USD {per_corpus:.4f} per "
        f"episode); designer USD {designer_usd:.2f}; induction USD {induce_usd:.2f} "
        f"(released-pipeline induction USD {induce_rel_usd:.2f}).",
        f"Eval: {eval_episodes} episodes (E0 {e0_episodes}, diagnosis {rel_episodes}), "
        f"USD {eval_usd:.2f} (USD {per_eval:.4f} per episode).",
        "",
    ]
    n_tasks = len({t.rollout_seed for t in traces})
    per_task = corpus_usd / n_tasks if n_tasks else float("nan")
    for n in (30, 50):
        adapt_arms = 3 * 3 + 4  # rounds 1-3 x {R, A, O} + round-1 {G, G+, A-ex, A+H}
        corpus_cost = adapt_arms * n * per_task
        confirm = adapt_arms * n * 16 * per_corpus
        evals = (3 * 3 + 4 + 1) * 3 * 274 * per_eval  # arms per round incl. N, 3 seeds, full splits
        lines.append(
            f"Projection N={n}: corpus USD {corpus_cost:.0f} + confirmations USD {confirm:.0f} "
            f"+ evals USD {evals:.0f} = USD {corpus_cost + confirm + evals:.0f}"
        )
    lines.append(
        f"Backbone rule: corpus episode USD {per_corpus:.4f} "
        f"{'>' if per_corpus > 0.10 else '<='} 0.10 -> "
        f"{'FALLBACK' if per_corpus > 0.10 else 'Flash-Lite stays'}."
    )
    (run_dir / "phase0b_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        choices=["corpus", "banks", "banks_released", "eval", "regime", "report"],
        required=True,
    )
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n-tasks", type=int, default=20)
    ap.add_argument("--fallback", action="store_true")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1000, 2000])
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--tag", default="", help="eval: output dir prefix (eval/<tag>-seeds-<s>)")
    ap.add_argument("--conditions", default="", help="eval: name=path,... relative to the run dir")
    ap.add_argument(
        "--only-split", default="", choices=["", "in_distribution", "out_of_distribution"]
    )
    ap.add_argument("--n-indist", type=int, default=None, help="eval: released --n-indist")
    ap.add_argument("--n-ood", type=int, default=None, help="eval: released --n-ood")
    args = ap.parse_args(argv)
    try:
        if args.stage == "corpus":
            stage_corpus(args.run_id, args.n_tasks, args.fallback)
        elif args.stage == "banks":
            stage_banks(args.run_id, args.fallback)
        elif args.stage == "banks_released":
            stage_banks_released(args.run_id, args.fallback)
        elif args.stage == "eval":
            stage_eval(
                args.run_id,
                args.fallback,
                tuple(args.seeds),
                args.concurrency,
                args.tag,
                args.conditions,
                args.only_split,
                tuple(
                    x
                    for flag, val in (("--n-indist", args.n_indist), ("--n-ood", args.n_ood))
                    if val is not None
                    for x in (flag, str(val))
                ),
            )
        elif args.stage == "regime":
            stage_regime(args.run_id)
        else:
            stage_report(args.run_id)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
