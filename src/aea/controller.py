"""The box (docs/spec/AEA_v0.4.md): estimate -> keep | harden | stage; three outcomes.

Every policy rollout is charged to the one budget (``aea.budget``) before it runs; the cap is a
hard stop and ends the task with ``dropped: budget``. Proposer calls, replays and oracle sessions
are not charged. Confirmations (K = 16, B_L) are a separate script and never change the outcome.

Outputs in the run directory: ``corpus.jsonl`` (released loader shape + ``aea`` block; kinds
``kept`` / ``knob`` / ``stage``), ``traces.jsonl`` (released ``TraceStore``), ``accounting.csv``,
``events.jsonl`` (M0 envelope; the resume log: a task whose ``task_done`` outcome is not
``infra_error`` is skipped on resume).

Task pool (``run(concurrency > 1)``): concurrency changes wall clock only, never a charged
number. Three rules make that true. (1) Every in-process ALFWorld session — the harden guard's
replay and oracle, the stage guard, prefix compilation, the fidelity check — runs under the one
:data:`aea.session.SESSION_LOCK` (taken here around the guard and staging sections, and again
inside :func:`aea.session.open_session`); policy rollouts, which run in subprocesses, overlap
freely. (2) The leverage prior is a sequential dependency: task *i* orders its families and
seeds its bracket only after every task before it in the run's task list has finished, exactly
the state the sequential loop would see. (3) ``corpus.jsonl`` and ``accounting.csv`` are
written in the run's task order, so the pooled run's files equal the sequential run's byte for
byte. The pool size is recorded in ``events.jsonl`` (``run_start``) and by the driver in the
manifest.

The leverage table (leverage rates and the frontier history behind the soft warm start) is
persistent: every ``record_leverage`` / ``record_frontier`` is written as a ``leverage`` event, and
a new controller on an existing run directory rebuilds the table from the events of the tasks that
completed (a task's
events count once its ``task_done`` is not ``infra_error``; an interrupted attempt's events are
discarded with the attempt), so a resumed run and a later extension of the task set continue the
same table the uninterrupted run would have.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from envharness.core.types import Candidate, Trace

from aea.bracket import BracketResult, DoseEval, bracket
from aea.budget import Budget
from aea.config import AEAConfig
from aea.core.io import append_jsonl
from aea.core.trace import TraceWriter as EventWriter
from aea.core.trace import read_trace
from aea.designer import (
    AssistDesign,
    AssistFamily,
    Evidence,
    Reference,
    ReferenceProvider,
    design_high,
    design_low,
    design_low_assist,
    design_low_refalign,
    reference_id,
    serialize_high,
    serialize_low,
    task_goal,
)
from aea.errors import BudgetExhausted, ConfigError, InfraError
from aea.estimate import EstimateResult, estimate
from aea.evaluate import Eval, evaluate
from aea.families import LIBRARY, Family, FamilyContext, LeverageTable, propose_families
from aea.intervention import V3Config, canonical_hash
from aea.io import (
    AeaMeta,
    TraceWriter,
    canonicalize_corpus,
    entry_from_candidate,
    write_accounting,
    write_corpus_entry,
)
from aea.llm.types import Attribution, BudgetName, ChatRequest, ChatResponse
from aea.llm_privilege_low import JudgedLowOptimizer, LLMLowPrivilegeScreen
from aea.low_optimizer import Feedback, LowEnvironmentOptimizer, propose_low
from aea.privilege_judge import PrivilegeJudge
from aea.privilege_surfaces import ReplayEpisode
from aea.rules_control import assist_bracket
from aea.semantic_low import LowPrivilegeScreen, ScreenedLowOptimizer
from aea.session import SESSION_LOCK, Session
from aea.stage import (
    StagedCandidate,
    build_stage_candidates,
    candidate_id,
    compile_prefix,
    seeded_failures,
    stage_candidate,
    trace_actions,
)
from aea.stage import (
    candidate_id as stage_candidate_id,
)
from aea.stage_control import InvalidStageError, stage_bracket
from aea.witness import Solvable, policy_shortest_success, solvable

type Outcome = Literal["accepted", "kept", "dropped", "infra_error"]


type AssistProvider = Callable[[TaskRef, Sequence[Trace], Reference, str], AssistDesign]
"""Experiment-only: (task, failures, reference, goal) -> the frozen hand-verified family."""


@dataclass(frozen=True)
class TaskRef:
    task_id: str
    seed: int
    label: str = "alfworld-corpus-ours-release"


class Substrate(Protocol):
    """Everything the controller needs from the world (released runner, or the offline fake)."""

    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]: ...

    def open_session(
        self, task: TaskRef, candidate: Candidate | None, reset_options: dict[str, Any] | None
    ) -> Session: ...

    def game_file(self, task: TaskRef) -> str: ...

    def stage_reset_options(self, task: TaskRef) -> dict[str, Any]: ...

    def designer(self) -> Callable[[ChatRequest], ChatResponse] | None: ...

    def designer_model(self) -> str: ...

    def has_oracle(self) -> bool: ...


@dataclass
class TaskOutcome:
    task: TaskRef
    outcome: Outcome
    reason: str = ""
    regime: str | None = None
    p_hat: float | None = None
    n_search: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


class _IntegratedPrivilegeScreen(LLMLowPrivilegeScreen):
    def _capture(self) -> tuple[ReplayEpisode, ...]:
        # In-process original-state replays share the environment bridge. The lock is
        # released before the independent model call.
        with SESSION_LOCK:
            return super()._capture()


class Controller:
    def __init__(
        self,
        config: AEAConfig,
        substrate: Substrate,
        run_dir: Path,
        run_id: str,
        *,
        arm: str = "A",
        use_proposer: bool = True,
        leverage: LeverageTable | None = None,
        reference: ReferenceProvider | None = None,
        assist_provider: AssistProvider | None = None,
        privilege_judge: PrivilegeJudge | None = None,
        designer_controller_config: V3Config | None = None,
    ) -> None:
        self.config = config
        self.integrated = config.method_version == "llm_v2_integrated"
        self.designer_controller = config.method_version == "llm_v3_designer_controller"
        self.task_local = self.integrated or self.designer_controller
        self.designer_controller_config = designer_controller_config or V3Config()
        self.design_sessions: dict[str, Any] = {}
        self._v3_episode_ids: set[str] = set()
        self._v3_started: set[str] = set()
        self._privilege_judge = privilege_judge
        self.reference = reference
        """``llm_v1`` LOW only: the privileged reference provider (None = failure-only mode)."""
        self.assist_provider = assist_provider
        """Experiment-only (docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md): a hand-verified
        assistive family per task replaces the LOW designer call of ``llm_v1_assistive_rules``;
        production never sets it (None = the designer path)."""
        self.substrate = substrate
        self.run_dir = run_dir
        self.run_id = run_id
        self.arm = arm
        self.use_proposer = use_proposer
        self.leverage = leverage or LeverageTable()
        run_dir.mkdir(parents=True, exist_ok=True)
        self.budget = Budget(config.cap)
        self.baseline_budget = Budget(config.k)
        self._frozen_families: dict[str, str] = {}
        self.events = EventWriter(run_dir / "events.jsonl", run_id)
        self.traces = TraceWriter(run_dir / "traces.jsonl")
        self.corpus_path = run_dir / "corpus.jsonl"
        self._estimates: dict[str, EstimateResult] = {}
        self._io_lock = threading.Lock()
        self._order: dict[str, int] = {}
        self._finished: dict[str, threading.Event] = {}
        if not self.task_local:
            self._restore_leverage()

    # ------------------------------------------------------------------ plumbing
    def _attr(self, task: TaskRef, phase: str, budget: BudgetName = "search") -> Attribution:
        return Attribution(phase=phase, budget=budget, arm=self.arm, task_id=task.task_id)

    def _ev(self, event: str, task: TaskRef, **payload: Any) -> None:
        self.events.write(event, {"task_id": task.task_id, **payload})

    def _rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        phase: str,
        *,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        """Charge ``n`` BEFORE running (the cap is a hard stop), then run and record."""
        account = self.baseline_budget if self.task_local and phase == "estimate" else self.budget
        account.charge(task.task_id, n, phase=phase)
        expected_candidate = (
            candidate.model_copy(deep=True) if self.designer_controller else candidate
        )
        traces = self.substrate.rollouts(
            task, candidate, n, attribution=self._attr(task, phase), reset_options=reset_options
        )
        if self.designer_controller:
            from aea.designer_controller_confirmation import candidate_hash, validate_traces

            with self._io_lock:
                evidence_path = (
                    self.run_dir
                    / "designer_controller"
                    / canonical_hash(task.task_id)[:16]
                    / "search_traces.jsonl"
                )
                for trace in traces:
                    append_jsonl(
                        evidence_path,
                        {
                            "phase": phase,
                            "candidate_sha256": candidate_hash(expected_candidate),
                            "trace": trace.model_dump(mode="json"),
                        },
                    )
                if candidate_hash(candidate) != candidate_hash(expected_candidate):
                    raise ConfigError("Dispatched v3 candidate was mutated during execution")
                validate_traces(traces, n, task, expected_candidate, self._v3_episode_ids)
        errored = sum(1 for t in traces if t.error)
        if errored:  # environment / infrastructure errors are refunded and never counted
            account.refund(task.task_id, errored, phase=phase)
            self._ev("rollout_errors", task, phase=phase, n=errored)
        for t in traces:
            self.traces.add(t)
        self._ev(
            "rollouts",
            task,
            phase=phase,
            n=len(traces),
            successes=sum(int(bool(t.success)) for t in traces),
        )
        if self.task_local and (
            len(traces) != n or (phase != "estimate" and any(trace.error for trace in traces))
        ):
            raise InfraError("incomplete integrated AEA policy batch", kind="rollout")
        return traces

    def _write_corpus(self, task: TaskRef, candidate: Candidate, meta: AeaMeta) -> None:
        if self.task_local:
            meta = meta.model_copy(
                update={
                    "n_search": self.baseline_budget.account(task.task_id).spent
                    + self.budget.account(task.task_id).spent
                }
            )
        write_corpus_entry(
            self.corpus_path, entry_from_candidate(self.substrate.game_file(task), candidate, meta)
        )
        self._ev("corpus_entry", task, kind=meta.kind, candidate_id=meta.candidate_id)

    def completed_tasks(self) -> set[str]:
        """Tasks with a ``task_done`` outcome; ``infra_error`` is not an outcome (re-run)."""
        path = self.run_dir / "events.jsonl"
        if not path.exists():
            return set()
        done: dict[str, str] = {}
        for e in read_trace(path):
            if e.kind == "task_done":
                done[str(e.payload["task_id"])] = str(e.payload.get("outcome"))
        return {t for t, o in done.items() if o != "infra_error"}

    def _record_leverage(self, task: TaskRef, family: str, has_leverage: bool) -> None:
        if not self.task_local:
            self.leverage.record_leverage(family, has_leverage)
        self._ev("leverage", task, family=family, tested=True, has_leverage=has_leverage)

    def _record_frontier(
        self, task: TaskRef, family: str, lo: float, hi: float, accepted: float | None
    ) -> None:
        frontier = accepted if accepted is not None else (lo + hi) / 2
        if self.task_local:
            return
        self.leverage.record_frontier(family, frontier)
        self._ev("leverage", task, family=family, frontier=frontier, lo=lo, hi=hi)

    def _restore_leverage(self) -> None:
        """Replay the ``leverage`` events of every completed task, in order, into the table."""
        path = self.run_dir / "events.jsonl"
        if not path.exists():
            return
        pending: dict[str, list[dict[str, Any]]] = {}
        committed: list[dict[str, Any]] = []
        for e in read_trace(path):
            t = str(e.payload.get("task_id"))
            if e.kind == "task_start":
                pending[t] = []
            elif e.kind == "leverage":
                pending.setdefault(t, []).append(dict(e.payload))
            elif e.kind == "task_done" and e.payload.get("outcome") != "infra_error":
                committed.extend(pending.pop(t, []))
        for p in committed:
            family = str(p["family"])
            if "frontier" in p:
                self.leverage.record_frontier(family, float(p["frontier"]))
            elif "dose" in p or "accepted_dose" in p:
                continue  # v0.3 population / v0.2 last-accepted-dose events: not part of the table
            else:
                self.leverage.record_leverage(family, bool(p.get("has_leverage")))
        if committed:
            self.events.write("leverage_restored", {"events": len(committed)})

    # ------------------------------------------------------------------ the loop
    def run(self, tasks: Sequence[TaskRef], *, concurrency: int = 1) -> list[TaskOutcome]:
        """Run ``tasks`` (in this order; ``concurrency`` of them at a time) and write the run
        files in task order. Tasks already done in ``run_dir`` are skipped."""
        done = self.completed_tasks()
        todo = [t for t in tasks if t.task_id not in done]
        if self.designer_controller:
            if len({task.task_id for task in tasks}) != len(tasks):
                raise ConfigError("V3 task identities must be unique")
            if not todo:
                return []  # preserve completed evidence; do not rewrite its accounting
            path = self.run_dir / "events.jsonl"
            previous = read_trace(path) if path.exists() else []
            started = {
                str(event.payload["task_id"]) for event in previous if event.kind == "task_start"
            }
            if any(task.task_id in started for task in todo):
                raise ConfigError("V3 task already started; implicit restart is forbidden")
            if any(event.run_id != self.run_id for event in previous):
                raise ConfigError("V3 run identity differs from stored history")
        order = [t.task_id for t in tasks]
        self._order = {t: i for i, t in enumerate(order)}
        for t in tasks:
            ev = self._finished.setdefault(t.task_id, threading.Event())
            if t.task_id in done:
                ev.set()
        self.events.write(
            "run_start",
            {"tasks": order, "todo": [t.task_id for t in todo], "concurrency": concurrency},
        )
        if concurrency <= 1:
            outcomes = [self.run_task(t) for t in todo]
        else:  # FIFO submission: a task only ever waits on tasks submitted before it
            with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
                outcomes = list(pool.map(self.run_task, todo))
        canonicalize_corpus(self.corpus_path, order)
        rows = self.budget.accounting_rows(order)
        if self.task_local:
            rows = self.baseline_budget.accounting_rows(order) + rows
        write_accounting(self.run_dir / "accounting.csv", rows)
        return outcomes

    def _await_predecessors(self, task: TaskRef) -> None:
        """Block until every task before ``task`` in the run's task list has finished (the
        leverage prior then holds exactly what the sequential loop would have recorded)."""
        rank = self._order.get(task.task_id)
        if rank is None:
            return
        for t, i in self._order.items():
            if i < rank:
                self._finished[t].wait()

    def run_task(self, task: TaskRef) -> TaskOutcome:
        if self.designer_controller:
            # Refuse BEFORE measurement: a new instance has empty in-memory budgets.
            # Replaying a partial task would otherwise silently buy another baseline.
            with self._io_lock:
                path = self.run_dir / "events.jsonl"
                previous = read_trace(path) if path.exists() else []
                if task.task_id in self._v3_started or any(
                    event.kind == "task_start" and event.payload["task_id"] == task.task_id
                    for event in previous
                ):
                    raise ConfigError("V3 task already started; implicit restart is forbidden")
                self._v3_started.add(task.task_id)
                self._ev(
                    "task_start",
                    task,
                    seed=task.seed,
                    arm=self.arm,
                    method_config=self.config.model_dump(mode="json"),
                    control_config=self.designer_controller_config.model_dump(mode="json"),
                )
        else:
            self._ev("task_start", task, seed=task.seed, arm=self.arm)
        try:
            try:
                outcome = self._run_task(task)
            except BudgetExhausted as exc:
                est = self._estimates.get(task.task_id)
                outcome = TaskOutcome(
                    task,
                    "dropped",
                    "budget",
                    est.regime if est else None,
                    est.p_hat if est else None,
                    detail={"spent": exc.spent},
                )
            except InfraError as exc:
                outcome = TaskOutcome(
                    task, "infra_error", "", detail={"error": str(exc), "kind": exc.kind}
                )
            outcome.n_search = self.budget.account(task.task_id).spent
            if self.task_local:
                measured = self.baseline_budget.account(task.task_id).spent
                outcome.detail.update(
                    baseline_rollouts=measured, adaptation_rollouts=outcome.n_search
                )
                outcome.n_search += measured
            self.events.write(
                "task_done",
                {
                    "task_id": task.task_id,
                    "outcome": outcome.outcome,
                    "reason": outcome.reason,
                    "regime": outcome.regime,
                    "p_hat": outcome.p_hat,
                    "n_search": outcome.n_search,
                    **outcome.detail,
                },
            )
        finally:  # never leave a successor waiting, whatever happened
            self._finished.setdefault(task.task_id, threading.Event()).set()
        return outcome

    def _run_task(self, task: TaskRef) -> TaskOutcome:
        est = self._estimate(task)
        self._estimates[task.task_id] = est
        self._ev(
            "estimate",
            task,
            regime=est.regime,
            p_hat=est.p_hat,
            n=est.n,
            probabilities=est.probabilities,
            stop=est.stop_reason,
        )
        if self.task_local:
            self._ev(
                "measurement_evidence",
                task,
                successes=est.successes,
                n=est.n,
                p_hat=est.p_hat,
                probabilities=est.probabilities,
                regime=est.regime,
                stop_reason=est.stop_reason,
                errors_retried=est.errors_retried,
                episode_ids=[trace.episode_id for trace in est.traces],
                baseline_rollouts=self.baseline_budget.account(task.task_id).spent,
                adaptation_cap=self.config.cap,
            )
        if est.regime == "band":
            if self.designer_controller:
                evidence_path = (
                    self.run_dir
                    / "designer_controller"
                    / canonical_hash(task.task_id)[:16]
                    / "search_traces.jsonl"
                )
                self._ev(
                    "v3_mid_freeze",
                    task,
                    search_evidence_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                )
            meta = AeaMeta(
                kind="kept",
                task_id=task.task_id,
                seed=task.seed,
                regime="band",
                p_hat=est.p_hat,
                n_search=est.n,
                candidate_id=f"{task.task_id}:kept",
            )
            self._write_corpus(task, Candidate(), meta)
            return TaskOutcome(task, "kept", "", "band", est.p_hat)
        if self.designer_controller:
            from aea.design_session import run_designer_controller

            return run_designer_controller(self, task, est)
        if est.regime == "saturated":
            return self._harden(task, est)
        return self._stage(task, est)

    def _estimate(self, task: TaskRef) -> EstimateResult:
        pending: list[Trace] = []
        impl = self.config.impl
        retry = False

        def rollout(i: int) -> Trace:
            nonlocal retry
            if self.task_local and retry:
                trace = self._rollouts(task, Candidate(), 1, "estimate")[0]
                retry = bool(trace.error)
                return trace
            if not pending:
                n = impl.batch_first if i == 0 else impl.batch_next
                pending.extend(self._rollouts(task, Candidate(), n, "estimate"))
            trace = pending.pop(0)
            retry = bool(trace.error)
            return trace

        return estimate(rollout, self.config)

    # ------------------------------------------------------------------ harden
    def _families(self, task: TaskRef, lengths: tuple[int, ...]) -> list[Family]:
        proposed: list[Family] = []
        designer = self.substrate.designer() if self.use_proposer else None
        if designer is not None and self.config.impl.proposer_cap > 0:
            calls_path = self.run_dir / "designer_calls.jsonl"
            try:
                got, rejected, ranking = propose_families(
                    designer,
                    model=self.substrate.designer_model(),
                    task_description=f"task {task.task_id}",
                    success_summary=f"successful episode lengths: {sorted(lengths)}",
                    cap=self.config.impl.proposer_cap,
                    attribution=self._attr(task, "propose", "designer"),
                    seed=task.seed,
                    record=lambda payload: self._append(
                        calls_path, {"task_id": task.task_id, **payload}
                    ),
                )
                proposed = list(got)
                self._ev(
                    "proposer",
                    task,
                    proposed=[k.name for k in got],
                    rejected=rejected,
                    ranking=ranking,
                )
            except InfraError as exc:
                self._ev("proposer_failed", task, error=str(exc))
        return self.leverage.order([*proposed, *LIBRARY])

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        with self._io_lock:
            append_jsonl(path, record)

    @property
    def _llm(self) -> bool:
        """Every llm_v1 variant shares every path except LOW."""
        return self.config.method_version.startswith("llm_v1") or self.config.method_version in (
            "llm_v2_iterative_low",
            "llm_v2_iterative_low_semantic_gate",
            "llm_v2_iterative_low_llm_judge",
            "llm_v2_integrated",
        )

    def _harden(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        if self._llm:
            return self._harden_llm(task, est)
        self._await_predecessors(task)  # the leverage prior is a sequential dependency
        successes = [t for t in est.traces if t.success]
        lengths = tuple(t.duration_steps or len(t.steps) for t in successes)
        ctx = FamilyContext(task_id=task.task_id, success_lengths=lengths)
        witness = policy_shortest_success(est.traces)
        families = self._families(task, lengths)
        self._ev("families", task, order=[f.name for f in families])
        tried = 0
        for fam in families:
            result = self._try_family(task, fam, ctx, witness, est)
            if result is None:
                continue
            tried += 1
            if result.outcome == "accepted":
                return result
        reason = "exhausted" if tried else "no_leverage"
        return TaskOutcome(
            task,
            "dropped",
            reason,
            "saturated",
            est.p_hat,
            detail={"families": [f.name for f in families]},
        )

    def _try_family(
        self,
        task: TaskRef,
        fam: Family,
        ctx: FamilyContext,
        witness: list[str] | None,
        est: EstimateResult,
    ) -> TaskOutcome | None:
        """None: the family did not apply (infeasible, unsolvable, or no leverage)."""
        cache: dict[float, Candidate] = {}

        def make(d: float) -> Candidate | None:
            if self.integrated:
                self._assert_frozen_family(task, fam)
            if d not in cache:
                cand = fam.make(d, ctx)
                if cand is None:
                    return None
                cache[d] = cand
            return cache[d]

        top = make(1.0)
        if top is None:
            self._ev("family_skipped", task, family=fam.name, reason="infeasible")
            return None
        with SESSION_LOCK:  # in-process replay / oracle sessions: one at a time per process
            guard = solvable(
                top,
                lambda c: self.substrate.open_session(task, c, None),
                self.config,
                policy_success=witness,
                oracle=self.substrate.has_oracle(),
                # v0.4: a trusted O-axis family is solvable by construction. llm_v1: the axis
                # is a self-declared label and certifies nothing; the guard always runs.
                by_construction=fam.axis == "O" and not self._llm,
            )
        self._ev(
            "solvable",
            task,
            family=fam.name,
            d=1.0,
            ok=guard.ok,
            source=guard.source,
            detail=guard.detail,
        )
        if not guard.ok:
            self._ev("family_skipped", task, family=fam.name, reason="uncertified")
            return None

        def evaluate_at(d: float) -> Eval:
            cand = make(d)
            if cand is None:
                raise _InfeasibleError(f"{fam.name} infeasible at d={d}")
            evaluation = evaluate(
                lambda n: self._rollouts(task, cand, n, f"dose:{fam.name}"), self.config
            )
            if self.integrated:
                self._assert_frozen_family(task, fam)
                if d != 1.0:
                    self._ev(
                        "dose_evaluation",
                        task,
                        family=fam.name,
                        source_sha256=self._source_hash(fam),
                        d=d,
                        s=evaluation.successes,
                        n=evaluation.n,
                        verdict=evaluation.verdict,
                    )
            return evaluation

        try:
            lev = evaluate_at(1.0)
        except _InfeasibleError:
            return None
        has_leverage = lev.verdict != "too_easy"
        if self.integrated:
            self._ev(
                "endpoint",
                task,
                family=fam.name,
                source_sha256=self._source_hash(fam),
                d=1.0,
                s=lev.successes,
                n=lev.n,
                verdict=lev.verdict,
            )
            if has_leverage:
                self._freeze_family(task, fam, "harder_with_d")
        self._record_leverage(task, fam.name, has_leverage)
        if lev.verdict == "in_band":
            return self._accept_knob(task, fam, cache[1.0], 1.0, lev, est, [DoseEval(1.0, lev)])
        if not has_leverage:
            self._ev("no_leverage", task, family=fam.name, successes=lev.successes, n=lev.n)
            return None
        start = self._start_dose(fam)
        try:
            result: BracketResult = bracket(
                evaluate_at, self.config, leverage=DoseEval(1.0, lev), start=start
            )
        except _InfeasibleError as why:
            self._ev("family_skipped", task, family=fam.name, reason=str(why))
            if self.integrated:
                return TaskOutcome(
                    task,
                    "dropped",
                    "infeasible",
                    "saturated",
                    est.p_hat,
                    detail={"family": fam.name},
                )
            return None
        # one frontier estimate per finished search: the accepted dose, else the midpoint of the
        # task's final local interval (exhausted or censored searches count too)
        lo = max([0.0] + [h.d for h in result.history if h.eval.verdict == "too_easy"])
        hi = min([1.0] + [h.d for h in result.history if h.eval.verdict == "too_hard"])
        acc_d = result.accepted.d if result.accepted is not None else None
        self._record_frontier(task, fam.name, lo, hi, acc_d)
        self._ev(
            "bracket",
            task,
            family=fam.name,
            start=start,
            local=[lo, hi],
            status=result.status,
            history=[
                {"d": h.d, "s": h.eval.successes, "n": h.eval.n, "verdict": h.eval.verdict}
                for h in result.history
            ],
        )
        if result.status == "accepted" and result.accepted is not None:
            ev = result.accepted
            return self._accept_knob(task, fam, cache[ev.d], ev.d, ev.eval, est, result.history)
        if result.status == "budget":
            raise BudgetExhausted(
                "cap during the bracket",
                budget="search",
                cap=self.config.cap,
                spent=self.budget.account(task.task_id).spent,
                task_id=task.task_id,
            )
        return TaskOutcome(
            task,
            "dropped",
            "exhausted",
            "saturated",
            est.p_hat,
            detail={"family": fam.name, "status": result.status},
        )

    @staticmethod
    def _source_hash(family: Family) -> str:
        source = getattr(family, "template", None)
        if not isinstance(source, str):
            raise ConfigError("Integrated family has no source template")
        return hashlib.sha256(source.encode()).hexdigest()

    @classmethod
    def _family_signature(cls, family: Family) -> str:
        return json.dumps(
            [
                family.name,
                family.axis,
                family.source,
                cls._source_hash(family),
                getattr(family, "direction", "harder_with_d"),
            ]
        )

    def _assert_frozen_family(self, task: TaskRef, family: Family) -> None:
        previous = self._frozen_families.get(task.task_id)
        if previous is not None and previous != self._family_signature(family):
            raise ConfigError("CONTROL attempted to change the frozen semantic family")

    def _freeze_family(self, task: TaskRef, family: Family, direction: str) -> None:
        self._assert_frozen_family(task, family)
        if task.task_id in self._frozen_families:
            raise ConfigError("A task cannot reopen its family freeze")
        self._frozen_families[task.task_id] = self._family_signature(family)
        self._ev(
            "family_frozen",
            task,
            family=family.name,
            source_sha256=self._source_hash(family),
            direction=direction,
        )

    def _start_dose(self, fam: Family) -> float:
        """The first interior probe of the bracket. v0.4: the family's soft warm start. llm_v1:
        always the midpoint — a generated family's name is a per-task identity, so no
        cross-task frontier history is trusted for it (docs/spec/AEA_llm_v1.md, "Warm start")."""
        if self._llm:
            return 0.5
        return self.leverage.warm_start(fam.name, self.config.impl.warm_start_min_history)

    def _accept_knob(
        self,
        task: TaskRef,
        fam: Family,
        cand: Candidate,
        d: float,
        ev: Eval,
        est: EstimateResult,
        history: list[DoseEval],
    ) -> TaskOutcome:
        if self.integrated:
            self._assert_frozen_family(task, fam)
        meta = AeaMeta(
            kind="knob",
            task_id=task.task_id,
            seed=task.seed,
            regime="saturated",
            family=fam.name,
            source=fam.source,
            axis=fam.axis,
            d=d,
            p_hat=ev.p_hat,
            candidate_id=f"{task.task_id}:{fam.name}:{d}",
        )
        self._write_corpus(task, cand, meta)
        return TaskOutcome(
            task,
            "accepted",
            "",
            "saturated",
            est.p_hat,
            detail={"family": fam.name, "d": d, "p8": ev.p_hat, "doses": [h.d for h in history]},
        )

    # ------------------------------------------------------------------ stage
    def _stage(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        if self.config.method_version in (
            "llm_v2_iterative_low",
            "llm_v2_iterative_low_semantic_gate",
            "llm_v2_iterative_low_llm_judge",
            "llm_v2_integrated",
        ):
            return self._stage_iterative_low(task, est)
        if self.config.method_version == "llm_v1_stage_control":
            return self._stage_control(task, est)
        if self.config.method_version == "llm_v1_assistive_rules":
            return self._stage_assist(task, est)
        if self._llm:
            return self._stage_llm(task, est)
        failures = seeded_failures(est.traces, self.config.impl.n_failed_rollouts, seed=task.seed)
        if not failures:
            return TaskOutcome(task, "dropped", "no_failed_rollout", "zero", est.p_hat)
        opts = self.substrate.stage_reset_options(task)
        with SESSION_LOCK:  # prefix compilation, oracle guard and fidelity check: in-process
            staged = build_stage_candidates(
                lambda c, ro: self.substrate.open_session(task, c, ro),
                task.task_id,
                failures,
                opts,
                self.config,
                oracle=self.substrate.has_oracle(),
            )
        self._ev(
            "stage_candidates",
            task,
            certified=[c.id for c in staged.candidates],
            kinds={c.id: c.kind for c in staged.candidates},
            rejected=staged.rejected,
            fidelity_ok=[c.fidelity_ok for c in staged.candidates if c.fidelity_ok is not None],
        )
        if not staged.candidates:
            return TaskOutcome(
                task,
                "dropped",
                "uncertified",
                "zero",
                est.p_hat,
                detail={"rejected": staged.rejected},
            )
        profile: list[dict[str, Any]] = []
        walked: list[StagedCandidate] = []
        try:
            for c in sorted(staged.candidates, key=lambda c: -c.t):
                walked.append(c)

                def run(n: int, c: StagedCandidate = c) -> list[Trace]:
                    return self._rollouts(task, c.candidate, n, "probe", reset_options=opts)

                ev = evaluate(run, self.config)
                profile.append(
                    {
                        "id": c.id,
                        "t": c.t,
                        "successes": ev.successes,
                        "n": ev.n,
                        "verdict": ev.verdict,
                    }
                )
                if ev.verdict == "in_band":
                    meta = AeaMeta(
                        kind="stage",
                        task_id=task.task_id,
                        seed=task.seed,
                        regime="zero",
                        t=c.t,
                        state_hash=c.state_hash,
                        profile=profile,
                        stage_budget=self.config.impl.stage_budget,
                        candidate_id=c.id,
                        p_hat=ev.p_hat,
                    )
                    self._write_corpus(task, c.candidate, meta)
                    self._ev("probe", task, profile=profile, accepted=c.id)
                    return TaskOutcome(
                        task,
                        "accepted",
                        "",
                        "zero",
                        est.p_hat,
                        detail={"t": c.t, "profile": profile},
                    )
        except BudgetExhausted:
            self._ev(
                "probe",
                task,
                profile=profile,
                accepted=None,
                skipped=[c.id for c in staged.candidates if c not in walked],
            )
            return TaskOutcome(
                task,
                "dropped",
                "budget",
                "zero",
                est.p_hat,
                detail={
                    "profile": profile,
                    "skipped": [c.id for c in staged.candidates if c not in walked],
                },
            )
        self._ev("probe", task, profile=profile, accepted=None)
        reason = "too_easy" if any(p["verdict"] == "too_easy" for p in profile) else "dead"
        return TaskOutcome(task, "dropped", reason, "zero", est.p_hat, detail={"profile": profile})

    # ------------------------------------------------------------------ llm_v1
    def _designer(self) -> Callable[[ChatRequest], ChatResponse]:
        designer = self.substrate.designer()
        if designer is None:
            raise InfraError("method llm_v1 needs a designer (none configured)", kind="config")
        return designer

    def _record_designer(
        self, task: TaskRef, regime: str, evidence: Evidence, **payload: Any
    ) -> None:
        """One row per designer call in ``designer_calls.jsonl`` (the redacted evidence: on LOW
        the reference block is replaced by its metadata) and a ``designer_evidence`` event."""
        self._append(
            self.run_dir / "designer_calls.jsonl",
            {
                "task_id": task.task_id,
                "regime": regime,
                "method_version": self.config.method_version,
                "evidence_sha256": evidence.sha256,
                "evidence": evidence.redacted,
                "reference_used": evidence.reference_used,
                **payload,
            },
        )
        self._ev(
            "designer_evidence",
            task,
            regime=regime,
            sha256=evidence.sha256,
            chars=len(evidence.text),
            n_traces=evidence.n_traces,
            reference_used=evidence.reference_used,
        )

    def _harden_llm(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        """HIGH under llm_v1: one designer call proposes the families; the existing empirical
        control (`_try_family`: guard, leverage test, bracket, cap) decides. The library is not
        executed; the designer is never called again."""
        successes = [t for t in est.traces if t.success]
        lengths = tuple(t.duration_steps or len(t.steps) for t in successes)
        ctx = FamilyContext(task_id=task.task_id, success_lengths=lengths)
        witness = policy_shortest_success(est.traces)
        evidence = serialize_high(est.traces, est.p_hat, est.n)
        design = design_high(
            self._designer(),
            model=self.substrate.designer_model(),
            evidence=evidence,
            attribution=self._attr(task, "design_high", "designer"),
            seed=task.seed,
        )
        self._record_designer(
            task,
            "saturated",
            evidence,
            arguments=design.arguments,
            accepted=[f.name for f in design.families],
            mechanisms=design.mechanisms,
            rejected=design.rejected,
            **(
                {
                    "accepted_sources": [
                        {"name": f.name, "source_sha256": self._source_hash(f)}
                        for f in design.families
                    ]
                }
                if self.integrated
                else {}
            ),
        )
        self._ev(
            "proposer",
            task,
            proposed=[f.name for f in design.families],
            rejected=design.rejected,
            mechanisms=design.mechanisms,
        )
        if not design.families:
            return TaskOutcome(
                task,
                "dropped",
                "no_valid_proposal",
                "saturated",
                est.p_hat,
                detail={"rejected": design.rejected},
            )
        families: list[Family] = list(design.families)  # designer order; the library is absent
        self._ev("families", task, order=[f.name for f in families], source="designer")
        tried = 0
        for fam in families:
            result = self._try_family(task, fam, ctx, witness, est)
            if result is None:
                continue
            tried += 1
            if result.outcome == "accepted" or self.integrated:
                return result
        reason = "exhausted" if tried else "no_leverage"
        return TaskOutcome(
            task,
            "dropped",
            reason,
            "saturated",
            est.p_hat,
            detail={"families": [f.name for f in families]},
        )

    def _lazy_reference(self, task: TaskRef) -> Reference | None:
        """LOW under llm_v1 only: the privileged reference, requested here and nowhere else."""
        if self.reference is None:
            self._ev("reference", task, requested=True, available=False, reason="no_provider")
            return None
        ref = self.reference(task)
        rid = reference_id(ref.actions) if ref.ok else None
        self._ev(
            "reference",
            task,
            requested=True,
            available=ref.ok,
            n_steps=ref.n_steps,
            reason=ref.reason,
            reference_id=rid,
        )
        if ref.ok:  # the exact instance the designer will see: privileged, audit-side only
            self._append(
                self.run_dir / "privileged_references.jsonl",
                {
                    "task_id": task.task_id,
                    **ref.as_record(),
                    "event_seq": self.events.seq,
                    "ts": datetime.now(UTC).isoformat(),
                },
            )
        return ref if ref.ok else None

    def _stage_llm(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        """LOW under llm_v1: failures (+ lazy reference) -> one designer call -> up to two
        grounded Stage cuts, compiled and guarded by the existing stage machinery, accepted only
        by the current policy's 4 -> 8 probe. No end/midpoint heuristic, no repair, no fallback."""
        failures = seeded_failures(est.traces, self.config.impl.n_failed_rollouts, seed=task.seed)
        if not failures:
            return TaskOutcome(task, "dropped", "no_failed_rollout", "zero", est.p_hat)
        reference = self._lazy_reference(task)
        refalign = self.config.method_version == "llm_v1_refalign" and reference is not None
        evidence = serialize_low(failures, est.p_hat, est.n, reference, rich=refalign)
        mode = "refalign" if refalign else ("direct" if reference is not None else "failure_only")
        diagnoses: list[dict[str, Any]] = []
        if refalign and reference is not None:
            rdesign = design_low_refalign(
                self._designer(),
                model=self.substrate.designer_model(),
                evidence=evidence,
                failures=failures,
                reference=reference,
                attribution=self._attr(task, "design_low", "designer"),
                seed=task.seed,
            )
            diagnoses = [
                {
                    "failure_id": d.failure_id,
                    "failure_step": d.failure_step,
                    "reference_step": d.reference_step,
                    "error_cause": d.error_cause,
                    "fix_hint": d.fix_hint,
                    "evidence": d.evidence,
                }
                for d in rdesign.diagnoses
            ]
            self._ev("llm_diagnosis", task, diagnoses=diagnoses, rejected=rdesign.rejected)
            design: Any = rdesign
        else:
            design = design_low(
                self._designer(),
                model=self.substrate.designer_model(),
                evidence=evidence,
                failures=failures,
                reference=reference,
                attribution=self._attr(task, "design_low", "designer"),
                seed=task.seed,
            )
        proposals = [
            {
                "source": p.source,
                "trajectory_id": p.trajectory_id,
                "step": p.step,
                **({"diagnosis": p.diagnosis} if refalign else {}),  # llm_v1 records unchanged
            }
            for p in design.stages
        ]
        self._record_designer(
            task,
            "zero",
            evidence,
            mode=mode,
            arguments=design.arguments,
            accepted=proposals,
            mechanisms=[p.mechanism_summary for p in design.stages],
            diagnoses=diagnoses,
            rejected=design.rejected,
            reference_steps=reference.n_steps if reference else None,
        )
        self._ev(
            "llm_stage_proposals", task, mode=mode, accepted=proposals, rejected=design.rejected
        )
        if not design.stages:
            return TaskOutcome(
                task,
                "dropped",
                "no_valid_proposal",
                "zero",
                est.p_hat,
                detail={"rejected": design.rejected},
            )
        opts = self.substrate.stage_reset_options(task)
        by_id = {t.episode_id: t for t in failures}
        staged: list[StagedCandidate] = []
        rejected: list[dict[str, Any]] = []
        with SESSION_LOCK:  # prefix compilation and the oracle guard: in-process sessions
            for p in design.stages:
                prefix = (
                    list(reference.actions[: p.step])
                    if p.source == "reference" and reference is not None
                    else trace_actions(by_id[str(p.episode_id)])[: p.step]
                )
                compiled = compile_prefix(
                    lambda c, ro: self.substrate.open_session(task, c, ro), prefix, opts
                )
                cid = candidate_id(task.task_id, compiled)
                if any(c.id == cid for c in staged):
                    rejected.append({"id": cid, "t": p.step, "reason": "duplicate state"})
                    continue
                cand = stage_candidate(compiled)
                guard = solvable(
                    cand,
                    lambda c: self.substrate.open_session(task, c, opts),
                    self.config,
                    oracle=self.substrate.has_oracle(),
                )
                c = StagedCandidate(
                    cid, p.episode_id or "reference", p.step, p.source, compiled, cand, guard
                )
                if guard.ok:
                    staged.append(c)
                else:
                    rejected.append({"id": cid, "t": p.step, "reason": guard.detail})
        self._ev(
            "stage_candidates",
            task,
            certified=[c.id for c in staged],
            kinds={c.id: c.kind for c in staged},
            rejected=rejected,
            source="designer",
        )
        if not staged:
            return TaskOutcome(
                task, "dropped", "uncertified", "zero", est.p_hat, detail={"rejected": rejected}
            )
        return self._probe_stages(task, est, staged, opts)

    # ------------------------------------------------------------------ experimental iterative LOW
    def _stage_iterative_low(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        failures = seeded_failures(est.traces, self.config.impl.n_failed_rollouts, seed=task.seed)
        if not failures:
            return TaskOutcome(task, "dropped", "no_failed_rollout", "zero", est.p_hat)
        reference = self._lazy_reference(task)
        if reference is None:
            return TaskOutcome(
                task,
                "dropped",
                "reference_unavailable",
                "zero",
                est.p_hat,
                detail={"design_status": "inconclusive"},
            )
        evidence = serialize_low(failures, est.p_hat, est.n, reference, rich=True)
        ctx = FamilyContext(task.task_id, ())
        privilege_screen: LowPrivilegeScreen | LLMLowPrivilegeScreen | None = None
        llm_screen: LLMLowPrivilegeScreen | None = None
        admissions: dict[str, dict[str, Any]] = {}

        def record_privilege(record: dict[str, Any]) -> None:
            filename = (
                "llm_privilege.jsonl"
                if (
                    self.config.method_version
                    in ("llm_v2_iterative_low_llm_judge", "llm_v2_integrated")
                )
                else "semantic_privilege.jsonl"
            )
            self._append(self.run_dir / filename, record)
            if self.integrated:
                decision = record["result"]
                binding = {
                    key: decision[key]
                    for key in (
                        "source_sha256",
                        "input_sha256",
                        "config_sha256",
                        "prompt_sha256",
                        "schema_sha256",
                    )
                }
                binding.update(verdict=decision["decision"]["verdict"], doses=record["doses"])
                admissions[binding["source_sha256"]] = binding
                self._ev("privilege_decision", task, family=record["family"], **binding)

        if self.config.method_version in (
            "llm_v2_iterative_low_semantic_gate",
            "llm_v2_iterative_low_llm_judge",
            "llm_v2_integrated",
        ):
            screen_kwargs: dict[str, Any] = dict(
                task_id=task.task_id,
                reference=reference,
                designer_evidence=serialize_low(failures, est.p_hat, est.n, None).text,
                failures=failures,
                goal=task_goal(failures),
                open_original_session=lambda: self.substrate.open_session(task, None, None),
                max_bisections=self.config.impl.max_bisections,
                max_steps=self.config.impl.policy_max_steps,
                audit_dir=self.run_dir
                / (
                    "llm_privilege_inputs"
                    if self.config.method_version
                    in ("llm_v2_iterative_low_llm_judge", "llm_v2_integrated")
                    else "semantic_privilege_inputs"
                ),
                record=record_privilege,
                task_prompt=str(getattr(self.substrate, "task_prompt", "")),
                action_format=str(
                    getattr(self.substrate, "policy_spec_kwargs", {}).get(
                        "action_format", "think_action"
                    )
                ),
            )

            if self.config.method_version in (
                "llm_v2_iterative_low_llm_judge",
                "llm_v2_integrated",
            ):
                judge = self._privilege_judge
                if judge is None:
                    factory = getattr(self.substrate, "privilege_judge", None)
                    if not callable(factory):
                        raise InfraError("independent privilege judge unavailable", kind="config")
                    judge = factory(self._attr(task, "privilege_judge", "none"))
                screen_type = (
                    _IntegratedPrivilegeScreen if self.integrated else LLMLowPrivilegeScreen
                )
                llm_screen = screen_type(judge=judge, **screen_kwargs)
                privilege_screen = llm_screen
            else:
                privilege_screen = LowPrivilegeScreen(**screen_kwargs)

        def propose(feedback: Feedback | None, index: int) -> dict[str, Any]:
            args = propose_low(
                self._designer(),
                model=self.substrate.designer_model(),
                evidence=evidence,
                feedback=feedback,
                attribution=self._attr(task, "design_low", "designer"),
                seed=task.seed + index - 1,
            )
            self._record_designer(
                task,
                "zero",
                evidence,
                mode="iterative_low",
                optimizer_call_index=index,
                arguments=args,
                feedback=feedback.as_record() if feedback else None,
            )
            return args

        def certify(candidate: Candidate) -> Solvable:
            if llm_screen is not None:
                llm_screen.require_pass_candidate(candidate, 1.0)
            with SESSION_LOCK:
                guard = solvable(
                    candidate,
                    lambda c: self.substrate.open_session(task, c, None),
                    self.config,
                    policy_success=None,
                    oracle=self.substrate.has_oracle(),
                    by_construction=False,
                )
            if self.integrated:
                self._ev(
                    "solvable",
                    task,
                    d=1.0,
                    ok=guard.ok,
                    source=guard.source,
                    detail=guard.detail,
                    candidate_sha256=hashlib.sha256(
                        (candidate.rules_code or "").encode()
                    ).hexdigest(),
                )
            return guard

        def measure(family: AssistFamily, dose: float) -> Eval:
            if self.integrated:
                self._assert_frozen_family(task, family)
            if privilege_screen is not None:
                privilege_screen.require_pass(family, dose)
            candidate = family.make(dose, ctx)
            assert candidate is not None

            def run(n: int) -> list[Trace]:
                traces = self._rollouts(task, candidate, n, f"dose:{family.name}")
                if len(traces) != n or any(t.error for t in traces):
                    raise InfraError("incomplete iterative LOW policy batch", kind="rollout")
                return traces

            evaluation = evaluate(run, self.config)
            if self.integrated:
                self._assert_frozen_family(task, family)
                self._ev(
                    "endpoint" if dose == 1.0 else "dose_evaluation",
                    task,
                    family=family.name,
                    source_sha256=self._source_hash(family),
                    d=dose,
                    s=evaluation.successes,
                    n=evaluation.n,
                    verdict=evaluation.verdict,
                )
            return evaluation

        optimizer_kwargs: dict[str, Any] = {
            "task_id": task.task_id,
            "propose": propose,
            "certify": certify,
            "measure": measure,
            "remaining": lambda: self.budget.account(task.task_id).remaining(),
            "endpoint_reserve": 2 * self.config.probe[1],
        }
        if self.integrated:
            optimizer_kwargs["max_calls"] = 3
        optimizer: LowEnvironmentOptimizer
        if llm_screen is not None:
            optimizer = JudgedLowOptimizer(
                evidence,
                failures,
                reference,
                task_goal(failures),
                screen=llm_screen.screen,
                **optimizer_kwargs,
            )
        elif isinstance(privilege_screen, LowPrivilegeScreen):
            optimizer = ScreenedLowOptimizer(
                evidence,
                failures,
                reference,
                task_goal(failures),
                screen=privilege_screen.screen,
                **optimizer_kwargs,
            )
        else:
            optimizer = LowEnvironmentOptimizer(
                evidence, failures, reference, task_goal(failures), **optimizer_kwargs
            )
        try:
            result = optimizer.run()
        finally:
            for record in optimizer.history:
                self._append(self.run_dir / "low_candidates.jsonl", record.as_record())
        self._ev(
            "iterative_design",
            task,
            status=result.status,
            reason=result.reason,
            candidate_ids=[r.candidate_id for r in optimizer.history],
        )
        if self.integrated and result.status == "inconclusive":
            raise InfraError(result.reason, kind="task_infrastructure")
        if result.status != "viable":
            return TaskOutcome(
                task,
                "dropped",
                result.reason,
                "zero",
                est.p_hat,
                detail={"design_status": result.status},
            )
        family, endpoint = result.family, result.endpoint
        assert family is not None and endpoint is not None
        if self.integrated:
            self._freeze_family(task, family, family.direction)
        self._ev(
            "low_family_frozen",
            task,
            candidate_id=result.candidate_id,
            source_sha256=optimizer.history[-1].source_sha256,
            family=family.name,
            direction=family.direction,
        )
        history = [DoseEval(1.0, endpoint)]
        accepted = history[0] if endpoint.verdict == "in_band" else None
        if accepted is None:
            control = assist_bracket(lambda d: measure(family, d), self.config, leverage=history[0])
            history = control.history
            accepted = control.accepted
            self._ev(
                "dose_control",
                task,
                family=family.name,
                direction=family.direction,
                status=control.status,
                lo=control.lo,
                hi=control.hi,
                history=[
                    {"d": h.d, "s": h.eval.successes, "n": h.eval.n, "verdict": h.eval.verdict}
                    for h in history
                ],
            )
            if accepted is None:
                return TaskOutcome(
                    task,
                    "dropped",
                    control.status,
                    "zero",
                    est.p_hat,
                    detail={"candidate_id": result.candidate_id, "family": family.name},
                )
        if self.integrated:
            self._assert_frozen_family(task, family)
        candidate = family.make(accepted.d, ctx)
        assert candidate is not None
        if self.integrated:
            assert llm_screen is not None
            llm_screen.require_pass_candidate(candidate, accepted.d)
            binding = admissions[self._source_hash(family)]
            if binding["verdict"] != "PASS" or accepted.d not in binding["doses"]:
                raise ConfigError("Selected LOW environment lacks exact admission")
            self._ev(
                "selected_admission",
                task,
                family=family.name,
                d=accepted.d,
                candidate_sha256=hashlib.sha256((candidate.rules_code or "").encode()).hexdigest(),
                **binding,
            )
        outcome = self._accept_assist(
            task, family, candidate, accepted.d, accepted.eval, est, history
        )
        outcome.detail["design_candidate_id"] = result.candidate_id
        outcome.detail["source_sha256"] = optimizer.history[-1].source_sha256
        return outcome

    # ------------------------------------------------------------------ llm_v1_assistive_rules
    def _stage_assist(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        """LOW under llm_v1_assistive_rules (docs/design/AEA_LOW_ASSISTIVE_RULES.md): failures
        + the exact rich reference -> ONE designer call (diagnosis, then <= 2 assistive Rules
        families W(d), easier with d) -> per family, in order: the existing guard at d = 1, the
        4 -> 8 measurement at d = 1 (too_hard = no leverage -> next family; in_band = accept;
        too_easy = mirrored bracket inward). No cascade to Stage, no repair, no second call."""
        failures = seeded_failures(est.traces, self.config.impl.n_failed_rollouts, seed=task.seed)
        if not failures:
            return TaskOutcome(task, "dropped", "no_failed_rollout", "zero", est.p_hat)
        reference = self._lazy_reference(task)
        if reference is None:
            return TaskOutcome(task, "dropped", "reference_unavailable", "zero", est.p_hat)
        goal = task_goal(failures)
        if self.assist_provider is not None:
            # experiment-only oracle actuator: the frozen hand-verified family replaces the
            # designer call; no designer record, no LLM; everything below is unchanged
            design = self.assist_provider(task, failures, reference, goal)
            families = [
                {
                    "name": f.name,
                    "axis": f.axis,
                    "mechanism": f.mechanism_summary,
                    "why": f.why,
                    "source": f.source,
                    "code_sha256": hashlib.sha256(f.template.encode("utf-8")).hexdigest()[:16],
                }
                for f in design.families
            ]
            self._append(
                self.run_dir / "oracle_families.jsonl",
                {
                    "task_id": task.task_id,
                    "regime": "zero",
                    "method_version": self.config.method_version,
                    "mode": "oracle",
                    "families": families,
                    "rejected": design.rejected,
                    "reference_steps": reference.n_steps,
                },
            )
            self._ev("oracle_actuator", task, families=families, rejected=design.rejected)
        else:
            evidence = serialize_low(failures, est.p_hat, est.n, reference, rich=True)
            design = design_low_assist(
                self._designer(),
                model=self.substrate.designer_model(),
                evidence=evidence,
                failures=failures,
                reference=reference,
                goal=goal,
                attribution=self._attr(task, "design_low", "designer"),
                seed=task.seed,
            )
            diagnoses = [
                {
                    "failure_id": d.failure_id,
                    "failure_step": d.failure_step,
                    "reference_step": d.reference_step,
                    "error_cause": d.error_cause,
                    "fix_hint": d.fix_hint,
                    "evidence": d.evidence,
                }
                for d in design.diagnoses
            ]
            families = [
                {"name": f.name, "axis": f.axis, "mechanism": f.mechanism_summary, "why": f.why}
                for f in design.families
            ]
            self._record_designer(
                task,
                "zero",
                evidence,
                mode="assist",
                arguments=design.arguments,
                accepted=[f["name"] for f in families],
                families=families,
                diagnoses=diagnoses,
                rejected=design.rejected,
                reference_steps=reference.n_steps,
            )
            self._ev("llm_diagnosis", task, diagnoses=diagnoses, rejected=[])
            self._ev("llm_assist_proposals", task, accepted=families, rejected=design.rejected)
        if not design.families:
            return TaskOutcome(
                task,
                "dropped",
                "no_valid_proposal",
                "zero",
                est.p_hat,
                detail={"rejected": design.rejected},
            )
        ctx = FamilyContext(task_id=task.task_id, success_lengths=())
        tried = 0
        last: str = "no_leverage"
        for fam in design.families:
            cache: dict[float, Candidate] = {}

            def make(d: float, fam: Any = fam, cache: dict[float, Candidate] = cache) -> Candidate:
                if d not in cache:
                    cand = fam.make(d, ctx)
                    assert cand is not None
                    cache[d] = cand
                return cache[d]

            top = make(1.0)
            with SESSION_LOCK:  # the existing guard at maximum assistance (oracle; no witness)
                guard = solvable(
                    top,
                    lambda c: self.substrate.open_session(task, c, None),
                    self.config,
                    policy_success=None,
                    oracle=self.substrate.has_oracle(),
                    by_construction=False,
                )
            self._ev(
                "solvable",
                task,
                family=fam.name,
                d=1.0,
                ok=guard.ok,
                source=guard.source,
                detail=guard.detail,
            )
            if not guard.ok:
                self._ev("family_skipped", task, family=fam.name, reason="uncertified")
                last = "uncertified"
                continue
            tried += 1

            def evaluate_at(d: float, fam: Any = fam, make: Any = make) -> Eval:
                return evaluate(
                    lambda n: self._rollouts(task, make(d), n, f"dose:{fam.name}"), self.config
                )

            lev = evaluate_at(1.0)
            has_leverage = lev.verdict != "too_hard"
            self._record_leverage(task, fam.name, has_leverage)
            if lev.verdict == "in_band":
                return self._accept_assist(
                    task, fam, cache[1.0], 1.0, lev, est, [DoseEval(1.0, lev)]
                )
            if not has_leverage:
                self._ev("no_leverage", task, family=fam.name, successes=lev.successes, n=lev.n)
                last = "no_leverage"
                continue
            result = assist_bracket(evaluate_at, self.config, leverage=DoseEval(1.0, lev))
            self._ev(
                "dose_control",
                task,
                family=fam.name,
                direction="easier_with_d",
                status=result.status,
                lo=result.lo,
                hi=result.hi,
                history=[
                    {"d": h.d, "s": h.eval.successes, "n": h.eval.n, "verdict": h.eval.verdict}
                    for h in result.history
                ],
            )
            if result.status == "accepted" and result.accepted is not None:
                ev = result.accepted
                return self._accept_assist(
                    task, fam, cache[ev.d], ev.d, ev.eval, est, result.history
                )
            if result.status == "budget":
                raise BudgetExhausted(
                    "cap during assistive dose control",
                    budget="search",
                    cap=self.config.cap,
                    spent=self.budget.account(task.task_id).spent,
                    task_id=task.task_id,
                )
            # a leveraged family that did not land ends the task: no second family gets
            # fresh budget (exhausted / dose_order_violation)
            return TaskOutcome(
                task,
                "dropped",
                result.status,
                "zero",
                est.p_hat,
                detail={"family": fam.name, "lo": result.lo, "hi": result.hi},
            )
        reason = last if tried == 0 else "no_leverage"
        return TaskOutcome(
            task,
            "dropped",
            reason,
            "zero",
            est.p_hat,
            detail={"families": [f.name for f in design.families]},
        )

    def _accept_assist(
        self,
        task: TaskRef,
        fam: Any,
        cand: Candidate,
        d: float,
        ev: Eval,
        est: EstimateResult,
        history: list[DoseEval],
    ) -> TaskOutcome:
        meta = AeaMeta(
            kind="knob",
            task_id=task.task_id,
            seed=task.seed,
            regime="zero",
            family=fam.name,
            source=getattr(fam, "source", "llm"),
            axis=fam.axis,
            d=d,
            p_hat=ev.p_hat,
            candidate_id=f"{task.task_id}:{fam.name}:{d}",
        )
        self._write_corpus(task, cand, meta)
        return TaskOutcome(
            task,
            "accepted",
            "",
            "zero",
            est.p_hat,
            detail={"family": fam.name, "d": d, "p8": ev.p_hat, "doses": [h.d for h in history]},
        )

    # ------------------------------------------------------------------ llm_v1_stage_control
    def _stage_control(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        """LOW under llm_v1_stage_control (docs/design/AEA_LOW_STAGE_CONTROL.md): the verified
        reference defines the assistance family E_t; the existing 4 -> 8 measurement drives an
        integer bracket from maximum assistance t_max inward. No designer call on this path."""
        reference = self._lazy_reference(task)
        if reference is None:
            return TaskOutcome(task, "dropped", "reference_unavailable", "zero", est.p_hat)
        opts = self.substrate.stage_reset_options(task)
        compiled: dict[int, list[str]] = {}
        cands: dict[int, Candidate] = {}
        cids: dict[int, str] = {}
        rejected: list[dict[str, Any]] = []

        def open_fn(c: Candidate | None, ro: dict[str, Any] | None) -> Session:
            return self.substrate.open_session(task, c, ro)

        def build(t: int) -> tuple[bool, bool]:
            """(exact replay, terminal after replay) for depth t; caches the candidate."""
            prefix = list(reference.actions[:t])
            comp = compile_prefix(open_fn, prefix, opts)
            body = comp[:-1] if comp and comp[-1] == "look" and prefix[-1:] != ["look"] else comp
            cand = stage_candidate(comp)
            sess = open_fn(cand, opts)
            try:
                terminal = bool(sess.won or sess.done)
            finally:
                sess.close()
            compiled[t], cands[t], cids[t] = comp, cand, stage_candidate_id(task.task_id, comp)
            return body == prefix, terminal

        with SESSION_LOCK:  # simulator-side, never charged: the deepest non-terminal prefix
            t_max = 0
            for t in range(reference.n_steps, 0, -1):
                exact, terminal = build(t)
                if exact and not terminal:
                    t_max = t
                    break
                rejected.append({"t": t, "reason": "terminal" if terminal else "inexact replay"})
        self._ev("stage_family", task, T=reference.n_steps, t_max=t_max, rejected=rejected)
        if t_max == 0:
            return TaskOutcome(
                task, "dropped", "no_stage_family", "zero", est.p_hat, detail={"rejected": rejected}
            )
        profile: list[dict[str, Any]] = []

        def evaluate_at(t: int) -> Eval:
            with SESSION_LOCK:
                if t not in cands:
                    exact, terminal = build(t)
                    if not exact or terminal:
                        self._ev(
                            "stage_candidates",
                            task,
                            certified=[],
                            kinds={},
                            rejected=[
                                {
                                    "id": cids[t],
                                    "t": t,
                                    "reason": "inexact" if not exact else "terminal",
                                }
                            ],
                            source="control",
                        )
                        raise InvalidStageError(f"depth {t}")
                guard = solvable(
                    cands[t],
                    lambda c: open_fn(c, opts),
                    self.config,
                    oracle=self.substrate.has_oracle(),
                )
            self._ev(
                "stage_candidates",
                task,
                certified=[cids[t]] if guard.ok else [],
                kinds={cids[t]: "control"} if guard.ok else {},
                rejected=[] if guard.ok else [{"id": cids[t], "t": t, "reason": guard.detail}],
                source="control",
            )
            if not guard.ok:
                raise InvalidStageError(f"depth {t} uncertified")
            ev = evaluate(
                lambda n: self._rollouts(task, cands[t], n, "probe", reset_options=opts),
                self.config,
            )
            profile.append(
                {
                    "id": cids[t],
                    "t": t,
                    "source": "control",
                    "successes": ev.successes,
                    "n": ev.n,
                    "verdict": ev.verdict,
                }
            )
            return ev

        result = stage_bracket(evaluate_at, t_max)
        acc = result.accepted
        self._ev(
            "stage_control",
            task,
            T=reference.n_steps,
            t_max=t_max,
            t_max_verdict=result.history[0].eval.verdict if result.history else None,
            history=[
                {"t": h.t, "s": h.eval.successes, "n": h.eval.n, "verdict": h.eval.verdict}
                for h in result.history
            ],
            lo=result.lo,
            hi=result.hi,
            status=result.status,
            unique_cuts=result.unique_cuts,
            accepted_t=acc.t if acc else None,
            accepted_d=(acc.t / t_max) if acc else None,
        )
        if result.status == "accepted" and acc is not None:
            t = acc.t
            meta = AeaMeta(
                kind="stage",
                task_id=task.task_id,
                seed=task.seed,
                regime="zero",
                t=t,
                state_hash=cids[t].split(":", 1)[1],
                profile=profile,
                stage_budget=self.config.impl.stage_budget,
                candidate_id=cids[t],
                p_hat=acc.eval.p_hat,
            )
            self._write_corpus(task, cands[t], meta)
            self._ev("probe", task, profile=profile, accepted=cids[t])
            return TaskOutcome(
                task,
                "accepted",
                "",
                "zero",
                est.p_hat,
                detail={"t": t, "t_max": t_max, "profile": profile},
            )
        self._ev("probe", task, profile=profile, accepted=None)
        if result.status == "budget":
            raise BudgetExhausted(
                "cap during stage control",
                budget="search",
                cap=self.config.cap,
                spent=self.budget.account(task.task_id).spent,
                task_id=task.task_id,
            )
        return TaskOutcome(
            task,
            "dropped",
            result.status,
            "zero",
            est.p_hat,
            detail={"t_max": t_max, "lo": result.lo, "hi": result.hi, "profile": profile},
        )

    def _probe_stages(
        self,
        task: TaskRef,
        est: EstimateResult,
        staged: list[StagedCandidate],
        opts: dict[str, Any],
    ) -> TaskOutcome:
        """Walk the candidates in the given (designer) order; the current policy's probe is the
        only acceptance (llm_v1 copy of the v0.4 walk, kept separate so v0.4 stays untouched)."""
        profile: list[dict[str, Any]] = []
        walked: list[StagedCandidate] = []
        try:
            for c in staged:
                walked.append(c)

                def run(n: int, c: StagedCandidate = c) -> list[Trace]:
                    return self._rollouts(task, c.candidate, n, "probe", reset_options=opts)

                ev = evaluate(run, self.config)
                profile.append(
                    {
                        "id": c.id,
                        "t": c.t,
                        "source": c.kind,
                        "successes": ev.successes,
                        "n": ev.n,
                        "verdict": ev.verdict,
                    }
                )
                if ev.verdict == "in_band":
                    meta = AeaMeta(
                        kind="stage",
                        task_id=task.task_id,
                        seed=task.seed,
                        regime="zero",
                        t=c.t,
                        state_hash=c.state_hash,
                        profile=profile,
                        stage_budget=self.config.impl.stage_budget,
                        candidate_id=c.id,
                        p_hat=ev.p_hat,
                    )
                    self._write_corpus(task, c.candidate, meta)
                    self._ev("probe", task, profile=profile, accepted=c.id)
                    return TaskOutcome(
                        task,
                        "accepted",
                        "",
                        "zero",
                        est.p_hat,
                        detail={"t": c.t, "profile": profile},
                    )
        except BudgetExhausted:
            skipped = [c.id for c in staged if c not in walked]
            self._ev("probe", task, profile=profile, accepted=None, skipped=skipped)
            return TaskOutcome(
                task,
                "dropped",
                "budget",
                "zero",
                est.p_hat,
                detail={"profile": profile, "skipped": skipped},
            )
        self._ev("probe", task, profile=profile, accepted=None)
        reason = "too_easy" if any(p["verdict"] == "too_easy" for p in profile) else "dead"
        return TaskOutcome(task, "dropped", reason, "zero", est.p_hat, detail={"profile": profile})


class _InfeasibleError(Exception):
    """A family that cannot be built at the requested dose; the loop moves on."""
