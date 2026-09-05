"""One rollout = one DeepSeek call -> program extraction -> offline execution -> scoring.

For EVERY rollout the response is processed under both extraction/execution variants
(raw = substrate extractor + substrate runner; c12 = c1 unwrap + c2 wrapper + substrate
runner) and each output is scored on BOTH paths (substrate, official). That yields four
verdicts per rollout: sub_raw (E_sub), off_raw (E_off), sub_c12 (E_c12), off_c12 (E_all).
The arm's primary verdict is the one matching its env. Results are appended to
results/emin/rollouts.jsonl (one row per rollout); every API attempt goes to ledger.jsonl.

CLI
  python -m emin.rollouts smoke  --arm A1              3 tasks x 2 rollouts (cost counted)
  python -m emin.rollouts run    --arm A1 [--limit N]  full arm (resumable: existing (arm,task,seed) rows are skipped)
  python -m emin.rollouts seedtest                     two identical calls with the same seed; are responses identical?
  python -m emin.rollouts r1     --ids-file FILE       answer-conditioned regeneration on the given task ids (E_all)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from emin import contracts
from emin.data import Task, pool_ids, pool_tasks, render_prompt, skill_text
from emin.llm import BudgetStop, Client, Ledger
from emin.score import Score, golden_recalced, score_official, score_substrate
from emin.settings import config, ensure_pilot_importable

ensure_pilot_importable()

from rethinkskill_spreadsheetbench.runtime import extract_python_code, run_generated_code  # noqa: E402

_ROWS_LOCK = threading.Lock()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _run_program(code: str, task: Task, workspace: Path, timeout: int) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "program.py").write_text(code, encoding="utf-8")
    out = workspace / "output.xlsx"
    res = run_generated_code(code, input_path=task.input_path, output_path=out, timeout_seconds=timeout)
    return {"failure": res.get("failure", ""), "returncode": res.get("returncode"), "timed_out": res.get("timed_out"),
            "output_exists": out.is_file()}


def _same_program(a: str, b: str) -> bool:
    """Semantic equality (AST) when both parse; else whitespace-normalised text equality."""
    import ast as _ast
    try:
        return _ast.dump(_ast.parse(a)) == _ast.dump(_ast.parse(b))
    except SyntaxError:
        return "\n".join(l.rstrip() for l in a.strip().splitlines()) == "\n".join(l.rstrip() for l in b.strip().splitlines())


def process_response(response: str, task: Task, root: Path) -> dict:
    """Run raw and c12 variants; score both outputs on both paths. Pure compute, no LLM."""
    cfg = config()
    timeout = int(cfg["execution"]["timeout_seconds"])
    result: dict = {}
    # raw (substrate extraction + runner)
    raw_ws = root / "raw"
    raw_ws.mkdir(parents=True, exist_ok=True)
    try:
        code_raw = extract_python_code(response)
        result["raw_extraction"] = "ok"
    except ValueError as exc:
        code_raw = ""
        result["raw_extraction"] = str(exc)[:80] or "contract_error"
    if code_raw:
        result["raw_exec"] = _run_program(code_raw, task, raw_ws, timeout)
    else:
        result["raw_exec"] = {"failure": "no_code", "output_exists": False}
    # c12 (c1 unwrap + c2 wrapper + substrate runner)
    c12_ws = root / "c12"
    c12_ws.mkdir(parents=True, exist_ok=True)
    try:
        code_c1 = contracts.unwrap_fence(response)
        result["c1_extraction"] = "ok"
    except ValueError as exc:
        code_c1 = ""
        result["c1_extraction"] = str(exc)[:80]
    result["c1_changed_code"] = bool(code_c1) and not _same_program(code_c1, code_raw)
    if code_c1:
        code_c12 = contracts.run_with_save_on_exception(code_c1)
        result["c12_exec"] = _run_program(code_c12, task, c12_ws, timeout)
    else:
        result["c12_exec"] = {"failure": "no_code", "output_exists": False}
    # scoring: 4 verdicts
    scores: dict[str, Score] = {}
    for variant, ws in (("raw", raw_ws), ("c12", c12_ws)):
        out = ws / "output.xlsx"
        scores[f"sub_{variant}"] = score_substrate(out, task.golden_path, task.answer_position)
        scores[f"off_{variant}"] = score_official(out, task.golden_path, task.answer_position, task.instruction_type,
                                                  root.parent.parent.parent / "_scoring")
    result["scores"] = {k: v.to_dict() for k, v in scores.items()}
    # did c2 actually fire?
    result["c2_fired"] = bool(result["c12_exec"].get("output_exists")) and not bool(result["raw_exec"].get("output_exists")) \
        and result["c1_extraction"] == "ok" and not result["c1_changed_code"]
    return result


ENV_KEY = {"E_sub": "sub_raw", "E_off": "off_raw", "E_c12": "sub_c12", "E_all": "off_c12"}


def existing_rows(path: Path) -> set[tuple[str, str, int]]:
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["arm"], r["unit_id"], int(r["seed"])))
    return done


def one_rollout(client: Client, *, arm: str, arm_cfg: dict, task: Task, seed: int, run_id: str, work_root: Path,
                prompt: str, skill_sha: str) -> dict:
    cfg = config()
    model = cfg["models"][arm_cfg["consumer"]]
    meta = {"run_id": run_id, "arm": arm, "unit_id": task.task_id, "seed": seed, "agent": arm_cfg["agent"],
            "env": arm_cfg["env"], "consumer": arm_cfg["consumer"], "kind": "rollout"}
    t0 = time.time()
    comp = client.complete(model=model, prompt=prompt, temperature=float(cfg["sampling"]["temperature"]), seed=seed, meta=meta)
    root = work_root / arm / task.task_id / f"seed{seed}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "response.md").write_text(comp.text, encoding="utf-8")
    row = {**meta, "model": model, "temperature": cfg["sampling"]["temperature"], "prompt_sha": sha(prompt), "skill_sha": skill_sha,
           "llm_ok": comp.ok, "llm_failure_class": comp.failure_class, "llm_attempts": comp.attempts,
           "response_sha": sha(comp.text) if comp.text else None, "response_chars": len(comp.text),
           "prompt_tokens": comp.usage.get("prompt_tokens"), "completion_tokens": comp.usage.get("completion_tokens")}
    if comp.ok:
        row.update(process_response(comp.text, task, root))
    else:
        row.update({"raw_extraction": "llm_failed", "c1_extraction": "llm_failed", "scores": {}})
    key = ENV_KEY[arm_cfg["env"]]
    row["primary_key"] = key
    row["primary_pass"] = bool(row.get("scores", {}).get(key, {}).get("verdict") == "PASS") if comp.ok else False
    row["primary_reason"] = row.get("scores", {}).get(key, {}).get("reason", "llm_failed")
    row["wall_seconds"] = round(time.time() - t0, 2)
    row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return row


def run_arm(arm: str, *, smoke: bool, limit: int | None, soft_ok: bool) -> None:
    cfg = config()
    arm_cfg = cfg["arms"][arm]
    results_dir = Path(cfg["results_dir"])
    work_root = Path(cfg["work_dir"]) / ("smoke" if smoke else "arms")
    rows_path = results_dir / ("rollouts_smoke.jsonl" if smoke else "rollouts.jsonl")
    ledger = Ledger(results_dir / "ledger.jsonl")
    client = Client(ledger, soft_ok=soft_ok)
    ids = pool_ids()
    seeds = list(arm_cfg["seeds"])
    if smoke:
        ids = ids[: int(cfg["smoke"]["tasks"])]
        seeds = seeds[: int(cfg["smoke"]["rollouts"])]
    elif limit:
        ids = ids[:limit]
    tasks = pool_tasks(ids)
    text = skill_text(arm_cfg["agent"])
    skill_sha = sha(text)
    # pre-warm golden recalc cache (deterministic; needed by the official path for every rollout)
    for t in tasks:
        golden_recalced(t.golden_path, work_root.parent / "_scoring" / "golden_recalc")
    done = existing_rows(rows_path)
    jobs = [(t, s) for t in tasks for s in seeds if (arm, t.task_id, s) not in done]
    run_id = f"emin-{arm}-{'smoke-' if smoke else ''}{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    print(f"[{run_id}] arm={arm} {arm_cfg} tasks={len(tasks)} seeds={seeds} jobs={len(jobs)} (skipped done={len(tasks)*len(seeds)-len(jobs)}) "
          f"ledger so far: {ledger.calls} calls USD {ledger.total_usd:.3f}", flush=True)
    prompts = {t.task_id: render_prompt(t, text) for t in tasks}
    stop = False
    n_done = n_pass = 0
    with ThreadPoolExecutor(max_workers=int(cfg["concurrency"]["api"])) as pool:
        futs = {}
        for t, s in jobs:
            futs[pool.submit(one_rollout, client, arm=arm, arm_cfg=arm_cfg, task=t, seed=s, run_id=run_id, work_root=work_root,
                             prompt=prompts[t.task_id], skill_sha=skill_sha)] = (t.task_id, s)
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except BudgetStop as exc:
                if not stop:
                    print(f"BUDGET STOP: {exc}", flush=True)
                    stop = True
                    for f in futs:
                        f.cancel()
                continue
            except Exception as exc:  # noqa: BLE001
                tid, s = futs[fut]
                row = {"run_id": run_id, "arm": arm, "unit_id": tid, "seed": s, "agent": arm_cfg["agent"], "env": arm_cfg["env"],
                       "consumer": arm_cfg["consumer"], "kind": "rollout", "llm_ok": False, "error": f"{type(exc).__name__}: {exc}"[:300],
                       "primary_pass": False, "primary_reason": "runner_error", "scores": {},
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            with _ROWS_LOCK:
                with open(rows_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_done += 1
            n_pass += int(bool(row.get("primary_pass")))
            if n_done % 25 == 0 or n_done == len(jobs):
                print(f"  {n_done}/{len(jobs)} primary pass {n_pass}  ledger USD {ledger.total_usd:.3f} ({ledger.calls} calls)", flush=True)
    print(f"[{run_id}] finished: {n_done} rollouts, primary pass {n_pass}; cumulative USD {ledger.total_usd:.3f} "
          f"(peak-bound {ledger.total_usd_peak_bound:.3f}); stopped_by_budget={stop}", flush=True)
    if stop:
        sys.exit(3)


def seedtest(soft_ok: bool) -> None:
    cfg = config()
    ledger = Ledger(Path(cfg["results_dir"]) / "ledger.jsonl")
    client = Client(ledger, soft_ok=soft_ok)
    task = pool_tasks(pool_ids()[:1])[0]
    prompt = render_prompt(task, skill_text("parent_minus"))
    outs = []
    for i in range(2):
        c = client.complete(model=cfg["models"]["pro"], prompt=prompt, temperature=0.7, seed=12345,
                            meta={"run_id": "emin-seedtest", "arm": "seedtest", "unit_id": task.task_id, "seed": 12345, "kind": "seedtest"})
        outs.append(c.text)
    print(json.dumps({"identical": outs[0] == outs[1], "sha": [sha(o) for o in outs], "usd": ledger.total_usd}))


def r1(ids_file: Path, soft_ok: bool) -> None:
    """Answer-conditioned regeneration (pilot reference protocol) for the given ids under E_all."""
    from pilot.judges import judge_authenticity
    from pilot.llm import JudgeClient
    from pilot.references import REFERENCE_BLOCK, spreadsheet_gold_text

    cfg = config()
    rc = cfg["r1"]
    results_dir = Path(cfg["results_dir"])
    work_root = Path(cfg["work_dir"]) / "r1"
    ledger = Ledger(results_dir / "ledger.jsonl")
    client = Client(ledger, soft_ok=soft_ok)
    ids = [l.strip() for l in Path(ids_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    tasks = pool_tasks(ids)
    text = skill_text(rc["agent"])
    model = cfg["models"][rc["consumer"]]
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", client._key)  # pilot JudgeClient reads the env var
    judge = JudgeClient(model=model, base_url=cfg["api"]["base_url"], api_key_env="DEEPSEEK_API_KEY", mode="nothink",
                        log_path=work_root / "judge_calls.jsonl")
    out_path = results_dir / "r1.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(l)["unit_id"] for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()}
    run_id = f"emin-R1-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"

    def do_task(task: Task) -> dict:
        g, status = golden_recalced(task.golden_path, Path(cfg["work_dir"]) / "_scoring" / "golden_recalc")
        gold_src = g if g is not None else task.golden_path       # gold text from the RECALCULATED golden (official values)
        gold = spreadsheet_gold_text(Path(gold_src), task.answer_position)
        prompt = render_prompt(task, text) + REFERENCE_BLOCK.format(gold=gold)
        rec = {"run_id": run_id, "unit_id": task.task_id, "gold_source": "recalculated_golden" if g is not None else "raw_golden",
               "attempts": [], "H_off_pass": False, "H_off_authentic": None}
        for attempt in range(1, int(rc["attempts"]) + 1):
            seed = 1000 + attempt
            meta = {"run_id": run_id, "arm": "R1", "unit_id": task.task_id, "seed": seed, "agent": rc["agent"], "env": rc["env"],
                    "consumer": rc["consumer"], "kind": "r1"}
            comp = client.complete(model=model, prompt=prompt, temperature=float(cfg["sampling"]["temperature"]), seed=seed, meta=meta)
            root = work_root / task.task_id / f"attempt{attempt}"
            root.mkdir(parents=True, exist_ok=True)
            (root / "response.md").write_text(comp.text, encoding="utf-8")
            entry = {"attempt": attempt, "llm_ok": comp.ok}
            if comp.ok:
                res = process_response(comp.text, task, root)
                entry["scores"] = res["scores"]
                entry["pass_E_all"] = res["scores"]["off_c12"]["verdict"] == "PASS"
                if entry["pass_E_all"]:
                    rec["H_off_pass"] = True
                    if rc.get("judge"):
                        v = judge_authenticity(judge, task=prompt, gold=gold, trajectory=comp.text,
                                               exec_note="; the program was executed offline and its output workbook passed the official answer-cell check",
                                               meta={"benchmark": "spreadsheetbench", "task_id": task.task_id, "attempt": attempt, "stage": "authenticity"})
                        u = v.get("usage", {}) or {}
                        from emin.llm import tariff_at, usd_for
                        ts = time.time()
                        ledger.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), **meta, "kind": "r1_judge", "model": model,
                                       "attempt": 1, "ok": True, "prompt_tokens": int(u.get("prompt_tokens", 0) or 0),
                                       "completion_tokens": int(u.get("completion_tokens", 0) or 0),
                                       "cache_hit_tokens": int(u.get("prompt_cache_hit_tokens", 0) or 0), "tariff": tariff_at(ts),
                                       "usd": usd_for(model, u, tariff_at(ts)), "usd_peak_bound": usd_for(model, u, "peak")})
                        entry["judge"] = {"authentic": v["authentic"], "reason": v["reason"]}
                        rec["H_off_authentic"] = bool(v["authentic"]) or bool(rec["H_off_authentic"])
                    rec["attempts"].append(entry)
                    break
            rec["attempts"].append(entry)
        rec["n_attempts"] = len(rec["attempts"])
        return rec

    todo = [t for t in tasks if t.task_id not in done]
    print(f"[{run_id}] R1 on {len(todo)} tasks (skipping {len(done)} done)", flush=True)
    with ThreadPoolExecutor(max_workers=int(cfg["concurrency"]["api"])) as pool:
        for rec in pool.map(do_task, todo):
            with open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  {rec['unit_id']}: H_off_pass={rec['H_off_pass']} authentic={rec['H_off_authentic']} attempts={rec['n_attempts']}  USD {ledger.total_usd:.3f}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("smoke", "run"):
        p = sub.add_parser(name)
        p.add_argument("--arm", required=True)
        p.add_argument("--limit", type=int, default=None)
        p.add_argument("--approve-beyond-soft", action="store_true", help="owner approved continuing past the USD 12 soft gate")
    p = sub.add_parser("seedtest")
    p.add_argument("--approve-beyond-soft", action="store_true")
    p = sub.add_parser("r1")
    p.add_argument("--ids-file", required=True, type=Path)
    p.add_argument("--approve-beyond-soft", action="store_true")
    a = ap.parse_args()
    if a.cmd in ("smoke", "run"):
        run_arm(a.arm, smoke=(a.cmd == "smoke"), limit=a.limit, soft_ok=a.approve_beyond_soft)
    elif a.cmd == "seedtest":
        seedtest(a.approve_beyond_soft)
    else:
        r1(a.ids_file, a.approve_beyond_soft)


if __name__ == "__main__":
    main()
