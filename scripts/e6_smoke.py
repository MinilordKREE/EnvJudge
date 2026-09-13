"""E6 smoke (experiments/alfworld_e6/PREREG_SMOKE.md): a six-task prospective mechanism smoke of
``method_version = llm_v1`` (three frozen-HIGH tasks then three frozen-LOW tasks, task
concurrency 1). Nothing here calls ``scripts/e3.py::stage_a`` (that driver builds the v0.4
default config); the ONE ``AEAConfig(method_version="llm_v1")`` built by :func:`config` is passed
to the substrate and to the controller, and the controller receives the substrate's reference
provider. E3's models, provider pin, corpus and stage config are reused unchanged.

Stages: ``probe`` (endpoint gate) -> ``search`` (the controller on the six tasks; then the
per-task leakage audit and the correctness gates, written next to the run) -> ``confirm`` (K = 16
on every accepted environment, evaluation-only) -> ``tables`` (scripts/make_tables_e6_smoke.py)
-> ``spend``. Runs: runs/e6-smoke-llm-v1, runs/e6-smoke-confirm; spend = every runs/e6-* ledger
against the USD 30 cap.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import load_run_context, write_manifest
from aea.designer import ExpertReference
from aea.errors import ConfigError
from aea.io import TraceWriter, read_corpus
from aea.substrate import AeaSubstrate

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3

ROOT = e3.ROOT
RUNS = e3.RUNS
EXP = ROOT / "experiments" / "alfworld_e6"
FROZEN = EXP / "frozen"
RESULTS = EXP / "results"
RUN_ID = "e6-smoke-llm-v1"
CONFIRM_RUN_ID = "e6-smoke-confirm"
METHOD_SHA = "47a0091"  # the frozen llm_v1 implementation (src/aea at this commit)
PREREG_SHA: str | None = None  # the PREREG_SMOKE.md commit, recorded before the first paid call
CAP_USD = 30.0
CONFIRM_K = 16
LIBRARY = ("footer_mask", "horizon_squeeze")

e3.SPEND_GLOB = "e6-*"  # the E3 helpers (spend guard, watchdog) now count runs/e6-*
e3.CAP_USD = CAP_USD
e3.EXPERIMENT = "E6 smoke (llm_v1 mechanism smoke, PREREG_SMOKE)"


# ---------------------------------------------------------------------------- frozen selection
def frozen_k16() -> dict[str, dict[str, Any]]:
    """The frozen original-environment K16 records copied from runs/e2-shared and
    runs/e3-shared (``confirm_summary.json``) into experiments/alfworld_e6/frozen/."""
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(FROZEN.glob("*_confirm_summary.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            if k.endswith(":orig"):
                out[str(v["task"])] = {**v, "source": f.name}
    return out


def select_tasks(records: dict[str, dict[str, Any]], n: int = 3) -> tuple[list[int], list[int]]:
    """HIGH pool: 16/16 with 0 errors; LOW pool: 0/16 with 0 errors; the n smallest ids of each.
    Fewer than n in a pool -> ConfigError (STOP; no other rule)."""
    clean = {int(t): r for t, r in records.items() if r["n"] == 16 and r["errors"] == 0}
    high = sorted(t for t, r in clean.items() if r["successes"] == 16)
    low = sorted(t for t, r in clean.items() if r["successes"] == 0)
    if len(high) < n or len(low) < n:
        raise ConfigError(f"pool too small: HIGH {high}, LOW {low}")
    return high[:n], low[:n]


HIGH_TASKS, LOW_TASKS = select_tasks(frozen_k16())
ORDER: tuple[int, ...] = (*HIGH_TASKS, *LOW_TASKS)  # HIGH ascending, then LOW ascending
EXPECTED = {**{str(t): "saturated" for t in HIGH_TASKS}, **{str(t): "zero" for t in LOW_TASKS}}


# ---------------------------------------------------------------------------- wiring
def config() -> AEAConfig:
    return AEAConfig(method_version="llm_v1")


def build(
    cfg: AEAConfig, d: Path, run_id: str, *, concurrency: int, with_designer: bool = True
) -> tuple[AeaSubstrate, Controller]:
    """The same ``cfg`` for the substrate and the controller; the substrate's own reference
    provider. Asserted, not assumed."""
    sub = AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=d,
        run_id=run_id,
        policy_llm=e3.policy_qwen(),
        designer_llm=e3.designer_deepseek() if with_designer else None,
        aea_config=cfg,
        stage_config_path=e3.STAGE_CONFIG,
        pricing_path=e3.PRICING,
        rollout_concurrency=concurrency,
        subprocess_timeout_s=600.0,
    )
    provider = sub.reference_provider(cfg)
    ctrl = Controller(cfg, sub, d, run_id, arm="LLM", use_proposer=True, reference=provider)
    check_wiring(cfg, ctrl, designer=with_designer)
    return sub, ctrl


def check_wiring(cfg: AEAConfig, ctrl: Controller, *, designer: bool = True) -> None:
    """The offline wiring assertion (also run by tests/unit/test_e6_smoke_driver.py)."""
    if cfg.method_version != "llm_v1":
        raise ConfigError(f"driver config is {cfg.method_version}, not llm_v1")
    if ctrl.config is not cfg or ctrl.config.method_version != "llm_v1":
        raise ConfigError("controller config is not the driver's llm_v1 config")
    if not isinstance(ctrl.reference, ExpertReference):
        raise ConfigError("controller has no ExpertReference provider")
    if designer and ctrl.substrate.designer() is None:
        raise ConfigError("no designer configured")


def _src_sha() -> str:
    """Hash of the tracked src/aea tree in the working copy (method freeze evidence)."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-s", "src/aea"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    dirty = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--quiet", METHOD_SHA, "--", "src/aea"],
        check=False,
    ).returncode
    return hashlib.sha256(out.encode()).hexdigest()[:16] + ("" if dirty == 0 else "+DIRTY")


# ---------------------------------------------------------------------------- search
def stage_search(concurrency: int) -> None:
    if PREREG_SHA is None:
        raise ConfigError("PREREG_SHA not recorded: commit PREREG_SMOKE.md first")
    e3.guard("search")
    cfg = config()
    policy = e3.policy_qwen()
    designer = e3.designer_deepseek()
    run_config = RunConfig(
        schema_version=1,
        name=RUN_ID,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=RUNS,
    )
    d = RUNS / RUN_ID
    if (d / "manifest.json").exists():
        ctx, _ = load_run_context(d)
    else:
        ctx = create_run_context(
            run_config,
            runs_root=RUNS,
            run_id=RUN_ID,
            repo_dir=ROOT,
            aea_config_sha256=aea_config_sha256(cfg),
        )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=e3._git_sha(e3.ENVHARNESS),
        extra={
            "experiment": e3.EXPERIMENT,
            "prereg": "experiments/alfworld_e6/PREREG_SMOKE.md",
            "prereg_sha": PREREG_SHA,
            "method_sha": METHOD_SHA,
            "src_aea_tree": _src_sha(),
            "method_version": cfg.method_version,
            "aea_config": cfg.model_dump(mode="json"),
            "tasks": list(ORDER),
            "expected_regime": dict(EXPECTED),
            "task_order": "HIGH ascending then LOW ascending (pre-registered)",
            "policy": policy.model_dump(mode="json", exclude={"api_key_env"}),
            "designer": designer.model_dump(mode="json", exclude={"api_key_env"}),
            "policy_endpoint_pin": policy.provider_pin,
            "cap_usd": CAP_USD,
            "concurrency": {"tasks": 1, "rollouts": concurrency, "inflight_episodes": concurrency},
        },
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub, ctrl = build(cfg, ctx.out_dir, ctx.run_id, concurrency=concurrency)
    stop = e3.start_watchdog("search", ctx.out_dir / "events.jsonl")
    outcomes = ctrl.run([TaskRef(str(t), t) for t in ORDER], concurrency=1)
    stop.set()
    e3.merge(ctx.out_dir)
    for o in outcomes:
        print(
            json.dumps(
                {
                    "task": o.task.task_id,
                    "expected": EXPECTED[o.task.task_id],
                    "regime": o.regime,
                    "outcome": o.outcome,
                    "reason": o.reason,
                    "n_search": o.n_search,
                }
            ),
            flush=True,
        )
    audit = leakage_audit(sub, ctx.out_dir)
    (ctx.out_dir / "leakage_audit.json").write_text(json.dumps(audit, indent=1), encoding="utf-8")
    gates = correctness_gates(ctx.out_dir, audit)
    (ctx.out_dir / "gates.json").write_text(json.dumps(gates, indent=1), encoding="utf-8")
    print(json.dumps({"stage": "search", "usd": round(e3.dir_spend(ctx.out_dir), 2), **gates}))


# ---------------------------------------------------------------------------- leakage audit
def _events(d: Path) -> list[dict[str, Any]]:
    return e3.jsonl(d / "events.jsonl")


def _by_kind(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        out[str(e.get("kind"))].append(dict(e.get("payload") or {}))
    return out


def _ref_hash(actions: list[str]) -> str:
    return hashlib.sha256(json.dumps(actions).encode("utf-8")).hexdigest()[:16]


def leakage_audit(sub: AeaSubstrate, d: Path) -> dict[str, Any]:
    """Per LOW task with an available reference: recompute the expert's action list (free,
    in-process, under the session lock), check it against the hash the run kept, then check that
    ``reference[k:]`` (past every selected cut) is never carried by a candidate prefix in
    traces.jsonl / corpus.jsonl and that the reference block itself is absent from every kept
    file. Policy-emitted actions are recorded by provenance (``independent_overlap``), never
    flagged."""
    ev = _by_kind(_events(d))
    calls = e3.jsonl(d / "designer_calls.jsonl")
    traces = e3.jsonl(d / "traces.jsonl")
    corpus = e3.jsonl(d / "corpus.jsonl")
    kept_text = {
        name: (d / name).read_text(encoding="utf-8", errors="replace")
        for name in ("events.jsonl", "designer_calls.jsonl", "traces.jsonl", "corpus.jsonl")
        if (d / name).exists()
    }
    out: dict[str, Any] = {"tasks": {}, "ok": True}
    for r in ev.get("reference", []):
        task = str(r["task_id"])
        rec: dict[str, Any] = {"available": bool(r.get("available")), "reason": r.get("reason")}
        if not r.get("available"):
            out["tasks"][task] = rec
            continue
        provider = sub.reference_provider(config())
        assert provider is not None
        ref = provider(TaskRef(task, int(task)))
        row = next((c for c in calls if str(c["task_id"]) == task and c["regime"] == "zero"), {})
        kept_hash = str(row.get("evidence", "")).split("sha256 ")[1][:16] if row else ""
        rec["recomputed_ok"] = ref.ok
        rec["hash_match"] = ref.ok and _ref_hash(list(ref.actions)) == kept_hash
        cuts = [
            int(p["step"])
            for p in next(
                (x for x in ev.get("llm_stage_proposals", []) if str(x["task_id"]) == task), {}
            ).get("accepted", [])
            if p.get("source") == "reference"
        ]
        rec["reference_cuts"] = cuts
        rec["reference_steps"] = len(ref.actions)
        k = min(cuts) if cuts else len(ref.actions)
        future = set(ref.actions[k:])
        leaks: list[str] = []
        # 1. candidate prefixes (the only channel a reference action can be COPIED through)
        prefixes = [
            [str(a.get("kwargs", {}).get("text", "")) for a in t["candidate"]["in_env_actions"]]
            for t in traces
            if str(t.get("rollout_seed")) == task
        ] + [
            [str(a.get("kwargs", {}).get("text", "")) for a in c.get("in_env_actions", [])]
            for c in corpus
            if str(c.get("aea", {}).get("task_id")) == task
        ]
        for pre in prefixes:
            if set(pre) & future:
                leaks.append(f"candidate prefix carries a post-cut reference action: {pre}")
        # 2. the reference block never appears in a kept file
        for name, text in kept_text.items():
            if "PRIVILEGED REFERENCE (a successful" in text:
                leaks.append(f"{name}: reference block present")
        if row and "[content withheld]" not in str(row.get("evidence", "")):
            leaks.append("designer_calls.jsonl: reference not redacted")
        # 3. provenance: post-cut actions the POLICY emitted itself (informational)
        indep = 0
        for t in traces:
            if str(t.get("rollout_seed")) != task:
                continue
            for s in t.get("steps", []):
                if str(s.get("raw_action", {}).get("kwargs", {}).get("text", "")) in future:
                    indep += 1
        rec["independent_overlap"] = indep
        rec["leaks"] = leaks
        out["tasks"][task] = rec
        if leaks or not rec["hash_match"]:
            out["ok"] = False
    return out


# ---------------------------------------------------------------------------- gates
def correctness_gates(d: Path, audit: dict[str, Any]) -> dict[str, Any]:
    ev = _by_kind(_events(d))
    calls = e3.jsonl(d / "designer_calls.jsonl")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    extra = manifest.get("extra", manifest)
    regime = {str(e["task_id"]): e["regime"] for e in ev.get("estimate", [])}
    done = {str(e["task_id"]): e for e in ev.get("task_done", [])}
    calls_per_task: dict[str, int] = defaultdict(int)
    for c in calls:
        calls_per_task[str(c["task_id"])] += 1
    ledger_designer: dict[str, int] = defaultdict(int)
    for r in e3._ledger_rows(d):
        if r.get("event") == "call" and r.get("budget") == "designer":
            ledger_designer[str(r.get("task_id"))] += 1
    gates: dict[str, Any] = {
        "method_version_runtime": extra.get("method_version") == "llm_v1"
        and all(c.get("method_version") == "llm_v1" for c in calls),
        "no_fixed_fallback": not any(
            set(f.get("order", [])) & set(LIBRARY) or f.get("source") != "designer"
            for f in ev.get("families", [])
        )
        and all(s.get("source") == "designer" for s in ev.get("stage_candidates", [])),
        "designer_calls_le_1": all(v <= 1 for v in calls_per_task.values()),
        "designer_ledger_calls_per_task": dict(ledger_designer),
        "proposals_le_2": all(len(c.get("accepted", [])) <= 2 for c in calls),
        "search_le_cap": all(int(e.get("n_search", 0)) <= 30 for e in done.values()),
        "no_axis_bypass": all(s.get("source") != "by_construction" for s in ev.get("solvable", [])),
        "reference_only_on_zero": all(
            regime.get(str(r["task_id"])) == "zero" for r in ev.get("reference", [])
        ),
        "reference_leakage": audit.get("ok", False),
        "tasks_preregistered": [str(t) for t in ORDER] == [str(t) for t in extra.get("tasks", [])]
        and set(done) <= {str(t) for t in ORDER},
        "method_unmodified": not str(extra.get("src_aea_tree", "")).endswith("+DIRTY")
        and not _src_sha().endswith("+DIRTY"),
    }
    gates["invalid_env_accepted"] = _invalid_accepted(d, ev)
    gates["all_pass"] = (
        all(
            v is True
            for k, v in gates.items()
            if k not in ("designer_ledger_calls_per_task", "invalid_env_accepted", "all_pass")
        )
        and gates["invalid_env_accepted"] == []
    )
    return gates


def _invalid_accepted(d: Path, ev: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Every accepted environment must be certified and, for a knob, loadable."""
    from envharness.core.code_loader import RulesCodeError, load_rules_subclass

    bad: list[str] = []
    if not (d / "corpus.jsonl").exists():
        return bad
    certified = {c for s in ev.get("stage_candidates", []) for c in s.get("certified", [])}
    guards = {(str(s["task_id"]), s.get("family")): s.get("ok") for s in ev.get("solvable", [])}
    for entry in read_corpus(d / "corpus.jsonl"):
        a = entry.aea
        if a.kind == "knob":
            try:
                load_rules_subclass(entry.rules_code)
            except RulesCodeError as exc:
                bad.append(f"{a.candidate_id}: {exc}")
            if not guards.get((a.task_id, a.family)):
                bad.append(f"{a.candidate_id}: accepted without a passing guard")
        elif a.kind == "stage" and a.candidate_id not in certified:
            bad.append(f"{a.candidate_id}: accepted stage was not certified")
    return bad


# ---------------------------------------------------------------------------- confirm
def accepted_envs() -> list[dict[str, Any]]:
    p = RUNS / RUN_ID / "corpus.jsonl"
    if not p.exists():
        return []
    envs = []
    for c in e3.jsonl(p):
        a = c["aea"]
        if a["kind"] in ("knob", "stage"):
            envs.append(
                {
                    "id": a["candidate_id"],
                    "task": a["task_id"],
                    "kind": a["kind"],
                    "family": a.get("family"),
                    "d": a.get("d"),
                    "t": a.get("t"),
                    "candidate": {
                        "rules_code": c.get("rules_code", ""),
                        "in_env_actions": c.get("in_env_actions", []),
                    },
                }
            )
    return envs


def stage_confirm(concurrency: int) -> None:
    e3.guard("confirm")
    d = RUNS / CONFIRM_RUN_ID
    d.mkdir(parents=True, exist_ok=True)
    envs = accepted_envs()
    (d / "envs.json").write_text(json.dumps(envs, indent=1), encoding="utf-8")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    sub, _ = build(config(), d, CONFIRM_RUN_ID, concurrency=concurrency, with_designer=False)
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "confirm.jsonl")
    cfg = config()
    for env in envs:
        if env["id"] in summary:
            continue
        e3.guard(f"confirm {env['id']}")
        task = TaskRef(env["task"], int(env["task"]))
        reset = sub.stage_reset_options(task) if env["kind"] == "stage" else None
        rec = e3._k16(
            sub,
            writer,
            env["id"],
            task,
            e3.to_candidate(env["candidate"]),
            arm="confirm",
            n=CONFIRM_K,
            reset_options=reset,
        )
        p16 = rec["p16"]
        summary[env["id"]] = {
            **rec,
            "kind": env["kind"],
            "family": env["family"],
            "d": env["d"],
            "t": env["t"],
            "in_band_l": p16 is not None and cfg.band_l[0] <= p16 <= cfg.band_l[1],
            "in_band_t": p16 is not None and cfg.band_t[0] <= p16 <= cfg.band_t[1],
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": env["id"], **rec}), flush=True)
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    e3.merge(d)
    print(json.dumps({"stage": "confirm", "envs": len(envs), "usd": round(e3.dir_spend(d), 2)}))


# ---------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage", required=True, choices=["probe", "search", "confirm", "tables", "spend"]
    )
    ap.add_argument("--concurrency", type=int, default=e3.ROLLOUT_CONCURRENCY)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe":
            return e3.stage_probe()
        if args.stage == "search":
            stage_search(args.concurrency)
        elif args.stage == "confirm":
            stage_confirm(args.concurrency)
        elif args.stage == "tables":
            mt = importlib.import_module("make_tables_e6_smoke")
            return int(mt.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            p.name: round(e3.dir_spend(p), 2)
                            for p in sorted(RUNS.glob("e6-*"))
                            if p.is_dir()
                        },
                        "ts": time.strftime("%FT%TZ", time.gmtime()),
                    }
                )
            )
    except ConfigError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
