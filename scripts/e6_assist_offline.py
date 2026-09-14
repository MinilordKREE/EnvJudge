# ruff: noqa: E501  (report-generation script: long markdown rows)
"""Phase 3.4 pre-experiment offline check (design audit, section "validation"): run the
``llm_v1_assistive_rules`` LOW designer ONCE on a few previously seen LOW tasks (frozen failed
estimate rollouts of the phase-3.3b shared stage + their frozen exact references) and report,
descriptively, whether it outputs valid executable Rules with DOSE, identity at d = 0, a defined
direction and no privileged serialisation. No policy rollout, no probe, no prompt tuning on
outcomes; only schema / parser / API-contract / execution / privilege bugs may be fixed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from envharness.core.types import Trace

from aea.config import AEAConfig
from aea.designer import Reference, ReferenceStep, design_low_assist, serialize_low, task_goal
from aea.llm.types import Attribution
from aea.stage import seeded_failures

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_assist  # noqa: F401  (re-targets e6_refalign so build() accepts the assistive variant)
import e6_refalign as er
import e6_smoke as e6

RUN_ID = "e6-assist-offline"
SOURCE = e6.RUNS / "e6-sc-shared"  # phase-3.3b shared evidence: frozen failures + references
DEFAULT_TASKS = ("62", "70", "78")


def frozen(task: str, cfg: AEAConfig) -> tuple[list[Trace], Reference | None]:
    traces = [
        Trace.model_validate(r)
        for r in e3.jsonl(SOURCE / "traces.jsonl")
        if str(r.get("rollout_seed")) == task
        and str(r.get("iteration_id", "")).startswith("estimate-")
    ]
    fails = seeded_failures(traces, cfg.impl.n_failed_rollouts, seed=int(task))
    ref = None
    for r in e3.jsonl(SOURCE / "privileged_references.jsonl"):
        if str(r["task_id"]) == task and r.get("success"):
            steps = tuple(
                ReferenceStep(
                    int(s["step"]), str(s["observation"]), tuple(s["admissible"]), str(s["action"])
                )
                for s in r.get("steps", [])
            )
            ref = Reference(True, "pass", tuple(r["actions"]), steps)
    return fails, ref


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    args = ap.parse_args(argv)
    cfg = AEAConfig.model_validate({"method_version": "llm_v1_assistive_rules"})
    d = e6.RUNS / RUN_ID
    d.mkdir(parents=True, exist_ok=True)
    sub, _ = er.build(cfg, d, RUN_ID, concurrency=1)
    designer = sub.designer()
    assert designer is not None
    out: list[dict[str, Any]] = []
    for task in args.tasks.split(","):
        fails, ref = frozen(task, cfg)
        if not fails or ref is None:
            out.append({"task": task, "skipped": "no frozen failures or reference"})
            continue
        evidence = serialize_low(fails, 0.0, 10, ref, rich=True)
        design = design_low_assist(
            designer,
            model=sub.designer_model(),
            evidence=evidence,
            failures=fails,
            reference=ref,
            goal=task_goal(fails),
            attribution=Attribution(
                phase="design_low", budget="designer", arm="offline", task_id=task
            ),
            seed=int(task),
        )
        row = {
            "task": task,
            "goal": task_goal(fails),
            "reference_steps": ref.n_steps,
            "n_diagnoses": len(design.diagnoses),
            "valid_families": [
                {
                    "name": f.name,
                    "axis": f.axis,
                    "mechanism": f.mechanism_summary,
                    "why": f.why,
                    "code_lines": f.template.count("\n"),
                }
                for f in design.families
            ],
            "rejected": design.rejected,
            "raw_families": len(design.arguments.get("families") or []),
            "arguments": design.arguments,
        }
        out.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "arguments"})[:900], flush=True)
    e3.merge(d)
    e6.RESULTS.mkdir(parents=True, exist_ok=True)
    (e6.RESULTS / "assist_offline.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = [
        "# Phase 3.4 offline check: llm_v1_assistive_rules designer on three phase-3.3b LOW tasks\n",
        "Descriptive only (no policy rollout, no probe, no tuning). Failures and references are the "
        "frozen phase-3.3b shared evidence. One designer call per task.\n",
        "| task | goal | reference steps | diagnoses | raw families | valid families (name, axis) | rejected (reason) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in out:
        if "skipped" in r:
            lines.append(f"| {r['task']} | - | - | - | - | - | {r['skipped']} |")
            continue
        fams = "; ".join(f"{f['name']} ({f['axis']})" for f in r["valid_families"]) or "-"
        rej = "; ".join(str(x).replace("|", "/")[:160] for x in r["rejected"]) or "-"
        lines.append(
            f"| {r['task']} | {r['goal']} | {r['reference_steps']} | {r['n_diagnoses']} | "
            f"{r['raw_families']} | {fams} | {rej} |"
        )
    lines.append("\n## Family mechanisms (LLM's own words)\n")
    for r in out:
        for f in r.get("valid_families", []):
            lines.append(
                f"- task {r['task']} {f['name']} ({f['axis']}): {f['mechanism']} / why: {f['why']}"
            )
    lines.append(f"\nDesigner spend (ledger): USD {round(e3.dir_spend(d), 3)}.")
    (e6.RESULTS / "assist_offline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
