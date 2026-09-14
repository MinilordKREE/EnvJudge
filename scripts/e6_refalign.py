"""E6 LOW refalign (experiments/alfworld_e6/PREREG_LOW_REFALIGN.md): paired LOW-only comparison
of the frozen ``llm_v1`` LOW (arm A, action-only projection of the reference) against
``llm_v1_refalign`` (arm B, rich observation/action reference + explicit diagnosis) on fresh
frozen-LOW tasks, with SHARED evidence per task.

Protocol per task (stages ``shared`` then ``arms``):
1. ``shared``: one normal current-policy regime estimation (the controller's own estimator
   schedule on the real substrate; every rollout charged and ledgered under
   runs/e6-refalign-shared) and, if the task enters ``zero``, ONE rich expert reference recorded
   in one session (privileged; runs/e6-refalign-shared/privileged_references.jsonl). Both are
   frozen to disk.
2. ``arms``: arm A = ``Controller(llm_v1)`` and arm B = ``Controller(llm_v1_refalign)``, each on
   its own run directory, over a :class:`FrozenSubstrate` that REPLAYS the frozen estimate
   rollouts for the ``estimate`` phase (no API call, still charged by the controller so the
   30-rollout cap is identical) and delegates every other rollout (the Stage probes) to the real
   substrate; the reference provider returns the frozen reference (arm A's serializer projects
   it to the action list, arm B's shows observations). One designer call per arm per task, the
   same designer model and settings, the same 4 -> 8 probe rule and cap.
3. ``confirm``: K = 16 on every accepted Stage of either arm (evaluation-only).
4. ``tables``: scripts/make_tables_e6_refalign.py -> experiments/alfworld_e6/results/
   e6_low_refalign.md; leakage audit per arm against the exact recorded reference.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller, TaskRef
from aea.core.config import RunConfig
from aea.core.context import create_run_context
from aea.core.manifest import load_run_context, write_manifest
from aea.core.trace import TraceWriter as EventWriter
from aea.designer import Reference, ReferenceStep, reference_id
from aea.errors import ConfigError
from aea.estimate import estimate
from aea.io import TraceWriter
from aea.llm.types import Attribution
from aea.substrate import AeaSubstrate

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_smoke as e6

ROOT = e6.ROOT
RUNS = e6.RUNS
EXP = e6.EXP
RESULTS = e6.RESULTS
SHARED_ID = "e6-refalign-shared"
ARM_IDS = {"A": "e6-refalign-A", "B": "e6-refalign-B"}
ARM_VERSIONS = {"A": "llm_v1", "B": "llm_v1_refalign"}
CONFIRM_ID = "e6-refalign-confirm"
PREREG = "PREREG_LOW_REFALIGN.md"
PREREG_SHA: str | None = "c073fcd"  # PREREG_LOW_REFALIGN.md commit (before the first paid call)
METHOD_SHA: str | None = "48dc028"  # the phase-3.2 implementation commit (src/aea frozen)
CAP_USD = 15.0
EXCLUDE: tuple[int, ...] = (8, 9, 10, 11, 14, 17)  # every previous LOW smoke task
N_TASKS = 6

e3.SPEND_GLOB = "e6-refalign-*"
e3.CAP_USD = CAP_USD
e3.EXPERIMENT = "E6 LOW refalign (paired shared-evidence comparison, PREREG_LOW_REFALIGN)"


def select_low(records: dict[str, dict[str, Any]]) -> list[int]:
    """The next ``N_TASKS`` smallest frozen-LOW ids after the exclusions, or all remaining."""
    _, low = e6.select_tasks(records, n=1, exclude=EXCLUDE)  # only the LOW pool matters here
    pool = sorted(
        int(t)
        for t, r in records.items()
        if r["n"] == 16 and r["errors"] == 0 and r["successes"] == 0 and int(t) not in EXCLUDE
    )
    assert low[0] == pool[0]
    return pool[:N_TASKS]


TASKS: list[int] = select_low(e6.frozen_k16())


def config(arm: str) -> AEAConfig:
    return AEAConfig.model_validate({"method_version": ARM_VERSIONS[arm]})


def build(
    cfg: AEAConfig, d: Path, run_id: str, *, concurrency: int, with_designer: bool = True
) -> tuple[AeaSubstrate, Controller]:
    """Like ``e6_smoke.build`` (same models, corpus, stage config, pricing) for either LLM
    method version; the same ``cfg`` goes to the substrate and the controller, and the
    controller gets the substrate's reference provider. Asserted, not assumed."""
    if cfg.method_version not in ARM_VERSIONS.values():
        raise ConfigError(f"driver config is {cfg.method_version}, not an llm_v1 variant")
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
    if ctrl.config is not cfg or provider is None or (with_designer and sub.designer() is None):
        raise ConfigError("wiring: config / reference provider / designer not as required")
    return sub, ctrl


# ---------------------------------------------------------------------------- frozen evidence
def shared_dir() -> Path:
    return RUNS / SHARED_ID


def frozen_traces(task: str) -> list[Trace]:
    p = shared_dir() / "traces.jsonl"
    return [
        Trace.model_validate(r)
        for r in e3.jsonl(p)
        if str(r.get("rollout_seed")) == task
        and str(r.get("iteration_id", "")).startswith("estimate-")
    ]


def frozen_reference(task: str) -> Reference | None:
    for r in e3.jsonl(shared_dir() / "privileged_references.jsonl"):
        if str(r["task_id"]) == task:
            if not r.get("success"):
                return Reference(False, str(r.get("reason", "unavailable")))
            steps = tuple(
                ReferenceStep(
                    int(s["step"]), str(s["observation"]), tuple(s["admissible"]), str(s["action"])
                )
                for s in r.get("steps", [])
            )
            return Reference(True, "pass", tuple(r["actions"]), steps)
    return None


def shared_estimate(task: str) -> dict[str, Any] | None:
    for r in e3.jsonl(shared_dir() / "shared.jsonl"):
        if str(r["task_id"]) == task:
            return r
    return None


class FrozenSubstrate:
    """The real substrate, except that ``estimate`` rollouts are replayed from the shared
    evidence (deep copies of the frozen traces, in order, no API call) and the reference is the
    frozen instance. Everything else (probes, sessions, guards, game files) is real."""

    def __init__(self, real: AeaSubstrate, task: str) -> None:
        self.real = real
        self.task = task
        self._pending = [copy.deepcopy(t) for t in frozen_traces(task)]
        self.replayed = 0
        self.ref = frozen_reference(task)

    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        if attribution.phase == "estimate":
            if task.task_id != self.task or len(self._pending) < n:
                raise ConfigError(f"frozen estimate exhausted for task {task.task_id}")
            out, self._pending = self._pending[:n], self._pending[n:]
            self.replayed += n
            return out
        return self.real.rollouts(
            task, candidate, n, attribution=attribution, reset_options=reset_options
        )

    def reference_provider(self, config: AEAConfig) -> Any:
        ref = self.ref

        def provider(task: Any) -> Reference:
            if ref is None:
                return Reference(False, "no_shared_reference")
            return ref

        return provider

    def __getattr__(self, name: str) -> Any:  # open_session, game_file, designer, ...
        return getattr(self.real, name)


# ---------------------------------------------------------------------------- audit
def leakage_audit(d: Path) -> dict[str, Any]:
    """Exact-reference leakage audit with PROVENANCE (PREREG_LOW_REFALIGN, gates): every Setup
    prefix found in traces.jsonl / corpus.jsonl is attributed through its candidate id to the
    run's own ``stage_candidates`` / ``probe`` records; a reference-source prefix must equal the
    recorded reference up to ITS OWN cut (plus the compiler's trailing ``look``); a
    failure-source prefix is the policy's own actions and is never compared by string; an
    unattributed prefix is a leak. The reference block never appears in a kept file, the
    designer record is redacted, provenance hashes agree, the expert is never re-run. Policy
    steps that repeat a post-cut reference action are counted (``independent_overlap``)."""
    ev = e6._by_kind(e6._events(d))
    calls = e3.jsonl(d / "designer_calls.jsonl")
    traces = e3.jsonl(d / "traces.jsonl")
    corpus = e3.jsonl(d / "corpus.jsonl")
    recorded = e6.recorded_references(d)
    kept_text = {
        name: (d / name).read_text(encoding="utf-8", errors="replace")
        for name in ("events.jsonl", "designer_calls.jsonl", "traces.jsonl", "corpus.jsonl")
        if (d / name).exists()
    }
    out: dict[str, Any] = {"tasks": {}, "ok": True, "expert_recomputed": False}
    for r in ev.get("reference", []):
        task = str(r["task_id"])
        rec: dict[str, Any] = {"available": bool(r.get("available")), "reason": r.get("reason")}
        if not r.get("available"):
            out["tasks"][task] = rec
            continue
        row = next((c for c in calls if str(c["task_id"]) == task and c["regime"] == "zero"), {})
        kept_hash = str(row.get("evidence", "")).split("sha256 ")[1][:16] if row else None
        prov = recorded.get(task)
        leaks: list[str] = []
        actions: list[str] = [str(a) for a in (prov or {}).get("actions", [])]
        if prov is None:
            leaks.append("no privileged_references.jsonl record for this task")
        else:
            rid = str(prov.get("reference_id"))
            rec["reference_id"] = rid
            # record == recomputed == reference event; and == the redacted designer evidence
            # when the arm made a designer call (a controller arm makes none by design)
            rec["provenance_intact"] = rid == reference_id(actions) == str(
                r.get("reference_id")
            ) and (kept_hash is None or kept_hash == rid)
            rec["designer_record"] = kept_hash is not None
            if not rec["provenance_intact"]:
                leaks.append("recorded reference hash does not match the record / event / evidence")
        # provenance of every staged prefix: candidate id -> (source, cut)
        kinds: dict[str, str] = {}
        cuts: dict[str, int] = {}
        for sc in ev.get("stage_candidates", []):
            if str(sc["task_id"]) == task:
                kinds.update({str(k): str(v) for k, v in sc.get("kinds", {}).items()})
        for pr in ev.get("probe", []):
            if str(pr["task_id"]) == task:
                for p in pr.get("profile", []):
                    cuts[str(p["id"])] = int(p["t"])
        ref_cuts = sorted(
            {cuts[c] for c, k in kinds.items() if k in ("reference", "control") and c in cuts}
        )
        rec["reference_cuts"] = ref_cuts
        rec["reference_steps"] = len(actions)
        prefixes = [
            [str(a.get("kwargs", {}).get("text", "")) for a in t["candidate"]["in_env_actions"]]
            for t in traces
            if str(t.get("rollout_seed")) == task and t["candidate"]["in_env_actions"]
        ] + [
            [str(a.get("kwargs", {}).get("text", "")) for a in c.get("in_env_actions", [])]
            for c in corpus
            if str(c.get("aea", {}).get("task_id")) == task and c.get("in_env_actions")
        ]
        from aea.stage import candidate_id as _cid

        attributed = {"failure": 0, "reference": 0}
        for pre in prefixes:
            cid = _cid(task, pre)
            kind = kinds.get(cid)
            if kind == "failure":
                attributed["failure"] += 1  # the policy's own actions: never a reference copy
            elif kind in ("reference", "control") and cid in cuts:
                k = cuts[cid]
                body = pre[:-1] if pre and pre[-1] == "look" and actions[:k] != pre else pre
                allowed = [a for a in actions[:k]]
                if any(a not in allowed for a in body) or any(
                    a in actions[k:] and a not in allowed for a in body
                ):
                    leaks.append(f"reference prefix exceeds its cut {k}: {pre}")
                attributed["reference"] += 1
            else:
                leaks.append(f"unattributed Setup prefix (no stage candidate of this run): {pre}")
        rec["prefixes_by_provenance"] = attributed
        for name, text in kept_text.items():
            if (
                "PRIVILEGED REFERENCE (a successful" in text
                or "PRIVILEGED REFERENCE TRAJECTORY" in text
            ):
                leaks.append(f"{name}: reference block present")
        if row and "[content withheld]" not in str(row.get("evidence", "")):
            leaks.append("designer_calls.jsonl: reference not redacted")
        k_min = min(ref_cuts) if ref_cuts else len(actions)
        future = set(actions[k_min:])
        indep = 0
        for t in traces:
            if str(t.get("rollout_seed")) != task:
                continue
            for st in t.get("steps", []):
                if str(st.get("raw_action", {}).get("kwargs", {}).get("text", "")) in future:
                    indep += 1
        rec["independent_overlap"] = indep
        rec["leaks"] = leaks
        out["tasks"][task] = rec
        if leaks:
            out["ok"] = False
    return out


def src_unmodified() -> bool:
    """``src/aea`` equals the pre-registered method commit (the smoke driver's tree hash
    compares against ITS method commit, so its marker is not used here)."""
    import subprocess

    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", str(METHOD_SHA), "--", "src/aea"],
            check=False,
        ).returncode
        == 0
    )


# ---------------------------------------------------------------------------- stages
def _manifest(d: Path, run_id: str, cfg: AEAConfig, extra: dict[str, Any]) -> Any:
    policy, designer = e3.policy_qwen(), e3.designer_deepseek()
    run_config = RunConfig(
        schema_version=1,
        name=run_id,
        kind="exploratory",
        require_clean_tree=False,
        policy=policy,
        designer=designer,
        runs_root=RUNS,
    )
    if (d / "manifest.json").exists():
        ctx, _ = load_run_context(d)
    else:
        ctx = create_run_context(
            run_config,
            runs_root=RUNS,
            run_id=run_id,
            repo_dir=ROOT,
            aea_config_sha256=aea_config_sha256(cfg),
        )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=e3._git_sha(e3.ENVHARNESS),
        extra={
            "experiment": e3.EXPERIMENT,
            "prereg": f"experiments/alfworld_e6/{PREREG}",
            "prereg_sha": PREREG_SHA,
            "method_sha": METHOD_SHA,
            "src_aea_tree": e6._src_sha(),  # NOTE: marker relative to the SMOKE method commit
            "src_aea_unmodified_vs_method_sha": src_unmodified(),
            "method_version": cfg.method_version,
            "aea_config": cfg.model_dump(mode="json"),
            "tasks": list(TASKS),
            "cap_usd": CAP_USD,
            "policy_endpoint_pin": policy.provider_pin,
            **extra,
        },
    )
    return ctx


def _ready() -> None:
    if PREREG_SHA is None or METHOD_SHA is None:
        raise ConfigError("PREREG_SHA / METHOD_SHA not recorded: commit the prereg first")
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))


def _estimate_task(
    sub: AeaSubstrate, cfg: AEAConfig, task: TaskRef, writer: TraceWriter
) -> tuple[Any, int]:
    """The controller's estimator schedule (``Controller._estimate``) on the real substrate;
    every rollout written to the shared traces file. Returns (estimate, charged rollouts)."""
    pending: list[Trace] = []
    charged = 0

    def rollout(i: int) -> Trace:
        nonlocal charged
        if not pending:
            n = cfg.impl.batch_first if i == 0 else cfg.impl.batch_next
            got = sub.rollouts(
                task,
                Candidate(),
                n,
                attribution=Attribution(
                    phase="estimate", budget="search", arm="shared", task_id=task.task_id
                ),
            )
            charged += n
            for tr in got:
                writer.add(tr)
            pending.extend(got)
        return pending.pop(0)

    return estimate(rollout, cfg), charged


def stage_shared(concurrency: int) -> None:
    """Per task: the controller's estimator schedule on the real substrate (charged, ledgered),
    then ONE rich expert reference if the task is ``zero``. Resumable per task."""
    _ready()
    e3.guard("shared")
    cfg = config("A")
    d = shared_dir()
    _manifest(d, SHARED_ID, cfg, {"stage": "shared evidence"})  # creates the run directory
    sub, _ = build(cfg, d, SHARED_ID, concurrency=concurrency, with_designer=False)
    provider = sub.reference_provider(cfg)
    assert provider is not None
    writer = TraceWriter(d / "traces.jsonl")
    events = EventWriter(d / "events.jsonl", SHARED_ID)
    done = {str(r["task_id"]) for r in e3.jsonl(d / "shared.jsonl")}
    for t in TASKS:
        task = TaskRef(str(t), t)
        if task.task_id in done:
            continue
        e3.guard(f"shared task {t}")
        est, charged = _estimate_task(sub, cfg, task, writer)
        rec: dict[str, Any] = {
            "task_id": task.task_id,
            "regime": est.regime,
            "p_hat": est.p_hat,
            "n": est.n,
            "charged": charged,
            "probabilities": est.probabilities,
            "reference": None,
        }
        events.write(
            "estimate",
            {"task_id": task.task_id, "regime": est.regime, "p_hat": est.p_hat, "n": est.n},
        )
        if est.regime == "zero":
            ref = provider(task)
            row = {
                "task_id": task.task_id,
                **ref.as_record(),
                "ts": time.strftime("%FT%TZ", time.gmtime()),
            }
            with (d / "privileged_references.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            rec["reference"] = {k: row[k] for k in ("reference_id", "success", "reason", "n_steps")}
            events.write(
                "reference",
                {
                    "task_id": task.task_id,
                    "available": ref.ok,
                    "n_steps": ref.n_steps,
                    "reason": ref.reason,
                    "reference_id": row["reference_id"],
                },
            )
        with (d / "shared.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)
        e3.merge(d)


def stage_arms(concurrency: int) -> None:
    """Both arms on every task whose shared evidence exists; resumable per (arm, task)."""
    _ready()
    e3.guard("arms")
    for t in TASKS:
        task_id = str(t)
        shared = shared_estimate(task_id)
        if shared is None:
            raise ConfigError(f"no shared evidence for task {t}: run --stage shared first")
        for arm in ("A", "B"):
            cfg = config(arm)
            d = RUNS / ARM_IDS[arm]
            ctx = _manifest(
                d, ARM_IDS[arm], cfg, {"arm": arm, "stage": "arms", "shared_run": SHARED_ID}
            )
            real, _ = build(cfg, d, ARM_IDS[arm], concurrency=concurrency)
            frozen = FrozenSubstrate(real, task_id)
            ctrl = Controller(
                cfg,
                frozen,
                d,
                ARM_IDS[arm],
                arm=arm,
                use_proposer=True,
                reference=frozen.reference_provider(cfg),
            )
            if task_id in ctrl.completed_tasks():
                continue
            e3.guard(f"arm {arm} task {t}")
            out = ctrl.run([TaskRef(task_id, t)], concurrency=1)[0]
            e3.merge(d)
            print(
                json.dumps(
                    {
                        "arm": arm,
                        "task": task_id,
                        "shared_regime": shared["regime"],
                        "regime": out.regime,
                        "outcome": out.outcome,
                        "reason": out.reason,
                        "n_search": out.n_search,
                        "replayed_estimate": frozen.replayed,
                    }
                ),
                flush=True,
            )
            del ctx


def accepted_envs(arm: str) -> list[dict[str, Any]]:
    p = RUNS / ARM_IDS[arm] / "corpus.jsonl"
    out = []
    for c in e3.jsonl(p):
        a = c["aea"]
        if a["kind"] == "stage":
            out.append(
                {
                    "id": f"{arm}:{a['candidate_id']}",
                    "arm": arm,
                    "task": a["task_id"],
                    "kind": "stage",
                    "t": a.get("t"),
                    "candidate": {
                        "rules_code": c.get("rules_code", ""),
                        "in_env_actions": c.get("in_env_actions", []),
                    },
                }
            )
    return out


def stage_confirm(concurrency: int) -> None:
    _ready()
    e3.guard("confirm")
    d = RUNS / CONFIRM_ID
    _manifest(d, CONFIRM_ID, config("A"), {"stage": "confirm"})
    envs = accepted_envs("A") + accepted_envs("B")
    (d / "envs.json").write_text(json.dumps(envs, indent=1), encoding="utf-8")
    sub, _ = build(config("A"), d, CONFIRM_ID, concurrency=concurrency, with_designer=False)
    summary_path = d / "confirm_summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    writer = TraceWriter(d / "confirm.jsonl")
    cfg = config("A")
    for env in envs:
        if env["id"] in summary:
            continue
        e3.guard(f"confirm {env['id']}")
        task = TaskRef(env["task"], int(env["task"]))
        rec = e3._k16(
            sub,
            writer,
            env["id"],
            task,
            e3.to_candidate(env["candidate"]),
            arm=f"confirm-{env['arm']}",
            n=e6.CONFIRM_K,
            reset_options=sub.stage_reset_options(task),
        )
        p16 = rec["p16"]
        summary[env["id"]] = {
            **rec,
            "arm": env["arm"],
            "t": env["t"],
            "in_band_l": p16 is not None and cfg.band_l[0] <= p16 <= cfg.band_l[1],
            "in_band_t": p16 is not None and cfg.band_t[0] <= p16 <= cfg.band_t[1],
        }
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps({"confirm": env["id"], **rec}), flush=True)
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    e3.merge(d)
    print(json.dumps({"stage": "confirm", "envs": len(envs), "usd": round(e3.dir_spend(d), 2)}))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage", required=True, choices=["probe", "shared", "arms", "confirm", "tables", "spend"]
    )
    ap.add_argument("--concurrency", type=int, default=e3.ROLLOUT_CONCURRENCY)
    args = ap.parse_args(argv)
    try:
        if args.stage == "probe":
            return e3.stage_probe()
        if args.stage == "shared":
            stage_shared(args.concurrency)
        elif args.stage == "arms":
            stage_arms(args.concurrency)
        elif args.stage == "confirm":
            stage_confirm(args.concurrency)
        elif args.stage == "tables":
            mt = importlib.import_module("make_tables_e6_refalign")
            return int(mt.main([]))
        else:
            print(
                json.dumps(
                    {
                        "usd": round(e3.e3_spend(), 2),
                        "cap": CAP_USD,
                        "by_run": {
                            p.name: round(e3.dir_spend(p), 2)
                            for p in sorted(RUNS.glob("e6-refalign-*"))
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
