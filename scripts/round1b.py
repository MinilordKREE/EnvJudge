"""E1-SL Round 1b (PREREG7 Amendment 3; owner brief of 2026-09-09): corrections and additions on
top of Round 1. Reuses scripts/round1.py (arm dirs, confirmations, eval jobs).

Stages, in the brief's order:
  banks-u2       A3.1: corrected Protocol U for A / A-ex / A+H (every task with >= 1 success in the
                 arm's own search); Round-1 banks and eval dirs archived as *_U_v1
  placebo        A3.2a: 5 task-irrelevant items induced by the released extractor from a neutral
                 transcript in the released trace format (vocabulary assertion)
  matched        A3.2b: every listed bank subsampled (seed 20260916) to 8 and to 20 items
  corpus-Aprime  A3.3: the A controller with cross-task family priors (aea.priors), seeds 0-29
  confirm-Aprime / banks-Aprime
  jobs           write the eval job list for a group: u2 | placebo | matched | aprime
  evals are run through scripts/round1.py --stage evals --jobs-file <list>
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import round1 as r1

from aea.config import AEAConfig, aea_config_sha256
from aea.controller import Controller
from aea.core.config import RunConfig
from aea.core.context import create_run_context
from aea.core.io import read_jsonl
from aea.core.manifest import write_manifest
from aea.errors import ConfigError
from aea.evalhook import install, make_hook
from aea.handoff import render_witness_trace
from aea.llm.attribution import attributed
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution
from aea.priors import FamilyPriors
from aea.runner import merge_ledgers

RUNS = r1.RUNS
BANKS = RUNS / "r1-banks"
EXTRA = BANKS / "extra_conditions.json"
MATCHED_SEED = 20260916
MATCHED_SIZES = (8, 20)
MATCHED_BANKS = ("O_U", "R_T2", "R_U", "G_T2", "G_U", "A_T2", "A_U", "Aex_U", "AplusH_T2")
ALFWORLD_VOCAB = {
    "go to",
    "take",
    "put",
    "open",
    "close",
    "toggle",
    "heat",
    "cool",
    "clean",
    "examine",
    "inventory",
    "look",
    "use",
    "slice",
    "cabinet",
    "drawer",
    "fridge",
    "countertop",
    "shelf",
    "sinkbasin",
    "sink",
    "microwave",
    "stoveburner",
    "stove",
    "garbagecan",
    "coffeemachine",
    "toaster",
    "sofa",
    "bed",
    "desk",
    "dresser",
    "armchair",
    "sidetable",
    "diningtable",
    "bathtubbasin",
    "bathtub",
    "toilet",
    "towelholder",
    "cart",
    "safe",
    "laundryhamper",
    "apple",
    "mug",
    "cup",
    "plate",
    "bowl",
    "pan",
    "pot",
    "knife",
    "spoon",
    "fork",
    "tomato",
    "potato",
    "lettuce",
    "bread",
    "egg",
    "book",
    "pen",
    "pencil",
    "laptop",
    "cellphone",
    "keychain",
    "creditcard",
    "remotecontrol",
    "watch",
    "box",
    "vase",
    "statue",
    "alarmclock",
    "cd",
    "pillow",
    "cloth",
    "soapbar",
    "soapbottle",
    "spraybottle",
    "toiletpaper",
    "candle",
    "tissuebox",
    "dishsponge",
    "kettle",
    "ladle",
    "spatula",
    "saltshaker",
    "peppershaker",
    "winebottle",
    "glassbottle",
    "butterknife",
    "houseplant",
    "newspaper",
    "basketball",
    "baseballbat",
    "tennisracket",
    "plunger",
    "scrubbrush",
    "papertowelroll",
    "teddybear",
    "footstool",
    "ottoman",
    "tvstand",
    "coffeetable",
    "floorlamp",
    "desklamp",
    "lightswitch",
    "showerhead",
    "showerdoor",
    "faucet",
    "receptacle",
    "household",
    "alfworld",
}


def extra_conditions() -> dict[str, list[Any]]:
    return json.loads(EXTRA.read_text(encoding="utf-8")) if EXTRA.exists() else {}


def add_condition(name: str, arm: str, path: Path | None) -> None:
    ex = extra_conditions()
    ex[name] = [arm, str(path) if path else None]
    EXTRA.write_text(json.dumps(ex, indent=1), encoding="utf-8")


def banks_meta() -> dict[str, Any]:
    p = BANKS / "banks_r1.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_meta(meta: dict[str, Any]) -> None:
    (BANKS / "banks_r1.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


def induce(name: str, by_task: dict[str, list[dict[str, Any]]], arm: str) -> tuple[Path, int]:
    """Single-success induction through the released _build_bank (as Round 1's banks stage)."""
    policy, _ = r1.backbone()
    pricing = load_pricing(r1.PRICING)
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"
    label = Attribution(phase="induce", budget="eval", arm=arm, task_id="r1b")
    install(
        make_hook(policy, run_dir=BANKS, run_id="r1-banks", pricing=pricing, default=(label, 0))
    )
    ip = r1._load_released("induce_pair", "scripts/induce_pair.py")
    path = BANKS / f"{name}.jsonl"
    with attributed(label, seed=0):
        n = ip._build_bank(
            condition=name,
            traces_by_task=by_task,
            llm_model=f"openai/{policy.model}",
            concurrency=4,
            embed_model="openai/google/gemini-embedding-001",
            out_path=path,
        )
    merge_ledgers(BANKS, "r1-banks")
    return path, int(n)


# ---------------------------------------------------------------------------- A3.1 corrected U
def corrected_u_inputs(arm: str) -> dict[str, list[dict[str, Any]]]:
    """U = T2 union every task with >= 1 success during the arm's own search (any status):
    for a task outside T2, all its non-hint search successes (original or transformed env)."""
    base = r1.bank_inputs(arm)
    t2 = base["T2"]
    records = r1.read_traces(r1.arm_dir(arm) / "traces.jsonl")
    u: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task, rs in t2.items():
        u[task].extend(rs)
    for rec in r1._success_traces(records):
        task = str(rec["rollout_seed"])
        if task not in t2:
            u[task].append(rec)
    if arm == "AplusH":
        for rec in r1.read_traces(r1.arm_dir(arm) / "handoff.jsonl"):
            u.setdefault(str(rec["rollout_seed"]), []).append(rec)
    return dict(u)


def stage_banks_u2() -> None:
    meta = banks_meta()
    for arm in ("A", "Aex", "AplusH"):
        name, v1 = f"{arm}_U", f"{arm}_U_v1"
        if v1 not in meta:  # archive Round 1's bank and its eval dirs once
            shutil.copy(BANKS / f"{name}.jsonl", BANKS / f"{v1}.jsonl")
            meta[v1] = {**meta[name], "archived_from": name, "definition": "Amendment 1"}
            for d in sorted((RUNS / "r1-eval").glob(f"{name}-seeds-*")):
                target = d.parent / d.name.replace(f"{name}-", f"{v1}-", 1)
                d.rename(target)
                for f in target.glob(f"round*/{name}_eval_*.jsonl"):
                    f.rename(f.parent / f.name.replace(f"{name}_", f"{v1}_", 1))
            add_condition(v1, arm, BANKS / f"{v1}.jsonl")
            save_meta(meta)
        by_task = corrected_u_inputs(arm)
        path, n = induce(name, by_task, arm)
        meta[name] = {
            "items": n,
            "tasks": sorted(by_task, key=int),
            "trajectories": {k: len(v) for k, v in by_task.items()},
            "induction": r1._induction_mix(path),
            "definition": "Amendment 3 A3.1",
        }
        save_meta(meta)
        print(json.dumps({"bank": name, "items": n, "tasks": len(by_task)}), flush=True)


# ---------------------------------------------------------------------------- A3.2a placebo
PLACEBO_DIALOGUE: list[tuple[str, str]] = [
    (
        "ask the clerk about tomorrow's departures",
        "Task: plan a rail journey from Bergen to Oslo arriving before noon. The clerk lists "
        "departures at 06:15, 07:58 and 09:40 from platform 3.",
    ),
    (
        "check the timetable for connections",
        "The 07:58 service is direct; the 06:15 requires a change at Voss with a 12-minute wait.",
    ),
    (
        "compare ticket prices",
        "Standard fare 890 kr, off-peak 620 kr valid on the 07:58 only, seat reservation 60 kr "
        "extra.",
    ),
    ("choose the 07:58 departure", "You select the 07:58 direct service; estimated arrival 11:35."),
    ("reserve a window seat", "Seat 41A in coach 5 is reserved; the ticket is sent to your phone."),
    (
        "set a reminder for the platform",
        "A reminder is set for 07:35: platform 3, coach 5, seat 41A.",
    ),
    ("confirm the booking", "Booking confirmed. Reference RJ-2841. The journey plan is complete."),
]


def stage_placebo() -> None:
    trace = render_witness_trace(
        "placebo", 0, [a for a, _ in PLACEBO_DIALOGUE], [o for _, o in PLACEBO_DIALOGUE]
    )
    rec = trace.model_dump(mode="json")
    path, n = induce("placebo_raw", {"placebo": [rec]}, "placebo")
    items = read_jsonl(path)
    bad = []
    for it in items:
        text = " ".join(str(it.get(k, "")) for k in ("title", "description", "content")).lower()
        hits = sorted(w for w in ALFWORLD_VOCAB if re.search(rf"\b{re.escape(w)}\b", text))
        if hits:
            bad.append((it.get("title"), hits))
    if bad:
        raise ConfigError(f"placebo items contain ALFWorld vocabulary: {bad}")
    keep = items[:5]
    if len(keep) < 5:
        raise ConfigError(
            f"placebo induction produced {len(keep)} items (< 5); extend the transcript"
        )
    out = BANKS / "placebo.jsonl"
    out.write_text("".join(json.dumps(it) + "\n" for it in keep), encoding="utf-8")
    meta = banks_meta()
    meta["placebo"] = {
        "items": len(keep),
        "induced": n,
        "titles": [it.get("title") for it in keep],
        "vocab_check": "no ALFWorld object, receptacle or verb",
        "definition": "Amendment 3 A3.2a",
    }
    save_meta(meta)
    add_condition("placebo", "placebo", out)
    print(json.dumps({"bank": "placebo", "items": len(keep), "titles": meta["placebo"]["titles"]}))


# ---------------------------------------------------------------------------- A3.2b matched
def stage_matched() -> None:
    (BANKS / "matched").mkdir(exist_ok=True)
    rng = random.Random(MATCHED_SEED)
    report: dict[str, Any] = {}
    conds = r1.conditions()
    for bank in MATCHED_BANKS:
        src = conds[bank][1]
        assert src is not None
        items = read_jsonl(src)
        for k in MATCHED_SIZES:
            name = f"{bank}@{k}"
            if len(items) <= k:
                report[name] = {
                    "items": len(items),
                    "flag": "full size (bank smaller than or equal to the target); evaluated as "
                    "the full bank",
                }
                continue
            sample = rng.sample(items, k)
            out = BANKS / "matched" / f"{name}.jsonl"
            out.write_text("".join(json.dumps(it) + "\n" for it in sample), encoding="utf-8")
            add_condition(name, conds[bank][0], out)
            report[name] = {"items": k, "of": len(items)}
    report["N@8"] = report["N@20"] = {"items": 0, "flag": "no bank; the N row is the reference"}
    (BANKS / "matched" / "matched.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=0))


# ---------------------------------------------------------------------------- A3.3 A'
def stage_corpus_aprime(task_concurrency: int) -> None:
    r1.spend_guard("corpus-Aprime")
    policy, designer = r1.backbone()
    run_id = "r1-Aprime"
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
        repo_dir=r1.ROOT,
        aea_config_sha256=aea_config_sha256(AEAConfig()),
    )
    write_manifest(
        ctx,
        run_config,
        envharness_sha=r1._git_sha(r1.ENVHARNESS),
        extra={
            "phase": "round1b",
            "arm": "Aprime",
            "use_designer": True,
            "priors": {"skip_after": 5, "demote_after": 5, "initial_start_dose": 0.5},
            "task_ids": [r1.TASKS[0], r1.TASKS[-1]],
            "amendment3": "A3.3",
            "policy_endpoint_pin": policy.provider_pin,
            "designer_endpoint_pin": designer.provider_pin,
            "thinking": policy.thinking,
        },
    )
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    substrate = r1.make_substrate(ctx.out_dir, ctx.run_id, with_designer=True, concurrency=4)
    priors = FamilyPriors(skip_after=5, demote_after=5)
    controller = Controller(
        AEAConfig(),
        substrate,
        ctx.out_dir,
        ctx.run_id,
        arm="Aprime",
        use_designer=True,
        priors=priors,
    )
    refs = r1.task_refs()
    for start in range(0, len(refs), 10):
        chunk = refs[start : start + 10]
        outcomes = controller.run(chunk, concurrency=task_concurrency)
        r1.merge_all(ctx.out_dir)
        for o in outcomes:
            print(
                json.dumps(
                    {
                        "arm": "Aprime",
                        "task": o.task.task_id,
                        "status": o.status,
                        "regime": o.regime,
                        "p_hat": o.p_hat,
                        "n_search": o.n_search,
                    }
                ),
                flush=True,
            )
        (ctx.out_dir / "priors.json").write_text(
            json.dumps(priors.snapshot(), indent=1), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "arm": "Aprime",
                    "tasks_done": start + len(chunk),
                    "usd": round(r1.dir_spend(ctx.out_dir), 2),
                    "priors": priors.snapshot(),
                }
            ),
            flush=True,
        )
        r1.spend_guard(f"corpus-Aprime after {start + len(chunk)} tasks")
    r1.write_arm_manifest(
        "Aprime", {"run_id": ctx.run_id, "use_designer": True, "priors": priors.snapshot()}
    )
    print(json.dumps({"stage": "corpus-Aprime", "done": True}))


def stage_banks_aprime() -> None:
    meta = banks_meta()
    t2 = r1.bank_inputs("Aprime")["T2"]
    u = corrected_u_inputs("Aprime")
    for name, by_task in (("Aprime_T2", t2), ("Aprime_U", u)):
        if by_task:
            path, n = induce(name, by_task, "Aprime")
        else:
            path, n = BANKS / f"{name}.jsonl", 0
            path.write_text("", encoding="utf-8")
        meta[name] = {
            "items": n,
            "tasks": sorted(by_task, key=int),
            "trajectories": {k: len(v) for k, v in by_task.items()},
            "induction": r1._induction_mix(path) if n else {},
            "definition": "A3.3 (T2; U per A3.1)",
        }
        save_meta(meta)
        add_condition(name, "Aprime", path)
        print(json.dumps({"bank": name, "items": n, "tasks": len(by_task)}), flush=True)


# ---------------------------------------------------------------------------- eval job lists
def jobs_for(group: str) -> list[tuple[str, int]]:
    six, three = list(r1.SEEDS_PRIMARY), list(r1.SEEDS_ABLATION)
    if group == "u2":
        return (
            [("A_U", s) for s in six]
            + [("Aex_U", s) for s in three]
            + [("AplusH_U", s) for s in three]
        )
    if group == "placebo":
        return [("placebo", s) for s in six]
    if group == "matched":
        conds = extra_conditions()
        return [(c, s) for c in sorted(conds) if "@" in c for s in three]
    if group == "aprime":
        return [("Aprime_T2", s) for s in six] + [("Aprime_U", s) for s in six]
    raise ConfigError(f"unknown job group {group}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=[
            "banks-u2",
            "placebo",
            "matched",
            "corpus-Aprime",
            "confirm-Aprime",
            "banks-Aprime",
            "jobs",
        ],
    )
    ap.add_argument("--group", default="")
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args(argv)
    try:
        if args.stage == "banks-u2":
            stage_banks_u2()
        elif args.stage == "placebo":
            stage_placebo()
        elif args.stage == "matched":
            stage_matched()
        elif args.stage == "corpus-Aprime":
            stage_corpus_aprime(args.concurrency)
        elif args.stage == "confirm-Aprime":
            r1.stage_confirm("Aprime", 8)
        elif args.stage == "banks-Aprime":
            stage_banks_aprime()
        else:
            jobs = jobs_for(args.group)
            out = RUNS / "r1-eval" / f"jobs_{args.group}.json"
            out.write_text(json.dumps(jobs), encoding="utf-8")
            print(json.dumps({"group": args.group, "jobs": len(jobs), "file": str(out)}))
    except ConfigError as exc:
        print(f"CONFIG/GATE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
