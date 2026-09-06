"""F_S0 — initial-state displacement, dose k ∈ {1, 2, 3} (LLM-free).

Target discovery: run the closed-loop expert in a scratch session until it executes `take <obj> from <recep>`
(pick_two: until two distinct objects are taken); record (obj, source_recep).
Synthesis (destination order seeded 20260910):
  k=1  move each target to a different OPEN receptacle (a `go to X` receptacle that is not openable), source excluded;
  k=2  put each target inside a closable container: go to C, open C, move obj to C, close C;
  k=3  k=2 plus `close` every other openable receptacle in the room.
Every list ends with `look`. Validation: execute the list on a fresh session; every step must be admissible before it is
issued and effective (no "Nothing happens"); on failure try the next destination; none → dose infeasible.

Receptacle classes are taken from the game's `go to` list; "openable" is decided empirically: after `go to X`, an
`open X` command in the admissible list means X is a closable container.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from envharness.core.types import Action, Candidate

from eobs.replay import open_session, run_expert

SEED = 20260910
TAKE_RE = re.compile(r"^take (.+?) from (.+)$")
MOVE_RE = re.compile(r"^move (.+?) to (.+)$")


def _cls(recep: str) -> str:
    return re.sub(r"\s*\d+$", "", recep)


GOAL_RE = re.compile(r"\b(?:in|on|under|with)\s+(?:the\s+|a\s+|an\s+)?([a-z]+)\s*\.?\s*$")


def _goal_class_from_text(goal_text: str) -> str | None:
    """'Your task is to: put two lettuce in fridge.' -> 'fridge'; used when the expert did not win (no final move seen)."""
    m = GOAL_RE.search((goal_text or "").lower())
    return m.group(1) if m else None


@dataclass
class TaskInfo:
    task_id: int
    targets: list[tuple[str, str]]              # (obj, source_recep)
    receptacles: list[str]                      # from the admissible `go to` list at reset
    openable: dict[str, bool] = field(default_factory=dict)
    expert_actions: list[str] = field(default_factory=list)
    goal_recep_class: str | None = None         # class of the receptacle in the expert's final `move` (never a destination)


def discover(task_id: int, n_targets: int, attempts: int = 3) -> TaskInfo | None:
    """Find the target objects by watching the expert; probe openability of every receptacle."""
    for _ in range(attempts):
        s = open_session(None, task_id)
        try:
            recs = [c[len("go to "):] for c in s.admissible() if c.startswith("go to ")]
            taken: list[tuple[str, str]] = []
            start = len(s.actions)
            res = run_expert(s, max_steps=50)
            for a in s.actions[start:]:
                m = TAKE_RE.match(a)
                if m and (m.group(1), m.group(2)) not in taken:
                    taken.append((m.group(1), m.group(2)))
                if len(taken) >= n_targets:
                    break
            if len(taken) >= n_targets:
                moves = [MOVE_RE.match(a) for a in s.actions[start:]]
                moves = [m for m in moves if m]
                goal_cls = _cls(moves[-1].group(2)) if (res.ok and moves) else _goal_class_from_text(s.bridge.state.goal_text)
                info = TaskInfo(task_id=task_id, targets=taken[:n_targets], receptacles=recs, expert_actions=list(s.actions[start:]), goal_recep_class=goal_cls)
                break
        finally:
            s.close()
    else:
        return None
    # openability probe: one session, visit each receptacle
    s = open_session(None, task_id)
    try:
        for r in info.receptacles:
            s.step_text(f"go to {r}")
            info.openable[r] = any(c == f"open {r}" or c == f"close {r}" for c in s.admissible())
    finally:
        s.close()
    return info


def _dest_order(cands: list[str], task_id: int, k: int) -> list[str]:
    rnd = random.Random(SEED + 1000 * k + task_id)
    c = list(cands)
    rnd.shuffle(c)
    return c


def synthesize(info: TaskInfo, k: int) -> list[list[str]]:
    """Return candidate action lists in deterministic order (first that validates is used)."""
    sources = {src for _, src in info.targets}
    banned = lambda r: r in sources or (info.goal_recep_class is not None and _cls(r) == info.goal_recep_class)   # never the goal receptacle class
    open_recs = [r for r in info.receptacles if not info.openable.get(r, False) and not banned(r)]
    closable = [r for r in info.receptacles if info.openable.get(r, False) and not banned(r)]
    lists: list[list[str]] = []
    if k == 1:
        for dest in _dest_order(open_recs, info.task_id, k):
            acts = []
            for obj, src in info.targets:
                acts += [f"go to {src}"] + ([f"open {src}"] if info.openable.get(src) else []) + [f"take {obj} from {src}", f"go to {dest}", f"move {obj} to {dest}"]
            lists.append(acts + ["look"])
    else:
        for dest in _dest_order(closable, info.task_id, k):
            acts = []
            for obj, src in info.targets:
                acts += [f"go to {src}"] + ([f"open {src}"] if info.openable.get(src) else []) + [f"take {obj} from {src}", f"go to {dest}", f"open {dest}", f"move {obj} to {dest}", f"close {dest}"]
            if k == 3:
                for other in closable:
                    if other != dest:
                        acts += [f"go to {other}", f"open {other}", f"close {other}"]   # ensure closed (open then close is a no-op if already closed? see validate)
            lists.append(acts + ["look"])
    return lists


def validate(task_id: int, actions: list[str]) -> tuple[bool, str]:
    """Every step admissible before issue and effective; k=3 close-only steps tolerate 'already closed'."""
    s = open_session(None, task_id)
    try:
        for i, a in enumerate(actions):
            adm = s.admissible()
            if a not in adm:
                if a.startswith("open ") or a.startswith("close "):
                    continue          # already in the wanted state: skip (the list is re-emitted without it below)
                return False, f"step {i} not admissible: {a}"
            r = s.step_text(a)
            if not r["effective"] and a != "look":
                return False, f"step {i} ineffective: {a}"
        return True, "ok"
    finally:
        s.close()


def compact(task_id: int, actions: list[str]) -> list[str]:
    """Drop open/close steps that were not admissible (already in state) so the stored list replays cleanly."""
    s = open_session(None, task_id)
    kept = []
    try:
        for a in actions:
            if a in s.admissible() or a == "look":
                s.step_text(a)
                kept.append(a)
            elif not (a.startswith("open ") or a.startswith("close ")):
                kept.append(a)
    finally:
        s.close()
    return kept


def build(info: TaskInfo, k: int) -> tuple[list[str] | None, str]:
    for acts in synthesize(info, k):
        ok, why = validate(info.task_id, acts)
        if ok:
            final = compact(info.task_id, acts)
            s = open_session(to_candidate(final), info.task_id)
            try:
                if s.won or s.done:
                    continue            # the staged state already solves (or ends) the task: not a valid displacement
            finally:
                s.close()
            return final, "ok"
    return None, "infeasible: no destination validated"


def to_candidate(actions: list[str]) -> Candidate:
    return Candidate(rules_code="", in_env_actions=[Action(name="do", kwargs={"text": a}) for a in actions], rationale="F_S0 structural displacement")
