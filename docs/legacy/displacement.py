"""Displacement builder (spec section 3, exemplar 3; S0 axis): the target objects the expert picks
up are moved before the policy starts.

k = 1: each target to a different OPEN receptacle (never its source, never the goal receptacle
class); k = 2: each target inside a closable container (go to C, open C, move, close C); k = 3:
k = 2 plus every other closable container closed. Destinations are tried in a seeded order; every
list is validated step by step on a fresh session (admissible before issue, effective after; the
open/close steps that are already in the wanted state are dropped) and rejected if the staged
state is already won or ended. Certified afterwards by the expert x3 (``aea.certs``).

Ported behaviour (oracle): docs/pilots/e1pilot/e1/operators/s0_displace.py (``discover``,
``synthesize``, ``validate``, ``compact``, ``build``; the pilot validated it LLM-free on seeds 7, 9,
2, 0 — see docs/pilots/e1pilot/LOG.md). ALFWorld facts relied on: the placement verb is
``move <obj> to <recep>``; a receptacle is closable iff ``open X`` / ``close X`` is admissible after
``go to X``; the expert plan is read through the certs session. No runtime import from the pilots.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from envharness.core.types import Action, Candidate

from aea.certs import Session, run_expert
from aea.knobs import displacement_k

SEED = 20260910
TAKE_RE = re.compile(r"^take (.+?) from (.+)$")
MOVE_RE = re.compile(r"^move (.+?) to (.+)$")
GOAL_RE = re.compile(r"\b(?:in|on|under|with)\s+(?:the\s+|a\s+|an\s+)?([a-z]+)\s*\.?\s*$")

type OpenFn = Callable[[Candidate | None], Session]


def receptacle_class(recep: str) -> str:
    return re.sub(r"\s*\d+$", "", recep)


def goal_class_from_text(goal_text: str) -> str | None:
    """'Your task is to: put two lettuce in fridge.' -> 'fridge' (when the expert did not win)."""
    m = GOAL_RE.search((goal_text or "").lower())
    return m.group(1) if m else None


@dataclass
class TaskInfo:
    task_id: str
    targets: list[tuple[str, str]]  # (object, source receptacle)
    receptacles: list[str]  # from the admissible `go to` list at reset
    openable: dict[str, bool] = field(default_factory=dict)
    expert_actions: list[str] = field(default_factory=list)
    goal_recep_class: str | None = None  # never a destination


def n_targets_for(goal_text: str) -> int:
    return 2 if "two" in (goal_text or "").lower() else 1


def discover(open_fn: OpenFn, *, attempts: int = 3, max_steps: int = 50) -> TaskInfo | None:
    """Find the targets by watching the expert; probe every receptacle's openability."""
    info: TaskInfo | None = None
    for _ in range(attempts):
        sess = open_fn(None)
        try:
            goal = str(getattr(sess.bridge.state, "goal_text", "") or "")
            wanted = n_targets_for(goal)
            recs = [c[len("go to ") :] for c in sess.admissible() if c.startswith("go to ")]
            start = len(sess.actions)
            res = run_expert(sess, max_steps=max_steps)
            taken: list[tuple[str, str]] = []
            for a in sess.actions[start:]:
                m = TAKE_RE.match(a)
                if m and (m.group(1), m.group(2)) not in taken:
                    taken.append((m.group(1), m.group(2)))
                if len(taken) >= wanted:
                    break
            if len(taken) >= wanted:
                moves = [MOVE_RE.match(a) for a in sess.actions[start:]]
                found = [m for m in moves if m]
                goal_cls = (
                    receptacle_class(found[-1].group(2))
                    if (res.ok and found)
                    else goal_class_from_text(goal)
                )
                info = TaskInfo(
                    task_id=str(sess.seed),
                    targets=taken[:wanted],
                    receptacles=recs,
                    expert_actions=list(sess.actions[start:]),
                    goal_recep_class=goal_cls,
                )
                break
        finally:
            sess.close()
    if info is None:
        return None
    sess = open_fn(None)
    try:
        for r in info.receptacles:
            sess.step_text(f"go to {r}")
            info.openable[r] = any(c in (f"open {r}", f"close {r}") for c in sess.admissible())
    finally:
        sess.close()
    return info


def destination_order(candidates: list[str], task_id: str, k: int) -> list[str]:
    rnd = random.Random(SEED + 1000 * k + int(task_id) if task_id.isdigit() else SEED + 1000 * k)
    out = list(candidates)
    rnd.shuffle(out)
    return out


def synthesize(info: TaskInfo, k: int) -> list[list[str]]:
    """Candidate action lists in deterministic order (the first that validates is used)."""
    sources = {src for _, src in info.targets}

    def banned(r: str) -> bool:
        return r in sources or (
            info.goal_recep_class is not None and receptacle_class(r) == info.goal_recep_class
        )

    open_recs = [r for r in info.receptacles if not info.openable.get(r, False) and not banned(r)]
    closable = [r for r in info.receptacles if info.openable.get(r, False) and not banned(r)]
    lists: list[list[str]] = []
    if k == 1:
        for dest in destination_order(open_recs, info.task_id, k):
            acts: list[str] = []
            for obj, src in info.targets:
                acts += [f"go to {src}"]
                acts += [f"open {src}"] if info.openable.get(src) else []
                acts += [f"take {obj} from {src}", f"go to {dest}", f"move {obj} to {dest}"]
            lists.append([*acts, "look"])
        return lists
    for dest in destination_order(closable, info.task_id, k):
        acts = []
        for obj, src in info.targets:
            acts += [f"go to {src}"]
            acts += [f"open {src}"] if info.openable.get(src) else []
            acts += [
                f"take {obj} from {src}",
                f"go to {dest}",
                f"open {dest}",
                f"move {obj} to {dest}",
                f"close {dest}",
            ]
        if k == 3:
            for other in closable:
                if other != dest:
                    acts += [f"go to {other}", f"open {other}", f"close {other}"]
        lists.append([*acts, "look"])
    return lists


def validate(open_fn: OpenFn, actions: list[str]) -> tuple[bool, str]:
    """Every step admissible before issue and effective; open/close already in state skipped."""
    sess = open_fn(None)
    try:
        for i, a in enumerate(actions):
            if a not in sess.admissible():
                if a.startswith(("open ", "close ")):
                    continue
                return False, f"step {i} not admissible: {a}"
            r = sess.step_text(a)
            if not r["effective"] and a != "look":
                return False, f"step {i} ineffective: {a}"
        return True, "ok"
    finally:
        sess.close()


def compact(open_fn: OpenFn, actions: list[str]) -> list[str]:
    """Drop open/close steps that were not admissible (already in state) so replay is clean."""
    sess = open_fn(None)
    kept: list[str] = []
    try:
        for a in actions:
            if a in sess.admissible() or a == "look":
                sess.step_text(a)
                kept.append(a)
            elif not a.startswith(("open ", "close ")):
                kept.append(a)
    finally:
        sess.close()
    return kept


def to_candidate(actions: list[str]) -> Candidate:
    return Candidate(
        in_env_actions=[Action(name="do", kwargs={"text": a}) for a in actions],
        rationale="displacement",
    )


def build(open_fn: OpenFn, info: TaskInfo, k: int) -> tuple[list[str] | None, str]:
    """The first synthesised list that validates and does not already solve/end the task."""
    for acts in synthesize(info, k):
        ok, _why = validate(open_fn, acts)
        if not ok:
            continue
        final = compact(open_fn, acts)
        sess = open_fn(to_candidate(final))
        try:
            if sess.won or sess.done:
                continue  # a state that already solves (or ends) the task is not a displacement
        finally:
            sess.close()
        return final, "ok"
    return None, "infeasible: no destination validated"


def setup_builder(open_fn: OpenFn) -> Callable[[float], list[str] | None]:
    """The ``KnobContext.setup_builder`` for a task: discovers once, builds per dose (k from d)."""
    cache: dict[str, TaskInfo | None] = {}
    memo: dict[int, list[str] | None] = {}

    def make(d: float) -> list[str] | None:
        k = displacement_k(d)
        if k in memo:
            return memo[k]
        if "info" not in cache:
            cache["info"] = discover(open_fn)
        info = cache["info"]
        if info is None:
            memo[k] = None
            return None
        actions, _ = build(open_fn, info, k)
        memo[k] = actions
        return actions

    return make
