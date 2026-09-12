"""The stage operator's candidates (docs/spec/AEA_v0.3.md, "Candidate states"): for each of
``impl.n_failed_rollouts`` seeded failed rollouts of the estimate, the end state, the midpoint
state and the quarter state (t = T/4); each prefix is compiled (ineffective actions dropped,
``look`` appended), replayed under the 100-step config (``reset_options.config_path``,
``bridge.py:149``) so the prefix does not consume the policy's horizon, deduplicated by the hash
of the compiled prefix, then capped at ``impl.max_candidates`` by priority end > mid > quarter
(a quarter state enters when ends or midpoints collapse to one state, as they do when the policy
loops to the step cap), walked latest-first. Each candidate is guarded by ``solvable()`` with the
oracle as the only source (a reset-origin success cannot witness a mid-trajectory state); without
an oracle the probe self-certifies. One fidelity check per task: the observation after replay
equals the archived observation at the cut.

Pilot oracle: docs/pilots/e1pilot/p5/p5/chs100.py (``staged_actions``), docs/pilots/eobs/eobs/
recover.py (``c_at``), docs/pilots/e1pilot/p4/docs/stage_budget_audit.md.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from envharness.core.types import Action, Candidate, Trace

from aea.config import AEAConfig
from aea.core.hashing import sha256_of
from aea.session import Session
from aea.witness import Solvable, solvable

type OpenFn = Callable[[Candidate | None, dict[str, Any] | None], Session]
"""Open a session on a candidate with explicit reset options (the staged config)."""


def stage_reset_options(base: dict[str, Any], config_path: Path | str) -> dict[str, Any]:
    """The base reset options plus the 100-step config; unstaged sessions keep ``base``."""
    return {**base, "config_path": str(config_path)}


def trace_actions(trace: Trace) -> list[str]:
    return [str(s.raw_action.kwargs.get("text", "")) for s in trace.steps]


def compile_prefix(
    open_fn: OpenFn, prefix: Sequence[str], reset_options: dict[str, Any]
) -> list[str]:
    """Replay ``prefix`` on a fresh staged-config session, keep admissible+effective actions, end
    with look."""
    sess = open_fn(None, reset_options)
    kept: list[str] = []
    try:
        for a in prefix:
            if a in sess.admissible():
                r = sess.step_text(a)
                if r["effective"]:
                    kept.append(a)
    finally:
        sess.close()
    if not kept or kept[-1] != "look":
        kept.append("look")
    return kept


def state_hash(compiled: Sequence[str]) -> str:
    return sha256_of(list(compiled))[:16]


def candidate_id(task_id: str, compiled: Sequence[str]) -> str:
    return f"{task_id}:{state_hash(compiled)}"


def stage_candidate(compiled: Sequence[str]) -> Candidate:
    return Candidate(
        in_env_actions=[Action(name="do", kwargs={"text": a}) for a in compiled],
        rationale="stage",
    )


def seeded_failures(traces: Sequence[Trace], n: int, seed: int) -> list[Trace]:
    fails = [t for t in traces if not t.success and not t.error and t.steps]
    rnd = random.Random(seed)
    return rnd.sample(fails, min(n, len(fails)))


KIND_RANK = {"end": 0, "mid": 1, "quarter": 2}
"""Priority when capping: end > mid > quarter."""


def candidate_states(lengths: dict[str, int], cap: int | None = None) -> list[tuple[str, int, str]]:
    """(episode, t, kind) for the end, midpoint and quarter state of each rollout, latest first;
    with ``cap``, reduced by :func:`cap_by_priority`."""
    cands: dict[tuple[str, int], str] = {}
    for eid, total in lengths.items():
        if total <= 0:
            continue
        cands.setdefault((eid, total), "end")
        cands.setdefault((eid, max(1, total // 2)), "mid")
        cands.setdefault((eid, max(1, total // 4)), "quarter")
    items = [(eid, t, kind) for (eid, t), kind in cands.items()]
    items.sort(key=lambda it: (-it[1], it[0]))
    return cap_by_priority(items, cap) if cap is not None else items


def cap_by_priority(items: list[tuple[str, int, str]], cap: int) -> list[tuple[str, int, str]]:
    """Drop the lowest-priority kind first (quarter, then mid; the latest end never drops), among
    equals the candidate nearest in t to another kept one; the result stays latest-first."""
    kept = list(items)
    while len(kept) > cap:
        head = kept[0]

        def key(it: tuple[str, int, str]) -> tuple[int, int, int]:
            others = [o for o in kept if o is not it]
            gap = min(abs(it[1] - o[1]) for o in others) if others else 0
            return (-KIND_RANK[it[2]], gap, it[1])

        drop = min((it for it in kept if it is not head), key=key)
        kept.remove(drop)
    return kept


@dataclass
class StagedCandidate:
    id: str
    episode_id: str
    t: int
    kind: str
    compiled: list[str]
    candidate: Candidate
    guard: Solvable
    fidelity_ok: bool | None = None

    @property
    def state_hash(self) -> str:
        return self.id.split(":", 1)[1]


@dataclass
class StageResult:
    candidates: list[StagedCandidate] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    fidelity_checked: bool = False


def build_stage_candidates(
    open_fn: OpenFn,
    task_id: str,
    failures: Sequence[Trace],
    reset_options: dict[str, Any],
    config: AEAConfig,
    *,
    oracle: bool = True,
) -> StageResult:
    """Select the states, compile every prefix, deduplicate by state hash, cap by priority, then
    guard the kept candidates with ``solvable()``."""
    result = StageResult()
    by_traj = {t.episode_id: t for t in failures}
    lengths = {eid: min(len(tr.steps), config.impl.policy_max_steps) for eid, tr in by_traj.items()}
    compiled_by_cid: dict[str, list[str]] = {}
    first: dict[str, tuple[str, int, str]] = {}
    for eid, t, kind in candidate_states(lengths):
        actions = trace_actions(by_traj[eid])[:t]
        compiled = compile_prefix(open_fn, actions, reset_options)
        cid = candidate_id(task_id, compiled)
        if cid in first:  # two prefixes compiling to the same staged state are one candidate
            if KIND_RANK[kind] < KIND_RANK[first[cid][2]]:  # keep the higher-priority label
                first[cid] = (first[cid][0], first[cid][1], kind)
            continue
        first[cid] = (eid, t, kind)
        compiled_by_cid[cid] = compiled
    unique = [(eid, t, kind, cid) for cid, (eid, t, kind) in first.items()]
    kept = cap_by_priority(
        [(cid, t, kind) for eid, t, kind, cid in unique], config.impl.max_candidates
    )
    kept_cids = {cid for cid, _, _ in kept}
    for eid, t, kind, cid in unique:
        if cid not in kept_cids:
            continue
        compiled = compiled_by_cid[cid]
        cand = stage_candidate(compiled)
        guard = solvable(cand, lambda c: open_fn(c, reset_options), config, oracle=oracle)
        staged = StagedCandidate(cid, eid, t, kind, compiled, cand, guard)
        if not result.fidelity_checked:
            staged.fidelity_ok = fidelity_check(open_fn, by_traj[eid], t, compiled, reset_options)
            result.fidelity_checked = True
        if guard.ok:
            result.candidates.append(staged)
        else:
            result.rejected.append({"id": staged.id, "t": t, "kind": kind, "reason": guard.detail})
    return result


def fidelity_check(
    open_fn: OpenFn, trace: Trace, t: int, compiled: Sequence[str], reset_options: dict[str, Any]
) -> bool:
    """The replayed observation equals the archived observation at the cut.

    The synthetic trailing ``look`` is left out unless the archived prefix itself ended with
    ``look`` (then it IS the cut step and its observation is the archived one)."""
    steps = trace.steps[:t]
    archived = steps[-1].filtered_observation or steps[-1].raw_observation
    if archived is None:
        return False
    prefix_ended_with_look = (
        bool(steps) and str(steps[-1].raw_action.kwargs.get("text", "")) == "look"
    )
    body = list(compiled)
    if body and body[-1] == "look" and not prefix_ended_with_look:
        body = body[:-1]
    sess = open_fn(stage_candidate(body) if body else None, reset_options)
    try:
        replayed = sess.stack.observe().text
    finally:
        sess.close()
    return _norm(replayed) == _norm(archived.text)


def _norm(text: str) -> str:
    return " ".join(text.split())
