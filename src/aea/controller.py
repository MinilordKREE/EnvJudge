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
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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
    Evidence,
    Reference,
    ReferenceProvider,
    design_high,
    design_low,
    serialize_high,
    serialize_low,
)
from aea.errors import BudgetExhausted, InfraError
from aea.estimate import EstimateResult, estimate
from aea.evaluate import Eval, evaluate
from aea.families import LIBRARY, Family, FamilyContext, LeverageTable, propose_families
from aea.io import (
    AeaMeta,
    TraceWriter,
    canonicalize_corpus,
    entry_from_candidate,
    write_accounting,
    write_corpus_entry,
)
from aea.llm.types import Attribution, BudgetName, ChatRequest, ChatResponse
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
from aea.witness import policy_shortest_success, solvable

type Outcome = Literal["accepted", "kept", "dropped", "infra_error"]


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
    ) -> None:
        self.config = config
        self.reference = reference
        """``llm_v1`` LOW only: the privileged reference provider (None = failure-only mode)."""
        self.substrate = substrate
        self.run_dir = run_dir
        self.run_id = run_id
        self.arm = arm
        self.use_proposer = use_proposer
        self.leverage = leverage or LeverageTable()
        run_dir.mkdir(parents=True, exist_ok=True)
        self.budget = Budget(config.cap)
        self.events = EventWriter(run_dir / "events.jsonl", run_id)
        self.traces = TraceWriter(run_dir / "traces.jsonl")
        self.corpus_path = run_dir / "corpus.jsonl"
        self._estimates: dict[str, EstimateResult] = {}
        self._io_lock = threading.Lock()
        self._order: dict[str, int] = {}
        self._finished: dict[str, threading.Event] = {}
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
        self.budget.charge(task.task_id, n, phase=phase)
        traces = self.substrate.rollouts(
            task, candidate, n, attribution=self._attr(task, phase), reset_options=reset_options
        )
        errored = sum(1 for t in traces if t.error)
        if errored:  # environment / infrastructure errors are refunded and never counted
            self.budget.refund(task.task_id, errored, phase=phase)
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
        return traces

    def _write_corpus(self, task: TaskRef, candidate: Candidate, meta: AeaMeta) -> None:
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
        self.leverage.record_leverage(family, has_leverage)
        self._ev("leverage", task, family=family, tested=True, has_leverage=has_leverage)

    def _record_frontier(
        self, task: TaskRef, family: str, lo: float, hi: float, accepted: float | None
    ) -> None:
        frontier = accepted if accepted is not None else (lo + hi) / 2
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
        write_accounting(self.run_dir / "accounting.csv", self.budget.accounting_rows(order))
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
        if est.regime == "band":
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
        if est.regime == "saturated":
            return self._harden(task, est)
        return self._stage(task, est)

    def _estimate(self, task: TaskRef) -> EstimateResult:
        pending: list[Trace] = []
        impl = self.config.impl

        def rollout(i: int) -> Trace:
            if not pending:
                n = impl.batch_first if i == 0 else impl.batch_next
                pending.extend(self._rollouts(task, Candidate(), n, "estimate"))
            return pending.pop(0)

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

    def _harden(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        if self.config.method_version == "llm_v1":
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
                by_construction=fam.axis == "O" and self.config.method_version != "llm_v1",
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
            return evaluate(
                lambda n: self._rollouts(task, cand, n, f"dose:{fam.name}"), self.config
            )

        try:
            lev = evaluate_at(1.0)
        except _InfeasibleError:
            return None
        has_leverage = lev.verdict != "too_easy"
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

    def _start_dose(self, fam: Family) -> float:
        """The first interior probe of the bracket. v0.4: the family's soft warm start. llm_v1:
        always the midpoint — a generated family's name is a per-task identity, so no
        cross-task frontier history is trusted for it (docs/spec/AEA_llm_v1.md, "Warm start")."""
        if self.config.method_version == "llm_v1":
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
        if self.config.method_version == "llm_v1":
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
                "method_version": "llm_v1",
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

    def _lazy_reference(self, task: TaskRef) -> Reference | None:
        """LOW under llm_v1 only: the privileged reference, requested here and nowhere else."""
        if self.reference is None:
            self._ev("reference", task, requested=True, available=False, reason="no_provider")
            return None
        ref = self.reference(task)
        self._ev(
            "reference",
            task,
            requested=True,
            available=ref.ok,
            n_steps=ref.n_steps,
            reason=ref.reason,
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
        evidence = serialize_low(failures, est.p_hat, est.n, reference)
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
            {"source": p.source, "trajectory_id": p.trajectory_id, "step": p.step}
            for p in design.stages
        ]
        self._record_designer(
            task,
            "zero",
            evidence,
            arguments=design.arguments,
            accepted=proposals,
            mechanisms=[p.mechanism_summary for p in design.stages],
            rejected=design.rejected,
            reference_steps=reference.n_steps if reference else None,
        )
        self._ev("llm_stage_proposals", task, accepted=proposals, rejected=design.rejected)
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
