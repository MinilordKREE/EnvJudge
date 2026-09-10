"""The one guard: ``solvable()`` (docs/spec/AEA_v0.2.md, "One guard, asymmetric").

Sources, by operator: harden -> (1) the policy's own shortest success on the task, replayed through
the wrapped environment, then (2) the benchmark oracle; stage -> the oracle only (a success from
reset cannot witness a mid-trajectory state). Any source passing -> solvable. A failed replay is not
evidence of unsolvability: replay fails -> try the oracle; oracle fails -> ``uncertified``; replay
fails and no oracle (or stage without an oracle) -> ``self_certify`` (the evaluation is the
evidence). Observation-axis families are solvable ``by_construction``. Replays and oracle sessions
are not policy rollouts and are never charged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from envharness.core.types import Candidate

from aea.config import AEAConfig
from aea.session import Session, replay_actions, run_expert

type SessionFactory = Callable[[Candidate | None], Session]
type Verdict = Literal["by_construction", "policy_replay", "oracle", "self_certify", "uncertified"]


@dataclass
class Solvable:
    ok: bool
    source: Verdict
    detail: dict[str, Any] = field(default_factory=dict)
    witness: list[str] | None = None


def solvable(
    candidate: Candidate,
    open_fn: SessionFactory,
    config: AEAConfig,
    *,
    policy_success: list[str] | None = None,
    oracle: bool = True,
    by_construction: bool = False,
) -> Solvable:
    if by_construction:
        return Solvable(True, "by_construction")
    detail: dict[str, Any] = {}
    if policy_success:
        sess = open_fn(candidate)
        try:
            r = replay_actions(sess, policy_success)
        finally:
            sess.close()
        if r.ok:
            return Solvable(True, "policy_replay", {"n_steps": r.n_steps}, list(policy_success))
        detail["policy_replay"] = r.reason
    if oracle:
        for attempt in range(1, config.impl.oracle_attempts + 1):
            sess = open_fn(candidate)
            try:
                r = run_expert(sess, max_steps=config.impl.oracle_max_steps)
            finally:
                sess.close()
            if r.ok:
                detail["oracle_attempt"] = attempt
                return Solvable(True, "oracle", detail, list(r.actions))
            detail[f"oracle_{attempt}"] = r.reason
        return Solvable(False, "uncertified", detail)
    return Solvable(True, "self_certify", detail)


def policy_shortest_success(traces: list[Any]) -> list[str] | None:
    """The policy's shortest successful action sequence among the estimate rollouts."""
    best: list[str] | None = None
    for t in traces:
        if not t.success or t.error:
            continue
        actions = [str(s.raw_action.kwargs.get("text", "")) for s in t.steps]
        if best is None or len(actions) < len(best):
            best = actions
    return best
