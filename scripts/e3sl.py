"""E3-SL: downstream skill evaluation of the E3 learner-facing sets (PREREG9 Addendum SL,
experiments/alfworld_e3/PREREG9_ADDENDUM_SL.md). Runs write runs/e3sl-banks/ and runs/e3sl-eval/;
spend is every runs/e3sl-* ledger (separate from the E3 search cap).

Banks (released ``_build_bank``, success-only trajectories, so the released single-success mode
picks the shortest success per environment; DeepSeek V4 Pro extractor with thinking off through the
eval hook, embeddings through OpenRouter):
  A_lf   A's learner-facing set: kept tasks (A's own estimate successes on the original) and
         accepted transformed environments (their search successes)
  G_lf, R_lf   accepted non-empty candidates (their accepted-validation successes)
  O      the 30 originals, successes from the shared K=16
  <arm>_cas    supplementary: the released cascade (``induce_pair.main``, automatic mode) on A
         (kinds remapped as in Round 1), G and R
Two inductions per bank (labels i1 / i2 = the addendum's extractor seeds 20260920 / 20260921; the
released single-success induction samples at temperature 0, so the two are replicate runs whose
difference is the endpoint's own nondeterminism — recorded in the LOG). Item matching subsamples
every learner-facing bank to the minimum item count over the eight bank files (seed 20260922).
Anchors: N (no bank) and placebo (5 task-irrelevant items, vocabulary-checked).

Evals: the released ``reasoning_bank_eval.py`` through ``aea.evaldriver.run_eval`` (Qwen3-8B
consumer, alibaba pin, reasoning off; the released SkillOS prompt, history 4, temperature 0.4,
top-5 MMR), full ID 140 + OOD 134, seeds 0 / 1000 / 2000, per-episode resume after a guard abort.
One job at a time; the job's concurrency is 16 minus the E3 chain's episodes in flight, clamped to
[6, 16], read from runs/r1-logs/e3_chain.log at job start.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from aea.core.io import append_jsonl, read_jsonl
from aea.errors import ConfigError
from aea.evaldriver import run_eval
from aea.evalhook import GUARD_MARKER, install, make_hook
from aea.llm.attribution import attributed
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution
from aea.runner import merge_ledgers

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3  # the E3 driver: backbones, run layout, learner-facing sets, candidate keys

ROOT = e3.ROOT
ENVHARNESS = e3.ENVHARNESS
RUNS = e3.RUNS
RESULTS = e3.RESULTS
PRICING = e3.PRICING
BANKS = RUNS / "e3sl-banks"
EVAL = RUNS / "e3sl-eval"
META = BANKS / "banks_e3.json"
CHAIN_LOG = RUNS / "r1-logs" / "e3_chain.log"
ADDENDUM_SHA = "f9623e2"
CAP_USD = 180.0
SEEDS: tuple[int, ...] = (0, 1000, 2000)
SPLITS: dict[str, int] = {"in_distribution": 140, "out_of_distribution": 134}
INDUCTIONS: tuple[int, ...] = (20260920, 20260921)
MATCHED_SEED = 20260922
LF_ARMS: tuple[str, ...] = ("A", "G", "R", "O")
CAS_ARMS: tuple[str, ...] = ("A", "G", "R")
E3_INFLIGHT = {"shared": 8, "A": 16, "G": 5, "R": 5, "h100": 8, "confirm": 8}
MIN_JOB_CONCURRENCY, MAX_JOB_CONCURRENCY = 6, 16  # the addendum guard: eval concurrency <= 16


# ---------------------------------------------------------------------------- spend
def _dir_usd(d: Path) -> float:
    files = (
        [d / "ledger.jsonl"] if (d / "ledger.jsonl").exists() else sorted(d.glob("ledger.*.jsonl"))
    )
    usd = 0.0
    for f in files:
        for r in e3.jsonl(f):
            if r.get("event") == "call":
                usd += float(r.get("usd") or 0.0)
    return usd


def sl_spend() -> float:
    total = 0.0
    for top in RUNS.glob("e3sl-*"):
        if not top.is_dir():
            continue
        for d, _, _ in os.walk(top):
            total += _dir_usd(Path(d))
    return total


def guard(where: str) -> None:
    total = sl_spend()
    print(
        json.dumps(
            {
                "spend_check": where,
                "usd": round(total, 2),
                "cap": CAP_USD,
                "ts": time.strftime("%FT%TZ", time.gmtime()),
            }
        ),
        flush=True,
    )
    if total >= CAP_USD:
        raise ConfigError(f"E3-SL cap USD {CAP_USD} reached ({total:.2f}); stopped at {where}")


# ---------------------------------------------------------------------------- E3 chain state
def e3_stage() -> str | None:
    """The E3 stage currently running (None when none is), from the chain log."""
    if not CHAIN_LOG.exists():
        return None
    running: str | None = None
    for line in CHAIN_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^(\w+) (start|done) ", line)
        if m:
            running = m.group(1) if m.group(2) == "start" else None
        elif line.startswith("E3_DONE") or line.startswith("CHAIN_FAILED"):
            running = None
    return running


def e3_marker_seen(marker: str) -> bool:
    if marker == "done":
        return (RUNS / "E3_DONE").exists()
    if not CHAIN_LOG.exists():
        return False
    return any(
        line.startswith(f"{marker} done")
        for line in CHAIN_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    )


def wait_for_e3(marker: str, poll_s: int = 120) -> None:
    printed = False
    while not e3_marker_seen(marker):
        if not printed:
            print(
                json.dumps(
                    {"waiting_for_e3": marker, "ts": time.strftime("%FT%TZ", time.gmtime())}
                ),
                flush=True,
            )
            printed = True
        time.sleep(poll_s)
    print(json.dumps({"e3_marker": marker, "seen": True}), flush=True)


CONCURRENCY_OVERRIDE = RUNS / "e3sl_concurrency.txt"


def job_concurrency() -> int:
    """Episodes in flight for the next job: the ceiling (``MAX_JOB_CONCURRENCY``, or the integer
    in ``runs/e3sl_concurrency.txt`` when the owner raises it during the run; every job's value is
    logged and written into its resolved eval config) minus the E3 chain's episodes in flight."""
    ceiling = MAX_JOB_CONCURRENCY
    if CONCURRENCY_OVERRIDE.exists() and CONCURRENCY_OVERRIDE.read_text().strip().isdigit():
        ceiling = max(1, min(64, int(CONCURRENCY_OVERRIDE.read_text().strip())))
    stage = e3_stage()
    inflight = E3_INFLIGHT.get(stage or "", 0)
    return max(MIN_JOB_CONCURRENCY, min(ceiling, ceiling - inflight))


# ---------------------------------------------------------------------------- bank inputs
def _successes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("success") and not r.get("error") and r.get("steps")]


def lf_inputs(arm: str) -> dict[str, list[dict[str, Any]]]:
    """{task: success traces of the arm's learner-facing environment on that task}."""
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if arm == "O":
        for d in (RUNS / "e2-shared", RUNS / "e3-shared"):
            for r in _successes(e3.jsonl(d / "confirm.jsonl")):
                by_task[str(r["rollout_seed"])].append(r)
        return dict(by_task)
    envs = [e for e in e3.learner_facing() if arm in e["arms"]]
    traces = _successes(e3.jsonl(RUNS / f"e3-{arm}" / "traces.jsonl"))
    for env in envs:
        task = str(env["task"])
        for r in traces:
            if str(r["rollout_seed"]) == task and _on_env(arm, env, r):
                by_task[task].append(r)
    return dict(by_task)


def _on_env(arm: str, env: dict[str, Any], r: dict[str, Any]) -> bool:
    """The rollout ran on this learner-facing environment: the original for a kept task; the
    accepted candidate otherwise (for G / R only its accepted-validation rollouts)."""
    if env["kind"] == "kept":
        return bool(e3.is_unchanged(r["candidate"]))
    if e3.candidate_key(r["candidate"]) != env["key"]:
        return False
    return arm == "A" or r.get("kind") == "accepted"


def cascade_traces(arm: str) -> Path:
    """R and G: their released traces as they are. A: kinds remapped for the released Stage 2
    (estimate rollouts -> baseline; rollouts on an accepted environment -> accepted; else
    exploration)."""
    src = RUNS / f"e3-{arm}" / "traces.jsonl"
    if arm != "A":
        return src
    keys = {
        (str(env["task"]), env["key"])
        for env in e3.learner_facing()
        if "A" in env["arms"] and env["kind"] != "kept"
    }
    out = BANKS / "traces_A_released.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in e3.jsonl(src):
            task = str(r["rollout_seed"])
            if str(r.get("iteration_id", "")).startswith("estimate-"):
                r["kind"] = "baseline"
            elif (task, e3.candidate_key(r["candidate"])) in keys:
                r["kind"] = "accepted"
            else:
                r["kind"] = "exploration"
            fh.write(json.dumps(r) + "\n")
    return out


# ---------------------------------------------------------------------------- induction
def meta() -> dict[str, Any]:
    return json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}


def save_meta(m: dict[str, Any]) -> None:
    BANKS.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(m, indent=1), encoding="utf-8")


def _load_released(name: str, rel: str) -> Any:
    sys.path.insert(0, str(ENVHARNESS))
    spec = importlib.util.spec_from_file_location(name, ENVHARNESS / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _install_extractor(arm: str, seed: int) -> None:
    """DeepSeek extractor for the completions, OpenRouter for the embeddings; rows on ``eval``."""
    label = Attribution(phase="induce", budget="eval", arm=arm, task_id="e3sl")
    install(
        make_hook(
            e3.designer_deepseek(),
            run_dir=BANKS,
            run_id="e3sl-banks",
            pricing=load_pricing(PRICING),
            default=(label, seed),
            embed_config=e3.policy_qwen(),
        )
    )
    os.environ["OPENAI_API_KEY"] = "routed-by-aea"


def _induction_mix(path: Path) -> dict[str, int]:
    mix: dict[str, int] = defaultdict(int)
    for it in read_jsonl(path):
        mix[str((it.get("source") or {}).get("induction"))] += 1
    return dict(mix)


def induce(name: str, by_task: dict[str, list[dict[str, Any]]], arm: str, seed: int) -> int:
    """Single-success induction through the released ``_build_bank``."""
    BANKS.mkdir(parents=True, exist_ok=True)
    _install_extractor(arm, seed)
    ip = _load_released("induce_pair", "scripts/induce_pair.py")
    path = BANKS / f"{name}.jsonl"
    label = Attribution(phase="induce", budget="eval", arm=arm, task_id="e3sl")
    with attributed(label, seed=seed):
        n = ip._build_bank(
            condition=name,
            traces_by_task=by_task,
            llm_model=f"openai/{e3.designer_deepseek().model}",
            concurrency=4,
            embed_model="openai/google/gemini-embedding-001",
            out_path=path,
        )
    merge_ledgers(BANKS, "e3sl-banks")
    return int(n)


def induce_cascade(arm: str, k: int, seed: int) -> Path:
    """The released Stage 2 verbatim (per-task cascade, automatic mode)."""
    _install_extractor(arm, seed)
    ip = _load_released("induce_pair", "scripts/induce_pair.py")
    rel_dir = BANKS / f"released-{arm}-i{k}"
    rel_dir.mkdir(parents=True, exist_ok=True)
    label = Attribution(phase="induce", budget="eval", arm=arm, task_id="e3sl")
    with attributed(label, seed=seed):
        rc = ip.main(
            [
                "--traces",
                str(cascade_traces(arm)),
                "--out-dir",
                str(rel_dir),
                "--llm-model",
                f"openai/{e3.designer_deepseek().model}",
                "--embed-model",
                "openai/google/gemini-embedding-001",
                "--concurrency",
                "4",
            ]
        )
    if rc:
        raise ConfigError(f"released induce_pair exited {rc} for {arm} (induction {k})")
    merge_ledgers(BANKS, "e3sl-banks")
    out = BANKS / f"{arm}_cas_i{k}.jsonl"
    shutil.copy(rel_dir / "ours_full.jsonl", out)
    return out


def stage_banks(arm: str) -> None:
    guard(f"banks-{arm}")
    m = meta()
    inputs = lf_inputs(arm)
    if not inputs:
        raise ConfigError(f"no learner-facing successes for {arm}; is its corpus on disk?")
    for k, seed in enumerate(INDUCTIONS, 1):
        name = f"{arm}_lf_i{k}"
        if name in m and (BANKS / f"{name}.jsonl").exists():
            continue
        n = induce(name, inputs, arm, seed)
        m[name] = {
            "items": n,
            "tasks": sorted(inputs, key=int),
            "trajectories": {t: len(v) for t, v in inputs.items()},
            "induction": _induction_mix(BANKS / f"{name}.jsonl"),
            "seed_label": seed,
            "extractor": e3.designer_deepseek().model,
            "note": "released single-success induction (temperature 0), shortest success per env",
        }
        save_meta(m)
        print(json.dumps({"bank": name, "items": n, "tasks": len(inputs)}), flush=True)
        guard(f"banks-{arm} after {name}")
    if arm in CAS_ARMS:
        for k, seed in enumerate(INDUCTIONS, 1):
            name = f"{arm}_cas_i{k}"
            if name in m and (BANKS / f"{name}.jsonl").exists():
                continue
            path = induce_cascade(arm, k, seed)
            items = read_jsonl(path)
            m[name] = {
                "items": len(items),
                "tasks": sorted(
                    {str((it.get("source") or {}).get("task_id")) for it in items},
                    key=lambda x: int(x) if x.isdigit() else -1,
                ),
                "induction": _induction_mix(path),
                "seed_label": seed,
                "extractor": e3.designer_deepseek().model,
                "note": "released Stage 2 verbatim (per-task cascade, automatic mode)",
            }
            save_meta(m)
            print(json.dumps({"bank": name, "items": len(items)}), flush=True)
            guard(f"banks-{arm} after {name}")
    print(json.dumps({"stage": f"banks-{arm}", "done": True, "usd": round(sl_spend(), 2)}))


# ---------------------------------------------------------------------------- placebo
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
PLACEBO_DIALOGUE_2: list[tuple[str, str]] = [
    (
        "ask the organiser how the bracket works",
        "Task: set up a 16-player chess knockout that finishes in one afternoon. The organiser "
        "says each round halves the field.",
    ),
    ("count the rounds needed", "Sixteen players need four rounds: 8, 4, 2 and 1 winner."),
    (
        "allot time per round",
        "With 25-minute games and 5-minute breaks, four rounds take about two hours.",
    ),
    (
        "seed the players by rating",
        "Players are seeded 1 to 16 so the top seeds meet only in the final.",
    ),
    (
        "print the pairing sheet",
        "The pairing sheet for round one is printed: seed 1 vs seed 16 and so on.",
    ),
    ("announce the start time", "Round one starts at 14:00; the schedule is posted on the board."),
    ("confirm the tournament plan", "The knockout is fully planned. The task is complete."),
]
ALFWORLD_VERBS = (  # the released command forms; everyday senses excluded (Round 1b)
    r"\bgo to\b",
    r"\btake \w+ \d* ?from\b",
    r"\bput \w+ \d* ?(in|on)\b",
    r"\bopen (the )?(cabinet|drawer|fridge|microwave|safe|box|door)\b",
    r"\bclose (the )?(cabinet|drawer|fridge|microwave|safe|box|door)\b",
    r"\btoggle\b",
    r"\b(heat|cool|clean) \w+ with\b",
    r"\bexamine\b",
    r"\binventory\b",
    r"\blook\b",
    r"\buse (the )?\w*(lamp|light)\b",
    r"\bslice\b",
)
ALFWORLD_NOUNS = {
    "cabinet", "drawer", "fridge", "countertop", "shelf", "sinkbasin", "sink", "microwave",
    "stoveburner", "stove", "garbagecan", "coffeemachine", "toaster", "sofa", "bed", "desk",
    "dresser", "armchair", "sidetable", "diningtable", "bathtubbasin", "bathtub", "toilet",
    "towelholder", "cart", "safe", "laundryhamper", "apple", "mug", "cup", "plate", "bowl", "pan",
    "pot", "knife", "spoon", "fork", "tomato", "potato", "lettuce", "bread", "egg", "book", "pen",
    "pencil", "laptop", "cellphone", "keychain", "creditcard", "remotecontrol", "watch", "box",
    "vase", "statue", "alarmclock", "cd", "pillow", "cloth", "soapbar", "soapbottle",
    "spraybottle", "toiletpaper", "candle", "tissuebox", "dishsponge", "kettle", "ladle",
    "spatula", "saltshaker", "peppershaker", "winebottle", "glassbottle", "butterknife",
    "houseplant", "newspaper", "basketball", "baseballbat", "tennisracket", "plunger",
    "scrubbrush", "papertowelroll", "teddybear", "footstool", "ottoman", "tvstand", "coffeetable",
    "floorlamp", "desklamp", "lightswitch", "showerhead", "showerdoor", "faucet", "receptacle",
    "household", "alfworld",
}  # fmt: skip


def alfworld_hits(text: str) -> list[str]:
    text = text.lower()
    hits = sorted(w for w in ALFWORLD_NOUNS if re.search(rf"\b{re.escape(w)}\b", text))
    hits += [m.group(0) for pat in ALFWORLD_VERBS for m in re.finditer(pat, text)]
    return hits


def stage_placebo() -> None:
    guard("placebo")
    m = meta()
    if "placebo" in m and (BANKS / "placebo.jsonl").exists():
        print(json.dumps({"bank": "placebo", "exists": True}))
        return
    hd = importlib.import_module("handoff_demos")
    recs: dict[str, list[dict[str, Any]]] = {}
    for label, dialogue in (("placebo", PLACEBO_DIALOGUE), ("placebo2", PLACEBO_DIALOGUE_2)):
        if alfworld_hits(" ".join(f"{a} {o}" for a, o in dialogue)):
            raise ConfigError(f"transcript {label} contains ALFWorld vocabulary")
        trace = hd.render_witness_trace(
            label, 0, [a for a, _ in dialogue], [o for _, o in dialogue]
        )
        recs[label] = [trace.model_dump(mode="json")]
    n = induce("placebo_raw", recs, "placebo", INDUCTIONS[0])
    items = read_jsonl(BANKS / "placebo_raw.jsonl")
    bad = []
    for it in items:
        text = " ".join(str(it.get(k, "")) for k in ("title", "description", "content"))
        if alfworld_hits(text):
            bad.append((it.get("title"), alfworld_hits(text)))
    if bad:
        raise ConfigError(f"placebo items contain ALFWorld vocabulary: {bad}")
    keep = items[:5]
    if len(keep) < 5:
        raise ConfigError(f"placebo induction produced {len(keep)} items (< 5)")
    (BANKS / "placebo.jsonl").write_text(
        "".join(json.dumps(it) + "\n" for it in keep), encoding="utf-8"
    )
    m["placebo"] = {
        "items": len(keep),
        "induced": n,
        "titles": [it.get("title") for it in keep],
        "vocab_check": "no ALFWorld object, receptacle or command-form verb",
        "extractor": e3.designer_deepseek().model,
    }
    save_meta(m)
    print(json.dumps({"bank": "placebo", "items": len(keep), "titles": m["placebo"]["titles"]}))


# ---------------------------------------------------------------------------- matching
def lf_bank_names() -> list[str]:
    return [f"{arm}_lf_i{k}" for arm in LF_ARMS for k in (1, 2)]


def stage_matched() -> None:
    m = meta()
    missing = [n for n in lf_bank_names() if not (BANKS / f"{n}.jsonl").exists()]
    if missing:
        raise ConfigError(f"learner-facing banks missing: {missing}")
    sizes = {n: len(read_jsonl(BANKS / f"{n}.jsonl")) for n in lf_bank_names()}
    k = min(sizes.values())
    if k == 0:
        raise ConfigError(f"an empty learner-facing bank: {sizes}")
    (BANKS / "matched").mkdir(exist_ok=True)
    rng = random.Random(MATCHED_SEED)
    report: dict[str, Any] = {"k": k, "sizes": sizes, "seed": MATCHED_SEED, "banks": {}}
    for n in lf_bank_names():
        items = read_jsonl(BANKS / f"{n}.jsonl")
        sample = items if len(items) == k else rng.sample(items, k)
        out = BANKS / "matched" / f"{n}_m.jsonl"
        out.write_text("".join(json.dumps(it) + "\n" for it in sample), encoding="utf-8")
        report["banks"][f"{n}_m"] = {
            "items": k,
            "of": len(items),
            "full_row_is_matched_row": len(items) == k,
        }
    m["matched"] = report
    save_meta(m)
    print(json.dumps(report, indent=0))


# ---------------------------------------------------------------------------- conditions / jobs
def conditions() -> dict[str, tuple[str, Path | None]]:
    """condition -> (arm label, bank path or None)."""
    out: dict[str, tuple[str, Path | None]] = {"N": ("N", None)}
    if (BANKS / "placebo.jsonl").exists():
        out["placebo"] = ("placebo", BANKS / "placebo.jsonl")
    for arm in LF_ARMS:
        for k in (1, 2):
            n = f"{arm}_lf_i{k}"
            if (BANKS / "matched" / f"{n}_m.jsonl").exists():
                out[f"{n}_m"] = (arm, BANKS / "matched" / f"{n}_m.jsonl")
            if (BANKS / f"{n}.jsonl").exists():
                out[n] = (arm, BANKS / f"{n}.jsonl")
    for arm in CAS_ARMS:
        for k in (1, 2):
            n = f"{arm}_cas_i{k}"
            if (BANKS / f"{n}.jsonl").exists():
                out[n] = (arm, BANKS / f"{n}.jsonl")
    return out


def jobs(group: str) -> list[tuple[str, int]]:
    conds = conditions()
    matched_report = meta().get("matched", {}).get("banks", {})
    if group == "anchors":
        names = [c for c in ("N", "placebo") if c in conds]
    elif group == "matched":
        names = [f"{a}_lf_i{k}_m" for a in LF_ARMS for k in (1, 2)]
    elif group == "full":  # a full bank the size of the matched one is already evaluated
        names = [
            f"{a}_lf_i{k}"
            for a in LF_ARMS
            for k in (1, 2)
            if not matched_report.get(f"{a}_lf_i{k}_m", {}).get("full_row_is_matched_row")
        ]
    elif group == "cascade":
        names = [f"{a}_cas_i{k}" for a in CAS_ARMS for k in (1, 2)]
    else:
        raise ConfigError(f"unknown group {group}")
    missing = [n for n in names if n not in conds]
    if missing:
        raise ConfigError(f"conditions without a bank: {missing}")
    return [(n, s) for n in names for s in SEEDS]


def eval_dir(cond: str, seed: int) -> Path:
    return EVAL / f"{cond}-seeds-{seed}"


def cell_files(d: Path, cond: str, split: str) -> list[Path]:
    files = sorted(d.glob(f"round*/{cond}_eval_{split}.jsonl"))
    files += sorted(d.parent.glob(f"{d.name}-resume-*/round*/{cond}_eval_{split}.jsonl"))
    return files


def cell_records(d: Path, cond: str, split: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in cell_files(d, cond, split):
        out.extend(e3.jsonl(f))
    return out


def cell_count(d: Path, cond: str, split: str) -> int:
    return sum(1 for r in cell_records(d, cond, split) if not r.get("error"))


def drop_errored(d: Path, cond: str, split: str) -> list[int]:
    """Remove errored episode records so their seeds are re-run (original kept as
    ``.with_errors``)."""
    dropped: list[int] = []
    for f in cell_files(d, cond, split):
        recs = []
        for r in e3.jsonl(f):
            if r.get("error"):
                dropped.append(int(r["seed"]))
            else:
                recs.append(r)
        if dropped:
            shutil.copy(f, f.with_suffix(".jsonl.with_errors"))
            f.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return dropped


def missing_runs(d: Path, cond: str, split: str, seed: int, n: int) -> list[tuple[int, int]]:
    have = {int(r["seed"]) for r in cell_records(d, cond, split) if not r.get("error")}
    missing = [s for s in range(seed, seed + n) if s not in have]
    runs: list[tuple[int, int]] = []
    for s in missing:
        if runs and runs[-1][0] + runs[-1][1] == s:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((s, 1))
    return runs


def stage_eval_job(cond: str, seed: int, concurrency: int) -> None:
    """One (condition, seed): both splits fresh, or exactly the missing episode seeds."""
    arm, bank = conditions()[cond]
    if bank is not None and (not bank.exists() or bank.stat().st_size == 0):
        raise ConfigError(f"empty bank for {cond}")
    policy = e3.policy_qwen()
    pricing = load_pricing(PRICING)
    base = eval_dir(cond, seed)
    for split in SPLITS:
        dropped = drop_errored(base, cond, split)
        if dropped:
            print(json.dumps({"eval_job": cond, "seed": seed, "split": split, "dropped": dropped}))
    plan: list[tuple[str, int, int]] = []
    for split, n in SPLITS.items():
        plan += [(split, st, k) for st, k in missing_runs(base, cond, split, seed, n)]
    if not plan:
        print(json.dumps({"eval_job": cond, "seed": seed, "complete": True}))
        return
    fresh = plan == [(split, seed, n) for split, n in SPLITS.items()]
    eval_yaml = ENVHARNESS / "experiments" / "alfworld" / "reasoning_bank_eval.yaml"
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    invocations = [(None, seed, SPLITS)] if fresh else [(sp, st, {sp: k}) for sp, st, k in plan]
    for only_split, start_seed, splits in invocations:
        cfg = yaml.safe_load(eval_yaml.read_text(encoding="utf-8"))
        cfg["model"]["name"] = f"openai/{policy.model}"
        cfg["eval"]["concurrency"] = concurrency
        cfg["eval"]["splits"] = {f"eval_{k}": v for k, v in splits.items()}
        out_dir = base if fresh else base.parent / f"{base.name}-resume-{int(time.time() * 1000)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved = out_dir / "reasoning_bank_eval_e3sl.yaml"
        resolved.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        rc = run_eval(
            arm=arm,
            conditions={cond: bank},
            config_yaml=resolved,
            out_dir=out_dir,
            start_seeds=(start_seed,),
            concurrency=concurrency,
            llm=policy,
            pricing=pricing,
            run_id="e3sl-eval",
            envharness_root=ENVHARNESS,
        )
        merge_ledgers(out_dir, "e3sl-eval")
        print(
            json.dumps(
                {
                    "eval_job": cond,
                    "seed": seed,
                    "split": only_split,
                    "start": start_seed,
                    "n": sum(splits.values()),
                    "concurrency": concurrency,
                    "rc": rc,
                    "out_dir": str(out_dir),
                }
            ),
            flush=True,
        )


def stage_evals(group: str) -> None:
    guard(f"evals-{group}")
    todo = jobs(group)
    pending = [
        (c, s)
        for c, s in todo
        if any(cell_count(eval_dir(c, s), c, split) < n for split, n in SPLITS.items())
    ]
    print(
        json.dumps({"stage": f"evals-{group}", "jobs": len(todo), "pending": len(pending)}),
        flush=True,
    )
    log_dir = EVAL / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    def run_job(job: tuple[str, int], concurrency: int) -> int:
        cond, seed = job
        with (log_dir / f"{cond}-{seed}.log").open("a", encoding="utf-8") as fh:
            return subprocess.call(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "e3sl.py"),
                    "--stage",
                    "eval-job",
                    "--cond",
                    cond,
                    "--seed",
                    str(seed),
                    "--concurrency",
                    str(concurrency),
                ],
                stdout=fh,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
            )

    def guard_incidents(job: tuple[str, int]) -> list[dict[str, Any]]:
        base = eval_dir(*job)
        found = []
        for d in [base, *base.parent.glob(f"{base.name}-resume-*")]:
            marker = d / GUARD_MARKER
            if marker.exists():
                found.append({"job": list(job), "dir": d.name, **json.loads(marker.read_text())})
                marker.rename(d / "guard_failure.handled.json")
        return found

    for done, job in enumerate(pending, 1):
        concurrency = job_concurrency()
        print(
            json.dumps({"eval_start": job, "concurrency": concurrency, "e3_stage": e3_stage()}),
            flush=True,
        )
        rc = 0
        for attempt in range(4):  # a guard abort ends one episode; resume the missing ones
            rc = run_job(job, concurrency)
            incidents = guard_incidents(job)
            for inc in incidents:
                append_jsonl(EVAL / "guard_incidents.jsonl", {**inc, "attempt": attempt})
                print(json.dumps({"guard_incident": inc}), flush=True)
            if rc == 0 or not incidents:
                break
        print(
            json.dumps(
                {
                    "eval_done": job,
                    "rc": rc,
                    "done": done,
                    "of": len(pending),
                    "usd": round(sl_spend(), 2),
                }
            ),
            flush=True,
        )
        if rc:
            raise ConfigError(f"eval job {job} failed rc={rc}; see {log_dir}")
        if done % 3 == 0:
            guard(f"evals-{group} after {done} jobs")
    print(json.dumps({"stage": f"evals-{group}", "done": True, "usd": round(sl_spend(), 2)}))


# ---------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        required=True,
        choices=[
            "placebo",
            "banks",
            "matched",
            "eval-job",
            "evals",
            "tables",
            "spend",
            "wait",
        ],
    )
    ap.add_argument("--arm", default="")
    ap.add_argument("--group", default="matched")
    ap.add_argument("--cond", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--for", dest="marker", default="done")
    args = ap.parse_args(argv)
    try:
        if args.stage == "placebo":
            stage_placebo()
        elif args.stage == "banks":
            stage_banks(args.arm)
        elif args.stage == "matched":
            stage_matched()
        elif args.stage == "eval-job":
            stage_eval_job(args.cond, args.seed, args.concurrency)
        elif args.stage == "evals":
            stage_evals(args.group)
        elif args.stage == "tables":
            mt3 = importlib.import_module("make_tables_e3sl")
            return int(mt3.main([]))
        elif args.stage == "wait":
            wait_for_e3(args.marker)
        else:
            print(
                json.dumps(
                    {
                        "usd": round(sl_spend(), 2),
                        "cap": CAP_USD,
                        "e3_stage": e3_stage(),
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
