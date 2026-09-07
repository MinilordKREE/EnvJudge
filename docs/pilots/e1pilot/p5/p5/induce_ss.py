"""P5.2 — induction-mode control: single_succ banks (released induce_memory_items(success=True) via scripts/induce_pair._build_bank,
fed ONLY successful trajectories so the released _pick_pair rule takes the shortest success and no failure exists).
  isat_ss       : the 9 I-sat envs, trajectories = P4.1 confirmation rollouts (run e1_p4_isat, tag p4isat-<tid>-<env>).
  origc_isat_ss : the same 9 tasks, original environment, P1 trajectories (run e1_qwen_map).
Item-matched by seeded subsampling (20260914) to min(items); full banks supplementary (built, not evaluated).
Outputs p5/results/{isat_ss_bank.jsonl, origc_isat_ss_bank.jsonl, isat_ss_m.jsonl, origc_isat_ss_m.jsonl, induce_ss.json}."""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EOBS = ROOT.parent / "eobs"
for p in (ROOT, EOBS, ROOT / "p5"):
    sys.path.insert(0, str(p))
from e1.p3a import EMBED_MODEL, install_wrappers  # noqa: E402
from eobs.settings import ENVHARNESS_ROOT  # noqa: E402
from p5.banksize import subsample  # noqa: E402

RES = ROOT / "p5" / "results"
SEED = 20260914


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def successes() -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    isat = [r for r in csv.DictReader(open(ROOT / "p4" / "results" / "isat_confirm.csv")) if r["confirmed"] == "True"]
    tr4 = _jsonl(ROOT / "work" / "runs" / "e1_p4_isat" / "traces.jsonl")
    tr1 = _jsonl(ROOT / "work" / "runs" / "e1_qwen_map" / "traces.jsonl")
    a, b = {}, {}
    for r in isat:
        tag = f"p4isat-{r['task_id']}-{r['env'].replace(':', '-')}"
        a[r["task_id"]] = [t for t in tr4 if t["candidate_id"] == tag and t["success"] and not t.get("error")]
        b[r["task_id"]] = [t for t in tr1 if str(t["rollout_seed"]) == r["task_id"] and t["success"] and not t.get("error")]
    return a, b


def main() -> None:
    install_wrappers("p5_induce", "deepseek")
    os.environ["EOBS_RUN_ID"] = "e1_p5_induce"
    sys.path.insert(0, str(ENVHARNESS_ROOT))
    spec = importlib.util.spec_from_file_location("induce_pair", ENVHARNESS_ROOT / "scripts" / "induce_pair.py")
    ip = importlib.util.module_from_spec(spec); spec.loader.exec_module(ip)
    a, b = successes()
    meta = {}
    for cond, by in (("isat_ss", a), ("origc_isat_ss", b)):
        assert all(v for v in by.values()), f"{cond}: a task has no successful trajectory"
        out = RES / f"{cond}_bank.jsonl"
        n = ip._build_bank(condition=cond, traces_by_task=by, llm_model="openai/deepseek-v4-pro", concurrency=4, embed_model=EMBED_MODEL, out_path=out)
        items = _jsonl(out)
        types = Counter(it["source"]["induction"] for it in items)
        assert set(types) == {"single_succ"}, types
        meta[cond] = {"tasks": sorted(by), "successes_per_task": {t: len(v) for t, v in by.items()}, "shortest_success_len": {t: min(len(x["steps"]) for x in v) for t, v in by.items()},
                      "items": n, "item_types": dict(types)}
        print(f"[P5.2] {cond}: {n} items {dict(types)}", flush=True)
    ia, ib = _jsonl(RES / "isat_ss_bank.jsonl"), _jsonl(RES / "origc_isat_ss_bank.jsonl")
    k = min(len(ia), len(ib))
    for cond, items in (("isat_ss", ia), ("origc_isat_ss", ib)):
        sub = subsample(items, k, SEED)
        with open(RES / f"{cond}_m.jsonl", "w") as fh:
            for it in sub:
                fh.write(json.dumps(it) + "\n")
        meta[cond]["items_matched"] = len(sub)
    meta["matched_items"] = k
    (RES / "induce_ss.json").write_text(json.dumps(meta, indent=1))
    print("[P5.2] done; matched items", k, flush=True)


if __name__ == "__main__":
    main()
