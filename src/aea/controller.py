"""The box (docs/spec/AEA_v0.2.md): estimate -> keep | harden | stage; three outcomes.

Every policy rollout is charged to the one budget (``aea.budget``) before it runs; the cap is a
hard stop and ends the task with ``dropped: budget``. Proposer calls, replays and oracle sessions
are not charged. Confirmations (K = 16, B_L) are a separate script and never change the outcome.

Outputs in the run directory: ``corpus.jsonl`` (released loader shape + ``aea`` block; kinds
``kept`` / ``knob`` / ``stage``), ``traces.jsonl`` (released ``TraceStore``), ``accounting.csv``,
``events.jsonl`` (M0 envelope; the resume log: a task whose ``task_done`` outcome is not
``infra_error`` is skipped on resume). Task-level concurrency through a thread pool.
"""

from __future__ import annotations

import concurrent.futures as cf
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
from aea.errors import BudgetExhausted, InfraError
from aea.estimate import EstimateResult, estimate
from aea.evaluate import Eval, evaluate
from aea.families import LIBRARY, Family, FamilyContext, LeverageTable, propose_families
from aea.io import AeaMeta, TraceWriter, entry_from_candidate, write_corpus_entry
from aea.llm.types import Attribution, BudgetName, ChatRequest, ChatResponse
from aea.session import Session
from aea.stage import StagedCandidate, build_stage_candidates, seeded_failures
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
    ) -> None:
        self.config = config
        self.substrate = substrate
        self.run_dir = run_dir
        self.run_id = run_id
        self.arm = arm
        self.use_proposer = use_proposer
        self.leverage = leverage or LeverageTable(
            min_tasks=config.impl.prior_min_tasks, min_rate=config.impl.prior_min_rate
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        self.budget = Budget(config.cap)
        self.events = EventWriter(run_dir / "events.jsonl", run_id)
        self.traces = TraceWriter(run_dir / "traces.jsonl")
        self.corpus_path = run_dir / "corpus.jsonl"
        self._estimates: dict[str, EstimateResult] = {}

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

    # ------------------------------------------------------------------ the loop
    def run(self, tasks: Sequence[TaskRef], *, concurrency: int = 1) -> list[TaskOutcome]:
        done = self.completed_tasks()
        todo = [t for t in tasks if t.task_id not in done]
        if concurrency <= 1:
            outcomes = [self.run_task(t) for t in todo]
        else:
            with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
                outcomes = list(pool.map(self.run_task, todo))
        from aea.io import write_accounting

        write_accounting(self.run_dir / "accounting.csv", self.budget.accounting_rows())
        return outcomes

    def run_task(self, task: TaskRef) -> TaskOutcome:
        self._ev("task_start", task, seed=task.seed, arm=self.arm)
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
                    record=lambda payload: append_jsonl(
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

    def _harden(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
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
        guard = solvable(
            top,
            lambda c: self.substrate.open_session(task, c, None),
            self.config,
            policy_success=witness,
            oracle=self.substrate.has_oracle(),
            by_construction=fam.axis == "O",
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
        self.leverage.record_leverage(fam.name, has_leverage)
        if lev.verdict == "in_band":
            self.leverage.record_accepted(fam.name, 1.0)
            return self._accept_knob(task, fam, cache[1.0], 1.0, lev, est, [DoseEval(1.0, lev)])
        if not has_leverage:
            self._ev("no_leverage", task, family=fam.name, successes=lev.successes, n=lev.n)
            return None
        start = self.leverage.start_dose(fam.name)
        try:
            result: BracketResult = bracket(
                evaluate_at, self.config, leverage=DoseEval(1.0, lev), start=start
            )
        except _InfeasibleError as why:
            self._ev("family_skipped", task, family=fam.name, reason=str(why))
            return None
        self._ev(
            "bracket",
            task,
            family=fam.name,
            start=start,
            status=result.status,
            history=[
                {"d": h.d, "s": h.eval.successes, "n": h.eval.n, "verdict": h.eval.verdict}
                for h in result.history
            ],
        )
        if result.status == "accepted" and result.accepted is not None:
            ev = result.accepted
            self.leverage.record_accepted(fam.name, ev.d)
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
        failures = seeded_failures(est.traces, self.config.impl.n_failed_rollouts, seed=task.seed)
        if not failures:
            return TaskOutcome(task, "dropped", "no_failed_rollout", "zero", est.p_hat)
        opts = self.substrate.stage_reset_options(task)
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


class _InfeasibleError(Exception):
    """A family that cannot be built at the requested dose; the loop moves on."""
