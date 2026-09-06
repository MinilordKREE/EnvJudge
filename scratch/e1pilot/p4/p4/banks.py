"""P4.4 banks: released induction (DeepSeek V4 Pro, thinking off; embeddings gemini-embedding-001 via OpenRouter) on
I-sat / N-sat / N-zero bank trajectories (8 per confirmed/selected env) and per-arm controls orig_c(arm) = 8 seeded P1
trajectories per task on the arm's task set. Item-matched banks subsample both sides to min(items), seed 20260912."""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(EOBS)); sys.path.insert(0, str(ROOT / "p4"))
from e1.p3a import EMBED_MODEL, install_wrappers  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402

RES = ROOT / "p4" / "results"
BANKS = RES / "banks"
SEED = 20260912


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def arm_trajectories() -> dict[str, dict[str, list[dict]]]:
    """arm -> {task_id: [trace dicts]} for the three treatment arms (confirmed/selected envs only)."""
    arms: dict[str, dict[str, list[dict]]] = {"isat": {}, "nsat": {}, "nzero": {}}
    isat = [r for r in csv.DictReader(open(RES / "isat_confirm.csv")) if r["confirmed"] == "True"]
    tr = _jsonl(ROOT / "work" / "runs" / "e1_p4_isat" / "traces.jsonl")
    for r in isat:
        tag = f"p4isat-{r['task_id']}-{r['env'].replace(':', '-')}"
        arms["isat"][r["task_id"]] = [t for t in tr if t["candidate_id"] == tag and not t.get("error")][:8]
    nsat = [r for r in _jsonl(RES / "nsat_doses.jsonl") if r.get("confirmed")]
    tr = _jsonl(ROOT / "work" / "runs" / "e1_p4_nsat" / "traces.jsonl")
    for r in nsat:
        tag = (f"p4nsat-{r['task_id']}-F_H-{r['dose']}-bank" if r["family"] == "F_H" else f"p4nsat-{r['task_id']}-Chain-2-{r['partner']}-bank")
        arms["nsat"][str(r["task_id"])] = [t for t in tr if t["candidate_id"] == tag and not t.get("error")][:8]
    nz = [r for r in csv.DictReader(open(RES / "nzero_envs.csv")) if r.get("status") == "selected"]
    tr = _jsonl(ROOT / "work" / "runs" / "e1_p4_nzero" / "traces.jsonl")
    for r in nz:
        tag = f"p4chs-{r['task_id']}-{r['selected_episode']}-{r['selected_t']}-bank"
        arms["nzero"][r["task_id"]] = [t for t in tr if t["candidate_id"] == tag and not t.get("error")][:8]
    return arms


def control_trajectories(task_ids: list[str]) -> dict[str, list[dict]]:
    rnd = random.Random(SEED)
    p1 = _jsonl(ROOT / "work" / "runs" / "e1_qwen_map" / "traces.jsonl")
    return {t: rnd.sample([x for x in p1 if str(x["rollout_seed"]) == t and not x.get("error")], 8) for t in task_ids}


def main() -> None:
    install_wrappers("p4_induce", "deepseek")
    os.environ["EOBS_RUN_ID"] = "e1_p4_banks"
    sys.path.insert(0, str(ENVHARNESS_ROOT))
    spec = importlib.util.spec_from_file_location("induce_pair", ENVHARNESS_ROOT / "scripts" / "induce_pair.py")
    ip = importlib.util.module_from_spec(spec); spec.loader.exec_module(ip)
    BANKS.mkdir(parents=True, exist_ok=True)
    arms = arm_trajectories()
    meta = {}
    for arm, by in arms.items():
        if not by:
            meta[arm] = {"built": False, "reason": "no confirmed/selected env"}; continue
        ctrl = control_trajectories(sorted(by))
        for cond, traces in ((arm, by), (f"origc_{arm}", ctrl)):
            out = BANKS / f"{cond}_full.jsonl"
            n = ip._build_bank(condition=cond, traces_by_task=traces, llm_model="openai/deepseek-v4-pro", concurrency=4, embed_model=EMBED_MODEL, out_path=out)
            items = _jsonl(out)
            meta[cond] = {"built": True, "tasks": sorted(traces), "trajectories_per_task": {t: len(v) for t, v in traces.items()},
                          "successes_per_task": {t: sum(bool(x["success"]) for x in v) for t, v in traces.items()}, "items": n,
                          "item_types": dict(Counter(it["source"]["induction"] for it in items))}
            print(f"[P4.4] {cond}: {n} items from {len(traces)} tasks {meta[cond]['item_types']}", flush=True)
        # item-matched pair
        a, b = _jsonl(BANKS / f"{arm}_full.jsonl"), _jsonl(BANKS / f"origc_{arm}_full.jsonl")
        k = min(len(a), len(b))
        rnd = random.Random(SEED)
        for cond, items in ((arm, a), (f"origc_{arm}", b)):
            sub = rnd.sample(items, k) if len(items) > k else list(items)
            with open(BANKS / f"{cond}_m.jsonl", "w") as fh:
                for it in sub:
                    fh.write(json.dumps(it) + "\n")
            meta[cond]["items_matched"] = len(sub)
        meta[f"pair_{arm}"] = {"matched_items": k}
    (RES / "banks.json").write_text(json.dumps(meta, indent=1))
    print("[P4.4] done", flush=True)


if __name__ == "__main__":
    main()
