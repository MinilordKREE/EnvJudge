"""Preregistered four-task iterative LOW D/I smoke; all paid work is explicit --stage run.

The experiment-only transport accounts for every physical HTTP attempt, including retries.
Production DESIGN, certification, evaluation and CONTROL are imported without modification.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
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
from aea.llm.envharness_client import AeaLLMClient
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.low_optimizer import LowEnvironmentOptimizer, iterative_messages, propose_low
from aea.rules_control import assist_bracket
from aea.session import SESSION_LOCK
from aea.stage import seeded_failures
from aea.substrate import AeaSubstrate
from aea.witness import Solvable, solvable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "e6-iterative-low-smoke"
EXP = ROOT / "experiments" / "alfworld_e6"
PREREG = EXP / "PREREG_ITERATIVE_LOW_SMOKE.md"
POOL = EXP / "frozen" / "low_pool3_k16.jsonl"
ORIGINAL_TRACES = ROOT / "runs" / "e6-pool3-k16" / "confirm.jsonl"
CAP_USD = 12.0
ADAPTATION_CAP = 20
MIN_USABLE_REFERENCES = 2
# Peak, uncached rates in the frozen pricing table. Returned upstream cost is also checked.
RATES = {"qwen/qwen3-8b": (0.117, 0.455), "deepseek-v4-pro": (1.32, 3.96)}
GATES = [
    "invalid",
    "valid",
    "certified",
    "endpoint too_hard",
    "endpoint viable",
    "search accepted",
    "K16-confirmed B_L",
]


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def audit_pool() -> dict[str, Any]:
    """Derive unused ZERO tasks from frozen classifications and actual adaptation events."""
    zero = {
        int(row["task_id"])
        for row in jsonl(POOL)
        if row["n"] == 16 and row["errors"] == 0 and row["successes"] == 0
    }
    used: set[int] = set()
    sources = []
    for base in (ROOT / "runs", EXP / "results"):
        for path in sorted(base.glob("**/events.jsonl")):
            if path.is_relative_to(RUN) or "pool3" in str(path):
                continue
            found = set()
            for row in jsonl(path):
                value = row.get("payload", row).get("task_id")
                if value is not None and str(value).isdigit() and int(value) in zero:
                    found.add(int(value))
            if found:
                used.update(found)
                sources.append({"path": str(path.relative_to(ROOT)), "tasks": sorted(found)})
    unused = sorted(zero - used)
    if len(unused) < 5:
        raise ConfigError("fewer than five untouched confirmed-zero tasks; no new screening")
    return {
        "zero": sorted(zero),
        "used": sorted(used),
        "unused": unused,
        "selected": unused[:4],
        "held_out": unused[4:],
        "sources": sources,
        "pool_sha256": digest(POOL.read_text()),
        "original_trace_file_sha256": digest(ORIGINAL_TRACES.read_text()),
    }


@contextmanager
def cap_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = (
            json.loads(path.read_text())
            if path.exists()
            else {
                "actual_usd": 0.0,
                "uncertain_usd": 0.0,
                "inflight": {},
                "attempts": 0,
            }
        )
        yield state
        write_json(path, state)
        fcntl.flock(lock, fcntl.LOCK_UN)


def committed_cost(state: dict[str, Any]) -> float:
    return float(state["actual_usd"] + state["uncertain_usd"] + sum(state["inflight"].values()))


class CappedTransport:
    """Guard the actual transport, so retries cannot bypass the shared USD ceiling.

    Prompt upper bound: UTF-8 bytes of the entire serialized wire + 4096 protocol tokens.
    Output upper bound: request max_tokens; thinking is disabled. Rates use the frozen peak,
    uncached table. An ambiguous failed attempt keeps its entire reservation as uncertain.
    """

    def __init__(self, transport: Callable[..., Any], cap_path: Path) -> None:
        self.transport = transport
        self.cap_path = cap_path

    def __call__(self, **wire: Any) -> Any:
        model = str(wire["model"])
        inp, out = RATES[model]
        input_bound = len(json.dumps(wire, ensure_ascii=False).encode()) + 4096
        output_bound = int(wire.get("max_tokens") or wire.get("max_completion_tokens") or 0)
        if output_bound <= 0:
            raise ConfigError("unbounded output request refused")
        reserve = (input_bound * inp + output_bound * out) / 1_000_000
        attempt = uuid.uuid4().hex
        stopped = ""
        with cap_lock(self.cap_path) as state:
            if state.get("bound_violation"):
                state["stopped"] = "bound_violation"
            if state.get("stopped"):
                stopped = str(state["stopped"])
            elif committed_cost(state) + reserve >= CAP_USD:
                state["stopped"] = stopped = "cost_cap"
            else:
                state["inflight"][attempt] = reserve
                state["attempts"] += 1
        if stopped:
            kind = "smoke_bound_error" if stopped == "bound_violation" else "smoke_cost_cap"
            raise InfraError(f"physical API calls stopped: {stopped}", kind=kind)
        started = time.time()
        try:
            completion = self.transport(**wire)
        except BaseException:
            with cap_lock(self.cap_path) as state:
                state["uncertain_usd"] += state["inflight"].pop(attempt)
            append_jsonl(
                self.cap_path.with_suffix(".attempts.jsonl"),
                {
                    "attempt": attempt,
                    "model": model,
                    "status": "ambiguous_failure",
                    "reserved_usd": reserve,
                    "started": started,
                },
            )
            raise
        usage = completion.usage
        tokens_in = int(usage.prompt_tokens) if usage else input_bound
        tokens_out = int(usage.completion_tokens) if usage else output_bound
        # The conservative token-price value upper-bounds cache and off-peak discounts.
        upper_actual = (tokens_in * inp + tokens_out * out) / 1_000_000
        upstream = getattr(usage, "cost", None) if usage else None
        actual = max(float(upstream or 0), upper_actual)
        violation = tokens_in > input_bound or tokens_out > output_bound or actual > reserve + 1e-9
        with cap_lock(self.cap_path) as state:
            state["inflight"].pop(attempt)
            state["actual_usd"] += actual
            if violation:
                state["bound_violation"] = True
                state["stopped"] = "bound_violation"
        append_jsonl(
            self.cap_path.with_suffix(".attempts.jsonl"),
            {
                "attempt": attempt,
                "model": model,
                "status": "returned",
                "started": started,
                "reserved_usd": reserve,
                "conservative_usd": actual,
                "upstream_usd": upstream,
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
            },
        )
        if violation:
            raise InfraError("request exceeded conservative cost bound", kind="smoke_bound_error")
        return completion


class CappedPolicyClient(AeaLLMClient):
    """Experiment-only factory used by the unchanged subprocess policy runner."""

    def __init__(self, *, cap_path: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client._transport = CappedTransport(self._client._transport, Path(cap_path))


def config() -> AEAConfig:
    return AEAConfig.model_validate({"method_version": "llm_v2_iterative_low"})


def build(*, paid: bool) -> AeaSubstrate:
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    RUN.mkdir(parents=True, exist_ok=True)
    sub = AeaSubstrate(
        corpus_yaml=ROOT / "configs" / "corpus_aea.yaml",
        run_dir=RUN,
        run_id=RUN.name,
        policy_llm=e3.policy_qwen(),
        designer_llm=e3.designer_deepseek() if paid else None,
        aea_config=config(),
        stage_config_path=e3.STAGE_CONFIG,
        pricing_path=e3.PRICING,
        rollout_concurrency=1,
        subprocess_timeout_s=600.0,
    )
    sub.policy_spec_kwargs["client_factory"] = "scripts.e6_iterative_low_smoke:CappedPolicyClient"
    sub.policy_spec_kwargs["client_kwargs"]["cap_path"] = str(RUN / "cap.json")
    if sub._designer is not None:
        sub._designer._transport = CappedTransport(sub._designer._transport, RUN / "cap.json")
    return sub


def prepare() -> None:
    """Read frozen evidence; generate exactly one local expert reference per selected task."""
    if (RUN / "prepared.json").exists():
        print((RUN / "prepared.json").read_text())
        return
    audit = audit_pool()
    write_json(RUN / "pool_audit.json", audit)
    all_traces = jsonl(ORIGINAL_TRACES)
    sub = build(paid=False)
    provider = sub.reference_provider(config())
    assert provider is not None
    prepared = []
    for task in audit["selected"]:
        rows = [r for r in all_traces if str(r["rollout_seed"]) == str(task)]
        assert len(rows) == 16 and all(not r["success"] and not r["error"] for r in rows)
        first = [Trace.model_validate(r) for r in rows[:10]]
        failures = seeded_failures(first, config().impl.n_failed_rollouts, seed=task)
        assert len(failures) == 3 and all(t.steps for t in failures)
        ref_path = RUN / f"task-{task}" / "privileged_reference.json"
        if ref_path.exists():
            raw_ref = json.loads(ref_path.read_text())
        else:
            ref = provider(TaskRef(str(task), task))
            raw_ref = ref.as_record()
            if raw_ref["success"] and (
                not raw_ref["steps"]
                or [step["action"] for step in raw_ref["steps"]] != raw_ref["actions"]
            ):
                raw_ref["success"], raw_ref["reason"] = False, "rich_reference_unavailable"
            write_json(ref_path, raw_ref)
        write_json(
            RUN / f"task-{task}" / "original_failures.json", [t.model_dump() for t in failures]
        )
        prepared.append(
            {
                "task_id": str(task),
                "original_k16": "0/16",
                "evidence_n": 10,
                "evidence_ids": [t.episode_id for t in failures],
                "evidence_source": str(ORIGINAL_TRACES),
                "evidence_sha256": digest([t.model_dump() for t in failures]),
                "reference_ok": raw_ref["success"],
                "reference_reason": raw_ref["reason"],
                "reference_id": raw_ref["reference_id"],
                "reference_sha256": digest(raw_ref),
                "reference_steps": raw_ref["n_steps"],
                "fresh_original_rollouts": 0,
            }
        )
        print(json.dumps(prepared[-1]), flush=True)
    write_json(RUN / "prepared.json", prepared)


def read_reference(task: int) -> Reference:
    row = json.loads((RUN / f"task-{task}" / "privileged_reference.json").read_text())
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
    if not PREREG.exists():
        raise ConfigError("missing preregistration")
    prereg_commit = git("log", "-1", "--format=%H", "--", str(PREREG.relative_to(ROOT)))
    if not prereg_commit or implementation_sha not in PREREG.read_text():
        raise ConfigError("preregistration does not record the implementation SHA")
    if git("status", "--porcelain", "--", "src/aea", str(PREREG.relative_to(ROOT))):
        raise ConfigError("production code or preregistration is dirty")
    old = git("rev-parse", f"{implementation_sha}:src/aea")
    current = git("rev-parse", "HEAD:src/aea")
    if old != current:
        raise ConfigError("production source changed after implementation freeze")
    frozen_inputs = (
        "scripts/e3.py",
        "configs/pricing.yaml",
        "configs/corpus_aea.yaml",
        "configs/alfworld_config_100.yaml",
    )
    if git("diff", implementation_sha, "--", *frozen_inputs):
        raise ConfigError("policy, pricing or experiment substrate changed after freeze")
    return {
        "frozen_input_hashes": {name: digest((ROOT / name).read_text()) for name in frozen_inputs},
        "implementation_sha": implementation_sha,
        "src_tree": old,
        "prereg_commit": prereg_commit,
        "prereg_sha256": digest(PREREG.read_text()),
        "driver_sha256": digest(Path(__file__).read_text()),
        "head": git("rev-parse", "HEAD"),
    }


def cost_check(where: str, projected: float = 0.0) -> None:
    with cap_lock(RUN / "cap.json") as state:
        total = committed_cost(state)
        if state.get("bound_violation"):
            raise ConfigError("monetary reservation bound failed")
        if total + projected >= CAP_USD:
            raise InfraError(f"USD12 cap at {where}", kind="smoke_cost_cap")
    append_jsonl(
        RUN / "cost_checks.jsonl",
        {"where": where, "committed_usd": total, "projected_usd": projected},
    )


def original_rollout_projection() -> float:
    """Frozen historical mean for planning only; transport reservations enforce the hard cap."""
    return 37.754917694 / 800


def stage_for(row: dict[str, Any]) -> int:
    """Stage reached by THIS candidate (a failed C2 may regress below C1)."""
    if row.get("rejection_reason") == "duplicate source hash":
        return 0
    endpoint = row.get("endpoint")
    if endpoint:
        return 3 if endpoint[2] == "too_hard" else 4
    solvability = row.get("solvability")
    if solvability and json.loads(solvability).get("ok"):
        return 2
    if not row.get("structural") and not row.get("privilege"):
        return 1
    return 0


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
    budget = Budget(ADAPTATION_CAP)
    call_index = 0
    writer = TraceWriter(d / "traces.jsonl")
    complete = sub.designer()
    assert complete is not None
    records: list[dict[str, Any]] = []

    def propose(feedback: Any, index: int) -> dict[str, Any]:
        nonlocal call_index
        call_index = index
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
            append_jsonl(d / "feedback.jsonl", {"call_index": index, "feedback": asdict(feedback)})
        return arguments

    def certify(candidate: Candidate) -> Solvable:
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

    class SharedCandidateOptimizer(LowEnvironmentOptimizer):
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
    )
    try:
        result = optimizer.run()
    finally:
        records = [record.as_record() for record in optimizer.history]
        write_json(d / "candidates.json", records)
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
        "gate": stage_for(records[-1]) if records else 0,
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
                gate=5,
                dose=selected.d,
                final_environment_hash=digest(candidate.rules_code),
                final_candidate=candidate.model_dump(),
            )
        summary["logical_rollouts"] = budget.account(str(task)).spent
        summary["physical_rollouts"] = summary["logical_rollouts"] - (
            shared["endpoint"].n if arm == "I" and "endpoint" in shared else 0
        )
    summary["gate_name"] = GATES[summary["gate"]]
    assert summary["logical_rollouts"] <= ADAPTATION_CAP and len(records) <= 2
    write_json(d / "summary.json", summary)
    return summary


def confirm(sub: AeaSubstrate, task: int, arms: dict[str, Any]) -> None:
    seen: dict[str, Any] = {}
    for arm in ("D", "I"):
        summary = arms[arm]
        if not summary["search_accepted"]:
            continue
        key = summary["final_environment_hash"]
        if key not in seen:
            # Frozen historical episode cost projects the full K16; each request is also capped.
            cost_check(
                f"confirmation task {task} {arm}", projected=16 * original_rollout_projection()
            )
            candidate = Candidate.model_validate(summary["final_candidate"])
            traces = sub.rollouts(
                TaskRef(str(task), task),
                candidate,
                16,
                attribution=Attribution(
                    phase="confirm", budget="eval", arm=f"confirm-{arm}", task_id=str(task)
                ),
            )
            writer = TraceWriter(RUN / f"task-{task}" / f"confirm-{key}.jsonl")
            for trace in traces:
                writer.add(trace)
            if len(traces) != 16 or any(trace.error for trace in traces):
                errors = "; ".join(str(trace.error) for trace in traces if trace.error)
                if "provider_mismatch" in errors or "pricing_mismatch" in errors:
                    raise ConfigError("confirmation provenance/accounting failure: " + errors)
                raise InfraError("K16 incomplete/errored: " + errors, kind="smoke_confirmation")
            successes = sum(bool(trace.success) for trace in traces)
            seen[key] = {
                "successes": successes,
                "n": 16,
                "in_band_l": config().band_l[0] <= successes / 16 <= config().band_l[1],
                "environment_hash": key,
                "physical_arm": arm,
            }
            write_json(RUN / f"task-{task}" / f"confirm-{key}.json", seen[key])
        summary["confirmation"] = seen[key]
        summary["logical_confirmation_rollouts"] = 16
        summary["physical_confirmation_rollouts"] = 16 if seen[key]["physical_arm"] == arm else 0
        if seen[key]["in_band_l"]:
            summary.update(gate=6, gate_name=GATES[6])


def run(implementation_sha: str) -> None:
    freeze = ensure_frozen(implementation_sha)
    prepared = json.loads((RUN / "prepared.json").read_text())
    audit = json.loads((RUN / "pool_audit.json").read_text())
    if [int(row["task_id"]) for row in prepared] != audit["selected"]:
        raise ConfigError("prepared task list does not match frozen selection")
    write_json(RUN / "freeze.json", freeze)
    cap_path = RUN / "cap.json"
    prior_attempts = json.loads(cap_path.read_text()).get("attempts", 0) if cap_path.exists() else 0
    if (RUN / "results.json").exists() or prior_attempts or jsonl(RUN / "cap.attempts.jsonl"):
        raise ConfigError("paid smoke already started; no implicit rerun/resume")
    with cap_lock(RUN / "cap.json"):
        pass
    sub = build(paid=True)
    results: dict[str, Any] = {"tasks": {}, "interruption": None, "freeze": freeze}
    try:
        if sum(row["reference_ok"] for row in prepared) < MIN_USABLE_REFERENCES:
            raise InfraError(
                "fewer than two usable frozen references", kind="smoke_reference_count"
            )
        for original in prepared:
            task = int(original["task_id"])
            frozen_failure_rows = json.loads(
                (RUN / f"task-{task}" / "original_failures.json").read_text()
            )
            frozen_reference = json.loads(
                (RUN / f"task-{task}" / "privileged_reference.json").read_text()
            )
            if (
                digest(frozen_failure_rows) != original["evidence_sha256"]
                or digest(frozen_reference) != original["reference_sha256"]
            ):
                raise ConfigError("frozen evidence/reference changed")
            ensure_frozen(implementation_sha)
            cost_check(f"task {task}", projected=40 * original_rollout_projection() + 0.30)
            task_result: dict[str, Any] = {"original": original, "arms": {}}
            results["tasks"][str(task)] = task_result
            if not original["reference_ok"]:
                task_result["status"] = "reference_unavailable"
                write_json(RUN / "results.json", results)
                continue
            shared: dict[str, Any] = {}
            d = run_arm(sub, task, "D", shared)
            task_result["arms"]["D"] = d
            c1 = d["candidates"][0] if d["candidates"] else None
            task_result["c1"] = c1
            task_result["c1_viable"] = bool(c1 and stage_for(c1) >= 4)
            if task_result["c1_viable"]:
                independent = copy.deepcopy(d)
                independent.update(
                    arm="I",
                    physical_rollouts=0,
                    designer_calls_physical=0,
                    shared_viable_result=True,
                )
            elif d["status"] == "inconclusive":
                task_result["status"] = "inconclusive"
                raise InfraError(d["reason"], kind="smoke_design_inconclusive")
            else:
                independent = run_arm(sub, task, "I", shared)
            task_result["arms"]["I"] = independent
            if independent["status"] == "inconclusive":
                task_result["status"] = "inconclusive"
                raise InfraError(independent["reason"], kind="smoke_design_inconclusive")
            write_json(RUN / "results.json", results)
            confirm(sub, task, task_result["arms"])
            task_result["status"] = "completed"
            write_json(RUN / "results.json", results)
            print(
                json.dumps(
                    {
                        "task": task,
                        "D": d["gate_name"],
                        "I": independent["gate_name"],
                        "C1_viable": task_result["c1_viable"],
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        results["interruption"] = {
            "type": type(exc).__name__,
            "reason": str(exc),
            "kind": getattr(exc, "kind", "implementation"),
        }
    finally:
        write_json(RUN / "results.json", results)
        report()


def report() -> dict[str, Any]:
    results = json.loads((RUN / "results.json").read_text())
    prepared = json.loads((RUN / "prepared.json").read_text())
    rows = results["tasks"].values()
    paired = [r for r in rows if r.get("status") == "completed" and len(r["arms"]) == 2]
    better = sum(r["arms"]["D"]["gate"] > r["arms"]["I"]["gate"] for r in paired)
    worse = sum(r["arms"]["D"]["gate"] < r["arms"]["I"]["gate"] for r in paired)
    improved = sum(
        not r["c1_viable"]
        and len(r["arms"]["D"]["candidates"]) == 2
        and r["arms"]["D"]["gate"] > stage_for(r["c1"])
        for r in paired
    )
    confirmed = sum(r["arms"]["D"].get("confirmation", {}).get("in_band_l", False) for r in paired)
    interruption = results.get("interruption")
    decision = "NO_FEEDBACK_SIGNAL"
    if interruption and interruption["kind"] in (
        "implementation",
        "smoke_bound_error",
        "provider_mismatch",
        "pricing_mismatch",
    ):
        decision = "IMPLEMENTATION_FAILURE"
    elif sum(p["reference_ok"] for p in prepared) < MIN_USABLE_REFERENCES or interruption:
        decision = "INCONCLUSIVE"
    elif improved >= 2 and better >= 1 and worse <= better:
        decision = "ITERATIVE_LOW_STRONG_SIGNAL" if confirmed else "ITERATIVE_LOW_SIGNAL"
    cap = json.loads((RUN / "cap.json").read_text())
    audit_path = RUN / "correctness_audit.json"
    correctness_audit = json.loads(audit_path.read_text()) if audit_path.exists() else None
    if cap.get("bound_violation") or (
        correctness_audit and correctness_audit.get("decision") == "IMPLEMENTATION_FAILURE"
    ):
        decision = "IMPLEMENTATION_FAILURE"
    ledger = [row for path in RUN.glob("ledger.*.jsonl") for row in jsonl(path)]
    physical_by_task = {}
    for task_id, task_result in results["tasks"].items():
        calls = [
            row for row in ledger if row.get("event") == "call" and str(row["task_id"]) == task_id
        ]
        own = {
            arm: sum(float(row["usd"] or 0) for row in calls if row["arm"] == arm)
            for arm in ("D", "I")
        }
        shared_c1 = sum(
            float(row["usd"] or 0)
            for row in calls
            if row["phase"] == "design_low_D_1" or str(row["phase"]).startswith("D:C1:")
        )
        logical = {"D": own["D"], "I": own["I"] + shared_c1}
        if task_result.get("c1_viable"):
            logical["I"] = own["D"]
        confirm_cost = {
            arm: sum(float(row["usd"] or 0) for row in calls if row["arm"] == f"confirm-{arm}")
            for arm in ("D", "I")
        }
        for arm, arm_result in task_result["arms"].items():
            conf = arm_result.get("confirmation")
            if conf:
                logical[arm] += confirm_cost[conf["physical_arm"]]
        physical_by_task[task_id] = {
            "physical_usd": sum(float(row["usd"] or 0) for row in calls),
            "logical_per_arm_usd": logical,
            "shared_c1_usd": shared_c1,
            "physical_designer_calls": sum(row["budget"] == "designer" for row in calls),
            "physical_policy_calls": sum(row["budget"] != "designer" for row in calls),
        }
    summary = {
        "correctness_audit": correctness_audit,
        "cost_by_task": physical_by_task,
        "decision": decision,
        "primary_denominator": 4,
        "completed_pairs": len(paired),
        "D_C2_improves_C1": improved,
        "D_better_I": better,
        "D_worse_I": worse,
        "ties": len(paired) - better - worse,
        "D_K16_BL": confirmed,
        "physical_ledger_usd": sum(
            float(row.get("usd") or 0) for row in ledger if row.get("event") == "call"
        ),
        "conservative_cap_account": cap,
        "interruption": interruption,
    }
    write_json(RUN / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("audit", "prepare", "run", "report"), required=True)
    parser.add_argument("--implementation-sha")
    args = parser.parse_args()
    if args.stage == "audit":
        print(json.dumps(audit_pool(), indent=2))
    elif args.stage == "prepare":
        prepare()
    elif args.stage == "report":
        report()
    else:
        if not args.implementation_sha:
            parser.error("run requires --implementation-sha")
        run(args.implementation_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
