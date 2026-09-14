"""Phase 3.2 offline diagnostic (docs/design/HARNESSEVOLVE_VS_AEA_LOW.md, section "offline"):
run the ``llm_v1_refalign`` LOW designer ONCE per previously seen LOW task (smoke 1: 8, 9, 10;
smoke 2: 11, 14, 17) on that smoke's frozen failed estimate rollouts plus a freshly recorded rich
expert reference, and write the diagnosis / proposals for human inspection. No policy rollout, no
Stage probe, no threshold or prompt tuning. Not an efficacy experiment.

The reference is recorded in a new expert session (the ALFWorld expert is not deterministic
across sessions, so it may differ from the action list the smoke designer saw); the report says
so. Output: experiments/alfworld_e6/results/refalign_offline.md (+ .json); the designer calls
are ledgered under runs/e6-refalign-offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from envharness.core.types import Trace

from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.designer import design_low_refalign, serialize_low
from aea.llm.types import Attribution
from aea.stage import seeded_failures

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_smoke as e6

RUN_ID = "e6-refalign-offline"
SOURCES: dict[str, str] = {
    "8": "e6-smoke-llm-v1",
    "9": "e6-smoke-llm-v1",
    "10": "e6-smoke-llm-v1",
    "11": "e6-smoke2-llm-v1",
    "14": "e6-smoke2-llm-v1",
    "17": "e6-smoke2-llm-v1",
}


def frozen_failures(task: str, run: Path, cfg: AEAConfig) -> list[Trace]:
    """The smoke's own estimate rollouts of the task (traces.jsonl, iteration ``estimate-``),
    sampled exactly as the controller did (``seeded_failures`` with the task seed)."""
    traces = [
        Trace.model_validate(r)
        for r in e3.jsonl(run / "traces.jsonl")
        if str(r.get("rollout_seed")) == task
        and str(r.get("iteration_id", "")).startswith("estimate-")
    ]
    return seeded_failures(traces, cfg.impl.n_failed_rollouts, seed=int(task))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=",".join(SOURCES))
    args = ap.parse_args(argv)
    cfg = AEAConfig(method_version="llm_v1_refalign")
    d = e6.RUNS / RUN_ID
    d.mkdir(parents=True, exist_ok=True)
    sub, _ = e6.build(cfg, d, RUN_ID, concurrency=1)
    designer = sub.designer()
    provider = sub.reference_provider(cfg)
    assert designer is not None and provider is not None
    out: list[dict[str, Any]] = []
    for task in args.tasks.split(","):
        run = e6.RUNS / SOURCES[task]
        failures = frozen_failures(task, run, cfg)
        ref = provider(TaskRef(task, int(task)))
        row: dict[str, Any] = {
            "task": task,
            "source_run": SOURCES[task],
            "n_failures": len(failures),
            "reference_ok": ref.ok,
            "reference_reason": ref.reason,
            "reference_steps": ref.n_steps,
            "reference_id": ref.as_record()["reference_id"],
        }
        (d / f"privileged_reference_{task}.json").write_text(
            json.dumps(ref.as_record(), indent=1), encoding="utf-8"
        )
        if not (failures and ref.ok):
            row["skipped"] = "no failures" if not failures else "reference unavailable"
            out.append(row)
            continue
        evidence = serialize_low(failures, 0.0, 10, ref, rich=True)
        design = design_low_refalign(
            designer,
            model=sub.designer_model(),
            evidence=evidence,
            failures=failures,
            reference=ref,
            attribution=Attribution(
                phase="design_low", budget="designer", arm="offline", task_id=task
            ),
            seed=int(task),
        )
        row.update(
            evidence_chars=len(evidence.text),
            reference_used=evidence.reference_used,
            goal=evidence.text.split("\n", 1)[0],
            failure_lengths=[len(t.steps) for t in failures],
            diagnoses=[d_.__dict__ for d_ in design.diagnoses],
            stages=[
                {"reference_step": p.step, "diagnosis": p.diagnosis, "why": p.mechanism_summary}
                for p in design.stages
            ],
            rejected=design.rejected,
            arguments=design.arguments,
        )
        out.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "arguments"})[:600], flush=True)
    e3.merge(d)
    e6.RESULTS.mkdir(parents=True, exist_ok=True)
    (e6.RESULTS / "refalign_offline.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = [
        "# Phase 3.2 offline diagnostic: llm_v1_refalign designer on the six previously seen "
        "LOW tasks\n",
        "Descriptive only (no policy rollout, no Stage probe, no tuning). Failures = the smoke's "
        "own frozen estimate rollouts; reference = a fresh rich expert trajectory (new session; "
        "may differ from the action list the smoke designer saw). One designer call per task.\n",
        "| task | goal | failures (steps) | reference | diagnosed failure step | reference step "
        "| error cause | fix hint | proposed reference cuts (linked?) | rejected |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in out:
        if "skipped" in r:
            cells = [
                r["task"],
                "-",
                str(r["n_failures"]),
                str(r["reference_reason"]),
                "-",
                "-",
                str(r["skipped"]),
                "-",
                "-",
                "-",
            ]
            lines.append("| " + " | ".join(cells) + " |")
            continue
        for i, dg in enumerate(r["diagnoses"] or [{}]):
            cuts = (
                "; ".join(f"ref@{s['reference_step']} (diag {s['diagnosis']})" for s in r["stages"])
                if i == 0
                else ""
            )
            cells = [
                str(r["task"]),
                str(r["goal"]).replace("TASK GOAL: ", ""),
                str(r["failure_lengths"]),
                f"ok, {r['reference_steps']} steps",
                f"{dg.get('failure_id', '-')}@{dg.get('failure_step', '-')}",
                str(dg.get("reference_step", "-")),
                str(dg.get("error_cause", "-")).replace("|", "/"),
                str(dg.get("fix_hint", "-")).replace("|", "/"),
                cuts,
                str(len(r["rejected"])),
            ]
            lines.append("| " + " | ".join(cells) + " |")
    lines.append(f"\nDesigner spend (ledger): USD {round(e3.dir_spend(d), 3)}.")
    (e6.RESULTS / "refalign_offline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
