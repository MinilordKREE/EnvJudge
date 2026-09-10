"""Offline Substrate for controller tests: scripted policies over the fake world (no LLM)."""

from __future__ import annotations

import random
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea.controller import TaskRef
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.session import Session
from tests.fixtures.fake_world import make_open

PLAN = ["go to a", "take x from a", "go to b", "move x to b"]

type PolicyKind = str
"""'expert' follows the plan; 'coin' succeeds with probability p; 'random' never picks a plan
action; 'footer' follows the plan only while the admissible footer is visible."""


class FakeSubstrate:
    def __init__(
        self,
        policies: dict[str, PolicyKind],
        *,
        p: float = 0.5,
        seed: int = 1,
        with_designer: bool = False,
        designer_fn: Callable[[ChatRequest], ChatResponse] | None = None,
        rollout_delay_s: float = 0.0,
        session_delay_s: float = 0.0,
    ) -> None:
        self.policies = policies
        self.p = p
        self.seed = seed
        # one generator per task, so a task's episodes do not depend on which other tasks ran
        # before or alongside it (the task pool must reproduce the sequential run)
        self._rngs: dict[str, random.Random] = {}
        self.calls: list[tuple[str, str, int]] = []
        self._open: Callable[..., Session] = make_open(PLAN)
        self._designer = designer_fn if with_designer else None
        # concurrency probes (docs/changelog_v0.2.md, task pool): guard / staging sessions opened
        # through ``open_session`` and rollout batches in flight, with their maxima
        self.rollout_delay_s = rollout_delay_s
        self.session_delay_s = session_delay_s
        self._probe_lock = threading.Lock()
        self.active_sessions = 0
        self.max_active_sessions = 0
        self.active_rollouts = 0
        self.max_active_rollouts = 0
        self.rollouts_during_session = 0

    def rng(self, task: TaskRef) -> random.Random:
        with self._probe_lock:
            if task.task_id not in self._rngs:
                self._rngs[task.task_id] = random.Random(f"{self.seed}:{task.task_id}")
            return self._rngs[task.task_id]

    # -- world -----------------------------------------------------------------
    def open_session(
        self, task: TaskRef, candidate: Candidate | None, reset_options: dict[str, Any] | None
    ) -> Session:
        with self._probe_lock:
            self.active_sessions += 1
            self.max_active_sessions = max(self.max_active_sessions, self.active_sessions)
        if self.session_delay_s:
            time.sleep(self.session_delay_s)
        sess = self._open(candidate, reset_options)

        def release() -> None:
            with self._probe_lock:
                self.active_sessions -= 1

        sess.close_fn = release
        return sess

    def game_file(self, task: TaskRef) -> str:
        return f"json_2.1.1/train/fake-{task.task_id}/game.tw-pddl"

    def stage_reset_options(self, task: TaskRef) -> dict[str, Any]:
        return {"config_path": "cfg100.yaml"}

    def designer(self) -> Callable[[ChatRequest], ChatResponse] | None:
        return self._designer

    def designer_model(self) -> str:
        return "fake-designer"

    def has_oracle(self) -> bool:
        return True  # the fake world exposes an expert plan

    # -- policy -----------------------------------------------------------------
    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        kind = self.policies[task.task_id]
        with self._probe_lock:
            self.calls.append((task.task_id, attribution.phase, n))
            self.active_rollouts += 1
            self.max_active_rollouts = max(self.max_active_rollouts, self.active_rollouts)
            self.rollouts_during_session += int(self.active_sessions > 0)
        try:
            if self.rollout_delay_s:
                time.sleep(self.rollout_delay_s)
            return [self._episode(task, candidate, kind, reset_options) for _ in range(n)]
        finally:
            with self._probe_lock:
                self.active_rollouts -= 1

    def _episode(
        self,
        task: TaskRef,
        candidate: Candidate,
        kind: PolicyKind,
        reset_options: dict[str, Any] | None,
    ) -> Trace:
        sess = self._open(candidate, reset_options)
        rng = self.rng(task)
        steps: list[Step] = []
        plan = list(PLAN)
        for _ in range(50):
            if sess.done or sess.won:
                break
            adm = sess.admissible()
            obs_now = sess.stack.observe()
            footer_visible = "Admissible commands" in obs_now.text
            if kind == "expert" or (kind == "footer" and footer_visible):
                nxt = next((a for a in plan if a in adm), None)
                if nxt is None:
                    nxt = "look"
                else:
                    plan.remove(nxt)
                if kind == "footer" and not footer_visible:
                    nxt = "look"
            elif kind == "coin":
                nxt = (
                    next((a for a in plan if a in adm), "look")
                    if rng.random() < self.p**0.25
                    else "look"
                )
                if nxt in plan:
                    plan.remove(nxt)
            elif kind == "footer":
                nxt = "look"
            else:  # 'random': a zero policy that never picks a plan action
                nxt = rng.choice([a for a in adm if a not in PLAN] or ["look"])
            r = sess.step_text(nxt)
            act = Action(name="do", kwargs={"text": nxt})
            obs = Observation(text=str(r["obs"]))
            steps.append(
                Step(
                    raw_action=act,
                    filtered_action=act,
                    raw_observation=obs,
                    filtered_observation=obs,
                    terminated=bool(r["terminated"]),
                    truncated=bool(r["truncated"]),
                    info={"effective": r["effective"]},
                )
            )
        success = sess.won
        sess.close()
        return Trace(
            episode_id=uuid.uuid4().hex[:10],
            iteration_id=attribution_phase(task),
            task_id=task.label,
            candidate=candidate,
            rollout_seed=task.seed,
            steps=steps,
            success=success,
            duration_steps=len(steps),
            kind="exploration",
            policy_model_id=f"fake:{kind}",
        )


def attribution_phase(task: TaskRef) -> str:
    return f"fake-{task.task_id}"
