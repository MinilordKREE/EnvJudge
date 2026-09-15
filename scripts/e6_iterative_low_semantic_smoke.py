"""Paid D/I smoke for the frozen semantic-screened iterative LOW method.

No production method is changed. Prior smoke helpers supply only I/O and the exact sticky
physical cost transport; all artifacts, admission records and outcomes use this new namespace.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace

from aea.bracket import DoseEval
from aea.budget import Budget
from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.core.io import append_jsonl
from aea.designer import AssistFamily, Reference, ReferenceStep, serialize_low, task_goal
from aea.errors import ConfigError, InfraError
from aea.evaluate import Eval, evaluate
from aea.families import FamilyContext
from aea.io import TraceWriter
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.low_optimizer import iterative_messages, propose_low
from aea.rules_control import assist_bracket
from aea.semantic_low import LowPrivilegeScreen, ScreenedLowOptimizer, SemanticAdmissionError
from aea.semantic_privilege import SCREEN_VERSION
from aea.session import SESSION_LOCK
from aea.substrate import AeaSubstrate
from aea.witness import Solvable, solvable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_iterative_low_smoke as historical

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "e6-iterative-low-semantic-smoke"
EXP = ROOT / "experiments" / "alfworld_e6"
PREREG = EXP / "PREREG_ITERATIVE_LOW_SEMANTIC_SMOKE.md"
TASKS = (114, 115, 126, 129)
CAP_USD = 12.0
ADAPTATION_CAP = 20
MIN_USABLE_REFERENCES = 2
METHOD = "llm_v2_iterative_low_semantic_gate"
GATES = [
    "no_reference",
    "invalid / privilege_fail",
    "valid",
    "certified",
    "endpoint_too_hard",
    "endpoint_viable",
    "search_accepted",
    "K16_B_L",
    "K16_B_T",
]
jsonl = historical.jsonl
write_json = historical.write_json
digest = historical.digest
git = historical.git
cap_lock = historical.cap_lock
committed_cost = historical.committed_cost
CappedTransport = historical.CappedTransport
original_rollout_projection = historical.original_rollout_projection


def config() -> AEAConfig:
    return AEAConfig.model_validate({"method_version": METHOD})


def build() -> AeaSubstrate:
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    sub = AeaSubstrate(
        corpus_yaml=ROOT / "configs/corpus_aea.yaml",
        run_dir=RUN,
        run_id=RUN.name,
        policy_llm=e3.policy_qwen(),
        designer_llm=e3.designer_deepseek(),
        aea_config=config(),
        stage_config_path=e3.STAGE_CONFIG,
        pricing_path=e3.PRICING,
        rollout_concurrency=1,
        subprocess_timeout_s=600.0,
    )
    sub.policy_spec_kwargs["client_factory"] = "scripts.e6_iterative_low_smoke:CappedPolicyClient"
    sub.policy_spec_kwargs["client_kwargs"]["cap_path"] = str(RUN / "cap.json")
    assert sub._designer is not None
    sub._designer._transport = CappedTransport(sub._designer._transport, RUN / "cap.json")
    return sub


def read_reference(task: int) -> Reference:
    row = json.loads((RUN / f"task-{task}/privileged_reference.json").read_text())
    return Reference(
        bool(row["success"]),
        row["reason"],
        tuple(row["actions"]),
        tuple(
            ReferenceStep(s["step"], s["observation"], tuple(s["admissible"]), s["action"])
            for s in row["steps"]
        ),
    )


def ensure_frozen(implementation_sha: str) -> dict[str, Any]:
    driver_path = "scripts/e6_iterative_low_semantic_smoke.py"
    frozen_inputs = (
        "scripts/e3.py",
        "scripts/e6_iterative_low_smoke.py",
        "configs/pricing.yaml",
        "configs/corpus_aea.yaml",
        "configs/alfworld_config_100.yaml",
    )
    if not PREREG.exists() or implementation_sha not in PREREG.read_text():
        raise ConfigError("missing preregistration or implementation freeze")
    if git(
        "status",
        "--porcelain",
        "--",
        "src/aea",
        driver_path,
        str(PREREG.relative_to(ROOT)),
        *frozen_inputs,
    ):
        raise ConfigError("frozen method, driver or preregistration is dirty")
    source_tree = git("rev-parse", f"{implementation_sha}:src/aea")
    if source_tree != git("rev-parse", "HEAD:src/aea"):
        raise ConfigError("production source changed after the frozen implementation")
    if git("diff", implementation_sha, "--", *frozen_inputs):
        raise ConfigError("frozen policy, transport helper or substrate configuration changed")
    prereg_commit = git("log", "-1", "--format=%H", "--", str(PREREG.relative_to(ROOT)))
    current_driver = digest(Path(__file__).read_text())
    if not prereg_commit or current_driver not in PREREG.read_text():
        raise ConfigError("preregistration must freeze the exact driver SHA256")
    gate_hash = digest((ROOT / "src/aea/semantic_privilege.py").read_text())
    if SCREEN_VERSION != "alfworld-semantic-screen-v1" or gate_hash not in PREREG.read_text():
        raise ConfigError("semantic screen version/hash differs from preregistration")
    git("merge-base", "--is-ancestor", prereg_commit, "origin/aea-llm-vnext")
    frozen_manifest_hashes = {}
    for name in (
        "prepared.json",
        "pool_audit.json",
        "frozen_invariants.json",
        "scanned_files.json",
    ):
        relative = f"experiments/alfworld_e6/frozen/iterative_low_semantic_smoke/{name}"
        actual = (ROOT / relative).read_text()
        committed = git("show", f"{prereg_commit}:{relative}")
        if actual.strip() != committed.strip():
            raise ConfigError("frozen manifest differs from pushed preregistration: " + name)
        frozen_manifest_hashes[name] = digest(actual)
    if digest((RUN / "prepared.json").read_text()) != frozen_manifest_hashes["prepared.json"]:
        raise InfraError("run preparation differs from committed evidence", kind="frozen_evidence")
    return {
        "frozen_manifest_hashes": frozen_manifest_hashes,
        "implementation_sha": implementation_sha,
        "src_tree": source_tree,
        "prereg_commit": prereg_commit,
        "prereg_sha256": digest(PREREG.read_text()),
        "driver_sha256": current_driver,
        "semantic_gate_sha256": gate_hash,
        "semantic_gate_version": SCREEN_VERSION,
        "method_version": METHOD,
        "input_hashes": {name: digest((ROOT / name).read_text()) for name in frozen_inputs},
    }


def cost_check(where: str, projected: float = 0.0) -> None:
    with cap_lock(RUN / "cap.json") as state:
        total = committed_cost(state)
        if state.get("bound_violation"):
            raise ConfigError("monetary request bound violation")
        if state.get("stopped") or total + projected >= CAP_USD:
            raise InfraError(f"physical cost cap at {where}", kind="smoke_cost_cap")
    append_jsonl(
        RUN / "cost_checks.jsonl",
        {"where": where, "committed_usd": total, "projected_usd": projected},
    )


def require_pass(screen: LowPrivilegeScreen, family: AssistFamily, dose: float) -> None:
    try:
        screen.require_pass(family, dose)
    except SemanticAdmissionError as exc:
        raise ConfigError("semantic admission binding failed: " + str(exc)) from exc


def stage_for(row: dict[str, Any]) -> int:
    return historical.stage_for(row) + 1


def semantic_results(shared: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source = {
        row["result"]["source_sha256"]: row["result"] for row in shared["semantic_records"]
    }
    return [
        {"candidate_id": row["candidate_id"], "result": by_source.get(row["source_sha256"])}
        for row in records
    ]


def make_screen(sub: AeaSubstrate, task: int, shared: dict[str, Any]) -> LowPrivilegeScreen:
    failures = [
        Trace.model_validate(row)
        for row in json.loads((RUN / f"task-{task}/original_failures.json").read_text())
    ]
    ref = read_reference(task)
    evidence = serialize_low(failures, 0.0, 10, None)
    shared["semantic_records"] = []

    def record(row: dict[str, Any]) -> None:
        stamped = {
            "arm": shared["active_arm"],
            "optimizer_call_index": shared["active_call"],
            **row,
        }
        shared["semantic_records"].append(stamped)
        append_jsonl(RUN / f"task-{task}/semantic_gates.jsonl", stamped)

    return LowPrivilegeScreen(
        task_id=str(task),
        reference=ref,
        designer_evidence=evidence.text,
        failures=failures,
        goal=task_goal(failures),
        open_original_session=lambda: sub.open_session(TaskRef(str(task), task), None, None),
        max_bisections=config().impl.max_bisections,
        audit_dir=RUN / f"task-{task}/privileged_semantic_inputs",
        record=record,
        max_steps=config().impl.policy_max_steps,
        task_prompt=sub.task_prompt,
        action_format=str(sub.policy_spec_kwargs["action_format"]),
    )


def run_arm(sub: AeaSubstrate, task: int, arm: str, shared: dict[str, Any]) -> dict[str, Any]:
    """I input is freshly constructed from original Evidence; feedback is never redacted into I."""
    cfg = config()
    taskref = TaskRef(str(task), task)
    d = RUN / f"task-{task}" / arm
    d.mkdir(parents=True, exist_ok=True)
    failures = [
        Trace.model_validate(r)
        for r in json.loads((RUN / f"task-{task}" / "original_failures.json").read_text())
    ]
    reference = read_reference(task)
    evidence = serialize_low(failures, 0.0, 10, reference, rich=True)
    screen: LowPrivilegeScreen = shared["screen"]
    budget = Budget(ADAPTATION_CAP)
    call_index = 0
    writer = TraceWriter(d / "traces.jsonl")
    complete = sub.designer()
    assert complete is not None
    records: list[dict[str, Any]] = []

    def propose(feedback: Any, index: int) -> dict[str, Any]:
        nonlocal call_index
        call_index = index
        shared["active_arm"], shared["active_call"] = arm, index
        if arm == "I" and index == 1:
            return copy.deepcopy(shared["arguments"])
        previous_source = shared["source"] if arm == "I" and index == 2 else None
        visible_feedback = None if arm == "I" else feedback
        expected = iterative_messages(evidence, visible_feedback, previous_source=previous_source)

        def logged_complete(request: ChatRequest) -> ChatResponse:
            if request.messages != expected:
                raise ConfigError("designer request differs from independent construction")
            # Privileged input is kept separately; the public record carries hashes and provenance.
            append_jsonl(d / "privileged_designer_requests.jsonl", request.model_dump(mode="json"))
            append_jsonl(
                d / "designer_inputs.jsonl",
                {
                    "call_index": index,
                    "arm": arm,
                    "evidence_sha256": evidence.sha256,
                    "feedback_supplied": visible_feedback is not None,
                    "requested_operation": "INDEPENDENT_PROPOSAL"
                    if previous_source is not None
                    else (visible_feedback.operation if visible_feedback else "PROPOSE"),
                    "previous_source_sha256": digest(previous_source) if previous_source else None,
                    "request_sha256": digest(request.model_dump(mode="json")),
                    "independently_constructed_match": True,
                },
            )
            cost_check(f"designer task {task} {arm} C{index}")
            return complete(request)

        arguments = propose_low(
            logged_complete,
            model=sub.designer_model(),
            evidence=evidence,
            feedback=visible_feedback,
            previous_source=previous_source,
            attribution=Attribution(
                phase=f"design_low_{arm}_{index}", budget="designer", arm=arm, task_id=str(task)
            ),
            seed=task + index - 1,
        )
        append_jsonl(d / "proposals.jsonl", {"call_index": index, "arguments": arguments})
        if arm == "D" and index == 1:
            shared["arguments"] = copy.deepcopy(arguments)
        if visible_feedback is not None:
            append_jsonl(
                d / "feedback.jsonl",
                {
                    "call_index": index,
                    "feedback": asdict(feedback),
                    "C1_source_sha256": feedback.source_sha256,
                    "gate_input_sha256": [
                        row["result"]["input_sha256"]
                        for row in shared["semantic_records"]
                        if row["result"]["source_sha256"] == feedback.source_sha256
                    ],
                },
            )
        return arguments

    def certify(candidate: Candidate) -> Solvable:
        family = optimizer.current
        if family is None:
            raise ConfigError("certification has no admitted family")
        require_pass(screen, family, 1.0)
        expected = family.make(1.0, FamilyContext(str(task), ()))
        if expected is None or candidate.rules_code != expected.rules_code:
            raise ConfigError("certification candidate differs from admitted source")
        if arm == "I" and call_index == 1:
            return copy.deepcopy(shared["guard"])
        with SESSION_LOCK:
            result = solvable(
                candidate,
                lambda c: sub.open_session(taskref, c, None),
                cfg,
                policy_success=None,
                oracle=sub.has_oracle(),
                by_construction=False,
            )
        if arm == "D" and call_index == 1:
            shared["guard"] = copy.deepcopy(result)
        return result

    def measure(family: AssistFamily, dose: float) -> Eval:
        require_pass(screen, family, dose)
        if arm == "I" and call_index == 1:
            result = copy.deepcopy(shared["endpoint"])
            budget.charge(str(task), result.n, phase="shared_C1")
            for trace in result.traces:
                writer.add(trace)
            return result
        candidate = family.make(dose, FamilyContext(task_id=str(task), success_lengths=()))
        assert candidate is not None
        phase = f"{arm}:C{call_index}:dose:{dose}"

        def rollouts(n: int) -> list[Trace]:
            budget.charge(str(task), n, phase=phase)
            write_json(d / "rollout_budget.json", budget.accounting_rows())
            append_jsonl(d / "physical_batches.jsonl", {"phase": phase, "n": n})
            traces = sub.rollouts(
                taskref,
                candidate,
                n,
                attribution=Attribution(phase=phase, budget="search", arm=arm, task_id=str(task)),
            )
            for trace in traces:
                writer.add(trace)
            if len(traces) != n or any(trace.error for trace in traces):
                errors = "; ".join(str(trace.error) for trace in traces if trace.error)
                if "provider_mismatch" in errors or "pricing_mismatch" in errors:
                    raise ConfigError("policy provenance/accounting failure: " + errors)
                raise InfraError(
                    "incomplete/errored policy measurement: " + errors, kind="smoke_rollout"
                )
            return traces

        result = evaluate(rollouts, cfg)
        append_jsonl(
            d / "measurements.jsonl",
            {
                "call_index": call_index,
                "family": family.name,
                "d": dose,
                "s": result.successes,
                "n": result.n,
                "verdict": result.verdict,
                "candidate_hash": digest(candidate.rules_code),
            },
        )
        if arm == "D" and call_index == 1 and dose == 1:
            shared["endpoint"] = copy.deepcopy(result)
        return result

    class SharedCandidateOptimizer(ScreenedLowOptimizer):
        def _validate(self, arguments: dict[str, Any]) -> Any:
            if arm == "I" and call_index == 1:
                return copy.deepcopy(shared["validation"])
            validation = super()._validate(arguments)
            if arm == "D" and call_index == 1:
                shared["validation"] = copy.deepcopy(validation)
            return validation

    optimizer = SharedCandidateOptimizer(
        evidence,
        failures,
        reference,
        task_goal(failures),
        task_id=str(task),
        propose=propose,
        certify=certify,
        measure=measure,
        remaining=lambda: budget.account(str(task)).remaining(),
        endpoint_reserve=16,
        screen=screen.screen,
    )
    try:
        result = optimizer.run()
    finally:
        records = [record.as_record() for record in optimizer.history]
        write_json(d / "candidates.json", records)
    if result.status == "inconclusive" and "semantic_privilege_uncertain" not in result.reason:
        raise InfraError(result.reason, kind="smoke_infrastructure")
    if arm == "D" and records:
        shared["source"] = optimizer.history[0].source
        shared["c1"] = records[0]
    if arm == "I" and records and records[0] != shared["c1"]:
        raise ConfigError("shared C1 identity or gate results differ between arms")
    summary: dict[str, Any] = {
        "arm": arm,
        "status": result.status,
        "reason": result.reason,
        "designer_calls_logical": len(records),
        "designer_calls_physical": len(records) - (arm == "I"),
        "candidates": records,
        "gate": None
        if result.status == "inconclusive"
        else stage_for(records[-1])
        if records
        else 1,
        "semantic": semantic_results(shared, records),
        "search_accepted": False,
        "logical_rollouts": budget.account(str(task)).spent,
        "physical_rollouts": budget.account(str(task)).spent
        - (shared["endpoint"].n if arm == "I" and "endpoint" in shared else 0),
    }
    if result.status == "viable":
        family, endpoint = result.family, result.endpoint
        assert family is not None and endpoint is not None
        selected = DoseEval(1.0, endpoint) if endpoint.verdict == "in_band" else None
        if selected is None:
            control = assist_bracket(
                lambda dose: measure(family, dose), cfg, leverage=DoseEval(1.0, endpoint)
            )
            summary["control"] = {
                "status": control.status,
                "lo": control.lo,
                "hi": control.hi,
                "history": [
                    {"d": h.d, "s": h.eval.successes, "n": h.eval.n, "verdict": h.eval.verdict}
                    for h in control.history
                ],
            }
            selected = control.accepted
        if selected is not None:
            candidate = family.make(
                selected.d, FamilyContext(task_id=str(task), success_lengths=())
            )
            assert candidate is not None
            summary.update(
                search_accepted=True,
                gate=6,
                dose=selected.d,
                final_environment_hash=digest(candidate.rules_code),
                final_candidate=candidate.model_dump(),
                final_family=asdict(family),
            )
        summary["logical_rollouts"] = budget.account(str(task)).spent
        summary["physical_rollouts"] = summary["logical_rollouts"] - (
            shared["endpoint"].n if arm == "I" and "endpoint" in shared else 0
        )
    summary["gate_name"] = (
        GATES[summary["gate"]]
        if summary["gate"] is not None
        else (
            "SEMANTIC_UNCERTAIN"
            if "semantic_privilege_uncertain" in result.reason
            else "CERTIFICATION_INCONCLUSIVE"
        )
    )
    if records and records[-1]["rejection_reason"] == "duplicate source hash":
        summary["terminal_stage"] = "duplicate_candidate"
    assert summary["logical_rollouts"] <= ADAPTATION_CAP and len(records) <= 2
    write_json(d / "summary.json", summary)
    return summary


def confirm(sub: AeaSubstrate, task: int, arms: dict[str, Any], screen: LowPrivilegeScreen) -> None:
    seen: dict[tuple[str, float], dict[str, Any]] = {}
    for arm in ("D", "I"):
        summary = arms[arm]
        if not summary["search_accepted"]:
            continue
        family = AssistFamily(**summary["final_family"])
        dose = float(summary["dose"])
        require_pass(screen, family, dose)
        candidate = Candidate.model_validate(summary["final_candidate"])
        expected = family.make(dose, FamilyContext(str(task), ()))
        if expected is None or expected.rules_code != candidate.rules_code:
            raise ConfigError("confirmation environment differs from frozen admitted family")
        if digest(candidate.rules_code) != summary["final_environment_hash"]:
            raise ConfigError("confirmation environment identity corrupted")
        key = summary["final_environment_hash"], dose
        if key not in seen:
            cost_check(
                f"confirmation task {task} {arm}", projected=16 * original_rollout_projection()
            )
            traces = sub.rollouts(
                TaskRef(str(task), task),
                candidate,
                16,
                attribution=Attribution(
                    phase="confirm", budget="eval", arm=f"confirm-{arm}", task_id=str(task)
                ),
            )
            writer = TraceWriter(RUN / f"task-{task}/confirm-{key[0]}-{dose}.jsonl")
            for trace in traces:
                writer.add(trace)
            if len(traces) != 16 or any(trace.error for trace in traces):
                errors = "; ".join(str(trace.error) for trace in traces if trace.error)
                if "provider_mismatch" in errors or "pricing_mismatch" in errors:
                    raise ConfigError("confirmation provenance failure: " + errors)
                raise InfraError("incomplete K16: " + errors, kind="smoke_confirmation")
            successes = sum(bool(trace.success) for trace in traces)
            seen[key] = {
                "successes": successes,
                "n": 16,
                "in_band_l": config().band_l[0] <= successes / 16 <= config().band_l[1],
                "in_band_t": config().band_t[0] <= successes / 16 <= config().band_t[1],
                "environment_hash": key[0],
                "dose": dose,
                "physical_arm": arm,
            }
            write_json(RUN / f"task-{task}/confirm-{key[0]}-{dose}.json", seen[key])
        summary["confirmation"] = seen[key]
        summary["logical_confirmation_rollouts"] = 16
        summary["physical_confirmation_rollouts"] = 16 if seen[key]["physical_arm"] == arm else 0
        if seen[key]["in_band_t"]:
            summary.update(gate=8, gate_name=GATES[8])
        elif seen[key]["in_band_l"]:
            summary.update(gate=7, gate_name=GATES[7])


def unavailable(arm: str) -> dict[str, Any]:
    return {
        "arm": arm,
        "status": "reference_unavailable",
        "reason": "reference_unavailable",
        "gate": 0,
        "gate_name": GATES[0],
        "candidates": [],
        "semantic": [],
        "designer_calls_logical": 0,
        "designer_calls_physical": 0,
        "logical_rollouts": 0,
        "physical_rollouts": 0,
        "search_accepted": False,
    }


def verify_evidence(original: dict[str, Any]) -> None:
    task = int(original["task_id"])
    if task not in TASKS:
        raise InfraError("unexpected prepared task", kind="frozen_evidence")
    for filename, key in (
        ("original_failures.json", "evidence_sha256"),
        ("privileged_reference.json", "reference_sha256"),
    ):
        data = json.loads((RUN / f"task-{task}" / filename).read_text())
        if digest(data) != original[key] or original[key] not in PREREG.read_text():
            raise InfraError(f"frozen {filename} hash mismatch", kind="frozen_evidence")
    if original["reference_ok"]:
        ref = read_reference(task)
        if not ref.ok or not ref.steps or tuple(step.action for step in ref.steps) != ref.actions:
            raise InfraError("frozen rich reference is incomplete", kind="frozen_evidence")


def run(implementation_sha: str) -> None:
    freeze = ensure_frozen(implementation_sha)
    prepared = json.loads((RUN / "prepared.json").read_text())
    if tuple(int(row["task_id"]) for row in prepared) != TASKS:
        raise InfraError("prepared task set differs from preregistration", kind="frozen_evidence")
    if (RUN / "results.json").exists():
        raise ConfigError("new smoke already started; no implicit resume or rerun")
    with cap_lock(RUN / "cap.json") as state:
        if state["attempts"] or state["inflight"]:
            raise ConfigError("physical requests already exist in this run namespace")
    write_json(RUN / "freeze.json", freeze)
    results: dict[str, Any] = {"tasks": {}, "interruption": None, "freeze": freeze}
    try:
        for original in prepared:
            verify_evidence(original)
        if sum(row["reference_ok"] for row in prepared) < MIN_USABLE_REFERENCES:
            raise InfraError("fewer than two usable references", kind="smoke_reference_count")
        sub = build()
        for original in prepared:
            task = int(original["task_id"])
            ensure_frozen(implementation_sha)
            verify_evidence(original)
            row: dict[str, Any] = {
                "original": original,
                "arms": {},
                "c1": None,
                "c1_viable": False,
                "c1_failed": False,
            }
            results["tasks"][str(task)] = row
            if not original["reference_ok"]:
                row.update(
                    status="reference_unavailable",
                    arms={arm: unavailable(arm) for arm in ("D", "I")},
                )
                write_json(RUN / "results.json", results)
                continue
            cost_check(f"task {task}", projected=40 * original_rollout_projection() + 0.30)
            shared: dict[str, Any] = {}
            shared["screen"] = make_screen(sub, task, shared)
            d = run_arm(sub, task, "D", shared)
            row["arms"]["D"] = d
            row["c1"] = d["candidates"][0] if d["candidates"] else None
            row["c1_viable"] = bool(row["c1"] and stage_for(row["c1"]) >= 5)
            c1_uncertain = d["status"] == "inconclusive" and len(d["candidates"]) == 1
            row["c1_failed"] = bool(row["c1"] and not row["c1_viable"] and not c1_uncertain)
            if row["c1_viable"] or c1_uncertain:
                independent = copy.deepcopy(d)
                independent.update(
                    arm="I", physical_rollouts=0, designer_calls_physical=0, shared_C1_terminal=True
                )
            else:
                # D2 screening uncertainty cannot suppress I2's matched independent opportunity.
                independent = run_arm(sub, task, "I", shared)
            row["arms"]["I"] = independent
            write_json(RUN / "results.json", results)
            confirm(sub, task, row["arms"], shared["screen"])
            row["status"] = "completed"
            row["paired_ordinal"] = all(a["gate"] is not None for a in row["arms"].values())
            write_json(RUN / "results.json", results)
            print(
                json.dumps(
                    {
                        "task": task,
                        "D": d["gate_name"],
                        "I": independent["gate_name"],
                        "C1_viable": row["c1_viable"],
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        kind = getattr(exc, "kind", "implementation")
        if isinstance(exc, SemanticAdmissionError):
            kind = "implementation"
        results["interruption"] = {"type": type(exc).__name__, "kind": kind, "reason": str(exc)}
    finally:
        write_json(RUN / "results.json", results)
        report()


def decision_for(results: dict[str, Any], referenced: int, cap: dict[str, Any]) -> dict[str, Any]:
    completed = [row for row in results["tasks"].values() if row.get("status") == "completed"]
    paired = [row for row in completed if row["c1_failed"] and row.get("paired_ordinal")]
    better = sum(row["arms"]["D"]["gate"] > row["arms"]["I"]["gate"] for row in paired)
    worse = sum(row["arms"]["D"]["gate"] < row["arms"]["I"]["gate"] for row in paired)
    improved = {
        arm: sum(
            len(row["arms"][arm]["candidates"]) == 2
            and row["arms"][arm]["gate"] > stage_for(row["c1"])
            for row in completed
            if row["c1_failed"] and row["arms"][arm]["gate"] is not None
        )
        for arm in ("D", "I")
    }
    confirmed = {
        arm: sum(
            row["arms"][arm].get("confirmation", {}).get("in_band_l", False) for row in completed
        )
        for arm in ("D", "I")
    }
    interruption = results.get("interruption")
    correctness = results.get("correctness_audit", {})
    outcome = "NO_FEEDBACK_SIGNAL"
    if (
        cap.get("bound_violation")
        or correctness.get("decision") == "IMPLEMENTATION_FAILURE"
        or (
            interruption
            and interruption["kind"]
            in ("implementation", "smoke_bound_error", "provider_mismatch", "pricing_mismatch")
        )
    ):
        outcome = "IMPLEMENTATION_FAILURE"
    elif referenced < MIN_USABLE_REFERENCES or interruption or len(completed) < referenced:
        outcome = "INCONCLUSIVE"
    elif confirmed["D"] >= 1 and better >= 1 and worse <= better:
        outcome = "ITERATIVE_LOW_STRONG_SIGNAL"
    elif improved["D"] >= 2 and better >= 1 and worse <= better:
        outcome = "ITERATIVE_LOW_SIGNAL"
    return {
        "decision": outcome,
        "primary_denominator": 4,
        "referenced_denominator": referenced,
        "completed_referenced_tasks": len(completed),
        "C1_failed_ordinal_pairs": len(paired),
        "D_better_I": better,
        "D_worse_I": worse,
        "ties": len(paired) - better - worse,
        "C2_improves_C1": improved,
        "K16_BL": confirmed,
        "unranked_tasks": [
            row["original"]["task_id"] for row in completed if not row.get("paired_ordinal")
        ],
        "interruption": interruption,
    }


def report() -> dict[str, Any]:
    results = json.loads((RUN / "results.json").read_text())
    prepared = json.loads((RUN / "prepared.json").read_text())
    cap = json.loads((RUN / "cap.json").read_text())
    if (RUN / "correctness_audit.json").exists():
        results["correctness_audit"] = json.loads((RUN / "correctness_audit.json").read_text())
    summary = decision_for(results, sum(row["reference_ok"] for row in prepared), cap)
    ledger = [row for path in RUN.glob("ledger.*.jsonl") for row in jsonl(path)]
    calls = [row for row in ledger if row.get("event") == "call"]
    costs = {}
    for task, row in results["tasks"].items():
        selected = [call for call in calls if str(call["task_id"]) == task]
        own = {
            arm: sum(float(call["usd"] or 0) for call in selected if call["arm"] == arm)
            for arm in ("D", "I")
        }
        c1 = sum(
            float(call["usd"] or 0)
            for call in selected
            if call["phase"] == "design_low_D_1" or str(call["phase"]).startswith("D:C1:")
        )
        logical = {"D": own["D"], "I": own["D"] if row.get("c1_viable") else own["I"] + c1}
        for arm, arm_result in row["arms"].items():
            confirmation = arm_result.get("confirmation")
            if confirmation:
                logical[arm] += sum(
                    float(call["usd"] or 0)
                    for call in selected
                    if call["arm"] == "confirm-" + confirmation["physical_arm"]
                )
        batches = {
            arm: jsonl(RUN / f"task-{task}/{arm}/physical_batches.jsonl") for arm in ("D", "I")
        }
        requested = {arm: sum(batch["n"] for batch in batches[arm]) for arm in ("D", "I")}
        shared_requested = sum(
            batch["n"] for batch in batches["D"] if batch["phase"].startswith("D:C1:")
        )
        designer_requests = {
            arm: len(jsonl(RUN / f"task-{task}/{arm}/designer_inputs.jsonl")) for arm in ("D", "I")
        }
        costs[task] = {
            "physical_requested_adaptation_rollouts": requested,
            "shared_C1_requested_rollouts": shared_requested,
            "logical_requested_adaptation_rollouts": {
                "D": requested["D"],
                "I": requested["D"] if row.get("c1_viable") else requested["I"] + shared_requested,
            },
            "physical_designer_requests": designer_requests,
            "logical_designer_requests": {
                "D": designer_requests["D"],
                "I": designer_requests["I"] + int(designer_requests["D"] > 0),
            },
            "physical_usd": sum(float(call["usd"] or 0) for call in selected),
            "shared_C1_usd": c1,
            "logical_per_arm_usd": logical,
        }
    semantic = [row for task in TASKS for row in jsonl(RUN / f"task-{task}/semantic_gates.jsonl")]
    summary.update(
        semantic_gate_counts={
            decision: sum(row["result"]["decision"] == decision for row in semantic)
            for decision in ("PASS", "FAIL", "UNCERTAIN")
        },
        physical_policy_usd=sum(
            float(row["usd"] or 0) for row in calls if row["budget"] == "search"
        ),
        physical_designer_usd=sum(
            float(row["usd"] or 0) for row in calls if row["budget"] == "designer"
        ),
        physical_confirmation_usd=sum(
            float(row["usd"] or 0) for row in calls if row["budget"] == "eval"
        ),
        physical_total_usd=sum(float(row["usd"] or 0) for row in calls),
        conservative_failed_request_reservation=cap["uncertain_usd"],
        conservative_cap_account=cap,
        cost_by_task=costs,
    )
    write_json(RUN / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("run", "report"), required=True)
    parser.add_argument("--implementation-sha")
    args = parser.parse_args()
    if args.stage == "report":
        report()
    else:
        if not args.implementation_sha:
            parser.error("run requires the preregistered --implementation-sha")
        run(args.implementation_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
