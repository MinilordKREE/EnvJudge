"""P3a — downstream skill sanity, two arms (nobank / skills-from-original), held-out ID 30 + OOD 30, same tasks × 3 replicates.

Uses the released ReasoningBank pipeline unchanged (scripts/induce_pair._build_bank for induction; experiments/alfworld/
reasoning_bank_eval.main for evaluation). Provider routing and accounting are injected by wrapping `litellm.completion` /
`litellm.embedding` IN THIS PROCESS (observe-and-route wrappers; third_party untouched):
  induction process: chat → DeepSeek V4 Pro (api.deepseek.com, thinking disabled), embeddings → OpenRouter google/gemini-embedding-001
  eval process:      chat → OpenRouter qwen/qwen3-8b (provider pinned alibaba, allow_fallbacks=false, reasoning off, usage.include),
                     embeddings → OpenRouter google/gemini-embedding-001 (same model as induction; 3072-d)
Every chat call → ledger row (phase p3_skills or p3_induce) with provider and upstream cost.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EOBS = ROOT.parent / "eobs"
sys.path.insert(0, str(EOBS))
from eobs.settings import ENVHARNESS_ROOT, secrets, tariff_at, usd_for  # noqa: E402

RES = ROOT / "results" / "e1pilot"
WORK = ROOT / "work"
LED = RES / "ledger.jsonl"
OR_BASE = "https://openrouter.ai/api/v1"
DS_BASE = "https://api.deepseek.com"
EMBED_MODEL = "openai/google/gemini-embedding-001"
QWEN = "openai/qwen/qwen3-8b"
PIN = {"reasoning": {"enabled": False}, "provider": {"order": ["alibaba"], "allow_fallbacks": False}, "usage": {"include": True}}


def _ledger(row: dict) -> None:
    LED.parent.mkdir(parents=True, exist_ok=True)
    with open(LED, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def install_wrappers(phase: str, chat_route: str) -> None:
    """chat_route: 'openrouter' (Qwen policy) or 'deepseek' (extractor). Embeddings always via OpenRouter."""
    import litellm
    sec = secrets()
    or_key = sec.openrouter_api_key.get_secret_value()
    ds_key = sec.deepseek_api_key.get_secret_value()
    real_completion, real_embedding = litellm.completion, litellm.embedding

    def completion(*args, **kw):
        model = kw.get("model", args[0] if args else "")
        if chat_route == "openrouter":
            kw.update({"api_base": OR_BASE, "api_key": or_key, "extra_body": {**(kw.get("extra_body") or {}), **PIN}})
        else:
            kw.update({"api_base": DS_BASE, "api_key": ds_key, "extra_body": {**(kw.get("extra_body") or {}), "thinking": {"type": "disabled"}}})
        t0 = time.time()
        try:
            r = real_completion(*args, **kw)
        except Exception as e:
            _ledger({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "phase": phase, "run_id": os.environ.get("EOBS_RUN_ID", ""), "model": model, "ok": False,
                     "error": f"{type(e).__name__}: {e}"[:200].replace(or_key, "<k>").replace(ds_key, "<k>"), "pid": os.getpid()})
            raise
        u = getattr(r, "usage", None)
        pt, ct = int(getattr(u, "prompt_tokens", 0) or 0), int(getattr(u, "completion_tokens", 0) or 0)
        cd = getattr(u, "completion_tokens_details", None)
        rt = int(getattr(cd, "reasoning_tokens", 0) or 0) if cd is not None else 0
        ts = time.time(); tariff = tariff_at(ts)
        _ledger({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), "phase": phase, "run_id": os.environ.get("EOBS_RUN_ID", ""), "task_id": os.environ.get("EOBS_TASK_ID", ""),
                 "model": model, "ok": True, "provider": getattr(r, "provider", None), "prompt_tokens": pt, "completion_tokens": ct, "reasoning_tokens": rt,
                 "upstream_cost": getattr(u, "cost", None), "tariff": tariff, "usd": usd_for(model, pt, 0, ct, tariff), "usd_peak_bound": usd_for(model, pt, 0, ct, "peak"),
                 "latency_ms": int((ts - t0) * 1000), "pid": os.getpid(), "pricing_version": __import__("eobs.settings", fromlist=["pricing_version_for"]).pricing_version_for(model)})
        return r

    def embedding(*args, **kw):
        kw.update({"api_base": OR_BASE, "api_key": or_key})
        r = real_embedding(*args, **kw)
        u = getattr(r, "usage", None)
        _ledger({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "phase": phase + "_embed", "model": kw.get("model", ""), "ok": True,
                 "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0), "completion_tokens": 0, "usd": 0.0, "usd_peak_bound": 0.0,
                 "upstream_cost": (u.get("cost") if isinstance(u, dict) else getattr(u, "cost", None)), "pid": os.getpid()})
        return r

    litellm.completion = completion
    litellm.embedding = embedding
    os.environ["EH_EMBED_MODEL"] = EMBED_MODEL
    os.environ["OPENAI_API_KEY"] = or_key if chat_route == "openrouter" else ds_key   # satisfies envharness's key presence checks; wrappers set the real key per call
    os.environ["EOBS_PHASE"] = phase


def _traces(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def induce(n_tasks: int = 30, concurrency: int = 4) -> None:
    """Skills-from-original: induce from Qwen's P1 trajectories (30 train tasks) with DeepSeek V4 Pro; bank = orig_qwen.jsonl."""
    install_wrappers("p3_induce", "deepseek")
    os.environ["EOBS_RUN_ID"] = "e1_p3a_induce"
    sys.path.insert(0, str(ENVHARNESS_ROOT))
    spec = importlib.util.spec_from_file_location("induce_pair", ENVHARNESS_ROOT / "scripts" / "induce_pair.py")
    ip = importlib.util.module_from_spec(spec); spec.loader.exec_module(ip)
    by_task = defaultdict(list)
    for t in _traces(WORK / "runs" / "e1_qwen_map" / "traces.jsonl"):
        if int(t["rollout_seed"]) < n_tasks and not t.get("error"):
            by_task[str(t["rollout_seed"])].append(t)
    out = RES / "banks" / "orig_qwen.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = ip._build_bank(condition="orig", traces_by_task=dict(by_task), llm_model="openai/deepseek-v4-pro", concurrency=concurrency, embed_model=EMBED_MODEL, out_path=out)
    print(f"[P3a] induced {n} items from {len(by_task)} tasks -> {out}", flush=True)


def make_eval_config(n_id: int, n_ood: int, concurrency: int) -> Path:
    cfg = yaml.safe_load((ENVHARNESS_ROOT / "experiments/alfworld/reasoning_bank_eval.yaml").read_text())
    cfg["model"]["name"] = QWEN
    cfg["eval"]["splits"] = {"eval_in_distribution": n_id, "eval_out_of_distribution": n_ood}
    cfg["eval"]["start_seed"] = 0
    cfg["eval"]["concurrency"] = concurrency
    p = ROOT / "configs" / "reasoning_bank_eval_qwen.yaml"
    p.write_text("# P3a: released reasoning_bank_eval.yaml with model.name -> openai/qwen/qwen3-8b, splits 30/30 (first tasks of each split, start_seed 0),\n# concurrency 6. Everything else (SkillOS prompt, history_length 4, temperature 0.4, retrieval mmr top_k 5) unchanged.\n" + yaml.safe_dump(cfg, sort_keys=False))
    return p


def evaluate(rep: int, n_id: int, n_ood: int, concurrency: int, conditions: str = "nobank,orig") -> None:
    install_wrappers("p3_skills", "openrouter")
    os.environ["EOBS_RUN_ID"] = f"e1_p3a_eval_r{rep}"
    sys.path.insert(0, str(ENVHARNESS_ROOT)); sys.path.insert(0, str(ENVHARNESS_ROOT / "experiments" / "alfworld"))
    os.chdir(ENVHARNESS_ROOT)
    import reasoning_bank_eval as rbe
    cfg = make_eval_config(n_id, n_ood, concurrency)
    out = WORK / "runs" / f"e1_p3a_eval_r{rep}"
    argv = ["--config", str(cfg), "--out-dir", str(out), "--start-seeds", "0", "--conditions", conditions, "--concurrency", str(concurrency),
            "--bank-overrides", f"orig={RES / 'banks' / 'orig_qwen.jsonl'}"]
    rc = rbe.main(argv)
    print(f"[P3a] eval rep {rep} rc={rc} -> {out}", flush=True)


def tables(reps: list[int]) -> None:
    rows = []
    for rep in reps:
        out = WORK / "runs" / f"e1_p3a_eval_r{rep}"
        for p in sorted(out.rglob("*.jsonl")):
            cond, _, split = p.stem.partition("_")
            for r in _traces(p):
                rows.append({"rep": rep, "condition": cond, "split": split, "seed": r["seed"], "success": bool(r["success"]), "steps": r["duration_steps"], "error": r.get("error", "")})
    if not rows:
        print("[P3a] no eval rows yet"); return
    with open(RES / "p3a_episodes.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    from eobs.analyze import boot_rate, fmt
    summ = []
    for cond in sorted({r["condition"] for r in rows}):
        for split in sorted({r["split"] for r in rows}):
            g = defaultdict(list)
            for r in rows:
                if r["condition"] == cond and r["split"] == split:
                    g[r["seed"]].append(r)
            b = boot_rate(g, lambda r: r["success"], lambda r: 1)
            summ.append({"condition": cond, "split": split, "n_tasks": len(g), "episodes": sum(len(v) for v in g.values()), "success": fmt(b[0]), "ci_lo": fmt(b[1]), "ci_hi": fmt(b[2]),
                         "errors": sum(bool(r["error"]) for v in g.values() for r in v)})
    # paired difference orig - nobank per task (mean over replicates)
    for split in sorted({r["split"] for r in rows}):
        per = defaultdict(lambda: defaultdict(list))
        for r in rows:
            if r["split"] == split:
                per[r["seed"]][r["condition"]].append(int(r["success"]))
        diffs = {s: (sum(c["orig"]) / len(c["orig"]) - sum(c["nobank"]) / len(c["nobank"])) for s, c in per.items() if c.get("orig") and c.get("nobank")}
        if diffs:
            import numpy as np
            x = np.array(list(diffs.values())); idx = np.random.default_rng(20260906).integers(0, len(x), size=(10000, len(x)))
            m = x[idx].mean(axis=1)
            summ.append({"condition": "orig - nobank (paired per task)", "split": split, "n_tasks": len(diffs), "episodes": "", "success": fmt(float(x.mean())), "ci_lo": fmt(float(np.percentile(m, 2.5))), "ci_hi": fmt(float(np.percentile(m, 97.5))), "errors": ""})
    with open(RES / "p3_skills.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
    for s in summ:
        print(s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["induce", "eval", "tables"], required=True)
    ap.add_argument("--rep", type=int, default=1); ap.add_argument("--n-id", type=int, default=30); ap.add_argument("--n-ood", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=6); ap.add_argument("--conditions", default="nobank,orig"); ap.add_argument("--reps", default="1,2,3")
    a = ap.parse_args()
    if a.stage == "induce":
        induce()
    elif a.stage == "eval":
        evaluate(a.rep, a.n_id, a.n_ood, a.concurrency, a.conditions)
    else:
        tables([int(x) for x in a.reps.split(",")])
