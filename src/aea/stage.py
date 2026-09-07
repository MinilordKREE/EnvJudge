"""Prefix staging with the re-based stage budget (spec section 5).

Compile order: take the prefix of a failed rollout -> drop ineffective actions (the bridge's
``effective`` flag, ``bridge.py:284``) -> append ``look`` -> build a ``Setup`` over the 100-step
config (``reset_options.config_path``, ``bridge.py:149``) -> actually replay -> certify THAT
environment with the expert x3 (``aea.certs``) -> only then probe. Candidate id =
``task_id + sha256(compiled prefix)``. One fidelity check per task: the observation after replay
equals the archived observation at the cut.

Candidates (spec section 5): for each of ``n_failed_trajectories`` seeded failed rollouts of length
T, the prefixes t in {T, 3T/4, T/2, T/4}; union, latest-first, capped at ``max_candidates`` by
dropping the candidate nearest in t to another kept one. Each candidate is compiled, replayed and
certified individually (no prefix sweep).

Pilot oracle: docs/pilots/e1pilot/p5/p5/chs100.py (``staged_actions``, ``select_candidates``),
docs/pilots/eobs/eobs/recover.py (``c_at``), docs/pilots/e1pilot/p4/docs/stage_budget_audit.md.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from envharness.core.types import Action, Candidate, Trace

from aea.certs import Certificate, Session, certify
from aea.config import AEAConfig
from aea.core.hashing import sha256_of

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


def candidate_id(task_id: str, compiled: Sequence[str]) -> str:
    return f"{task_id}:{sha256_of(list(compiled))[:16]}"


def stage_candidate(compiled: Sequence[str]) -> Candidate:
    return Candidate(
        in_env_actions=[Action(name="do", kwargs={"text": a}) for a in compiled],
        rationale="stage",
    )


def select_candidates(
    certified_by_traj: dict[str, list[int]], fractions: Sequence[float], cap: int
) -> list[tuple[str, int, str]]:
    """Per trajectory: L and the certified states nearest each fraction of L; union latest-first;
    cap by dropping the candidate nearest in t to a kept one (the latest overall never drops)."""
    cands: dict[tuple[str, int], str] = {}
    for eid, ts in certified_by_traj.items():
        certified = sorted({t for t in ts if t > 0})
        if not certified:
            continue
        latest = certified[-1]
        for frac in fractions:
            target = frac * latest
            t = min(certified, key=lambda x: (abs(x - target), -x))
            kind = "L" if frac == 1.0 else f"{frac:g}L"
            cands.setdefault((eid, t), kind)
    items = sorted(cands.items(), key=lambda kv: (-kv[0][1], kv[0][0]))
    while len(items) > cap:
        head = items[0]

        def gap(it: tuple[tuple[str, int], str]) -> tuple[int, int]:
            others = [o for o in items if o is not it]
            return (min(abs(it[0][1] - o[0][1]) for o in others), it[0][1])

        drop = min((it for it in items if it is not head), key=gap)
        items.remove(drop)
    return [(eid, t, kind) for (eid, t), kind in items]


def seeded_failures(traces: Sequence[Trace], n: int, seed: int) -> list[Trace]:
    fails = [t for t in traces if not t.success and not t.error and t.steps]
    rnd = random.Random(seed)
    return rnd.sample(fails, min(n, len(fails)))


@dataclass
class StagedCandidate:
    id: str
    episode_id: str
    t: int
    kind: str
    compiled: list[str]
    candidate: Candidate
    certificate: Certificate
    fidelity_ok: bool | None = None

    @property
    def certified(self) -> bool:
        return self.certificate.certified


@dataclass
class StageResult:
    candidates: list[StagedCandidate] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    fidelity_checked: bool = False


def candidate_states(
    lengths: dict[str, int], fractions: Sequence[float], cap: int
) -> list[tuple[str, int, str]]:
    """Prefix lengths at the fractions of each trajectory's length T; union latest-first; capped."""
    valid = {eid: total for eid, total in lengths.items() if total > 0}
    return _fraction_candidates(valid, fractions, cap)


def _fraction_candidates(
    lengths: dict[str, int], fractions: Sequence[float], cap: int
) -> list[tuple[str, int, str]]:
    cands: dict[tuple[str, int], str] = {}
    for eid, total in lengths.items():
        for frac in fractions:
            t = max(1, round(frac * total))
            kind = "T" if frac == 1.0 else f"{frac:g}T"
            cands.setdefault((eid, t), kind)
    items = sorted(cands.items(), key=lambda kv: (-kv[0][1], kv[0][0]))
    while len(items) > cap:
        head = items[0]

        def gap(it: tuple[tuple[str, int], str]) -> tuple[int, int]:
            others = [o for o in items if o is not it]
            return (min(abs(it[0][1] - o[0][1]) for o in others), it[0][1])

        drop = min((it for it in items if it is not head), key=gap)
        items.remove(drop)
    return [(eid, t, kind) for (eid, t), kind in items]


def build_stage_candidates(
    open_fn: OpenFn,
    task_id: str,
    failures: Sequence[Trace],
    reset_options: dict[str, Any],
    config: AEAConfig,
    *,
    certified_states: dict[str, list[int]] | None = None,
) -> StageResult:
    """Select candidate states, compile each prefix, replay it, certify that environment.

    ``certified_states`` (tests / pilot fixtures) overrides the T-fraction rule with explicit
    prefix lengths per trajectory."""
    result = StageResult()
    by_traj = {t.episode_id: t for t in failures}
    if certified_states is not None:
        selected = select_candidates(
            certified_states, config.candidate_fractions, config.max_candidates
        )
    else:
        lengths = {eid: min(len(tr.steps), config.policy_max_steps) for eid, tr in by_traj.items()}
        selected = candidate_states(lengths, config.candidate_fractions, config.max_candidates)
    seen: set[str] = set()
    for eid, t, kind in selected:
        actions = trace_actions(by_traj[eid])[:t]
        compiled = compile_prefix(open_fn, actions, reset_options)
        cid = candidate_id(task_id, compiled)
        if cid in seen:  # two prefixes compiling to the same staged state are one candidate
            continue
        seen.add(cid)
        cand = stage_candidate(compiled)
        cert = certify(cand, lambda c: open_fn(c, reset_options), config)
        staged = StagedCandidate(cid, eid, t, kind, compiled, cand, cert)
        if not result.fidelity_checked:
            staged.fidelity_ok = fidelity_check(open_fn, by_traj[eid], t, compiled, reset_options)
            result.fidelity_checked = True
        if cert.certified:
            result.candidates.append(staged)
        else:
            result.rejected.append({"id": staged.id, "t": t, "reason": cert.detail})
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
