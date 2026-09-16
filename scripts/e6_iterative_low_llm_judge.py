"""Frozen LLM-judge validation and two-task LOW engineering acceptance.

Only prepare runs local archived-action replay. No original screening or reference
generation is available. Validation and engineering have separate physical caps.
"""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import math
import os
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from envharness.core.types import Candidate, Trace

import aea.low_optimizer as optimizer_module
from aea.bracket import DoseEval
from aea.budget import Budget
from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.core.io import append_jsonl
from aea.designer import AssistFamily, Reference, ReferenceStep, serialize_low, task_goal
from aea.errors import ConfigError, InfraError
from aea.evaluate import Eval, evaluate
from aea.families import FamilyContext
from aea.llm.attribution import attributed, current_attribution
from aea.llm.client import OpenAICompatibleClient, make_openai_transport
from aea.llm.envharness_client import AeaLLMClient
from aea.llm.ledger import Ledger
from aea.llm.pricing import load_pricing
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.llm_privilege_low import JudgedLowOptimizer, LLMLowPrivilegeScreen, compact_low_input
from aea.low_optimizer import Feedback, iterative_messages, propose_low
from aea.privilege_judge import JudgeConfig, LLMPrivilegeJudge, PrivilegeJudgeInput, canonical_json
from aea.privilege_surfaces import ReplayEpisode, capture_episode, probe_template
from aea.rules_control import assist_bracket
from aea.semantic_low import SemanticAdmissionError, reachable_screen_doses
from aea.session import SESSION_LOCK
from aea.settings import load_settings
from aea.stage import trace_actions
from aea.substrate import AeaSubstrate
from aea.witness import Solvable, solvable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_iterative_low_smoke as historical
import semantic_privilege_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/e6-iterative-low-llm-judge"
PRIVATE = BASE / "private"
RUN = PRIVATE / "engineering"
VALIDATION = PRIVATE / "validation"
EXP = ROOT / "experiments/alfworld_e6"
FROZEN = EXP / "frozen/iterative_low_llm_judge"
VALIDATION_PREREG = EXP / "PREREG_ITERATIVE_LOW_LLM_JUDGE_VALIDATION.md"
PREREG = EXP / "PREREG_ITERATIVE_LOW_LLM_JUDGE_ENGINEERING.md"
PRIOR = ROOT / "runs/e6-iterative-low-viability-v3"
PRIOR_MANIFEST = EXP / "frozen/iterative_low_viability_v3/input_manifest.json"
PRIOR_MANIFEST_SHA = "ad6019cff5b1ee1712e892404cefd5eb2813f032341e322de782f277d8ada46d"
BASE_DRIVER_SHA = "980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33"
METHOD = "llm_v2_iterative_low_llm_judge"
ARM = "iterative_low_llm_judge"
TASKS = (154, 159)
DESIGNER_CALL_CAP = 3
ADAPTATION_CAP = 30
STAGE_LIMITS = {"validation": 3.0, "engineering": 8.0}
RATES = {**historical.RATES, "deepseek-v4-flash": (0.44, 1.32)}
REPEAT_CASES = (
    "archived_task110",
    "publicly_observed_location",
    "generic_prerequisite",
    "direct_reference_route",
)
EXPECTED_CASES = {
    "archived_task110": "FAIL",
    "publicly_observed_location": "PASS",
    "generic_prerequisite": "PASS",
    "hidden_location_ranking": "FAIL",
    "hidden_location_filtering": "FAIL",
    "hidden_transition_feedback": "FAIL",
    "delayed_location_ranking": "FAIL",
    "dose_activated_location": "FAIL",
    "goal_only_emphasis": "PASS",
    "direct_reference_route": "FAIL",
    "historical_failure_not_public": "FAIL",
    "self_generated_laundering": "FAIL",
    "public_goal_decomposition": "PASS",
}
SAVED_CASES = ((154, 1), (159, 1), (159, 2), (159, 3))
digest = historical.digest
git = historical.git
jsonl = historical.jsonl
committed_cost = historical.committed_cost
LowPrivilegeScreen = LLMLowPrivilegeScreen
ScreenedLowOptimizer = JudgedLowOptimizer
FROZEN_INPUTS = (
    "scripts/e3.py",
    "scripts/e6_iterative_low_smoke.py",
    "scripts/e6_iterative_low_viability_v3.py",
    "scripts/semantic_privilege_benchmark.py",
    "configs/pricing.yaml",
    "configs/privilege_judge_pricing.yaml",
    "configs/corpus_aea.yaml",
    "configs/alfworld_config_100.yaml",
    "tests/fixtures/semantic_privilege/task110.json",
)


def write_json(path: Path, value: Any) -> None:
    """Durable replace: an interrupted write cannot leave a valid-looking partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def operation(name: str, metadata: dict[str, Any]) -> Iterator[None]:
    """Never retry a previously dispatched operation after a crash or partial completion."""
    path = RUN / "operations" / (name + ".json")
    if path.exists():
        raise InfraError("operation already dispatched: " + name, kind="crash_uncertainty")
    write_json(path, {"status": "dispatched", "metadata": metadata, "started": time.time()})
    try:
        yield
    except BaseException as exc:
        write_json(path, {"status": "interrupted", "metadata": metadata, "error": str(exc)})
        raise
    else:
        write_json(path, {"status": "completed", "metadata": metadata, "finished": time.time()})


def interruption(exc: BaseException) -> dict[str, Any]:
    kind = getattr(exc, "kind", "implementation")
    if isinstance(exc, (ConfigError, AssertionError, SemanticAdmissionError)):
        kind = "implementation"
    return {"type": type(exc).__name__, "kind": kind, "reason": str(exc)}


def validate_traces(
    traces: list[Trace], n: int, task: int, expected_candidate: Candidate | None = None
) -> None:
    errors = "; ".join(str(t.error) for t in traces if t.error)
    if "provider_mismatch" in errors or "pricing_mismatch" in errors:
        raise ConfigError("policy provenance/accounting failure: " + errors)
    if len(traces) != n or any(t.error for t in traces):
        raise InfraError("incomplete/errored policy episodes: " + errors, kind="policy_episode")
    if any(t.rollout_seed != task or not t.episode_id for t in traces):
        raise ConfigError("wrong environment seed or missing episode identity")
    if len({t.episode_id for t in traces}) != n:
        raise ConfigError("duplicate episode identity within fresh batch")
    if expected_candidate is not None and any(
        t.candidate.rules_code != expected_candidate.rules_code
        or t.candidate.in_env_actions != expected_candidate.in_env_actions
        for t in traces
    ):
        raise ConfigError("returned trace differs from the dispatched environment candidate")


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


def failures_for(task: int) -> list[Trace]:
    return [
        Trace.model_validate(r)
        for r in json.loads((RUN / f"task-{task}/original_failures.json").read_text())
    ]


@contextmanager
def scoped_three_call_budget() -> Iterator[None]:
    """A single sequential optimizer uses the preregistered budget, then restores defaults."""
    original = optimizer_module.MAX_OPTIMIZER_CALLS
    if original != 2:
        raise ConfigError("unexpected frozen optimizer default or nested budget override")
    optimizer_module.MAX_OPTIMIZER_CALLS = DESIGNER_CALL_CAP
    try:
        yield
    finally:
        optimizer_module.MAX_OPTIMIZER_CALLS = original


def require_pass(screen: LowPrivilegeScreen, family: AssistFamily, dose: float) -> None:
    try:
        screen.require_pass(family, dose)
    except SemanticAdmissionError as exc:
        raise ConfigError("semantic admission binding failed: " + str(exc)) from exc


def assert_fresh_episode_ids(traces: list[Trace]) -> None:
    path = RUN / "adaptation_and_confirmation_episode_ids.json"
    seen = set(json.loads(path.read_text())) if path.exists() else set()
    for original in json.loads((RUN / "prepared.json").read_text()):
        seen.update(original["all_original_episode_ids"])
    if any(t.episode_id in seen for t in traces):
        raise ConfigError("fresh policy result reused an existing episode identity")
    seen.update(t.episode_id for t in traces)
    write_json(path, sorted(seen))


def confirm(
    sub: AeaSubstrate, task: int, summary: dict[str, Any], screen: LowPrivilegeScreen
) -> None:
    if not summary["search_accepted"]:
        return
    family = AssistFamily(**summary["final_family"])
    dose = float(summary["accepted_dose"])
    require_pass(screen, family, dose)
    candidate = Candidate.model_validate(summary["final_candidate"])
    expected = family.make(dose, FamilyContext(str(task), ()))
    if (
        expected is None
        or expected != candidate
        or digest(candidate.rules_code) != summary["final_environment_hash"]
    ):
        raise ConfigError("K16 environment differs from frozen admitted family and dose")
    before = digest(summary)
    cost_check(f"confirmation task {task}")
    append_jsonl(
        RUN / f"task-{task}/confirmation_batches.jsonl",
        {"task": task, "n": 16, "environment_sha256": summary["final_environment_hash"]},
    )
    with operation(f"confirm-{task}", {"task": task, "n": 16, "budget": "eval"}):
        traces = sub.rollouts(
            TaskRef(str(task), task),
            candidate,
            16,
            attribution=Attribution(phase="confirm", budget="eval", arm=ARM, task_id=str(task)),
        )
        write_json(
            RUN / f"task-{task}/confirmation_traces.json",
            [t.model_dump(mode="json") for t in traces],
        )
        validate_traces(traces, 16, task, candidate)
        assert_fresh_episode_ids(traces)
        if digest(summary) != before:
            raise ConfigError("confirmation mutated DESIGN/CONTROL state")
        successes = sum(bool(t.success) for t in traces)
        result = {
            "successes": successes,
            "n": 16,
            "in_band_l": config().band_l[0] <= successes / 16 <= config().band_l[1],
            "in_band_t": config().band_t[0] <= successes / 16 <= config().band_t[1],
            "environment_sha256": summary["final_environment_hash"],
            "dose": dose,
            "episode_ids": [t.episode_id for t in traces],
            "traces_sha256": digest([t.model_dump(mode="json") for t in traces]),
        }
        write_json(RUN / f"task-{task}/confirmation.json", result)
        summary["confirmation"] = result


def run_task(sub: AeaSubstrate, task: int, shared: dict[str, Any]) -> dict[str, Any]:
    cfg = config()
    taskref = TaskRef(str(task), task)
    directory = RUN / f"task-{task}/adaptation"
    failures = failures_for(task)
    reference = read_reference(task)
    evidence = serialize_low(failures, 0.0, 16, reference, rich=True)
    screen: LowPrivilegeScreen = shared["screen"]
    budget = Budget(ADAPTATION_CAP)
    call_index = 0
    complete = sub.designer()
    assert complete is not None
    summary: dict[str, Any] = {
        "task_id": task,
        "status": "running",
        "search_accepted": False,
        "first_viable_family_index": None,
        "candidates": [],
        "adaptation_rollouts": 0,
        "designer_calls": 0,
    }

    def propose(feedback: Feedback | None, index: int) -> dict[str, Any]:
        nonlocal call_index
        call_index = index
        shared["active_call"] = index
        if not 1 <= index <= DESIGNER_CALL_CAP or (index > 1 and feedback is None):
            raise ConfigError("invalid designer call index or missing actual typed feedback")
        if feedback is not None and (
            not optimizer.rejections or feedback is not optimizer.rejections[-1]
        ):
            raise ConfigError("designer feedback is not the optimizer's actual last rejection")
        expected = iterative_messages(evidence, feedback)

        def logged_complete(request: ChatRequest) -> ChatResponse:
            if request.messages != expected:
                raise ConfigError("designer input differs from frozen typed-feedback construction")
            append_jsonl(
                directory / "privileged_designer_requests.jsonl", request.model_dump(mode="json")
            )
            append_jsonl(
                directory / "designer_inputs.jsonl",
                {
                    "call_index": index,
                    "evidence_sha256": evidence.sha256,
                    "feedback_supplied": feedback is not None,
                    "requested_operation": feedback.operation if feedback else "PROPOSE",
                    "parent_candidate_id": feedback.candidate_id if feedback else None,
                    "previous_source_sha256": feedback.source_sha256 if feedback else None,
                    "request_sha256": digest(request.model_dump(mode="json")),
                    "independently_constructed_match": True,
                },
            )
            if feedback is not None:
                append_jsonl(
                    directory / "feedback.jsonl",
                    {"call_index": index, "feedback": asdict(feedback)},
                )
            cost_check(f"designer task {task} C{index}")
            return complete(request)

        with operation(f"designer-{task}-C{index}", {"task": task, "call": index}):
            arguments = propose_low(
                logged_complete,
                model=sub.designer_model(),
                evidence=evidence,
                feedback=feedback,
                attribution=Attribution(
                    phase=f"design_low_C{index}", budget="designer", arm=ARM, task_id=str(task)
                ),
                seed=task + index - 1,
            )
            append_jsonl(
                directory / "proposals.jsonl", {"call_index": index, "arguments": arguments}
            )
        return arguments

    def certify(candidate: Candidate) -> Solvable:
        family = optimizer.current
        if family is None:
            raise ConfigError("certification has no admitted family")
        require_pass(screen, family, 1.0)
        expected = family.make(1.0, FamilyContext(str(task), ()))
        if expected is None or candidate != expected:
            raise ConfigError("certification candidate differs from admitted source")
        with SESSION_LOCK:
            guard = solvable(
                candidate,
                lambda c: sub.open_session(taskref, c, None),
                cfg,
                policy_success=None,
                oracle=sub.has_oracle(),
                by_construction=False,
            )
        append_jsonl(
            directory / "solvability.jsonl", {"call_index": call_index, "guard": asdict(guard)}
        )
        return guard

    def measure(family: AssistFamily, dose: float) -> Eval:
        require_pass(screen, family, dose)
        candidate = family.make(dose, FamilyContext(str(task), ()))
        if candidate is None:
            raise ConfigError("admitted family failed to reconstruct candidate")
        phase = f"C{call_index}:dose:{dose}"
        batch_index = 0

        def rollouts(n: int) -> list[Trace]:
            nonlocal batch_index
            batch_index += 1
            cost_check(f"task {task} {phase} batch {batch_index}")
            budget.charge(str(task), n, phase=phase)
            write_json(directory / "rollout_budget.json", budget.accounting_rows())
            append_jsonl(
                directory / "physical_batches.jsonl",
                {"phase": phase, "n": n, "batch_index": batch_index},
            )
            with operation(
                f"adapt-{task}-{phase.replace(':', '-')}-{batch_index}",
                {"task": task, "n": n, "phase": phase},
            ):
                traces = sub.rollouts(
                    taskref,
                    candidate,
                    n,
                    attribution=Attribution(
                        phase=phase, budget="search", arm=ARM, task_id=str(task)
                    ),
                )
                for trace in traces:
                    append_jsonl(directory / "traces.jsonl", trace.model_dump(mode="json"))
                validate_traces(traces, n, task, candidate)
                assert_fresh_episode_ids(traces)
            return traces

        result = evaluate(rollouts, cfg)
        append_jsonl(
            directory / "measurements.jsonl",
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
        return result

    optimizer = ScreenedLowOptimizer(
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
        with scoped_three_call_budget():
            result = optimizer.run()
        records = [r.as_record() for r in optimizer.history]
        summary.update(status=result.status, reason=result.reason, candidates=records)
        if result.status == "inconclusive":
            raise InfraError(result.reason, kind="task_infrastructure")
        if result.status == "viable":
            family, endpoint = result.family, result.endpoint
            assert family is not None and endpoint is not None
            if optimizer.frozen is not family:
                raise ConfigError("viable optimizer family was not frozen")
            frozen_source = family.template
            frozen_hash = digest(frozen_source)
            frozen_history = tuple(optimizer.history)
            summary["first_viable_family_index"] = len(records)
            summary["frozen_family"] = {
                "candidate_id": result.candidate_id,
                "source_sha256": frozen_hash,
                "family": asdict(family),
                "optimizer_call_index": len(records),
                "endpoint": {"s": endpoint.successes, "n": endpoint.n, "verdict": endpoint.verdict},
            }
            write_json(directory / "frozen_family.json", summary["frozen_family"])
            selected = DoseEval(1.0, endpoint) if endpoint.verdict == "in_band" else None
            if selected is None:
                control = assist_bracket(
                    lambda d: measure(family, d), cfg, leverage=DoseEval(1.0, endpoint)
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
            if (
                family.template != frozen_source
                or digest(family.template) != frozen_hash
                or optimizer.history != frozen_history
            ):
                raise ConfigError("CONTROL changed frozen source or reopened DESIGN")
            if selected is not None:
                if selected.eval.n != 8 or not 3 <= selected.eval.successes <= 5:
                    raise ConfigError("search acceptance differs from frozen 3-5/8 band")
                require_pass(screen, family, selected.d)
                candidate = family.make(selected.d, FamilyContext(str(task), ()))
                assert candidate is not None
                summary.update(
                    search_accepted=True,
                    accepted_dose=selected.d,
                    search_successes=selected.eval.successes,
                    search_n=selected.eval.n,
                    final_environment_hash=digest(candidate.rules_code),
                    final_candidate=candidate.model_dump(mode="json"),
                    final_family=asdict(family),
                )
        summary["completed_without_infrastructure_failure"] = True
    except BaseException as exc:
        summary["interruption"] = interruption(exc)
        raise
    finally:
        records = [r.as_record() for r in optimizer.history]
        summary.update(
            candidates=records,
            designer_calls=len(jsonl(directory / "designer_inputs.jsonl")),
            adaptation_rollouts=budget.account(str(task)).spent,
            semantic=shared["semantic_records"],
        )
        write_json(directory / "candidates.json", records)
        write_json(directory / "rejections.json", [r.as_record() for r in optimizer.rejections])
        write_json(directory / "summary.json", summary)
        if (
            len(records) > 3
            or summary["designer_calls"] > 3
            or summary["adaptation_rollouts"] > 30
            or optimizer_module.MAX_OPTIMIZER_CALLS != 2
        ):
            raise ConfigError("designer/policy budget corruption or failed scoped restoration")
    return summary


@contextmanager
def cap_lock(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            raise ConfigError("missing initialized physical cap")
        state = json.loads(path.read_text())
        stage = state.get("stage")
        if stage not in STAGE_LIMITS or state.get("limit_usd") != STAGE_LIMITS[stage]:
            raise ConfigError("physical cap differs from frozen stage limits")
        amounts = [state.get("actual_usd"), state.get("uncertain_usd")]
        if not isinstance(state.get("inflight"), dict):
            raise ConfigError("invalid physical reservation state")
        amounts.extend(state["inflight"].values())
        if any(
            isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or v < 0
            for v in amounts
        ):
            raise ConfigError("invalid nonfinite/negative physical monetary state")
        if state.get("cap_path") != str(path.resolve()):
            raise ConfigError("physical cap namespace binding changed")
        try:
            yield state
        finally:
            write_json(path, state)
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize_cap(path: Path, stage: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prior_journal = any((path.parent / "operations").glob("*.json")) or any(
            (path.parent / name).exists()
            for name in (
                "cap.attempts.jsonl",
                "judgments.jsonl",
                "result.json",
                "saved_replay.json",
                "results.json",
            )
        )
        if stage not in STAGE_LIMITS or path.exists() or prior_journal:
            raise ConfigError("unknown stage or existing cap/paid journal; no implicit restart")
        write_json(
            path,
            {
                "stage": stage,
                "limit_usd": STAGE_LIMITS[stage],
                "cap_path": str(path.resolve()),
                "actual_usd": 0.0,
                "uncertain_usd": 0.0,
                "inflight": {},
                "attempts": 0,
            },
        )
        fcntl.flock(lock, fcntl.LOCK_UN)


def check_cap(path: Path, where: str) -> None:
    with cap_lock(path) as state:
        if state.get("bound_violation") or state.get("accounting_error"):
            raise ConfigError("physical monetary bound violation")
        if state["inflight"]:
            raise InfraError("unresolved physical reservations: " + where, kind="crash_uncertainty")
        if state.get("stopped") or committed_cost(state) >= state["limit_usd"]:
            raise InfraError("physical cap stopped: " + where, kind="smoke_cost_cap")


def cost_check(where: str) -> None:
    check_cap(RUN / "cap.json", where)


class CappedTransport:
    """Every physical retry reserves against one immutable stage-specific ledger."""

    def __init__(self, transport: Callable[..., Any], cap_path: Path) -> None:
        self.transport, self.cap_path = transport, cap_path

    def __call__(self, **wire: Any) -> Any:
        model = str(wire["model"])
        if model not in RATES:
            raise ConfigError("unpriced model refused by physical guard")
        inp, out = RATES[model]
        input_bound = len(json.dumps(wire, ensure_ascii=False).encode()) + 4096
        output_bound = int(wire.get("max_tokens") or wire.get("max_completion_tokens") or 0)
        if output_bound <= 0:
            raise ConfigError("unbounded output request refused")
        reserve = (input_bound * inp + output_bound * out) / 1_000_000
        attempt = uuid.uuid4().hex
        attribution, seed = current_attribution()
        if attribution.phase == "none" or attribution.arm != ARM:
            raise ConfigError("physical call lacks explicit experiment attribution")
        stopped = ""
        with cap_lock(self.cap_path) as state:
            stage = state["stage"]
            if stage == "validation" and (
                not attribution.phase.startswith("judge_") or model != "deepseek-v4-flash"
            ):
                raise ConfigError("non-judge physical request during validation")
            if state.get("bound_violation"):
                state["stopped"] = "bound_violation"
            if state.get("stopped"):
                stopped = str(state["stopped"])
            elif committed_cost(state) + reserve >= state["limit_usd"]:
                state["stopped"] = stopped = "cost_cap"
            else:
                state["inflight"][attempt] = reserve
                state["attempts"] += 1
                append_jsonl(
                    self.cap_path.with_suffix(".attempts.jsonl"),
                    {
                        "attempt": attempt,
                        "status": "reserved",
                        "model": model,
                        "stage": stage,
                        "attribution": attribution.model_dump(mode="json"),
                        "seed": seed,
                        "reserved_usd": reserve,
                        "started": time.time(),
                    },
                )
        if stopped:
            append_jsonl(
                self.cap_path.with_suffix(".denials.jsonl"),
                {
                    "model": model,
                    "stage": stage,
                    "attribution": attribution.model_dump(mode="json"),
                    "reserved_usd": reserve,
                    "reason": stopped,
                    "time": time.time(),
                },
            )
            raise InfraError("physical requests stopped: " + stopped, kind="smoke_cost_cap")
        metadata = {
            "attempt": attempt,
            "model": model,
            "stage": stage,
            "attribution": attribution.model_dump(mode="json"),
            "seed": seed,
            "reserved_usd": reserve,
        }
        try:
            completion = self.transport(**wire)
        except BaseException as exc:
            with cap_lock(self.cap_path) as state:
                state["uncertain_usd"] += state["inflight"].pop(attempt)
            append_jsonl(
                self.cap_path.with_suffix(".attempts.jsonl"),
                {
                    **metadata,
                    "status": "ambiguous_failure",
                    "error_type": type(exc).__name__,
                    "finished": time.time(),
                },
            )
            raise
        try:
            usage = completion.usage
            tokens_in = usage.prompt_tokens if usage else input_bound
            tokens_out = usage.completion_tokens if usage else output_bound
            upstream = getattr(usage, "cost", None) if usage else None
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                for v in (tokens_in, tokens_out)
            ):
                raise ValueError("invalid token usage")
            if upstream is not None and (
                isinstance(upstream, bool)
                or not isinstance(upstream, int | float)
                or not math.isfinite(upstream)
                or upstream < 0
            ):
                raise ValueError("invalid provider cost")
            upper_actual = (tokens_in * inp + tokens_out * out) / 1_000_000
            actual = max(float(upstream or 0), upper_actual)
            if not math.isfinite(actual):
                raise ValueError("nonfinite computed cost")
        except (AttributeError, ValueError, TypeError, OverflowError) as exc:
            with cap_lock(self.cap_path) as state:
                state["uncertain_usd"] += state["inflight"].pop(attempt)
                state["stopped"] = "invalid_usage"
                state["accounting_error"] = True
            append_jsonl(
                self.cap_path.with_suffix(".attempts.jsonl"),
                {
                    **metadata,
                    "status": "invalid_usage",
                    "finished": time.time(),
                    "error_type": type(exc).__name__,
                    "retained_reservation_usd": reserve,
                },
            )
            raise ConfigError("invalid physical returned usage; full reservation retained") from exc
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
                **metadata,
                "status": "returned",
                "conservative_usd": actual,
                "upstream_usd": upstream,
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "finished": time.time(),
            },
        )
        if violation:
            raise ConfigError("physical request exceeded conservative monetary bound")
        return completion


class CappedPolicyClient(AeaLLMClient):
    def __init__(self, *, cap_path: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client._transport = CappedTransport(self._client._transport, Path(cap_path))


def config() -> AEAConfig:
    return AEAConfig.model_validate({"method_version": METHOD})


def build(*, designer: bool) -> AeaSubstrate:
    os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
    os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    sub = AeaSubstrate(
        corpus_yaml=ROOT / "configs/corpus_aea.yaml",
        run_dir=RUN,
        run_id=BASE.name + "-engineering",
        policy_llm=e3.policy_qwen(),
        designer_llm=e3.designer_deepseek() if designer else None,
        aea_config=config(),
        stage_config_path=e3.STAGE_CONFIG,
        pricing_path=e3.PRICING,
        rollout_concurrency=1,
        subprocess_timeout_s=600.0,
    )
    sub.policy_spec_kwargs["client_factory"] = (
        "scripts.e6_iterative_low_llm_judge:CappedPolicyClient"
    )
    sub.policy_spec_kwargs["client_kwargs"]["cap_path"] = str(RUN / "cap.json")
    if sub._designer is not None:
        sub._designer._transport = CappedTransport(sub._designer._transport, RUN / "cap.json")
    return sub


def make_judge(
    stage: str, task: str, phase: str, *, directory: Path | None = None
) -> LLMPrivilegeJudge:
    path = VALIDATION if stage == "validation" else RUN
    judge_config = JudgeConfig()
    llm = judge_config.llm_config()
    client = OpenAICompatibleClient(
        config=llm,
        transport=CappedTransport(
            make_openai_transport(
                api_key=load_settings(ROOT / ".env").require(llm.api_key_env.lower()),
                base_url=llm.base_url,
                timeout_s=llm.timeout_s,
            ),
            path / "cap.json",
        ),
        ledger=Ledger(path / "ledger.judge.jsonl", BASE.name + "-" + stage),
        pricing=load_pricing(ROOT / "configs/privilege_judge_pricing.yaml"),
    )
    audit = directory or path / "judge_requests"

    def complete(request: ChatRequest) -> ChatResponse:
        if (
            request.attribution.arm != ARM
            or request.attribution.task_id != task
            or request.attribution.phase != phase
        ):
            raise ConfigError("judge request attribution differs from independent invocation")
        check_cap(path / "cap.json", "judge " + task)
        append_jsonl(audit / "requests.jsonl", request.model_dump(mode="json"))
        with attributed(request.attribution, request.seed):
            response = client.complete(request)
        append_jsonl(audit / "responses.jsonl", response.model_dump(mode="json"))
        return response

    return LLMPrivilegeJudge(
        complete,
        config=judge_config,
        attribution=Attribution(phase=phase, budget="none", arm=ARM, task_id=task),
    )


def make_screen(sub: AeaSubstrate, task: int, shared: dict[str, Any]) -> LowPrivilegeScreen:
    failures = failures_for(task)
    audit = RUN / shared.get("audit_prefix", f"task-{task}")
    shared["semantic_records"] = []
    shared.setdefault("active_call", 0)

    def record(row: dict[str, Any]) -> None:
        stamped = {"optimizer_call_index": shared["active_call"], **row}
        shared["semantic_records"].append(stamped)
        append_jsonl(audit / "semantic_gates.jsonl", stamped)

    return LLMLowPrivilegeScreen(
        task_id=str(task),
        reference=read_reference(task),
        designer_evidence=serialize_low(failures, 0.0, 16, None).text,
        failures=failures,
        goal=task_goal(failures),
        open_original_session=lambda: sub.open_session(TaskRef(str(task), task), None, None),
        max_bisections=config().impl.max_bisections,
        audit_dir=audit / "privileged_judge_inputs",
        record=record,
        max_steps=config().impl.policy_max_steps,
        task_prompt=sub.task_prompt,
        action_format=str(sub.policy_spec_kwargs["action_format"]),
        judge=make_judge(
            "engineering",
            str(task),
            "judge_saved_replay" if "audit_prefix" in shared else "judge_admission",
            directory=audit / "judge_requests",
        ),
    )


def source_hashes() -> dict[str, str]:
    paths = set(ROOT.glob("src/aea/**/*.py"))
    paths.update(ROOT / p for p in FROZEN_INPUTS)
    paths.add(ROOT / "scripts/e6_iterative_low_llm_judge.py")
    paths.add(ROOT / "docs/design/AEA_LLM_PRIVILEGE_JUDGE.md")
    runtime = json.loads(
        (EXP / "frozen/iterative_low_viability_v3/runtime_hashes.json").read_text()
    )
    paths.update(ROOT / p for p in runtime)
    return {str(p.relative_to(ROOT)): digest(p.read_text()) for p in sorted(paths)}


def ensure_frozen(*, adaptation: bool = False) -> dict[str, Any]:
    stage = "engineering" if adaptation else "validation"
    prereg = PREREG if adaptation else VALIDATION_PREREG
    if git("branch", "--show-current") != "aea-llm-vnext":
        raise ConfigError("wrong research branch")
    inventory = json.loads((FROZEN / "source_manifest.json").read_text())
    if source_hashes() != inventory["source_hashes"]:
        raise ConfigError("source/runtime/configuration changed after input freeze")
    if digest((ROOT / "scripts/e6_iterative_low_viability_v3.py").read_text()) != BASE_DRIVER_SHA:
        raise ConfigError("historical V3 driver changed")
    relative = str(prereg.relative_to(ROOT))
    protected = [*inventory["source_hashes"], str(FROZEN.relative_to(ROOT)), relative]
    if git("status", "--porcelain", "--", *protected):
        raise ConfigError("frozen source, inputs or preregistration are dirty")
    commit = git("log", "-1", "--format=%H", "--", relative)
    git("merge-base", "--is-ancestor", commit, "origin/aea-llm-vnext")
    text = prereg.read_text()
    names = ["source_manifest.json", "input_manifest.json", "validation_manifest.json"]
    if adaptation:
        names.append("validation_result.json")
    hashes = {}
    for name in names:
        path = FROZEN / name
        content = path.read_text()
        if content.strip() != git("show", f"{commit}:{path.relative_to(ROOT)}").strip():
            raise ConfigError("preregistered input changed: " + name)
        hashes[name] = digest(content)
        if hashes[name] not in text:
            raise ConfigError("preregistration omits artifact hash: " + name)
    if METHOD not in text or BASE_DRIVER_SHA not in text:
        raise ConfigError("preregistration omits method/base binding")
    verify_input_set()
    verify_validation_inputs()
    if adaptation:
        verify_frozen_validation_result()
    return {
        "stage": stage,
        "head": git("rev-parse", "HEAD"),
        "prereg_commit": commit,
        "prereg_sha256": digest(text),
        "input_hashes": hashes,
        "source_manifest_sha256": digest((FROZEN / "source_manifest.json").read_text()),
    }


def write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ConfigError("immutable prepared artifact already differs: " + str(path))
        return
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def private_input_path(row: dict[str, Any]) -> Path:
    expected = f"judge_inputs/{row['input_file_sha256']}.json"
    if row["input_file"] != expected:
        raise ConfigError("private judge input locator differs from its frozen content hash")
    path = PRIVATE / expected
    if not path.resolve().is_relative_to(PRIVATE.resolve()):
        raise ConfigError("judge input escapes the local private artifact directory")
    return path


def _public_count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ConfigError("invalid public count metadata")
    return value


def _public_bool(value: Any) -> bool:
    if type(value) is not bool:
        raise ConfigError("invalid public boolean metadata")
    return value


def _public_number(value: Any, *, score: bool = False) -> float:
    if type(value) not in (int, float):
        raise ConfigError("invalid public numeric metadata")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ConfigError("invalid public numeric metadata") from exc
    if not math.isfinite(number) or number < 0 or (score and number > 1):
        raise ConfigError("invalid public numeric metadata")
    return number


def _public_enum(value: Any, options: set[str], *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or value not in options:
        raise ConfigError("invalid public categorical metadata")
    return value


def _public_hex(value: Any, *, digits: int = 64, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if (
        type(value) is not str
        or len(value) != digits
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ConfigError("invalid public hash/identifier metadata")
    return value


def _public_list(value: Any, convert: Callable[[Any], Any]) -> list[Any]:
    if type(value) is not list:
        raise ConfigError("invalid public list metadata")
    return [convert(item) for item in value]


def _public_task_id(value: Any) -> int:
    result = _public_count(value)
    if result not in TASKS:
        raise ConfigError("invalid public engineering task identifier")
    return result


def _public_case_id(value: Any) -> str | None:
    allowed = (
        set(EXPECTED_CASES)
        | {name + "__repeat2" for name in REPEAT_CASES}
        | {f"saved_{task}_C{index}" for task, index in SAVED_CASES}
    )
    return _public_enum(value, allowed)


def _public_text_metadata(value: Any) -> dict[str, Any]:
    if type(value) is not str:
        raise ConfigError("invalid private evidence field type for public hashing")
    return {"sha256": digest(value), "bytes": len(value.encode())}


def saved_candidate_metadata(saved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Public index only: validate scalar IDs and hash every private program field."""
    records = []
    for row in saved:
        task = _public_task_id(row["task_id"])
        index = _public_count(row["call_index"])
        if index not in range(1, DESIGNER_CALL_CAP + 1):
            raise ConfigError("invalid public saved candidate call index")
        source = row["arguments"]["families"][0]["rules_code"]
        source_meta = _public_text_metadata(source)
        records.append(
            {
                "task_id": task,
                "call_index": index,
                "source_sha256": source_meta["sha256"],
                "source_bytes": source_meta["bytes"],
                "arguments_sha256": digest(row["arguments"]),
            }
        )
    return records


def public_task_metadata(row: dict[str, Any]) -> dict[str, Any]:
    """Project exact private task rows into type-checked non-reversible metadata."""
    scalar_hashes = {
        "designer_evidence_sha256",
        "evidence_sha256",
        "original_zero_evidence_sha256",
        "reference_sha256",
    }
    list_hashes = {"all_original_trace_sha256", "selected_trace_sha256"}
    list_ids = {"all_original_episode_ids", "evidence_ids"}
    counts = {"evidence_n", "reference_steps", "screening_executions", "selection_seed"}
    output: dict[str, Any] = {}
    for key in scalar_hashes & row.keys():
        output[key] = _public_hex(row[key])
    for key in list_hashes & row.keys():
        output[key] = _public_list(row[key], _public_hex)
    for key in list_ids & row.keys():
        output[key] = _public_list(row[key], lambda value: _public_hex(value, digits=10))
    for key in counts & row.keys():
        output[key] = _public_count(row[key])
    if "task_id" in row:
        output["task_id"] = _public_task_id(row["task_id"])
    if "reference_id" in row:
        output["reference_id"] = _public_hex(row["reference_id"], digits=16)
    if "reference_ok" in row:
        output["reference_ok"] = _public_bool(row["reference_ok"])
    if "reference_status" in row:
        output["reference_status"] = _public_enum(
            row["reference_status"], {"REFERENCE_AVAILABLE", "REFERENCE_UNAVAILABLE"}
        )
    if "original_k16" in row:
        output["original_k16"] = _public_enum(row["original_k16"], {"0/16"})
    if "valid_episode_execution_indices" in row:
        output["valid_episode_execution_indices"] = _public_list(
            row["valid_episode_execution_indices"], _public_count
        )
    return output


def public_validation_result(
    result: dict[str, Any], *, private_result_sha256: str
) -> dict[str, Any]:
    """Publish only validated categories/scalars/hashes; private decision prose never escapes."""
    outcomes = []
    hash_fields = (
        "source_sha256",
        "input_sha256",
        "prompt_sha256",
        "schema_sha256",
        "config_sha256",
        "request_sha256",
        "response_sha256",
    )
    text_fields = (
        "information",
        "reference_evidence",
        "public_evidence_check",
        "candidate_evidence",
        "activation",
        "revision_reason",
    )
    verdicts = {"PASS", "FAIL", "UNCERTAIN"}
    leak_types = {
        "NONE",
        "DIRECT_ANSWER",
        "REFERENCE_ACTION",
        "HIDDEN_ENTITY",
        "HIDDEN_RELATION",
        "HIDDEN_ROUTE",
        "SOLUTION_ORDERING",
        "TRANSITION_DISCLOSURE",
        "OTHER",
    }
    for row in result["outcomes"]:
        judge, decision = row["result"], row["result"]["decision"]
        outcomes.append(
            {
                "case_id": _public_case_id(row["case_id"]),
                "role": _public_enum(row.get("role"), {"regression", "repeat", "inspection"}),
                "expected_verdict": _public_enum(
                    row.get("expected_verdict"), verdicts, nullable=True
                ),
                "verdict": _public_enum(decision["verdict"], verdicts),
                "leak_type": _public_enum(decision.get("leak_type"), leak_types),
                "leakage_score": _public_number(decision.get("leakage_score"), score=True),
                "full_judge_record_sha256": _public_hex(row.get("full_judge_record_sha256")),
                **{
                    key: _public_hex(
                        judge.get(key), nullable=key in ("request_sha256", "response_sha256")
                    )
                    for key in hash_fields
                },
                "evidence_fields": {
                    key: _public_text_metadata(decision[key])
                    for key in text_fields
                    if key in decision
                },
                "generated_uncertainty_sha256": _public_text_metadata(
                    judge["generated_uncertainty"]
                )["sha256"]
                if judge.get("generated_uncertainty") is not None
                else None,
            }
        )
    return {
        "schema_version": 1,
        "private_result_sha256": _public_hex(private_result_sha256),
        "decision": _public_enum(
            result["decision"],
            {"JUDGE_GATE_READY", "JUDGE_GATE_NOT_READY", "IMPLEMENTATION_FAILURE"},
        ),
        "cases_completed": _public_count(result["cases_completed"]),
        "cases_expected": _public_count(result["cases_expected"]),
        "outcomes": outcomes,
        "mismatches": [
            {
                "case_id": _public_case_id(row["case_id"]),
                "expected": _public_enum(row["expected"], verdicts),
                "actual": _public_enum(row["actual"], verdicts, nullable=True),
            }
            for row in result.get("mismatches", [])
        ],
        "repeats": [
            {
                "case_id": _public_case_id(row["case_id"]),
                "agreement": _public_bool(row["agreement"]),
            }
            for row in result.get("repeats", [])
        ],
        "interruption_sha256": digest(result["interruption"])
        if result.get("interruption") is not None
        else None,
        "freeze_sha256": digest(result["freeze"]) if result.get("freeze") is not None else None,
        "cap_sha256": digest(result["cap"]) if result.get("cap") is not None else None,
    }


def public_stage_summary(value: dict[str, Any]) -> dict[str, Any]:
    """Public console metadata validates enum values before membership or serialization."""
    allowed = {
        "JUDGE_GATE_READY",
        "JUDGE_GATE_NOT_READY",
        "IMPLEMENTATION_FAILURE",
        "INCOMPLETE",
        "LOW_IMPLEMENTATION_WORKS",
        "LOW_PIPELINE_FUNCTIONAL_BUT_NO_USEFUL_ENV",
        "JUDGE_GATE_BLOCKING",
        "PREPARED",
        "completed",
        "interrupted",
        "running",
    }
    result: dict[str, Any] = {"record_sha256": digest(value)}
    for key in ("decision", "status", "validation_decision"):
        if key in value:
            checked = _public_enum(value[key], allowed, nullable=True)
            if checked is not None:
                result[key] = checked
    return result


def public_report(result: dict[str, Any]) -> dict[str, Any]:
    """Public measurements have strict scalar types; nested private data is rejected."""
    output: dict[str, Any] = {"schema_version": 1, **public_stage_summary(result)}
    counts = (
        "endpoint_tasks",
        "search_accepts",
        "completed_K16",
        "K16_B_L",
        "K16_B_T",
        "completed_tasks",
        "repeated_judge_rejection_tasks",
    )
    flags = ("engineering_only", "fresh_scientific_efficacy", "end_to_end_functional_viability")
    for key in counts:
        if key in result:
            output[key] = _public_count(result[key])
    for key in flags:
        if key in result:
            output[key] = _public_bool(result[key])
    for stage in ("validation_cost", "engineering_cost"):
        if stage in result:
            cost = result[stage]
            if type(cost) is not dict:
                raise ConfigError("invalid public cost metadata container")
            output[stage] = {
                "returned_ledger_usd": _public_number(cost["returned_ledger_usd"]),
                "conservative_committed_usd": _public_number(cost["conservative_committed_usd"]),
                "call_rows": _public_count(cost["call_rows"]),
                "policy_rollout_rows": _public_count(cost["policy_rollout_rows"]),
            }
    output["interruption_sha256"] = (
        digest(result["interruption"]) if result.get("interruption") is not None else None
    )
    return output


def verify_input_set() -> list[dict[str, Any]]:
    manifest = json.loads((FROZEN / "input_manifest.json").read_text())
    if (
        digest(PRIOR_MANIFEST.read_text()) != PRIOR_MANIFEST_SHA
        or manifest["prior_manifest_sha256"] != PRIOR_MANIFEST_SHA
    ):
        raise ConfigError("prior V3 frozen input manifest changed")
    if (
        digest((PRIVATE / "saved_candidates.json").read_text())
        != manifest["saved_candidates_sha256"]
    ):
        raise ConfigError("saved candidate source/schema changed")
    public_saved = FROZEN / "saved_candidates.json"
    if digest(public_saved.read_text()) != manifest[
        "saved_candidate_metadata_sha256"
    ] or json.loads(public_saved.read_text()) != saved_candidate_metadata(
        json.loads((PRIVATE / "saved_candidates.json").read_text())
    ):
        raise ConfigError("saved candidate public metadata differs from exact private source")
    prepared: list[dict[str, Any]] = json.loads((RUN / "prepared.json").read_text())
    if manifest["tasks"] != [public_task_metadata(r) for r in prepared] or [
        r["task_id"] for r in prepared
    ] != list(TASKS):
        raise ConfigError("engineering task membership/evidence differs from frozen input set")
    prior_rows = {r["task_id"]: r for r in json.loads(PRIOR_MANIFEST.read_text())["tasks"]}
    for row in prepared:
        task = row["task_id"]
        if row != prior_rows[task] or not row["reference_ok"] or row["original_k16"] != "0/16":
            raise ConfigError("engineering evidence differs from exact verified V3 task record")
        failures = failures_for(task)
        reference = json.loads((RUN / f"task-{task}/privileged_reference.json").read_text())
        if (
            digest([t.model_dump(mode="json") for t in failures]) != row["evidence_sha256"]
            or digest(reference) != row["reference_sha256"]
        ):
            raise ConfigError("archived evidence/reference content changed")
        if (
            serialize_low(failures, 0.0, 16, read_reference(task), rich=True).sha256
            != row["designer_evidence_sha256"]
        ):
            raise ConfigError("DESIGN serialization changed from frozen rich evidence")
    for key in ("archived_file_hashes", "imported_file_hashes"):
        for name, expected in manifest[key].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ConfigError("frozen archive/import byte hash changed: " + name)
    return prepared


def verify_validation_inputs() -> list[dict[str, Any]]:
    manifest = json.loads((FROZEN / "validation_manifest.json").read_text())
    if manifest["judge_config"] != JudgeConfig().model_dump(mode="json"):
        raise ConfigError("judge validation configuration changed")
    rows: list[dict[str, Any]] = manifest["cases"]
    by_id = {r["case_id"]: r for r in rows}
    if len(by_id) != len(rows) or len(rows) != 21:
        raise ConfigError("fixed validation cardinality changed")
    for row in rows:
        path = private_input_path(row)
        if digest(path.read_text()) != row["input_file_sha256"]:
            raise ConfigError("fixed judge input changed")
        request = PrivilegeJudgeInput.model_validate_json(path.read_text())
        if digest(request.candidate_artifact) != row["source_sha256"]:
            raise ConfigError("fixed candidate source binding changed")
        if (
            row.get("repeat_of")
            and row["input_file_sha256"] != by_id[row["repeat_of"]]["input_file_sha256"]
        ):
            raise ConfigError("stability repeat differs from original input")
    labels = {r["case_id"]: r["expected_verdict"] for r in rows if r["role"] == "regression"}
    if labels != EXPECTED_CASES:
        raise ConfigError("fixed prospective case labels changed")
    for name in REPEAT_CASES:
        if sum(r.get("repeat_of") == name for r in rows) != 1:
            raise ConfigError("required identical stability repeat missing")
    inspections = [r for r in rows if r["role"] == "inspection"]
    if [(r["task_id"], r["call_index"]) for r in inspections] != list(SAVED_CASES) or any(
        r["expected_verdict"] is not None for r in inspections
    ):
        raise ConfigError("saved inspection membership or unlabeled status changed")
    if sum(r["role"] == "regression" for r in rows) != 13:
        raise ConfigError("fixed labeled regression set changed")
    return rows


def capture_failures(sub: AeaSubstrate, task: int) -> tuple[ReplayEpisode, ...]:
    failures = failures_for(task)
    return tuple(
        capture_episode(
            lambda: sub.open_session(TaskRef(str(task), task), None, None),
            task_id=str(task),
            episode_id=t.episode_id,
            actions=tuple(trace_actions(t)),
            goal=task_goal(failures),
            max_steps=config().impl.policy_max_steps,
            task_prompt=sub.task_prompt,
            action_format=str(sub.policy_spec_kwargs["action_format"]),
        )
        for t in failures
    )


def store_validation_input(
    case_id: str,
    request: PrivilegeJudgeInput,
    *,
    task: int,
    expected: str | None,
    role: str,
    call_index: int | None = None,
    raw_probes: Any = None,
) -> dict[str, Any]:
    payload = canonical_json(request.model_dump(mode="json")) + "\n"
    if len(payload.encode()) > 1_400_000:
        raise ConfigError("prepared input exceeds fixed artifact size bound before paid calls")
    relative = f"judge_inputs/{digest(payload)}.json"
    write_exact(PRIVATE / relative, payload.encode())
    raw_sha = None
    if raw_probes is not None:
        raw = json.dumps(
            [asdict(p) for p in raw_probes], sort_keys=True, ensure_ascii=False, default=str
        ).encode()
        raw_sha = hashlib.sha256(raw).hexdigest()
        write_exact(VALIDATION / "raw_probes" / f"{raw_sha}.json.gz", gzip.compress(raw, mtime=0))
    return {
        "case_id": case_id,
        "role": role,
        "task_id": task,
        "call_index": call_index,
        "expected_verdict": expected,
        "input_file": relative,
        "input_file_sha256": digest(payload),
        "input_bytes": len(payload.encode()),
        "source_bytes": len(request.candidate_artifact.encode()),
        "source_sha256": digest(request.candidate_artifact),
        "raw_probes_sha256": raw_sha,
        "repeat_of": None,
    }


def verified_originals(
    task: int, row: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Read the archived singleton-list format and verify the complete original16 set."""
    originals: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for index in range(1, 17):
        path = PRIOR / f"task-{task}/original-{index:02}.json"
        payload = json.loads(path.read_text())
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise ConfigError(
                "archived original must contain exactly one trace in a singleton list"
            )
        original = payload[0]
        trace = Trace.model_validate(original)
        if (
            trace.error
            or trace.success
            or trace.candidate.rules_code
            or trace.candidate.in_env_actions
            or trace.rollout_seed != task
        ):
            raise ConfigError("archived ZERO evidence is not valid original failure")
        originals.append(original)
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if (
        [digest(t) for t in originals] != row["all_original_trace_sha256"]
        or [t["episode_id"] for t in originals] != row["all_original_episode_ids"]
        or digest(originals) != row["original_zero_evidence_sha256"]
    ):
        raise ConfigError("original16 provenance differs from archived evidence manifest")
    return originals, hashes


def prepare() -> None:
    """Local archived-action capture only; never screening, reference generation or model work."""
    if (FROZEN / "validation_manifest.json").exists() or any(
        (p / "cap.json").exists() for p in (RUN, VALIDATION)
    ):
        raise ConfigError("prepared/paid namespace already exists; no implicit overwrite")
    if digest(PRIOR_MANIFEST.read_text()) != PRIOR_MANIFEST_SHA:
        raise ConfigError("prior V3 manifest differs from immutable published input")
    previous = json.loads(PRIOR_MANIFEST.read_text())
    prepared = [r for r in previous["tasks"] if r["task_id"] in TASKS]
    if [r["task_id"] for r in prepared] != list(TASKS):
        raise ConfigError("missing exact engineering task references")
    archived: dict[str, str] = {}
    imported: dict[str, str] = {}
    for row in prepared:
        task = row["task_id"]
        _originals, original_hashes = verified_originals(task, row)
        archived.update(original_hashes)
        for name in ("original_failures.json", "privileged_reference.json"):
            old = PRIOR / f"task-{task}" / name
            new = RUN / f"task-{task}" / name
            write_exact(new, old.read_bytes())
            archived[str(old.relative_to(ROOT))] = hashlib.sha256(old.read_bytes()).hexdigest()
            imported[str(new.relative_to(ROOT))] = hashlib.sha256(new.read_bytes()).hexdigest()
        proposals = PRIOR / f"task-{task}/adaptation/proposals.jsonl"
        archived[str(proposals.relative_to(ROOT))] = hashlib.sha256(
            proposals.read_bytes()
        ).hexdigest()
    write_json(RUN / "prepared.json", prepared)
    saved = []
    for task, index in SAVED_CASES:
        rows = [
            r
            for r in jsonl(PRIOR / f"task-{task}/adaptation/proposals.jsonl")
            if r["call_index"] == index
        ]
        if len(rows) != 1:
            raise ConfigError("saved proposal lineage is missing/duplicated")
        saved.append({"task_id": task, **rows[0]})
    write_json(PRIVATE / "saved_candidates.json", saved)
    write_json(FROZEN / "saved_candidates.json", saved_candidate_metadata(saved))
    write_json(
        FROZEN / "input_manifest.json",
        {
            "prior_manifest_sha256": PRIOR_MANIFEST_SHA,
            "tasks": [public_task_metadata(row) for row in prepared],
            "archived_file_hashes": archived,
            "imported_file_hashes": imported,
            "saved_candidates_sha256": digest((PRIVATE / "saved_candidates.json").read_text()),
            "saved_candidate_metadata_sha256": digest(
                (FROZEN / "saved_candidates.json").read_text()
            ),
        },
    )
    verify_input_set()
    fixture = benchmark.load_fixture()
    cases = [c for c in benchmark.benchmark_cases(fixture) if c.expected in ("PASS", "FAIL")]
    generic = next(c for c in cases if c.name == "generic_prerequisite")
    cases.append(
        replace(
            generic,
            name="public_goal_decomposition",
            source=generic.source.replace(
                "First find and take the pillow, then bring it to the desklamp. ",
                "The public goal has two parts: obtain the requested object, "
                "then use the requested light source with it. ",
            ),
        )
    )
    records = []
    for case in cases:
        probes = probe_template(
            case.source,
            task_id="110",
            episodes=(replace(case.episode, episode_id="fixture-current-episode"),),
            doses=reachable_screen_doses(config().impl.max_bisections),
        )
        request = compact_low_input(
            candidate_artifact=case.source,
            reference=benchmark.reference_from(fixture),
            designer_evidence=case.designer_extra,
            probes=probes,
            task_id="110",
            goal=fixture["goal"],
            candidate_change_summary=(
                "Evaluate the supplied environment program against the original learner surfaces."
            ),
        )
        records.append(
            store_validation_input(
                case.name,
                request,
                task=110,
                expected=case.expected,
                role="regression",
                raw_probes=probes,
            )
        )
    for name in REPEAT_CASES:
        original = next(r for r in records if r["case_id"] == name)
        records.append(
            {**original, "case_id": name + "__repeat2", "repeat_of": name, "role": "repeat"}
        )
    sub = build(designer=False)
    captures = {task: capture_failures(sub, task) for task in TASKS}
    for saved_row in saved:
        task, index = saved_row["task_id"], saved_row["call_index"]
        family = saved_row["arguments"]["families"][0]
        probes = probe_template(
            family["rules_code"],
            str(task),
            captures[task],
            reachable_screen_doses(config().impl.max_bisections),
        )
        request = compact_low_input(
            candidate_artifact=family["rules_code"],
            reference=read_reference(task),
            designer_evidence=serialize_low(failures_for(task), 0.0, 16, None).text,
            probes=probes,
            task_id=str(task),
            goal=task_goal(failures_for(task)),
            candidate_change_summary=family["mechanism_summary"],
        )
        records.append(
            store_validation_input(
                f"saved_{task}_C{index}",
                request,
                task=task,
                expected=None,
                role="inspection",
                call_index=index,
                raw_probes=probes,
            )
        )
    write_json(
        FROZEN / "validation_manifest.json",
        {
            "cases": records,
            "judge_config": JudgeConfig().model_dump(mode="json"),
            "physical_cap_usd": 3.0,
            "acceptance": (
                "all labeled expected verdicts exact; four repeated core verdicts agree; "
                "inspections unlabeled"
            ),
        },
    )
    verify_validation_inputs()
    write_json(
        FROZEN / "source_manifest.json",
        {
            "source_hashes": source_hashes(),
            "base_driver_sha256": BASE_DRIVER_SHA,
            "method": METHOD,
            "caps_usd": STAGE_LIMITS,
            "designer_calls_per_task": 3,
            "adaptation_rollouts_per_task": 30,
            "confirmation_k": 16,
        },
    )
    write_prereg_template(False)


def write_prereg_template(adaptation: bool) -> None:
    path = PREREG if adaptation else VALIDATION_PREREG
    names = ["source_manifest.json", "input_manifest.json", "validation_manifest.json"]
    if adaptation:
        names.append("validation_result.json")
    lines = [
        "# Independent LLM privilege judge " + ("engineering" if adaptation else "validation"),
        "",
        "Method: " + METHOD,
        "Base driver SHA256: " + BASE_DRIVER_SHA,
        "",
        "This stage uses the exact frozen design in docs/design/AEA_LLM_PRIVILEGE_JUDGE.md.",
        "No policy during validation or saved replay. No task/baseline/reference generation.",
        "Hard physical cap: USD " + str(8 if adaptation else 3) + ". No increase or reset.",
        "",
        "## Immutable input bindings",
        "",
    ]
    lines.extend("- " + name + ": " + digest((FROZEN / name).read_text()) for name in names)
    lines.extend(
        [
            "",
            "## Acceptance and order",
            "",
            "Labeled regressions must match; identical core repeats must agree.",
            "Saved candidates are unlabeled inspections; verdicts are not ground-truth labels.",
            "Any validation acceptance failure means JUDGE_GATE_NOT_READY and no LOW policy.",
            "Engineering requires pushed passing validation and frozen implementation first,",
            "then saved admission replay, then new DESIGN on 154/159 only with 3 calls/task,",
            "30 adaptation episodes/task, reserve16 unchanged and fresh evaluation-only K16.",
            "Reporting precedence and limitations are exactly those in the frozen design document.",
            "",
        ]
    )
    write_exact(path, "\n".join(lines).encode())


@contextmanager
def stage_operation(directory: Path, name: str, metadata: dict[str, Any]) -> Iterator[None]:
    path = directory / "operations" / (name + ".json")
    if path.exists():
        raise InfraError("stage operation already dispatched: " + name, kind="crash_uncertainty")
    write_json(path, {"status": "dispatched", "metadata": metadata, "started": time.time()})
    try:
        yield
    except BaseException as exc:
        write_json(
            path, {"status": "interrupted", "metadata": metadata, "error": interruption(exc)}
        )
        raise
    else:
        write_json(path, {"status": "completed", "metadata": metadata, "finished": time.time()})


def validation_decision(
    cases: list[dict[str, Any]], outcomes: list[dict[str, Any]], error: dict[str, Any] | None = None
) -> dict[str, Any]:
    by_id = {r["case_id"]: r for r in outcomes}
    mismatches, repeats = [], []
    for case in cases:
        row = by_id.get(case["case_id"])
        actual = row["result"]["decision"]["verdict"] if row else None
        expected = case["expected_verdict"]
        if expected is not None and actual != expected:
            mismatches.append({"case_id": case["case_id"], "expected": expected, "actual": actual})
        if case.get("repeat_of"):
            prior = by_id.get(case["repeat_of"])
            agreement = bool(
                row
                and prior
                and actual == prior["result"]["decision"]["verdict"]
                and row["result"]["input_sha256"] == prior["result"]["input_sha256"]
                and row["result"]["config_sha256"] == prior["result"]["config_sha256"]
                and row["result"]["prompt_sha256"] == prior["result"]["prompt_sha256"]
                and row["result"]["schema_sha256"] == prior["result"]["schema_sha256"]
            )
            repeats.append({"case_id": case["repeat_of"], "agreement": agreement})
    ready = (
        error is None
        and len(outcomes) == len(cases)
        and not mismatches
        and all(r["agreement"] for r in repeats)
        and len(repeats) == 4
    )
    return {
        "decision": "JUDGE_GATE_READY" if ready else "JUDGE_GATE_NOT_READY",
        "mismatches": mismatches,
        "repeats": repeats,
        "cases_completed": len(outcomes),
        "cases_expected": len(cases),
        "interruption": error,
    }


def validate() -> dict[str, Any]:
    freeze = ensure_frozen()
    cases = verify_validation_inputs()
    initialize_cap(VALIDATION / "cap.json", "validation")
    outcomes: list[dict[str, Any]] = []
    error = None
    try:
        for index, case in enumerate(cases, 1):
            request = PrivilegeJudgeInput.model_validate_json(private_input_path(case).read_text())
            with stage_operation(VALIDATION, f"judge-{index:02}", {"case": case, "freeze": freeze}):
                judge = make_judge("validation", str(case["task_id"]), "judge_validation")
                judgment = judge.judge(request)
                full = judgment.as_record()
                row = {
                    "case_id": case["case_id"],
                    "expected_verdict": case["expected_verdict"],
                    "role": case["role"],
                    "result": {k: v for k, v in full.items() if k not in ("request", "response")},
                    "full_judge_record_sha256": digest(full),
                }
                outcomes.append(row)
                append_jsonl(VALIDATION / "judgments.jsonl", {**row, "result": full})
                write_json(
                    VALIDATION / "result.json",
                    {
                        **validation_decision(cases, outcomes),
                        "outcomes": outcomes,
                        "freeze": freeze,
                    },
                )
            print(
                json.dumps(
                    {"validation": index, "case": case["case_id"], "verdict": judgment.verdict}
                ),
                flush=True,
            )
    except BaseException as exc:
        error = interruption(exc)
        with cap_lock(VALIDATION / "cap.json") as state:
            state["stopped"] = state.get("stopped") or error["kind"]
    result = {
        **validation_decision(cases, outcomes, error),
        "outcomes": outcomes,
        "freeze": freeze,
        "cap": json.loads((VALIDATION / "cap.json").read_text()),
    }
    if error and error["kind"] in ("implementation", "provider_mismatch", "pricing_mismatch"):
        result["decision"] = "IMPLEMENTATION_FAILURE"
    write_json(VALIDATION / "result.json", result)
    return result


def verify_validation_result(result: dict[str, Any]) -> None:
    full_rows = jsonl(VALIDATION / "judgments.jsonl")
    if len(full_rows) != len(result["outcomes"]):
        raise ConfigError("validation full/compact record counts differ")
    for compact, full in zip(result["outcomes"], full_rows, strict=True):
        expected = {
            **full,
            "result": {k: v for k, v in full["result"].items() if k not in ("request", "response")},
        }
        if compact != expected or digest(full["result"]) != compact["full_judge_record_sha256"]:
            raise ConfigError("compact validation record differs from original judge audit")


def verify_frozen_validation_result() -> dict[str, Any]:
    public_result = json.loads((FROZEN / "validation_result.json").read_text())
    private_payload = (VALIDATION / "result.json").read_text()
    result: dict[str, Any] = json.loads(private_payload)
    verify_validation_result(result)
    expected_public = public_validation_result(
        result, private_result_sha256=digest(private_payload)
    )
    if result.get("decision") != "JUDGE_GATE_READY" or public_result != expected_public:
        raise ConfigError("engineering requires exact private validation and public hash binding")
    return result


def freeze_validation() -> None:
    ensure_frozen()
    result = json.loads((VALIDATION / "result.json").read_text())
    verify_validation_result(result)
    computed = validation_decision(
        verify_validation_inputs(), result["outcomes"], result.get("interruption")
    )
    if result["decision"] != "JUDGE_GATE_READY" or computed["decision"] != "JUDGE_GATE_READY":
        raise ConfigError("judge validation did not pass; engineering prohibited")
    check_cap(VALIDATION / "cap.json", "validation freeze")
    public = public_validation_result(
        result, private_result_sha256=digest((VALIDATION / "result.json").read_text())
    )
    write_exact(FROZEN / "validation_result.json", (canonical_json(public) + "\n").encode())
    write_prereg_template(True)


def replay_saved() -> dict[str, Any]:
    freeze = ensure_frozen(adaptation=True)
    initialize_cap(RUN / "cap.json", "engineering")
    saved = json.loads((PRIVATE / "saved_candidates.json").read_text())
    result: dict[str, Any] = {
        "status": "running",
        "cases": [],
        "freeze": freeze,
        "interruption": None,
    }
    write_json(RUN / "saved_replay.json", result)
    try:
        sub = build(designer=False)
        for record in saved:
            task, index = record["task_id"], record["call_index"]
            shared: dict[str, Any] = {
                "active_call": index,
                "audit_prefix": f"saved_replay/task-{task}/C{index}",
            }
            screen = make_screen(sub, task, shared)
            failures = failures_for(task)
            evidence = serialize_low(failures, 0.0, 16, read_reference(task), rich=True)

            def prohibited(*args: Any, **kwargs: Any) -> Any:
                raise ConfigError("saved replay attempted DESIGN, solvability or policy")

            optimizer = JudgedLowOptimizer(
                evidence,
                failures,
                read_reference(task),
                task_goal(failures),
                task_id=str(task),
                propose=prohibited,
                certify=prohibited,
                measure=prohibited,
                remaining=lambda: 0,
                endpoint_reserve=16,
                screen=screen.screen,
            )
            with operation(f"saved-replay-{task}-C{index}", {"task": task, "saved_call": index}):
                family, structural, privilege = optimizer._validate(record["arguments"])
                row = {
                    "task_id": task,
                    "saved_call_index": index,
                    "source_sha256": digest(record["arguments"]["families"][0]["rules_code"]),
                    "structural": structural,
                    "hard_or_semantic_rejections": privilege,
                    "admitted": family is not None and not structural and not privilege,
                    "judge_records": shared["semantic_records"],
                    "expected_verdict": None,
                }
                result["cases"].append(row)
                write_json(RUN / "saved_replay.json", result)
        result["status"] = "completed"
    except BaseException as exc:
        result["interruption"] = interruption(exc)
        result["status"] = "interrupted"
        stop(result["interruption"])
    write_json(RUN / "saved_replay.json", result)
    return result


def stop(error: dict[str, Any]) -> None:
    if (RUN / "cap.json").exists():
        with cap_lock(RUN / "cap.json") as state:
            state["stopped"] = state.get("stopped") or error["kind"]
    write_json(RUN / "STOP.json", error)


def adapt() -> dict[str, Any]:
    freeze = ensure_frozen(adaptation=True)
    prepared = verify_input_set()
    if (RUN / "results.json").exists():
        raise ConfigError("engineering DESIGN already dispatched; no implicit resume")
    replay = json.loads((RUN / "saved_replay.json").read_text())
    if replay["status"] != "completed" or replay["interruption"] or len(replay["cases"]) != 4:
        raise ConfigError("full saved admission replay has not completed")
    cost_check("new DESIGN after saved replay")
    results: dict[str, Any] = {
        "tasks": {
            str(r["task_id"]): {"original": r, "status": "pending", "summary": None}
            for r in prepared
        },
        "freeze": freeze,
        "saved_replay_sha256": digest((RUN / "saved_replay.json").read_text()),
        "interruption": None,
    }
    write_json(RUN / "results.json", results)
    try:
        sub = build(designer=True)
        for original in prepared:
            task = original["task_id"]
            ensure_frozen(adaptation=True)
            row = results["tasks"][str(task)]
            shared: dict[str, Any] = {}
            shared["screen"] = make_screen(sub, task, shared)
            row["status"] = "adapting"
            write_json(RUN / "results.json", results)
            row["summary"] = run_task(sub, task, shared)
            write_json(RUN / "results.json", results)
            confirm(sub, task, row["summary"], shared["screen"])
            row["status"] = "completed"
            write_json(RUN / "results.json", results)
    except BaseException as exc:
        results["interruption"] = interruption(exc)
        stop(results["interruption"])
    finally:
        for task, row in results["tasks"].items():
            partial = RUN / f"task-{task}/adaptation/summary.json"
            if row["summary"] is None and partial.exists():
                row["summary"] = json.loads(partial.read_text())
        write_json(RUN / "results.json", results)
    report()
    return results


def decision_for(results: dict[str, Any], cap: dict[str, Any]) -> dict[str, Any]:
    rows = list(results["tasks"].values())
    summaries = [r["summary"] for r in rows if r.get("summary")]
    completed = [r for r in rows if r["status"] == "completed"]
    error = results.get("interruption")
    endpoints = sum(
        any(c.get("endpoint") is not None for c in s.get("candidates", [])) for s in summaries
    )
    accepts = sum(bool(s.get("search_accepted")) for s in summaries)
    confirmed = sum(bool(s.get("confirmation", {}).get("in_band_l")) for s in summaries)
    confirmations = sum(s.get("confirmation", {}).get("n") == 16 for s in summaries)
    normal_exhaustion = sum(
        s.get("completed_without_infrastructure_failure") is True
        and s.get("designer_calls") == 3
        and not any(c.get("endpoint") is not None for c in s.get("candidates", []))
        for s in summaries
    )
    repeated_gate_rejections = sum(
        sum(
            bool(c.get("privilege")) and any("llm_privilege_" in p for p in c.get("privilege", []))
            for c in s.get("candidates", [])
        )
        >= 2
        for s in summaries
    )
    correctness = results.get("correctness_audit", {}).get("decision") == "IMPLEMENTATION_FAILURE"
    if (
        correctness
        or cap.get("bound_violation")
        or cap.get("accounting_error")
        or (
            error
            and error["kind"]
            in ("implementation", "smoke_bound_error", "provider_mismatch", "pricing_mismatch")
        )
    ):
        decision = "IMPLEMENTATION_FAILURE"
    elif error or len(completed) != 2 or (accepts and confirmations != accepts):
        decision = "INCOMPLETE"
    elif accepts and confirmations == accepts and not confirmed:
        decision = "LOW_PIPELINE_FUNCTIONAL_BUT_NO_USEFUL_ENV"
    elif accepts and (endpoints == 2 or (endpoints == 1 and normal_exhaustion >= 1)):
        decision = "LOW_IMPLEMENTATION_WORKS"
    elif endpoints:
        decision = "LOW_PIPELINE_FUNCTIONAL_BUT_NO_USEFUL_ENV"
    elif repeated_gate_rejections == 2 and results.get("judge_precision_blocking_verified") is True:
        decision = "JUDGE_GATE_BLOCKING"
    else:
        decision = "INCOMPLETE"
    return {
        "decision": decision,
        "endpoint_tasks": endpoints,
        "search_accepts": accepts,
        "completed_K16": confirmations,
        "K16_B_L": confirmed,
        "K16_B_T": sum(bool(s.get("confirmation", {}).get("in_band_t")) for s in summaries),
        "completed_tasks": len(completed),
        "repeated_judge_rejection_tasks": repeated_gate_rejections,
        "interruption": error,
        "engineering_only": True,
        "fresh_scientific_efficacy": False,
        "end_to_end_functional_viability": decision == "LOW_IMPLEMENTATION_WORKS" and confirmed > 0,
    }


def spend(directory: Path) -> dict[str, Any]:
    rows = [r for p in directory.glob("ledger*.jsonl") for r in jsonl(p)]
    state = (
        json.loads((directory / "cap.json").read_text())
        if (directory / "cap.json").exists()
        else None
    )
    return {
        "returned_ledger_usd": sum(float(r.get("usd", 0)) for r in rows),
        "cap": state,
        "conservative_committed_usd": committed_cost(state) if state else 0,
        "call_rows": sum(r.get("event") == "call" for r in rows),
        "policy_rollout_rows": sum(r.get("event") == "rollout" for r in rows),
    }


def report() -> dict[str, Any]:
    validation = (
        json.loads((VALIDATION / "result.json").read_text())
        if (VALIDATION / "result.json").exists()
        else None
    )
    if (RUN / "results.json").exists():
        results = json.loads((RUN / "results.json").read_text())
        result = decision_for(results, json.loads((RUN / "cap.json").read_text()))
    elif (RUN / "STOP.json").exists():
        error = json.loads((RUN / "STOP.json").read_text())
        result = {
            "decision": "IMPLEMENTATION_FAILURE"
            if error["kind"] in ("implementation", "provider_mismatch", "pricing_mismatch")
            else "INCOMPLETE",
            "interruption": error,
        }
    else:
        result = {"decision": validation["decision"] if validation else "PREPARED"}
    result.update(
        validation_cost=spend(VALIDATION),
        engineering_cost=spend(RUN),
        validation_decision=validation["decision"] if validation else None,
    )
    write_json(PRIVATE / "report.json", result)
    write_json(BASE / "report.json", public_report(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=("prepare", "validate", "freeze", "replay", "adapt", "report")
    )
    args = parser.parse_args()
    actions = {
        "prepare": prepare,
        "validate": validate,
        "freeze": freeze_validation,
        "replay": replay_saved,
        "adapt": adapt,
        "report": report,
    }
    try:
        value = actions[args.stage]()
        if value is not None:
            print(
                json.dumps(
                    public_stage_summary(value),
                    sort_keys=True,
                ),
                flush=True,
            )
        if args.stage == "validate":
            assert value is not None
            return 0 if value["decision"] == "JUDGE_GATE_READY" else 2
        if args.stage == "replay":
            assert value is not None
            return 0 if value["status"] == "completed" else 2
        if args.stage == "adapt":
            assert value is not None
            return 0 if value["interruption"] is None else 2
        return 0
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        write_json(PRIVATE / f"{args.stage}_interruption.json", interruption(exc))
        print(
            json.dumps({"stage": args.stage, "error_sha256": digest(interruption(exc))}), flush=True
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
