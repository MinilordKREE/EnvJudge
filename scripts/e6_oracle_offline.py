# ruff: noqa: E501  (report-generation script: long markdown rows)
"""Phase 3.5a offline validation of the seven hand-verified families BEFORE the freeze
(docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md, section "Offline validation"). LLM-free, no
current-policy call. Per family: the phase-3.4 validation (loader + smoke at d = 1, identity at
d = 0, structural privilege check against the frozen failures and reference); on the real
ALFWorld environment: the frozen reference replayed under W(0) and W(1) (task preserved: the
verified reference still wins; support events counted); a frozen failure prefix replayed under
d in {0.25, 0.5, 0.75, 1} (support-event counts non-decreasing in d); the existing oracle guard
(handcoded expert under W(1)). Writes ``oracle_actuators/validation.json`` and ``.md``.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_oracle as eo  # noqa: F401  (re-targets e6_refalign to the frozen phase-3.4 evidence)
import e6_refalign as er
import oracle_actuators as oa

from aea.config import AEAConfig
from aea.designer import task_goal
from aea.families import FamilyContext
from aea.session import SESSION_LOCK
from aea.stage import seeded_failures
from aea.substrate import AeaSubstrate
from aea.witness import solvable

RUN_ID = "e6-oa-offline"
DOSES = (0.25, 0.5, 0.75, 1.0)
PREFIX_STEPS = 12  # the first actions of one frozen failure (the policy's own trajectory)


def replay(
    sub: AeaSubstrate, task_id: str, cand: Candidate | None, actions: list[str]
) -> dict[str, Any]:
    """Replay verbatim on the real environment; returns win / blocked count / observations."""
    task = e3.TaskRef(task_id, int(task_id))
    with SESSION_LOCK:
        sess = sub.open_session(task, cand, None)
        try:
            obs_texts: list[str] = []
            blocked: list[bool] = []
            for a in actions:
                if sess.done:
                    break
                r = sess.step_text(a)
                obs_texts.append(str(r["obs"]))
                blocked.append(bool(r["blocked"]))
                if r["won"]:
                    break
            won = sess.won
        finally:
            sess.close()
    return {"won": won, "n_steps": len(obs_texts), "blocked": blocked, "obs": obs_texts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=",".join(oa.TASKS))
    args = ap.parse_args(argv)
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    cfg = AEAConfig.model_validate({"method_version": "llm_v1_assistive_rules"})
    d = er.RUNS / RUN_ID
    d.mkdir(parents=True, exist_ok=True)
    sub, _ = er.build(cfg, d, RUN_ID, concurrency=1, with_designer=False)
    fams = oa.frozen_families()
    out: dict[str, Any] = {}
    for task_id in args.tasks.split(","):
        spec = oa.SPEC_BY_TASK[task_id]
        fam = fams[task_id]
        traces = er.frozen_traces(task_id)
        fails = seeded_failures(traces, cfg.impl.n_failed_rollouts, seed=int(task_id))
        ref = er.frozen_reference(task_id)
        assert ref is not None and ref.ok
        goal = task_goal(fails)
        rec: dict[str, Any] = {
            "task": task_id,
            "class": spec.cls,
            "family": spec.name,
            "code_sha256_16": oa.sha(fam.template),
            "goal": goal,
            "reference_id": er.reference_id(list(ref.actions)),
            "reference_steps": ref.n_steps,
            "validation_reasons": oa.validate(
                fam, task=task_id, failures=fails, reference=ref, goal=goal
            ),
        }
        ctx = FamilyContext(task_id=task_id)

        def cand(dose: float, fam: Any = fam, ctx: Any = ctx) -> Candidate:
            c = fam.make(dose, ctx)
            assert c is not None
            return c

        # reference replayed under W(0) and W(1): the task is preserved
        for dose in (0.0, 1.0):
            r = replay(sub, task_id, cand(dose), list(ref.actions))
            rec[f"reference_replay_d{dose:g}"] = {
                "won": r["won"],
                "n_steps": r["n_steps"],
                "blocked_steps": sum(r["blocked"]),
                "annotated_obs": sum(1 for t in r["obs"] if "Goal steps:" in t),
            }
        base = replay(sub, task_id, None, list(ref.actions))
        rec["reference_replay_original"] = {"won": base["won"], "n_steps": base["n_steps"]}
        r0 = replay(sub, task_id, cand(0.0), list(ref.actions))
        rec["identity_at_zero_on_env"] = r0["obs"] == base["obs"] and r0["won"] == base["won"]
        # a frozen failure prefix (the policy's own actions) under increasing dose
        failure = fails[0]
        prefix = [str(s.raw_action.kwargs.get("text", "")) for s in failure.steps[:PREFIX_STEPS]]
        rec["failure_prefix"] = prefix
        counts: dict[str, int] = {}
        for dose in DOSES:
            r = replay(sub, task_id, cand(dose), prefix)
            if spec.cls == "S":
                # pruning is visible as a shorter admissible list than the original environment
                base_r = replay(sub, task_id, None, prefix)
                n = sum(
                    1
                    for a, b in zip(r["obs"], base_r["obs"], strict=False)
                    if len(a.split("Admissible commands:")[-1])
                    < len(b.split("Admissible commands:")[-1])
                )
            elif spec.cls == "P":
                n = sum(r["blocked"])
            else:
                n = sum(1 for t in r["obs"] if "Goal steps:" in t)
            counts[f"{dose:g}"] = n
        rec["failure_prefix_support_events"] = counts
        vals = [counts[f"{x:g}"] for x in DOSES]
        rec["support_monotone_in_dose"] = all(a <= b for a, b in itertools.pairwise(vals))
        # the existing oracle guard at d = 1 (handcoded expert under W(1))
        with SESSION_LOCK:
            guard = solvable(
                cand(1.0),
                lambda c, t=task_id: sub.open_session(e3.TaskRef(t, int(t)), c, None),
                cfg,
                policy_success=None,
                oracle=True,
                by_construction=False,
            )
        rec["oracle_guard_d1"] = {"ok": guard.ok, "source": guard.source, "detail": guard.detail}
        rec["offline_valid"] = (
            not rec["validation_reasons"]
            and rec["reference_replay_d1"]["won"]
            and rec["identity_at_zero_on_env"]
            and rec["support_monotone_in_dose"]
            and guard.ok
        )
        out[task_id] = rec
        print(
            json.dumps({k: v for k, v in rec.items() if k not in ("failure_prefix",)}, default=str)[
                :600
            ],
            flush=True,
        )
    (oa.DOSSIER / "validation.json").write_text(
        json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8"
    )
    lines = [
        "# Oracle actuator offline validation (before the freeze; LLM-free; no current-policy call)\n",
        "| task | class / family | code sha | validation reasons | ref replay original / d=0 / d=1 (won, steps) | identity at 0 on env | support events on a failure prefix at d = 0.25 / 0.5 / 0.75 / 1 | monotone | expert under W(1) | offline valid |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t, r in out.items():

        def rr(k: str, r: dict[str, Any] = r) -> str:
            return f"{'won' if r[k]['won'] else 'lost'} {r[k]['n_steps']}"

        se = r["failure_prefix_support_events"]
        lines.append(
            f"| {t} | {r['class']} / {r['family']} | {r['code_sha256_16']} | {'; '.join(r['validation_reasons']) or '-'} | {rr('reference_replay_original')} / {rr('reference_replay_d0')} / {rr('reference_replay_d1')} (blocked {r['reference_replay_d1']['blocked_steps']}) | {r['identity_at_zero_on_env']} | {se['0.25']} / {se['0.5']} / {se['0.75']} / {se['1']} | {r['support_monotone_in_dose']} | {r['oracle_guard_d1']['source']} {r['oracle_guard_d1']['ok']} | {r['offline_valid']} |"
        )
    (oa.DOSSIER / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
