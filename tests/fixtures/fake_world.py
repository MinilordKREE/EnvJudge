"""An offline ActionableEnv standing in for the ALFWorld bridge (no TextWorld, no LLM).

The world is a required action sequence; any other admissible action is a no-op ("Nothing
happens", ``effective=False``). It exposes the same surface aea touches on the real bridge:
``state`` (done, won, step_count, admissible_commands, obs_text, goal_text), ``_env`` with
``last_infos["extra.expert_plan"]`` (the remaining required actions, as the ALFWorld expert
wrapper publishes it), ``notify_replay_complete``, ``evaluate``, and the wrapped observation text
with the ``Admissible commands:`` footer (``bridge.py:717-745``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from envharness.core.actionable_env import ActionableEnv
from envharness.core.code_loader import load_rules_instance
from envharness.core.types import (
    Action,
    Candidate,
    EnvResetResponse,
    EnvResponse,
    EvaluationResult,
    Observation,
)
from envharness.harnesses.setup import Setup

from aea.certs import RecordingProxy, Session

ENGINE_CAP = 50


@dataclass
class FakeState:
    goal_text: str = "put x in b"
    obs_text: str = "You are in a room."
    admissible_commands: list[str] = field(default_factory=list)
    done: bool = False
    won: bool = False
    step_count: int = 0
    last_action_was_effective: bool = True
    engine_steps: int = 0
    progress: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


class FakeEngine:
    """Stands in for the TextWorld batch env beneath the bridge (reset/step tuples)."""

    def __init__(self, bridge: FakeBridge) -> None:
        self.bridge = bridge

    def reset(self) -> tuple[list[str], dict[str, list[Any]]]:
        return [self.bridge.state.obs_text], self.bridge._infos()

    def step(
        self, commands: list[str]
    ) -> tuple[list[str], list[float], list[bool], dict[str, list[Any]]]:
        return [self.bridge.state.obs_text], [0.0], [self.bridge.state.done], self.bridge._infos()


class FakeBridge(ActionableEnv):  # type: ignore[misc]  # envharness ships no type information
    """Required sequence ``plan``; ``cap`` = engine step cap (counts replayed prefixes, like
    TextWorld)."""

    def __init__(
        self,
        plan: list[str] | None = None,
        cap: int = ENGINE_CAP,
        gamefile: str = "fake/game.tw-pddl",
    ) -> None:
        self.plan = list(plan or ["go to a", "take x from a", "go to b", "move x to b"])
        self.cap = cap
        self.gamefile = gamefile
        self.state = FakeState()
        self._env: Any = FakeEngine(self)
        self.reset_calls = 0

    @classmethod
    def env_type(cls) -> str:
        return "fake"

    def _infos(self) -> dict[str, list[Any]]:
        return {
            "extra.expert_plan": [list(self.plan[self.state.progress :]) or ["look"]],
            "extra.gamefile": [self.gamefile],
            "won": [self.state.won],
        }

    def _admissible(self) -> list[str]:
        nxt = [self.plan[self.state.progress]] if self.state.progress < len(self.plan) else []
        return sorted({*nxt, "look", "inventory", "go to c", "examine a"})

    def reset(
        self, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> EnvResetResponse:
        self.reset_calls += 1
        opts = options or {}
        self.cap = int(opts.get("_fake_cap", self.cap))
        self.state = FakeState(admissible_commands=self._admissible())
        self._env.reset()
        return EnvResetResponse(
            observation=self.observe(), info={"extra.gamefile": self.gamefile, "won": False}
        )

    def step(self, action: Action) -> EnvResponse:
        text = str(action.kwargs.get("text", "")).strip()
        self.state.step_count += 1
        self.state.engine_steps += 1
        effective = True
        if self.state.progress < len(self.plan) and text == self.plan[self.state.progress]:
            self.state.progress += 1
            self.state.obs_text = f"You {text}."
            if self.state.progress == len(self.plan):
                self.state.won = True
        elif text in ("look", "inventory", "examine a", "go to c"):
            self.state.obs_text = f"You {text}. Nothing new."
        else:
            self.state.obs_text = "Nothing happens."
            effective = False
        self.state.last_action_was_effective = effective
        engine_done = self.state.won or self.state.engine_steps >= self.cap
        self.state.done = engine_done
        self.state.admissible_commands = self._admissible()
        self._env.step([text])
        return EnvResponse(
            observation=self.observe(),
            reward=1.0 if self.state.won else 0.0,
            terminated=engine_done,
            truncated=False,
            info={
                "success": self.state.won if engine_done else None,
                "effective": effective,
                "won": self.state.won,
                "admissible_commands": list(self.state.admissible_commands),
                "result": {"won": self.state.won},
            },
        )

    def observe(self) -> Observation:
        text = (
            f"Task: {self.state.goal_text}\n\n{self.state.obs_text}\n\nAdmissible commands: "
            + ", ".join(self.state.admissible_commands)
        )
        return Observation(
            text=text,
            data={
                "goal_text": self.state.goal_text,
                "admissible_commands": list(self.state.admissible_commands),
            },
        )

    def evaluate(self) -> EvaluationResult:
        return EvaluationResult(success=self.state.won, score=1.0 if self.state.won else 0.0)

    def get_env_state(self) -> FakeState:
        return self.state

    def notify_replay_complete(self) -> None:
        self.state.step_count = 0

    def save_state(self) -> dict[str, Any]:
        return {"plan": self.plan, "cap": self.cap}

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> FakeBridge:
        return cls(plan=list(state.get("plan") or []), cap=int(state.get("cap", ENGINE_CAP)))

    def close(self) -> None:
        pass


def make_open(plan: list[str] | None = None, cap: int = ENGINE_CAP):  # type: ignore[no-untyped-def]
    """A ``SessionFactory`` over a fresh FakeBridge per session, stacked exactly like the runner."""

    def open_fn(
        candidate: Candidate | None, reset_options: dict[str, Any] | None = None
    ) -> Session:
        bridge = FakeBridge(plan=plan, cap=cap)
        proxy = RecordingProxy(bridge._env)
        bridge._env = proxy
        cand = candidate or Candidate()
        stack: Any = bridge
        if cand.in_env_actions:
            stack = Setup(inner=stack, actions=list(cand.in_env_actions))
        if (cand.rules_code or "").strip():
            stack = load_rules_instance(cand.rules_code, inner=stack)
        stack.reset(seed=0, options=dict(reset_options or {}))
        return Session(stack=stack, bridge=bridge, proxy=proxy, seed=0, gamefile=bridge.gamefile)

    return open_fn
