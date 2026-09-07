"""The AEA loop (spec section 9): estimate -> band | saturated (knobs, dose) | zero (stage, probe).

Every policy rollout is charged to ``search`` through :class:`aea.budget.Budget` before it runs;
the per-task hard cap stops the task with ``budget_cap_hit``. Designer calls, expert sessions and
verbatim replays are recorded but not charged. K16 confirmation is a separate script (section 10)
and never changes controller output. Unresolved and frozen tasks go to accounting only; the
AEA+Handoff arm additionally records an expert demonstration for unresolved zero tasks (section 7).

Outputs in the run directory: ``corpus.jsonl`` (released loader shape + ``aea`` block),
``traces.jsonl`` (released ``TraceStore``), ``accounting.csv``, ``handoff.jsonl``, ``events.jsonl``
(M0 envelope; the resume log). Resumable per task: a task with a ``task_done`` event is skipped.
Task-level concurrency through a thread pool; batches inside a task are 4 or 2.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from envharness.core.types import Candidate, Trace

from aea import dose as dose_mod
from aea import probe as probe_mod
from aea.budget import Budget
from aea.certs import Session, certify
from aea.config import AEAConfig
from aea.core.trace import TraceWriter as EventWriter
from aea.core.trace import read_trace
from aea.errors import BudgetExhausted, InfraError
from aea.estimate import EstimateResult, estimate
from aea.handoff import handoff
from aea.io import (
    AeaMeta,
    TraceWriter,
    entry_from_candidate,
    mark_hint,
    write_accounting,
    write_corpus_entry,
)
from aea.knobs import EXEMPLARS, Knob, KnobContext, order_families, propose_knobs
from aea.llm.types import Attribution, BudgetName, ChatRequest, ChatResponse
from aea.stage import StagedCandidate, build_stage_candidates, seeded_failures, trace_actions

logger = logging.getLogger(__name__)

type TaskStatus = Literal[
    "band",
    "accepted_knob",
    "frozen_no_leverage",
    "exhausted",
    "accepted_stage",
    "unresolved",
    "unresolved_budget_limited",
    "budget_cap_hit",
    "infra_error",
    "no_failed_trajectory",
]


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
        hint: Sequence[str] | None = None,
    ) -> list[Trace]: ...

    def open_session(
        self, task: TaskRef, candidate: Candidate | None, reset_options: dict[str, Any] | None
    ) -> Session: ...

    def game_file(self, task: TaskRef) -> str: ...

    def stage_reset_options(self, task: TaskRef) -> dict[str, Any]: ...

    def designer(self) -> Callable[[ChatRequest], ChatResponse] | None: ...

    def designer_model(self) -> str: ...

    def setup_builder(self, task: TaskRef) -> Callable[[float], list[str] | None] | None: ...


@dataclass
class TaskOutcome:
    task: TaskRef
    status: TaskStatus
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
        round_index: int = 0,
        with_handoff: bool = False,
        use_designer: bool = True,
    ) -> None:
        self.config = config
        self.substrate = substrate
        self.run_dir = run_dir
        self.run_id = run_id
        self.arm = arm
        self.round_index = round_index
        self.with_handoff = with_handoff
        self.use_designer = use_designer
        run_dir.mkdir(parents=True, exist_ok=True)
        self.budget = Budget(config.search_cap)
        self.events = EventWriter(run_dir / "events.jsonl", run_id)
        self.traces = TraceWriter(run_dir / "traces.jsonl")
        self.handoffs = TraceWriter(run_dir / "handoff.jsonl")
        self.corpus_path = run_dir / "corpus.jsonl"
        self._estimates: dict[str, EstimateResult] = {}

    # ------------------------------------------------------------------ plumbing
    def _attr(self, task: TaskRef, phase: str, budget: BudgetName = "search") -> Attribution:
        return Attribution(phase=phase, budget=budget, arm=self.arm, task_id=task.task_id)

    def _charged_rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        phase: str,
        *,
        reset_options: dict[str, Any] | None = None,
        hint: Sequence[str] | None = None,
    ) -> list[Trace]:
        """Charge ``n`` to search BEFORE running (the cap is a hard stop), then run and record."""
        self.budget.charge(
            task.task_id, n, budget="search", phase=phase, round_index=self.round_index
        )
        traces = self.substrate.rollouts(
            task,
            candidate,
            n,
            attribution=self._attr(task, phase),
            reset_options=reset_options,
            hint=hint,
        )
        errored = sum(1 for t in traces if t.error)
        if errored:  # environment / infrastructure errors are refunded and never counted
            self.budget.refund(
                task.task_id, errored, budget="search", phase=phase, round_index=self.round_index
            )
            self.events.write(
                "rollout_errors", {"task_id": task.task_id, "phase": phase, "n": errored}
            )
        for t in traces:
            if hint:
                mark_hint(t)
            self.traces.add(t)
        self.events.write(
            "rollouts",
            {
                "task_id": task.task_id,
                "phase": phase,
                "n": len(traces),
                "successes": sum(int(bool(t.success)) for t in traces),
            },
        )
        return traces

    def _write_corpus(self, task: TaskRef, candidate: Candidate, meta: AeaMeta) -> None:
        write_corpus_entry(
            self.corpus_path, entry_from_candidate(self.substrate.game_file(task), candidate, meta)
        )
        self.events.write(
            "corpus_entry",
            {"task_id": task.task_id, "kind": meta.kind, "candidate_id": meta.candidate_id},
        )

    def completed_tasks(self) -> set[str]:
        path = self.run_dir / "events.jsonl"
        if not path.exists():
            return set()
        return {str(e.payload["task_id"]) for e in read_trace(path) if e.kind == "task_done"}

    # ------------------------------------------------------------------ the loop
    def run(self, tasks: Sequence[TaskRef], *, concurrency: int = 1) -> list[TaskOutcome]:
        done = self.completed_tasks()
        todo = [t for t in tasks if t.task_id not in done]
        outcomes: list[TaskOutcome] = []
        if concurrency <= 1:
            for task in todo:
                outcomes.append(self.run_task(task))
        else:
            with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
                outcomes = list(pool.map(self.run_task, todo))
        write_accounting(self.run_dir / "accounting.csv", self.budget.accounting_rows())
        return outcomes

    def run_task(self, task: TaskRef) -> TaskOutcome:
        self.events.write(
            "task_start", {"task_id": task.task_id, "seed": task.seed, "arm": self.arm}
        )
        try:
            outcome = self._run_task(task)
        except BudgetExhausted as exc:
            est = self._estimates.get(task.task_id)
            outcome = TaskOutcome(
                task,
                "budget_cap_hit",
                est.regime if est else None,
                est.p_hat if est else None,
                detail={"spent": exc.spent, "budget": exc.budget},
            )
        except InfraError as exc:
            outcome = TaskOutcome(task, "infra_error", detail={"error": str(exc), "kind": exc.kind})
        outcome.n_search = self.budget.account(task.task_id, self.round_index).search_spent
        self.events.write(
            "task_done",
            {
                "task_id": task.task_id,
                "status": outcome.status,
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
        self.events.write(
            "estimate",
            {
                "task_id": task.task_id,
                "regime": est.regime,
                "p_hat": est.p_hat,
                "n": est.n,
                "probabilities": est.probabilities,
                "stop": est.stop_reason,
            },
        )
        if est.regime == "band":
            meta = AeaMeta(
                kind="band",
                task_id=task.task_id,
                seed=task.seed,
                round=self.round_index,
                regime="band",
                p8=est.p_hat,
                n_search=est.n,
                candidate_id=f"{task.task_id}:band",
            )
            self._write_corpus(task, Candidate(), meta)
            return TaskOutcome(task, "band", "band", est.p_hat)
        if est.regime == "saturated":
            return self._saturated(task, est)
        return self._zero(task, est)

    def _estimate(self, task: TaskRef) -> EstimateResult:
        pending: list[Trace] = []
        cfg = self.config

        def rollout(i: int) -> Trace:
            if not pending:
                n = cfg.batch_first if i == 0 else cfg.batch_next
                pending.extend(self._charged_rollouts(task, Candidate(), n, "estimate"))
            return pending.pop(0)

        return estimate(rollout, cfg)

    # ------------------------------------------------------------------ saturated side
    def _saturated(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        successes = [t for t in est.traces if t.success]
        lengths = tuple(t.duration_steps or len(t.steps) for t in successes)
        witnesses = sorted((trace_actions(t) for t in successes), key=len)
        ctx = KnobContext(
            task_id=task.task_id,
            success_lengths=lengths,
            setup_builder=self.substrate.setup_builder(task),
        )
        families = self._families(task, lengths)
        exhausted: list[str] = []
        for knob in families:
            outcome = self._try_family(task, knob, ctx, witnesses, est)
            if outcome is None:
                continue
            if outcome.status == "exhausted":  # spec section 9: only acceptance breaks the loop
                exhausted.append(knob.name)
                continue
            return outcome
        status: TaskStatus = "exhausted" if exhausted else "frozen_no_leverage"
        return TaskOutcome(
            task,
            status,
            "saturated",
            est.p_hat,
            detail={"families": [k.name for k in families], "exhausted": exhausted},
        )

    def _families(self, task: TaskRef, lengths: tuple[int, ...]) -> list[Knob]:
        designer = self.substrate.designer() if self.use_designer else None
        if designer is None or self.config.max_designer_families == 0:
            return list(EXEMPLARS)
        try:
            proposed, rejected, ranking = propose_knobs(
                designer,
                model=self.substrate.designer_model(),
                task_description=f"task {task.task_id}",
                success_summary=f"successful episode lengths: {sorted(lengths)}",
                max_families=self.config.max_designer_families,
                attribution=self._attr(task, "propose", "designer"),
                seed=task.seed,
            )
        except InfraError as exc:
            self.events.write("designer_failed", {"task_id": task.task_id, "error": str(exc)})
            return list(EXEMPLARS)
        self.events.write(
            "designer",
            {
                "task_id": task.task_id,
                "proposed": [k.name for k in proposed],
                "rejected": rejected,
                "ranking": ranking,
            },
        )
        return order_families(proposed, ranking)

    def _try_family(
        self,
        task: TaskRef,
        knob: Knob,
        ctx: KnobContext,
        witnesses: list[list[str]],
        est: EstimateResult,
    ) -> TaskOutcome | None:
        cache: dict[float, Candidate] = {}
        certified: dict[float, str] = {}

        def make(d: float) -> Candidate | None:
            if d not in cache:
                cand = knob.make(d, ctx)
                if cand is None:
                    return None
                cache[d] = cand
            return cache[d]

        def run(d: float, n: int) -> list[Trace]:
            cand = make(d)
            if cand is None:
                raise _InfeasibleError(f"{knob.name} infeasible at d={d}")
            if d not in certified:
                certified[d] = self._certify_knob(task, knob, cand, d, witnesses)
                if certified[d] == "uncertified":
                    raise _InfeasibleError(f"{knob.name} uncertified at d={d}")
            return self._charged_rollouts(task, cand, n, f"dose:{knob.name}")

        try:
            result = dose_mod.dose_search(run, self.config)
        except _InfeasibleError as why:
            self.events.write(
                "family_skipped", {"task_id": task.task_id, "family": knob.name, "reason": str(why)}
            )
            return None
        self.events.write(
            "dose_search",
            {
                "task_id": task.task_id,
                "family": knob.name,
                "status": result.status,
                "history": [
                    {"d": h.d, "s": h.successes, "n": h.n, "cls": h.cls} for h in result.history
                ],
                "non_monotone": result.non_monotone,
            },
        )
        if result.status == "accepted" and result.accepted is not None:
            ev = result.accepted
            cand = cache[ev.d]
            meta = AeaMeta(
                kind="knob",
                task_id=task.task_id,
                seed=task.seed,
                round=self.round_index,
                regime="saturated",
                family=knob.name,
                source=knob.source,
                axis=knob.axis,
                d=ev.d,
                p8=ev.p_hat,
                candidate_id=f"{task.task_id}:{knob.name}:{ev.d}",
                certificate=certified.get(ev.d),
            )
            self._write_corpus(task, cand, meta)
            return TaskOutcome(
                task,
                "accepted_knob",
                "saturated",
                est.p_hat,
                detail={"family": knob.name, "d": ev.d, "p8": ev.p_hat},
            )
        if result.status == "budget_cap_hit":
            raise BudgetExhausted(
                "cap during dose search",
                budget="search",
                cap=self.config.search_cap,
                spent=self.budget.account(task.task_id, self.round_index).search_spent,
                task_id=task.task_id,
            )
        if result.status == "exhausted":
            return TaskOutcome(
                task, "exhausted", "saturated", est.p_hat, detail={"family": knob.name}
            )
        return None  # no_leverage: next family

    def _certify_knob(
        self, task: TaskRef, knob: Knob, cand: Candidate, d: float, witnesses: list[list[str]]
    ) -> str:
        shortest = min((len(w) for w in witnesses), default=None)
        m = _m_of(cand)
        by_construction = knob.axis == "O" or (
            knob.name == "horizon_squeeze"
            and shortest is not None
            and m is not None
            and m >= shortest
        )

        def hint_rollout(plan: list[str]) -> bool:
            traces = self._charged_rollouts(task, cand, 1, f"hint:{knob.name}", hint=plan)
            return bool(traces and traces[0].success)

        cert = certify(
            cand,
            lambda c: self.substrate.open_session(task, c, None),
            self.config,
            policy_witness=witnesses[0] if witnesses else None,
            by_construction=by_construction,
            hint_rollout=hint_rollout if self.config.hint_attempts else None,
        )
        self.events.write(
            "certificate",
            {
                "task_id": task.task_id,
                "family": knob.name,
                "d": d,
                "source": cert.source,
                "detail": cert.detail,
            },
        )
        return cert.source

    # ------------------------------------------------------------------ zero side
    def _zero(self, task: TaskRef, est: EstimateResult) -> TaskOutcome:
        failures = seeded_failures(est.traces, self.config.n_failed_trajectories, seed=task.seed)
        if not failures:
            return TaskOutcome(task, "no_failed_trajectory", "zero", est.p_hat)
        opts = self.substrate.stage_reset_options(task)
        staged = build_stage_candidates(
            lambda c, ro: self.substrate.open_session(task, c, ro),
            task.task_id,
            failures,
            opts,
            self.config,
        )
        self.events.write(
            "stage_candidates",
            {
                "task_id": task.task_id,
                "certified": [c.id for c in staged.candidates],
                "rejected": staged.rejected,
                "fidelity_ok": [
                    c.fidelity_ok for c in staged.candidates if c.fidelity_ok is not None
                ],
            },
        )

        def run(c: StagedCandidate, n: int) -> list[Trace]:
            return self._charged_rollouts(task, c.candidate, n, "probe", reset_options=opts)

        # Spec section 5: probes <= 5 x 4 within the 30 cap. Only candidates the remaining budget
        # can afford are walked (latest-first); the rest are recorded as skipped, not charged.
        remaining = self.budget.account(task.task_id, self.round_index).remaining()
        affordable = max(remaining // self.config.probe_k, 0)
        ordered = sorted(staged.candidates, key=lambda c: -c.t)
        walk, skipped = ordered[:affordable], ordered[affordable:]
        if skipped:
            self.events.write(
                "probe_skipped_budget",
                {"task_id": task.task_id, "skipped": [c.id for c in skipped]},
            )
        result = probe_mod.probe(walk, run, self.config)
        profile = [
            {"t": e.candidate.t, "successes": e.successes, "n": e.n, "cls": e.cls}
            for e in result.profile
        ]
        self.events.write(
            "probe", {"task_id": task.task_id, "status": result.status, "profile": profile}
        )
        if result.status == "accepted" and result.accepted is not None:
            c = result.accepted.candidate
            meta = AeaMeta(
                kind="stage",
                task_id=task.task_id,
                seed=task.seed,
                round=self.round_index,
                regime="zero",
                t=c.t,
                prefix_sha=c.id.split(":", 1)[1],
                profile=profile,
                stage_budget=self.config.stage_budget,
                candidate_id=c.id,
                certificate=c.certificate.source,
                p8=result.accepted.p_hat,
            )
            self._write_corpus(task, c.candidate, meta)
            return TaskOutcome(
                task, "accepted_stage", "zero", est.p_hat, detail={"t": c.t, "profile": profile}
            )
        if result.status == "budget_cap_hit":
            raise BudgetExhausted(
                "cap during probes",
                budget="search",
                cap=self.config.search_cap,
                spent=self.budget.account(task.task_id, self.round_index).search_spent,
                task_id=task.task_id,
            )
        if skipped:  # probes cut by the remaining budget: not an exhaustive verdict, no hand-off
            return TaskOutcome(
                task,
                "unresolved_budget_limited",
                "zero",
                est.p_hat,
                detail={
                    "profile": profile,
                    "too_easy": [e.candidate.t for e in result.too_easy],
                    "skipped": [c.id for c in skipped],
                },
            )
        if self.with_handoff:
            demo = handoff(
                lambda c: self.substrate.open_session(task, c, None),
                self.config,
                task_label=task.label,
                task_seed=task.seed,
            )
            if demo is not None:
                self.handoffs.add(demo)
                self.events.write(
                    "handoff", {"task_id": task.task_id, "steps": demo.duration_steps}
                )
        return TaskOutcome(
            task,
            "unresolved",
            "zero",
            est.p_hat,
            detail={"profile": profile, "too_easy": [e.candidate.t for e in result.too_easy]},
        )


class _InfeasibleError(Exception):
    """A family that cannot be built or certified at the requested dose; the loop moves on."""


def _m_of(cand: Candidate) -> int | None:
    for line in cand.rules_code.splitlines():
        if line.strip().startswith("M = "):
            try:
                return int(line.split("=", 1)[1].strip())
            except ValueError:
                return None
    return None
