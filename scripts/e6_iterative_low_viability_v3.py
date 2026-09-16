"""One-task ZERO top-up and frozen one-arm LOW viability continuation.

Production method code is imported unchanged. Experiment configuration permits three
designer calls and thirty adaptation episodes; original screening and K16 are separate.
The shared physical-request dollar guard survives every stage and never resets spending.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
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
from aea.llm.attribution import current_attribution
from aea.llm.envharness_client import AeaLLMClient
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.low_optimizer import Feedback, iterative_messages, propose_low
from aea.rules_control import assist_bracket
from aea.semantic_low import LowPrivilegeScreen, ScreenedLowOptimizer, SemanticAdmissionError
from aea.semantic_privilege import SCREEN_VERSION
from aea.session import SESSION_LOCK
from aea.stage import seeded_failures
from aea.substrate import AeaSubstrate
from aea.witness import Solvable, solvable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e3
import e6_iterative_low_smoke as historical

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/e6-iterative-low-viability-v3"
EXP = ROOT / "experiments/alfworld_e6"
FROZEN = EXP / "frozen/iterative_low_viability_v3"
POOL_PREREG = EXP / "PREREG_ITERATIVE_LOW_TOPUP.md"
PREREG = EXP / "PREREG_ITERATIVE_LOW_VIABILITY_V3.md"
VALIDATOR_SHA = "bec74ed8a6ff40e119b2299c92b07b8602ff5fef"
METHOD = "llm_v2_iterative_low_semantic_gate"
SCREENING_CAP_USD = 4.0
ADAPTATION_CONFIRMATION_CAP_USD = 25.0
CAP_USD = SCREENING_CAP_USD + ADAPTATION_CONFIRMATION_CAP_USD
CORE_TASKS = (154, 158, 159)
TOPUP_TASK_LIMIT = 10
PRIOR_RUN = ROOT / "runs/e6-iterative-low-viability-v2"
PRIOR_EVIDENCE = EXP / "results/iterative_low_viability_v2/screening_qualified_evidence.json"
DESIGNER_CALL_CAP = 3
ADAPTATION_CAP = 30
MAX_EPISODE_EXECUTIONS_PER_VALID_SLOT = 3
BASE_DRIVER_SHA = "c230bcfaea60b3c1b346018a5a7380c96d67c25e4f8fbe75702aef517d6129f4"
BASE_DRIVER_COMMIT = "b6cd05418f619ad23318e55916aaae2a96d07875"
ARM = "iterative_low"
RATES = historical.RATES
digest = historical.digest
git = historical.git
jsonl = historical.jsonl
committed_cost = historical.committed_cost
FROZEN_INPUTS = (
    "scripts/e3.py",
    "scripts/e6_iterative_low_smoke.py",
    "configs/pricing.yaml",
    "configs/corpus_aea.yaml",
    "configs/alfworld_config_100.yaml",
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
def cap_lock(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            raise ConfigError("missing initialized shared monetary cap")
        state = json.loads(path.read_text())
        if (
            state.get("total_limit_usd") != CAP_USD
            or state.get("screening_limit_usd") != SCREENING_CAP_USD
            or state.get("adaptation_confirmation_limit_usd") != ADAPTATION_CONFIRMATION_CAP_USD
        ):
            raise ConfigError("shared cap differs from frozen experiment limits")
        try:
            yield state
        finally:
            write_json(path, state)
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize_cap() -> None:
    path = RUN / "cap.json"
    if path.exists():
        raise ConfigError("run monetary state already exists; refusing a fresh paid start")
    write_json(
        path,
        {
            "actual_usd": 0.0,
            "uncertain_usd": 0.0,
            "inflight": {},
            "attempts": 0,
            "phase": "screening",
            "total_limit_usd": CAP_USD,
            "screening_limit_usd": SCREENING_CAP_USD,
            "adaptation_confirmation_limit_usd": ADAPTATION_CONFIRMATION_CAP_USD,
        },
    )


class CappedTransport:
    """Historical reservation arithmetic, with this run's frozen phase and total limits."""

    def __init__(self, transport: Callable[..., Any], cap_path: Path) -> None:
        self.transport, self.cap_path = transport, cap_path

    def __call__(self, **wire: Any) -> Any:
        model = str(wire["model"])
        inp, out = RATES[model]
        input_bound = len(json.dumps(wire, ensure_ascii=False).encode()) + 4096
        output_bound = int(wire.get("max_tokens") or wire.get("max_completion_tokens") or 0)
        if output_bound <= 0:
            raise ConfigError("unbounded output request refused")
        reserve = (input_bound * inp + output_bound * out) / 1_000_000
        attempt = uuid.uuid4().hex
        attribution, _ = current_attribution()
        stopped = ""
        with cap_lock(self.cap_path) as state:
            phase = state["phase"]
            if phase not in ("screening", "adaptation"):
                raise ConfigError("physical request outside an enabled paid phase")
            limit = phase_limit(state, self.cap_path)
            if state.get("bound_violation"):
                state["stopped"] = "bound_violation"
            if state.get("stopped"):
                stopped = str(state["stopped"])
            elif committed_cost(state) + reserve >= limit:
                state["stopped"] = stopped = (
                    "screening_cost_cap" if phase == "screening" else "cost_cap"
                )
            else:
                state["inflight"][attempt] = reserve
                state["attempts"] += 1
        if stopped:
            kind = "smoke_bound_error" if stopped == "bound_violation" else "smoke_cost_cap"
            raise InfraError(f"physical API calls stopped: {stopped}", kind=kind)
        started = time.time()
        metadata = {
            "attempt": attempt,
            "model": model,
            "phase": phase,
            "attribution": attribution.model_dump(mode="json"),
            "reserved_usd": reserve,
            "started": started,
        }
        try:
            completion = self.transport(**wire)
        except BaseException:
            with cap_lock(self.cap_path) as state:
                state["uncertain_usd"] += state["inflight"].pop(attempt)
            append_jsonl(
                self.cap_path.with_suffix(".attempts.jsonl"),
                {**metadata, "status": "ambiguous_failure"},
            )
            raise
        usage = completion.usage
        tokens_in = int(usage.prompt_tokens) if usage else input_bound
        tokens_out = int(usage.completion_tokens) if usage else output_bound
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
                **metadata,
                "status": "returned",
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
        run_id=RUN.name,
        policy_llm=e3.policy_qwen(),
        designer_llm=e3.designer_deepseek() if designer else None,
        aea_config=config(),
        stage_config_path=e3.STAGE_CONFIG,
        pricing_path=e3.PRICING,
        rollout_concurrency=1,
        subprocess_timeout_s=600.0,
    )
    sub.policy_spec_kwargs["client_factory"] = (
        "scripts.e6_iterative_low_viability_v3:CappedPolicyClient"
    )
    sub.policy_spec_kwargs["client_kwargs"]["cap_path"] = str(RUN / "cap.json")
    if sub._designer is not None:
        sub._designer._transport = CappedTransport(sub._designer._transport, RUN / "cap.json")
    return sub


def ensure_frozen(*, adaptation: bool = False) -> dict[str, Any]:
    prereg = PREREG if adaptation else POOL_PREREG
    paths = [
        "used_task_audit.json",
        "runtime_hashes.json",
        "core_manifest.json",
        *(["input_manifest.json"] if adaptation else []),
    ]
    if not prereg.exists():
        raise ConfigError("missing paid-stage preregistration")
    relative = str(prereg.relative_to(ROOT))
    driver = "scripts/e6_iterative_low_viability_v3.py"
    if git("branch", "--show-current") != "aea-llm-vnext":
        raise ConfigError("wrong research branch")
    if git("status", "--porcelain", "--", "src/aea", driver, relative, *FROZEN_INPUTS):
        raise ConfigError("frozen production, driver, configuration or preregistration is dirty")
    tree = git("rev-parse", f"{VALIDATOR_SHA}:src/aea")
    if tree != git("rev-parse", "HEAD:src/aea") or git("diff", VALIDATOR_SHA, "--", *FROZEN_INPUTS):
        raise ConfigError("production method or frozen substrate changed")
    commit = git("log", "-1", "--format=%H", "--", relative)
    git("merge-base", "--is-ancestor", commit, "origin/aea-llm-vnext")
    gate = digest((ROOT / "src/aea/semantic_privilege.py").read_text())
    driver_hash = digest(Path(__file__).read_text())
    text = prereg.read_text()
    base_driver = ROOT / "scripts/e6_iterative_low_viability_v2.py"
    if digest(base_driver.read_text()) != BASE_DRIVER_SHA:
        raise ConfigError("historical base driver changed")
    if (
        digest(git("show", f"{BASE_DRIVER_COMMIT}:scripts/e6_iterative_low_viability_v2.py") + "\n")
        != BASE_DRIVER_SHA
    ):
        raise ConfigError("base driver commit/source provenance differs")
    for required in (
        VALIDATOR_SHA,
        METHOD,
        SCREEN_VERSION,
        gate,
        driver_hash,
        BASE_DRIVER_SHA,
        BASE_DRIVER_COMMIT,
    ):
        if required not in text:
            raise ConfigError("preregistration does not freeze an exact method/driver identifier")
    hashes = {}
    for name in paths:
        path = FROZEN / name
        content = path.read_text()
        if content.strip() != git("show", f"{commit}:{path.relative_to(ROOT)}").strip():
            raise ConfigError("frozen input changed after preregistration: " + name)
        hashes[name] = digest(content)
        if hashes[name] not in text:
            raise ConfigError("preregistration omits input artifact hash: " + name)
    runtime = json.loads((FROZEN / "runtime_hashes.json").read_text())
    required_runtime = {
        "third_party/envharness/envharness/bridges/alfworld/bridge.py",
        "third_party/envharness/envharness/harnesses/rules.py",
        "third_party/envharness/envharness/core/code_loader.py",
        "third_party/envharness/envharness/agents/policy.py",
        "third_party/envharness/envharness/orchestration/episode_worker.py",
        "third_party/envharness/envharness/orchestration/runner.py",
    }
    if not required_runtime.issubset(runtime):
        raise ConfigError("frozen runtime inventory omits required bridge/wrapper/policy sources")
    for name, expected in runtime.items():
        if digest((ROOT / name).read_text()) != expected:
            raise ConfigError("frozen runtime source changed: " + name)
    return {
        "implementation_sha": VALIDATOR_SHA,
        "validator_fidelity_sha": VALIDATOR_SHA,
        "source_tree": tree,
        "prereg_commit": commit,
        "prereg_sha256": digest(text),
        "driver_sha256": driver_hash,
        "base_driver_sha256": BASE_DRIVER_SHA,
        "base_driver_commit": BASE_DRIVER_COMMIT,
        "semantic_gate_sha256": gate,
        "semantic_gate_version": SCREEN_VERSION,
        "input_hashes": hashes,
        "frozen_config_hashes": {name: digest((ROOT / name).read_text()) for name in FROZEN_INPUTS},
    }


def cost_check(where: str) -> None:
    with cap_lock(RUN / "cap.json") as state:
        if state.get("bound_violation"):
            raise ConfigError("monetary request bound violation")
        if state.get("inflight"):
            raise InfraError("unresolved physical request reservation", kind="crash_uncertainty")
        limit = phase_limit(state)
        if state.get("stopped") or committed_cost(state) >= limit:
            raise InfraError("hard physical cost cap: " + where, kind="smoke_cost_cap")


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


def stop(error: dict[str, Any]) -> None:
    with cap_lock(RUN / "cap.json") as state:
        state["stopped"] = state.get("stopped") or error["kind"]
    write_json(RUN / "STOP.json", error)


def ledger_rows() -> list[dict[str, Any]]:
    return [row for path in sorted(RUN.glob("ledger.*.jsonl")) for row in jsonl(path)]


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


def validate_screening_trace(trace: Trace, task: int, seen_ids: set[str]) -> None:
    """Check identity/provenance even when an execution has no behavioral outcome."""
    if trace.rollout_seed != task or not trace.episode_id:
        raise ConfigError("wrong original environment seed or missing episode identity")
    if trace.episode_id in seen_ids:
        raise ConfigError("screening reused an episode identity")
    if trace.candidate.rules_code or trace.candidate.in_env_actions:
        raise ConfigError("screening trace differs from the dispatched original environment")
    fatal = (
        "provider_mismatch",
        "pricing_mismatch",
        "smoke_bound_error",
        "ConfigError",
        "RulesCodeError",
    )
    error_context = (trace.error or "") + "\n" + (trace.subprocess_stderr or "")
    if trace.error and any(marker in error_context for marker in fatal):
        raise ConfigError("screening provenance/configuration failure: " + trace.error)
    if not trace.error and (
        not trace.steps
        or trace.duration_steps != len(trace.steps)
        or trace.duration_steps > config().impl.policy_max_steps
    ):
        raise ConfigError("completed screening trace has inconsistent episode length")
    seen_ids.add(trace.episode_id)


def reconcile_screening_inflight(task: int, phase: str, *, child_returned: bool) -> int:
    """Retain killed/exited worker reservations; never refund an ambiguous request.

    Called only after n=1 frozen SubprocessRunner has returned an errored Trace. Its
    subprocess.run has already waited, including kill-and-wait on timeout. A fresh
    pre-dispatch cost_check proved no older in-flight requests existed. If the call
    itself raises, worker completion is unknown and this helper must not reconcile.
    """
    with cap_lock(RUN / "cap.json") as state:
        if state.get("bound_violation"):
            raise ConfigError("monetary request bound violation")
        if not child_returned:
            raise InfraError(
                "worker completion unknown; reservation retained in-flight",
                kind="crash_uncertainty",
            )
        if state["phase"] != "screening":
            raise ConfigError("orphan reconciliation outside sequential screening")
        orphans = dict(state["inflight"])
        for attempt, reserve in orphans.items():
            state["uncertain_usd"] += state["inflight"].pop(attempt)
            append_jsonl(
                RUN / "cap.attempts.jsonl",
                {
                    "attempt": attempt,
                    "model": "qwen/qwen3-8b",
                    "phase": "screening",
                    "status": "orphan_reconciled",
                    "reserved_usd": reserve,
                    "started": None,
                    "reconciled_at": time.time(),
                    "attribution": {
                        "phase": phase,
                        "budget": "eval",
                        "arm": "screen",
                        "task_id": str(task),
                    },
                    "resolution": "worker_returned_error_after_exit_or_timeout_kill_and_wait",
                    "behavioral_outcome": None,
                },
            )
        return len(orphans)


def screening_stop_check() -> None:
    """A sticky cost stop ends the whole screen; it is never a reason to try another ID."""
    with cap_lock(RUN / "cap.json") as state:
        if state.get("bound_violation") or state.get("stopped") == "bound_violation":
            raise ConfigError("monetary request bound violation")
        if (
            state.get("stopped") in ("screening_cost_cap", "cost_cap")
            or committed_cost(state) >= SCREENING_CAP_USD
        ):
            raise InfraError("hard screening committed-cost cap", kind="smoke_cost_cap")
        if state.get("stopped"):
            raise InfraError(
                "physical transport stopped: " + str(state["stopped"]),
                kind="screening_transport_stop",
            )


def phase_limit(state: dict[str, Any], cap_path: Path | None = None) -> float:
    """Cumulative ceiling for the active phase; historical top-up spend never resets."""
    if state["phase"] == "screening":
        return SCREENING_CAP_USD
    if state["phase"] != "adaptation":
        raise ConfigError("physical cost check outside an enabled paid phase")
    path = (cap_path or RUN / "cap.json").parent / "topup_cost_baseline.json"
    if not path.exists() or digest(path.read_text()) != state.get("screening_baseline_sha256"):
        raise ConfigError("missing or changed immutable top-up cost baseline")
    baseline = json.loads(path.read_text())
    spent = float(baseline["screening_committed_usd"])
    if (
        baseline["screening_status"] != "qualified"
        or spent != state.get("screening_committed_usd")
        or not 0 <= spent < SCREENING_CAP_USD
        or abs(spent - baseline["actual_usd"] - baseline["uncertain_usd"]) > 1e-9
        or state["actual_usd"] < baseline["actual_usd"]
        or state["uncertain_usd"] < baseline["uncertain_usd"]
        or state["attempts"] < baseline["physical_attempts"]
    ):
        raise ConfigError("historical top-up spend was changed or refunded")
    return min(CAP_USD, spent + ADAPTATION_CONFIRMATION_CAP_USD)


def selected_failures(task: int, traces: list[Trace]) -> list[Trace]:
    """Reuse the prior sampled order exactly; only Z4 performs a new seeded selection."""
    if task not in CORE_TASKS:
        return seeded_failures(traces, config().impl.n_failed_rollouts, seed=task)
    manifest: dict[str, Any] = json.loads((FROZEN / "core_manifest.json").read_text())
    rows = [row for row in manifest["tasks"] if row["task_id"] == task]
    if len(rows) != 1:
        raise ConfigError("core evidence does not identify exactly one prior task")
    row = rows[0]
    indices = row["selected_valid_indices"]
    if (
        row["selection_seed"] != task
        or row["selection_n"] != 3
        or row["evidence_n"] != 16
        or len(indices) != 3
        or len(set(indices)) != 3
        or any(type(index) is not int or not 1 <= index <= 16 for index in indices)
        or len(traces) != 16
    ):
        raise ConfigError("prior core evidence selection changed")
    failures = [traces[index - 1] for index in indices]
    raw = [trace.model_dump(mode="json") for trace in failures]
    if (
        [trace.episode_id for trace in failures] != row["evidence_ids"]
        or [digest(trace) for trace in raw] != row["selected_trace_sha256"]
        or digest(raw) != row["evidence_sha256"]
    ):
        raise ConfigError("exact prior seeded three-trace evidence differs")
    return failures


def verify_core() -> dict[str, Any]:
    """Read-only binding of the three core tasks to the committed V2 evidence record."""
    manifest: dict[str, Any] = json.loads((FROZEN / "core_manifest.json").read_text())
    if [row["task_id"] for row in manifest["tasks"]] != list(CORE_TASKS):
        raise ConfigError("prior three-task core membership or order changed")
    if (
        ROOT / manifest["prior_screening_path"] != PRIOR_RUN / "screening.json"
        or ROOT / manifest["prior_qualified_evidence_path"] != PRIOR_EVIDENCE
    ):
        raise ConfigError("core source paths differ from the frozen V2 namespace")
    prior_text = PRIOR_EVIDENCE.read_text()
    if digest(prior_text) != manifest["prior_qualified_evidence_sha256"]:
        raise ConfigError("prior committed evidence file changed")
    if (
        prior_text.strip()
        != git("show", f"{manifest['prior_commit']}:{PRIOR_EVIDENCE.relative_to(ROOT)}").strip()
    ):
        raise ConfigError("core evidence differs from the prior committed result")
    previous = json.loads(prior_text)
    screening_text = (PRIOR_RUN / "screening.json").read_text()
    if (
        digest(screening_text) != manifest["prior_screening_sha256"]
        or digest(screening_text) != previous["screening_sha256"]
        or previous["tasks"] != manifest["tasks"]
        or previous["qualified_task_ids"] != list(CORE_TASKS)
    ):
        raise ConfigError("prior screening or exact core evidence provenance changed")
    screening = json.loads(screening_text)
    if screening["status"] != "SCREENING_COST_LIMIT" or screening["qualified"] != list(CORE_TASKS):
        raise ConfigError("prior V2 result or core qualification changed")
    required_files = {}
    all_ids: set[str] = set()
    for row in manifest["tasks"]:
        task = int(row["task_id"])
        traces = frozen_valid_traces(task, screening["tasks"][str(task)], source_run=PRIOR_RUN)
        raw = [trace.model_dump(mode="json") for trace in traces]
        ids = [trace.episode_id for trace in traces]
        if (
            ids != row["all_original_episode_ids"]
            or [digest(trace) for trace in raw] != row["all_original_trace_sha256"]
            or digest(raw) != row["original_zero_evidence_sha256"]
            or all_ids.intersection(ids)
        ):
            raise ConfigError("prior core original evidence differs or reuses an episode ID")
        all_ids.update(ids)
        selected_failures(task, traces)
        for artifact in row["all_execution_artifacts"] + row["valid_original_artifacts"]:
            relative = Path(artifact["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ConfigError("invalid prior original artifact path")
            source = PRIOR_RUN / relative
            name = str(source.relative_to(ROOT))
            if digest(source.read_text()) != artifact["file_sha256"]:
                raise ConfigError("prior original execution or valid alias bytes changed")
            required_files[name] = artifact["file_sha256"]
    if manifest["raw_file_hashes"] != required_files:
        raise ConfigError("core original file inventory differs from committed evidence")
    return manifest


def core_import_record(manifest: dict[str, Any]) -> dict[str, Any]:
    screening = json.loads((PRIOR_RUN / "screening.json").read_text())
    return {
        "core_manifest_sha256": digest((FROZEN / "core_manifest.json").read_text()),
        "prior_commit": manifest["prior_commit"],
        "all_episode_ids": [
            episode for row in manifest["tasks"] for episode in row["all_original_episode_ids"]
        ],
        "tasks": {str(task): screening["tasks"][str(task)] for task in CORE_TASKS},
    }


def import_core() -> dict[str, Any]:
    """Copy verified original bytes into the new namespace without rerunning an episode."""
    manifest = verify_core()
    if (RUN / "core_import.json").exists():
        raise ConfigError("core already imported; refusing implicit continuation resume")
    copies = [
        (ROOT / name, RUN / (ROOT / name).relative_to(PRIOR_RUN))
        for name in manifest["raw_file_hashes"]
    ]
    if any(target.exists() for _, target in copies):
        raise ConfigError("partial or preexisting core copies; refusing to overwrite evidence")
    record = core_import_record(manifest)
    with operation("import-core", {"tasks": list(CORE_TASKS), "policy_rollouts": 0}):
        for source, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(source.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
        write_json(RUN / "core_import.json", record)
    return record


def combined_screening() -> dict[str, Any]:
    manifest = verify_core()
    imported = json.loads((RUN / "core_import.json").read_text())
    if imported != core_import_record(manifest):
        raise ConfigError("imported core provenance changed")
    topup = json.loads((RUN / "screening.json").read_text())
    allowed = json.loads((FROZEN / "used_task_audit.json").read_text())["never_used_ids"]
    if (
        topup["status"] != "qualified"
        or len(topup["qualified"]) != 1
        or topup["qualified"][0] not in allowed
        or topup["qualified"][0] <= 162
        or topup["core_manifest_sha256"] != imported["core_manifest_sha256"]
        or topup["core_tasks"] != list(CORE_TASKS)
    ):
        raise ConfigError("one prospectively qualified fresh top-up task is required")
    task = topup["qualified"][0]
    tasks = {**imported["tasks"], str(task): topup["tasks"][str(task)]}
    all_ids: set[str] = set()
    for task_id, record in tasks.items():
        originals = frozen_valid_traces(int(task_id), record)
        ids = {trace.episode_id for trace in originals}
        if all_ids.intersection(ids):
            raise ConfigError("combined ZERO evidence reuses an original episode identity")
        all_ids.update(ids)
    return {
        "status": "qualified",
        "qualified": [*CORE_TASKS, task],
        "tasks": tasks,
        "core_import_sha256": digest((RUN / "core_import.json").read_text()),
        "topup_screening_sha256": digest((RUN / "screening.json").read_text()),
    }


def screen() -> None:
    freeze = ensure_frozen()
    audit = json.loads((FROZEN / "used_task_audit.json").read_text())
    tasks = audit["never_used_ids"]
    if (
        len(tasks) != TOPUP_TASK_LIMIT
        or tasks != sorted(set(tasks))
        or any(type(t) is not int for t in tasks)
    ):
        raise ConfigError("audit must freeze exactly ten ascending never-used task IDs")
    if (RUN / "screening.json").exists():
        raise ConfigError("screening already started; no implicit resume or paid repeat")
    if any(t <= 162 for t in tasks) or tasks[0] != audit["smallest_never_used"]:
        raise ConfigError("top-up task order includes consumed IDs or skips the smallest unused ID")
    core = import_core()
    initialize_cap()
    result: dict[str, Any] = {
        "tasks": {},
        "qualified": [],
        "freeze": freeze,
        "status": "running",
        "core_manifest_sha256": core["core_manifest_sha256"],
        "core_tasks": list(CORE_TASKS),
    }
    write_json(RUN / "screening.json", result)
    active: dict[str, Any] | None = None
    try:
        sub = build(designer=False)
        seen_ids = set(core["all_episode_ids"])
        for task in tasks:
            ensure_frozen()
            active = {
                "task_id": task,
                "episodes": [],
                "valid_episode_indices": [],
                "valid_episodes": 0,
                "valid_successes": 0,
                "executions": 0,
                "recovered_provider_errors": 0,
                "recovered_episode_executions": 0,
                "recoveries": [],
                "status": "screening",
            }
            result["tasks"][str(task)] = active
            write_json(RUN / "screening.json", result)
            for valid_index in range(1, 17):
                slot_errors = 0
                slot_retry_events = 0
                slot_invalid_executions = 0
                for slot_attempt in range(1, MAX_EPISODE_EXECUTIONS_PER_VALID_SLOT + 1):
                    phase = f"screen:{task}:valid:{valid_index}:attempt:{slot_attempt}"
                    cost_check(phase)
                    execution_index = active["executions"] + 1
                    if execution_index > 16 * MAX_EPISODE_EXECUTIONS_PER_VALID_SLOT:
                        raise ConfigError("per-task fresh execution bound exceeded")
                    attempt_start = len(jsonl(RUN / "cap.attempts.jsonl"))
                    with operation(
                        f"screen-{task}-valid-{valid_index}-attempt-{slot_attempt}",
                        {
                            "task": task,
                            "n": 1,
                            "execution_index": execution_index,
                            "target_valid_index": valid_index,
                            "slot_attempt": slot_attempt,
                        },
                    ):
                        active["executions"] = execution_index
                        write_json(RUN / "screening.json", result)
                        try:
                            traces = sub.rollouts(
                                TaskRef(str(task), task),
                                Candidate(rationale="original"),
                                1,
                                attribution=Attribution(
                                    phase=phase, budget="eval", arm="screen", task_id=str(task)
                                ),
                            )
                        except (ConfigError, AssertionError):
                            raise
                        except Exception as exc:
                            # No returned Trace means the frozen runner's termination guarantee
                            # cannot be relied on. Preserve in-flight reservations and stop.
                            screening_stop_check()
                            if getattr(exc, "kind", "") in (
                                "provider_mismatch",
                                "pricing_mismatch",
                                "smoke_bound_error",
                            ):
                                raise ConfigError(
                                    "screening provenance/accounting failure: " + str(exc)
                                ) from exc
                            raise InfraError(
                                "screening dispatch raised without a returned trace: " + str(exc),
                                kind="crash_uncertainty",
                            ) from exc
                        trace_path = (
                            RUN / f"task-{task}/original-execution-{execution_index:02}.json"
                        )
                        raw_traces = [t.model_dump(mode="json") for t in traces]
                        write_json(trace_path, raw_traces)
                        if len(traces) != 1:
                            raise ConfigError(
                                "single-worker screening returned an inconsistent trace count"
                            )
                        trace = traces[0]
                        validate_screening_trace(trace, task, seen_ids)
                        if trace.error:
                            reconcile_screening_inflight(task, phase, child_returned=True)
                        attempts = jsonl(RUN / "cap.attempts.jsonl")[attempt_start:]
                        retries = [
                            r
                            for r in ledger_rows()
                            if r.get("phase") == phase
                            and r.get("event") in ("infra_retry", "infra_failure")
                        ]
                        if any(
                            r.get("error_kind")
                            in ("provider_mismatch", "pricing_mismatch", "smoke_bound_error")
                            for r in retries
                        ):
                            raise ConfigError(
                                "screening ledger reports a provenance/accounting failure"
                            )
                        provider_errors = sum(
                            r["status"] in ("ambiguous_failure", "orphan_reconciled")
                            for r in attempts
                        )
                        is_valid = not bool(trace.error)
                        record = {
                            "index": execution_index,
                            "execution_index": execution_index,
                            "target_valid_index": valid_index,
                            "slot_attempt": slot_attempt,
                            "phase": phase,
                            "is_valid": is_valid,
                            "behavioral_success": bool(trace.success) if is_valid else None,
                            "episode_ids": [trace.episode_id],
                            "trace_file": str(trace_path.relative_to(RUN)),
                            "trace_sha256": digest(raw_traces),
                            "file_sha256": digest(trace_path.read_text()),
                            "successes": int(bool(trace.success)) if is_valid else 0,
                            "terminal_errors": int(bool(trace.error)),
                            "missing_outcome_reason": trace.error,
                            "physical_provider_errors": provider_errors,
                            "provider_retry_or_failure_events": len(retries),
                        }
                        active["episodes"].append(record)
                        slot_errors += provider_errors
                        slot_retry_events += len(retries)
                        if is_valid:
                            validate_traces(traces, 1, task, Candidate())
                            # Preserve the original adaptation evidence filenames: their index
                            # identifies valid behavioral observations, never failed executions.
                            write_json(
                                RUN / f"task-{task}/original-{valid_index:02}.json", raw_traces
                            )
                            active["valid_episode_indices"].append(execution_index)
                            active["valid_episodes"] += 1
                            active["valid_successes"] += int(bool(trace.success))
                            if slot_errors or slot_retry_events or slot_invalid_executions:
                                active["recoveries"].append(
                                    {
                                        "status": "RECOVERED_PROVIDER_ERROR",
                                        "valid_index": valid_index,
                                        "episode_id": trace.episode_id,
                                        "physical_provider_errors": slot_errors,
                                        "provider_retry_or_failure_events": slot_retry_events,
                                        "failed_episode_executions": slot_invalid_executions,
                                    }
                                )
                                active["recovered_provider_errors"] += slot_errors
                                active["recovered_episode_executions"] += slot_invalid_executions
                        else:
                            slot_invalid_executions += 1
                        write_json(RUN / "screening.json", result)
                        screening_stop_check()
                        with cap_lock(RUN / "cap.json") as state:
                            if state["inflight"]:
                                raise ConfigError(
                                    "valid execution left an unexplained in-flight reservation"
                                )
                    if is_valid:
                        break
                else:
                    active["status"] = "INFRA_INCONCLUSIVE"
                    active["infrastructure_reason"] = "episode_execution_cap_exhausted"
                    break
                if active["valid_successes"]:
                    active["status"] = "NON_ZERO"
                    break
            else:
                if active["valid_episodes"] != 16 or active["valid_successes"] != 0:
                    raise ConfigError("ZERO qualification counters are inconsistent")
                active["status"] = "CONFIRMED_ZERO"
                active["original_k16"] = "0/16"
                result["qualified"].append(task)
            write_json(RUN / "screening.json", result)
            print(
                json.dumps(
                    {
                        "task": task,
                        "status": active["status"],
                        "valid_episodes": active["valid_episodes"],
                        "valid_successes": active["valid_successes"],
                        "executions": active["executions"],
                    }
                ),
                flush=True,
            )
            if len(result["qualified"]) == 1:
                break
        result["status"] = "qualified" if len(result["qualified"]) == 1 else "TOPUP_INCONCLUSIVE"
        if result["status"] == "TOPUP_INCONCLUSIVE":
            result["stop_reason"] = "task_limit"
        with cap_lock(RUN / "cap.json") as state:
            state["phase"] = "screening_complete"
            state["screening_committed_usd"] = committed_cost(state)
            write_json(
                RUN / "topup_cost_baseline.json",
                {
                    "screening_committed_usd": state["screening_committed_usd"],
                    "actual_usd": state["actual_usd"],
                    "uncertain_usd": state["uncertain_usd"],
                    "physical_attempts": state["attempts"],
                    "screening_status": result["status"],
                },
            )
            state["screening_baseline_sha256"] = digest(
                (RUN / "topup_cost_baseline.json").read_text()
            )
    except BaseException as exc:
        error = interruption(exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            error["kind"] = "infrastructure_interruption"
        result["interruption"] = error
        if error["kind"] in (
            "implementation",
            "smoke_bound_error",
            "provider_mismatch",
            "pricing_mismatch",
        ):
            result["status"] = "IMPLEMENTATION_FAILURE"
        elif error["kind"] == "smoke_cost_cap":
            result["status"] = "TOPUP_INCONCLUSIVE"
            result["stop_reason"] = "topup_cost_cap"
        else:
            result["status"] = "TOPUP_INCONCLUSIVE"
            result["stop_reason"] = error["kind"]
        if active is not None:
            active["status"] = (
                "IMPLEMENTATION_FAILURE"
                if result["status"] == "IMPLEMENTATION_FAILURE"
                else "INFRA_INCONCLUSIVE"
            )
            active["infrastructure_reason"] = error["kind"]
        stop(error)
    finally:
        write_json(RUN / "screening.json", result)
    print(json.dumps({"screening": result["status"], "qualified": result["qualified"]}), flush=True)


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


def frozen_valid_traces(
    task: int, task_screen: dict[str, Any], *, source_run: Path | None = None
) -> list[Trace]:
    """Bind all original execution artifacts and select exactly the sixteen valid failures."""
    artifact_root = RUN if source_run is None else source_run
    if (
        task_screen["status"] != "CONFIRMED_ZERO"
        or task_screen["valid_episodes"] != 16
        or task_screen["valid_successes"] != 0
        or len(task_screen["valid_episode_indices"]) != 16
        or task_screen["executions"] != len(task_screen["episodes"])
        or task_screen["executions"] > 16 * MAX_EPISODE_EXECUTIONS_PER_VALID_SLOT
    ):
        raise ConfigError("ZERO qualification does not contain exactly sixteen valid failures")
    selected: list[Trace] = []
    mapping = []
    seen_ids: set[str] = set()
    for index, record in enumerate(task_screen["episodes"], 1):
        path = artifact_root / f"task-{task}/original-execution-{index:02}.json"
        rows = json.loads(path.read_text())
        if (
            record["execution_index"] != index
            or record["trace_file"] != str(path.relative_to(artifact_root))
            or digest(path.read_text()) != record["file_sha256"]
            or digest(rows) != record["trace_sha256"]
            or len(rows) != 1
        ):
            raise ConfigError("original execution artifact differs from screening checkpoint")
        trace = Trace.model_validate(rows[0])
        validate_screening_trace(trace, task, seen_ids)
        if (
            record["episode_ids"] != [trace.episode_id]
            or record["terminal_errors"] != int(bool(trace.error))
            or record["target_valid_index"] != len(selected) + 1
            or not 1 <= record["slot_attempt"] <= MAX_EPISODE_EXECUTIONS_PER_VALID_SLOT
        ):
            raise ConfigError("screening checkpoint episode identity or counters changed")
        if record["is_valid"] != (not bool(trace.error)):
            raise ConfigError("screening record reclassified an invalid execution")
        if not record["is_valid"]:
            if record["behavioral_success"] is not None or record["successes"] != 0:
                raise ConfigError("infrastructure failure was counted as behavioral evidence")
            continue
        if trace.success or record["behavioral_success"] or record["successes"]:
            raise ConfigError("ZERO qualification contains a valid success")
        selected.append(trace)
        mapping.append(index)
        valid_path = artifact_root / f"task-{task}/original-{len(selected):02}.json"
        if valid_path.read_text() != path.read_text():
            raise ConfigError("valid episode alias differs from its exact original execution")
    if mapping != task_screen["valid_episode_indices"]:
        raise ConfigError("frozen valid episode mapping changed")
    validate_traces(selected, 16, task, Candidate())
    return selected


def freeze_inputs() -> None:
    ensure_frozen()
    screening = combined_screening()
    if screening["status"] != "qualified" or len(screening["qualified"]) != 4:
        raise ConfigError("exactly four fresh qualified ZERO tasks are required")
    if (RUN / "input_manifest.json").exists():
        raise ConfigError("input set already frozen; no reference regeneration")
    sub = build(designer=False)
    provider = sub.reference_provider(config())
    assert provider is not None
    prepared = []
    with operation("freeze-inputs", {"tasks": screening["qualified"]}):
        write_json(RUN / "combined_screening.json", screening)
        for task in screening["qualified"]:
            task_screen = screening["tasks"][str(task)]
            traces = frozen_valid_traces(task, task_screen)
            failures = selected_failures(task, traces)
            if len(failures) != 3:
                raise ConfigError("normal seeded LOW evidence does not contain three failures")
            failure_rows = [t.model_dump(mode="json") for t in failures]
            write_json(RUN / f"task-{task}/original_failures.json", failure_rows)
            with operation(f"reference-{task}", {"task": task, "provider_calls": 1}):
                reference = provider(TaskRef(str(task), task))
                raw = reference.as_record()
                if reference.ok and (
                    not reference.steps
                    or tuple(s.action for s in reference.steps) != reference.actions
                ):
                    raise ConfigError("successful rich expert reference is internally inconsistent")
                write_json(RUN / f"task-{task}/privileged_reference.json", raw)
            evidence = serialize_low(failures, 0.0, 16, reference, rich=True)
            row = {
                "task_id": task,
                "original_k16": "0/16",
                "all_original_episode_ids": [t.episode_id for t in traces],
                "all_original_trace_sha256": [digest(t.model_dump(mode="json")) for t in traces],
                "original_zero_evidence_sha256": digest(
                    [t.model_dump(mode="json") for t in traces]
                ),
                "evidence_n": 16,
                "selection_seed": task,
                "valid_episode_execution_indices": task_screen["valid_episode_indices"],
                "screening_executions": task_screen["executions"],
                "evidence_ids": [t.episode_id for t in failures],
                "selected_trace_sha256": [digest(t.model_dump(mode="json")) for t in failures],
                "evidence_sha256": digest(failure_rows),
                "designer_evidence_sha256": evidence.sha256,
                "reference_status": "REFERENCE_AVAILABLE"
                if reference.ok
                else "REFERENCE_UNAVAILABLE",
                "reference_ok": reference.ok,
                "reference_reason": reference.reason,
                "reference_id": raw["reference_id"],
                "reference_sha256": digest(raw),
                "reference_steps": reference.n_steps,
            }
            prepared.append(row)
            write_json(RUN / "prepared.json", prepared)
            print(json.dumps(row), flush=True)
        manifest = {
            "tasks": prepared,
            "screening_sha256": digest((RUN / "screening.json").read_text()),
            "combined_screening_sha256": digest((RUN / "combined_screening.json").read_text()),
            "core_manifest_sha256": digest((FROZEN / "core_manifest.json").read_text()),
            "topup_cost_baseline_sha256": digest((RUN / "topup_cost_baseline.json").read_text()),
            "used_task_audit_sha256": digest((FROZEN / "used_task_audit.json").read_text()),
            "policy_config": e3.policy_qwen().model_dump(mode="json"),
            "designer_config": e3.designer_deepseek().model_dump(mode="json"),
            "effective_designer_max_tokens": 6144,
            "environment": {
                "import": sub.env_import,
                "reset_options": sub.reset_options,
                "max_steps": sub.max_steps,
            },
            "policy_surface": {
                "task_prompt": sub.task_prompt,
                "action_format": sub.policy_spec_kwargs["action_format"],
                "max_history": sub.policy_spec_kwargs["max_history"],
            },
            "semantic_gate_version": SCREEN_VERSION,
            "semantic_gate_sha256": digest((ROOT / "src/aea/semantic_privilege.py").read_text()),
            "validator_fidelity_sha": VALIDATOR_SHA,
            "method_implementation_sha": VALIDATOR_SHA,
            "base_viability_driver_sha256": BASE_DRIVER_SHA,
            "base_viability_driver_commit": BASE_DRIVER_COMMIT,
            "method": METHOD,
        }
        write_json(RUN / "input_manifest.json", manifest)


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


def make_screen(sub: AeaSubstrate, task: int, shared: dict[str, Any]) -> LowPrivilegeScreen:
    failures = failures_for(task)
    ref = read_reference(task)
    evidence = serialize_low(failures, 0.0, 16, None)
    shared["semantic_records"] = []
    shared["active_call"] = 0

    def record(row: dict[str, Any]) -> None:
        stamped = {"optimizer_call_index": shared["active_call"], **row}
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
        if result.status == "inconclusive" and "semantic_privilege_uncertain" not in result.reason:
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


def verify_input_set() -> list[dict[str, Any]]:
    frozen = (FROZEN / "input_manifest.json").read_text()
    if (RUN / "input_manifest.json").read_text() != frozen:
        raise ConfigError("run inputs differ from preregistered four-task manifest")
    manifest = json.loads(frozen)
    prepared: list[dict[str, Any]] = json.loads((RUN / "prepared.json").read_text())
    if (
        manifest["tasks"] != prepared
        or len(prepared) != 4
        or len({r["task_id"] for r in prepared}) != 4
    ):
        raise ConfigError("primary four-task membership changed")
    if digest((RUN / "screening.json").read_text()) != manifest["screening_sha256"]:
        raise ConfigError("frozen screening outcomes changed")
    combined = combined_screening()
    if [r["task_id"] for r in prepared] != combined["qualified"]:
        raise ConfigError("combined core/top-up task membership or order changed")
    for filename, hash_key in (
        ("combined_screening.json", "combined_screening_sha256"),
        ("topup_cost_baseline.json", "topup_cost_baseline_sha256"),
    ):
        if digest((RUN / filename).read_text()) != manifest[hash_key]:
            raise ConfigError("frozen continuation provenance changed: " + filename)
    if json.loads((RUN / "combined_screening.json").read_text()) != combined:
        raise ConfigError("combined provenance differs from original core/top-up records")
    if digest((FROZEN / "core_manifest.json").read_text()) != manifest["core_manifest_sha256"]:
        raise ConfigError("frozen historical core manifest changed")
    for row in prepared:
        task = int(row["task_id"])
        screening = combined_screening()
        originals = [
            t.model_dump(mode="json")
            for t in frozen_valid_traces(task, screening["tasks"][str(task)])
        ]
        if [digest(t) for t in originals] != row["all_original_trace_sha256"] or digest(
            originals
        ) != row["original_zero_evidence_sha256"]:
            raise ConfigError("one or more of the sixteen original traces changed")
        failures = failures_for(task)
        expected_failures = selected_failures(task, [Trace.model_validate(t) for t in originals])
        if [t.model_dump(mode="json") for t in failures] != [
            t.model_dump(mode="json") for t in expected_failures
        ]:
            raise ConfigError("frozen LOW failures differ from exact prior/seeded evidence")
        raw = json.loads((RUN / f"task-{task}/privileged_reference.json").read_text())
        if (
            digest([t.model_dump(mode="json") for t in failures]) != row["evidence_sha256"]
            or digest(raw) != row["reference_sha256"]
        ):
            raise ConfigError("frozen failure/reference bytes changed")
        evidence = serialize_low(failures, 0.0, 16, read_reference(task), rich=True)
        if evidence.sha256 != row["designer_evidence_sha256"]:
            raise ConfigError("frozen designer evidence changed")
    return prepared


def adapt() -> None:
    freeze = ensure_frozen(adaptation=True)
    prepared = verify_input_set()
    if (RUN / "results.json").exists():
        raise ConfigError("adaptation already dispatched; no implicit resume or paid rerun")
    with cap_lock(RUN / "cap.json") as state:
        if state.get("stopped") or state["inflight"] or state["phase"] != "screening_complete":
            raise InfraError(
                "screening cap/interruption prevents adaptation", kind="crash_uncertainty"
            )
        state["phase"] = "adaptation"
    results: dict[str, Any] = {
        "tasks": {
            str(r["task_id"]): {"original": r, "status": "pending", "summary": None}
            for r in prepared
        },
        "freeze": freeze,
        "interruption": None,
    }
    write_json(RUN / "results.json", results)
    try:
        sub = build(designer=True)
        for original in prepared:
            task = int(original["task_id"])
            row = results["tasks"][str(task)]
            ensure_frozen(adaptation=True)
            verify_input_set()
            if not original["reference_ok"]:
                row.update(
                    status="reference_unavailable",
                    summary={
                        "status": "reference_unavailable",
                        "candidates": [],
                        "search_accepted": False,
                        "designer_calls": 0,
                        "adaptation_rollouts": 0,
                    },
                )
                write_json(RUN / "results.json", results)
                continue
            shared: dict[str, Any] = {}
            shared["screen"] = make_screen(sub, task, shared)
            row["status"] = "adapting"
            write_json(RUN / "results.json", results)
            row["summary"] = run_task(sub, task, shared)
            write_json(RUN / "results.json", results)
            confirm(sub, task, row["summary"], shared["screen"])
            row["status"] = "completed"
            write_json(RUN / "results.json", results)
            print(
                json.dumps(
                    {
                        "task": task,
                        "status": row["summary"]["status"],
                        "search_accepted": row["summary"]["search_accepted"],
                        "K16": row["summary"].get("confirmation"),
                    }
                ),
                flush=True,
            )
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


def decision_for(results: dict[str, Any], cap: dict[str, Any]) -> dict[str, Any]:
    rows = list(results["tasks"].values())
    completed = [r for r in rows if r["status"] == "completed"]
    summaries = [r["summary"] for r in rows if r.get("summary")]
    confirmed = sum(bool(s.get("confirmation", {}).get("in_band_l")) for s in summaries)
    viable = sum(s.get("first_viable_family_index") is not None for s in summaries)
    failed_confirmations = sum(
        bool(s.get("search_accepted"))
        and s.get("confirmation", {}).get("n") == 16
        and s["confirmation"].get("in_band_l") is False
        for s in summaries
    )
    referenced = sum(r["original"]["reference_ok"] for r in rows)
    error = results.get("interruption")
    correctness = results.get("correctness_audit", {}).get("decision") == "IMPLEMENTATION_FAILURE"
    if (
        correctness
        or cap.get("bound_violation")
        or (
            error
            and error["kind"]
            in ("implementation", "smoke_bound_error", "provider_mismatch", "pricing_mismatch")
        )
    ):
        decision = "IMPLEMENTATION_FAILURE"
    elif confirmed >= 2:
        decision = "LOW_VIABLE"
    elif error or len(completed) < referenced:
        decision = "INCONCLUSIVE"
    elif confirmed == 1 or failed_confirmations >= 2:
        decision = "LOW_PARTIAL_SIGNAL"
    elif len(completed) >= 3:
        decision = "LOW_NOT_WORKING"
    else:
        decision = "INCONCLUSIVE"
    return {
        "decision": decision,
        "primary_denominator": 4,
        "referenced_tasks": referenced,
        "completed_referenced_tasks": len(completed),
        "K16_B_L": confirmed,
        "K16_B_T": sum(bool(s.get("confirmation", {}).get("in_band_t")) for s in summaries),
        "endpoint_viable_tasks": viable,
        "failed_K16_confirmations": failed_confirmations,
        "interruption": error,
    }


def report() -> dict[str, Any]:
    stage_path = RUN / "stage_interruption.json"
    stage_failure = json.loads(stage_path.read_text()) if stage_path.exists() else None
    stage_error = stage_failure["error"] if stage_failure else None
    if not (RUN / "results.json").exists():
        screening = json.loads((RUN / "screening.json").read_text())
        cap = json.loads((RUN / "cap.json").read_text())
        calls = [row for row in ledger_rows() if row.get("event") == "call"]
        correctness = screening["status"] == "IMPLEMENTATION_FAILURE" or (
            stage_error
            and stage_error["kind"]
            in ("implementation", "smoke_bound_error", "provider_mismatch", "pricing_mismatch")
        )
        final_decision = (
            "IMPLEMENTATION_FAILURE"
            if correctness
            else "INCONCLUSIVE"
            if screening["status"] == "qualified"
            else "TOPUP_INCONCLUSIVE"
        )
        summary = {
            "decision": final_decision,
            "final_viability_decision": final_decision,
            "phase": "screening",
            "screening_status": screening["status"],
            "screening_outcome": screening["status"],
            "topup_stop_reason": screening.get("stop_reason"),
            "stage_interruption": stage_failure,
            "qualified_tasks": screening["qualified"],
            "prior_core_tasks": list(CORE_TASKS),
            "historical_v2_cost_included": False,
            "inspected_task_ids": [int(t) for t in screening["tasks"]],
            "screening_episodes": sum(len(row["episodes"]) for row in screening["tasks"].values()),
            "requested_episode_executions": sum(
                row["executions"] for row in screening["tasks"].values()
            ),
            "valid_episodes": sum(row["valid_episodes"] for row in screening["tasks"].values()),
            "valid_successes": sum(row["valid_successes"] for row in screening["tasks"].values()),
            "recovered_provider_errors": sum(
                row["recovered_provider_errors"] for row in screening["tasks"].values()
            ),
            "recovered_episode_executions": sum(
                row["recovered_episode_executions"] for row in screening["tasks"].values()
            ),
            "infrastructure_inconclusive_tasks": [
                int(task)
                for task, row in screening["tasks"].items()
                if row["status"] == "INFRA_INCONCLUSIVE"
            ],
            "screening_tasks": screening["tasks"],
            "actual_ledger_usd": sum(float(row.get("usd") or 0) for row in calls),
            "conservative_cap_account": cap,
            "interruption": stage_error or screening.get("interruption"),
            "efficacy_evidence_available": False,
        }
        write_json(RUN / "summary.json", summary)
        print(
            json.dumps({k: v for k, v in summary.items() if k != "screening_tasks"}, indent=2),
            flush=True,
        )
        return summary
    results = json.loads((RUN / "results.json").read_text())
    cap = json.loads((RUN / "cap.json").read_text())
    if stage_error and not results.get("interruption"):
        results["interruption"] = stage_error
    if (RUN / "correctness_audit.json").exists():
        results["correctness_audit"] = json.loads((RUN / "correctness_audit.json").read_text())
    summary = decision_for(results, cap)
    summary["final_viability_decision"] = summary["decision"]
    funnel = dict.fromkeys(
        (
            "reference_unavailable",
            "candidate_structural_failures",
            "d0_identity_rejects",
            "lexical_privilege_rejects",
            "semantic_FAIL",
            "semantic_UNCERTAIN",
            "solvability_failures",
            "endpoint_too_hard",
            "endpoint_viable",
            "CONTROL_unresolved",
            "search_accepted",
            "K16_B_L",
            "K16_B_T",
        ),
        0,
    )
    calls = [r for r in ledger_rows() if r.get("event") == "call"]
    tasks = {}
    for task, row in results["tasks"].items():
        own = row.get("summary") or {}
        funnel["reference_unavailable"] += int(not row["original"]["reference_ok"])
        for record in own.get("candidates", []):
            funnel["candidate_structural_failures"] += bool(record["structural"])
            priv = "; ".join(record["privilege"])
            funnel["d0_identity_rejects"] += any(
                reason.startswith("DOSE = 0") for reason in record["privilege"]
            )
            funnel["lexical_privilege_rejects"] += any(
                not reason.startswith("DOSE = 0") and "semantic_privilege_" not in reason
                for reason in record["privilege"]
            )
            funnel["semantic_FAIL"] += "semantic_privilege_fail" in priv
            funnel["semantic_UNCERTAIN"] += "semantic_privilege_uncertain" in priv
            funnel["solvability_failures"] += str(record.get("rejection_reason", "")).startswith(
                "uncertified:"
            )
            endpoint = record.get("endpoint")
            funnel["endpoint_too_hard"] += bool(endpoint and endpoint[2] == "too_hard")
            funnel["endpoint_viable"] += bool(endpoint and endpoint[2] in ("in_band", "too_easy"))
        funnel["CONTROL_unresolved"] += bool(
            own.get("control") and own["control"]["status"] != "accepted"
        )
        funnel["search_accepted"] += bool(own.get("search_accepted"))
        funnel["K16_B_L"] += bool(own.get("confirmation", {}).get("in_band_l"))
        funnel["K16_B_T"] += bool(own.get("confirmation", {}).get("in_band_t"))
        selected = [r for r in calls if str(r.get("task_id")) == task]
        tasks[task] = {**row, "usd": sum(float(r.get("usd") or 0) for r in selected)}
    summary.update(
        failure_funnel=funnel,
        tasks=tasks,
        actual_ledger_usd=sum(float(r.get("usd") or 0) for r in calls),
        screening_usd=sum(float(r.get("usd") or 0) for r in calls if r.get("arm") == "screen"),
        designer_usd=sum(float(r.get("usd") or 0) for r in calls if r.get("budget") == "designer"),
        adaptation_usd=sum(float(r.get("usd") or 0) for r in calls if r.get("budget") == "search"),
        confirmation_usd=sum(
            float(r.get("usd") or 0) for r in calls if r.get("phase") == "confirm"
        ),
        physical_attempts=cap["attempts"],
        conservative_cap_account=cap,
    )
    write_json(RUN / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "tasks"}, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage", choices=("screen", "freeze-inputs", "adapt", "report"), required=True
    )
    args = parser.parse_args()
    try:
        {"screen": screen, "freeze-inputs": freeze_inputs, "adapt": adapt, "report": report}[
            args.stage
        ]()
    except BaseException as exc:
        if args.stage == "report":
            raise
        error = interruption(exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            error["kind"] = "infrastructure_interruption"
        path = RUN / "stage_interruption.json"
        if not path.exists():
            write_json(path, {"stage": args.stage, "error": error})
        if (RUN / "cap.json").exists():
            try:
                stop(error)
            except ConfigError:
                # A corrupt monetary state must still leave an explicit terminal record.
                write_json(RUN / "STOP.json", error)
        print(json.dumps({"stage": args.stage, "interruption": error}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
