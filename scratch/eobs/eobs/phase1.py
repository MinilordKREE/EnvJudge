"""Phase 1: W_base witnesses (LLM-free) and 11 extra independent policy rollouts per task.

The extra rollouts use the orchestrator's OWN baseline code path: `run_harness.build_from_config` builds the
Orchestrator from corpus_eobs.yaml (identical PolicySpec/EnvSpec), with `k_per_candidate` overridden to 11 and
`rollout_concurrency` to 11 (permitted knob); we then call `Orchestrator._rollout_baseline_k(task_idx, task_id)`
per task and store the traces (kind="baseline", source "extra") in a separate run dir. Prompt identity with
EnvRigger's baseline is checked in `prove_prompt_identity` by comparing the logged first policy call (system prompt +
initial user observation) of the smoke/Phase-2 run with this run on the same task.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from eobs.settings import ENVHARNESS_ROOT, EOBS_ROOT, RESULTS, WORK, secrets


def _witness(seed: int) -> dict:
    from eobs.replay import witness_base
    return witness_base(seed)


def run_witnesses(n: int, out: Path, workers: int = 6) -> list[dict]:
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_witness, range(n)))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def run_extra_rollouts(n: int, run_name: str, k: int = 11) -> None:
    os.environ["OPENAI_API_KEY"] = secrets().deepseek_api_key.get_secret_value()
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["EOBS_RUN_ID"] = run_name
    os.environ["EOBS_PHASE"] = "phase1"
    os.environ["PYTHONPATH"] = str(EOBS_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    sys.path.insert(0, str(ENVHARNESS_ROOT / "scripts"))
    sys.path.insert(0, str(ENVHARNESS_ROOT))
    os.chdir(ENVHARNESS_ROOT)
    import run_harness  # released script, used as a library
    orch = run_harness.build_from_config(EOBS_ROOT / "configs" / "corpus_eobs.yaml", run_name,
                                         overrides={"n_tasks": n, "n_iterations": n, "k_per_candidate": k, "rollout_concurrency": k})
    orch.log.event("phase1_start", n_tasks=n, k=k, note="extra baseline rollouts via Orchestrator._rollout_baseline_k")
    done = {(t.rollout_seed) for t in orch.trace_store.all()}
    for task_idx in range(n):
        task_id = orch.config.base_seed + task_idx * orch.config.task_id_stride + orch.config.task_id_base_offset
        if sum(1 for t in orch.trace_store.all() if t.rollout_seed == task_id) >= k:
            continue   # resumable
        os.environ["EOBS_TASK_ID"] = str(task_id)
        t0 = time.time()
        traces = orch._rollout_baseline_k(task_idx, task_id)
        for t in traces:
            t.kind = "baseline"
            orch.trace_store.add(t)
        sr = sum(1 for t in traces if t.success) / max(len(traces), 1)
        orch.log.event("phase1_task_done", task_idx=task_idx, task_id=task_id, k=len(traces), sr=round(sr, 3),
                       n_errors=sum(1 for t in traces if t.error), wall_s=round(time.time() - t0, 1))
        print(f"[phase1] task {task_id}: sr11={sr:.2f} errors={sum(1 for t in traces if t.error)} {time.time()-t0:.0f}s", flush=True)
    orch.log.event("phase1_end", n_traces=len(orch.trace_store))


def prove_prompt_identity(run_a: Path, run_b: Path, task_id: int) -> dict:
    """Compare the first policy call (system + first user message) for `task_id` between two runs."""
    def first_call(run: Path):
        rows = []
        for p in sorted(run.glob("policy_calls*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        rows.sort(key=lambda r: r.get("ts", 0))
        for r in rows:
            msgs = r.get("messages") or []
            if len(msgs) >= 2 and msgs[0].get("role") == "system":
                return msgs[0].get("content"), msgs[1].get("content")
        return None, None
    sa, ua = first_call(run_a)
    sb, ub = first_call(run_b)
    return {"system_identical": sa == sb and sa is not None, "first_user_identical": ua == ub and ua is not None,
            "system_len": (len(sa or ""), len(sb or "")), "user_len": (len(ua or ""), len(ub or ""))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-tasks", type=int, default=30)
    ap.add_argument("--run-name", default="eobs_phase1_extra")
    ap.add_argument("--witness-only", action="store_true")
    ap.add_argument("--rollouts-only", action="store_true")
    a = ap.parse_args()
    if not a.rollouts_only:
        rows = run_witnesses(a.n_tasks, RESULTS / "witness_base.jsonl")
        print(f"[phase1] W_base: {sum(r['W_base'] for r in rows)}/{len(rows)} pass; within 50 steps: {sum(r['within_policy_cap'] for r in rows)}", flush=True)
    if not a.witness_only:
        run_extra_rollouts(a.n_tasks, a.run_name)


if __name__ == "__main__":
    main()
