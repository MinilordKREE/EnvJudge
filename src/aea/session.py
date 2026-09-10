"""Sessions on a candidate environment: reset-and-drive, replay of an action list, and the
benchmark oracle (docs/spec/AEA_v0.2.md, "One guard": the sources ``solvable()`` replays are run
through these sessions; sessions are never policy rollouts and are never charged).

A :class:`Session` drives the SAME harness stack the released runner builds
(``runner.py:129-142``: base -> Setup -> Rules) over a per-process bridge that is reused per
``config_path`` (the ALFWorld config, including the step cap, is read once per bridge instance —
``bridge.py:177-178``). ``Session.done`` reads the stack-level ``terminated`` / ``truncated`` so a
T-axis termination is not missed. The handcoded expert's next action is read from
``infos["extra.expert_plan"]`` beneath the bridge through an observe-only proxy on its ``_env``
(``RecordingProxy``; permitted by the do-not list, documented in docs/reuse/certs.md).

Ported behaviour (oracle): docs/pilots/eobs/eobs/replay.py (``Session``, ``replay_actions``,
``run_expert``, ``_base_bridge``). No runtime import from the pilots.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from envharness.core.types import Action, Candidate

TASK_LABEL = "alfworld-corpus-ours-release"
DEFAULT_RESET_OPTIONS: dict[str, Any] = {"split": "train", "repetition_threshold": 0}
EXPERT_STUCK_N = 4


class RecordingProxy:
    """Observe-only proxy around the bridge's underlying TextWorld env: records the last infos."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "last_infos", None)

    def step(self, *args: Any, **kwargs: Any) -> Any:
        out = self._target.step(*args, **kwargs)
        object.__setattr__(self, "last_infos", out[3] if len(out) > 3 else None)
        return out

    def reset(self, *args: Any, **kwargs: Any) -> Any:
        out = self._target.reset(*args, **kwargs)
        infos = out[1] if isinstance(out, tuple) and len(out) > 1 else None
        object.__setattr__(self, "last_infos", infos)
        return out

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_target"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_target"), name, value)


def _unwrap(info: Any) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in info.items()}


class StackLike(Protocol):
    """What a Session needs from the harness stack (real envharness stack or a test fake)."""

    def step(self, action: Action) -> Any: ...
    def evaluate(self) -> Any: ...
    def observe(self) -> Any: ...


@dataclass
class Session:
    """One reset-and-drive session on a candidate env stack."""

    stack: StackLike
    bridge: Any
    proxy: RecordingProxy | None
    seed: int
    gamefile: str = ""
    actions: list[str] = field(default_factory=list)
    blocked: int = 0
    ended: bool = False
    close_fn: Callable[[], None] | None = None

    @property
    def won(self) -> bool:
        return bool(self.stack.evaluate().success)

    @property
    def done(self) -> bool:
        return bool(getattr(self.bridge.state, "done", False)) or self.ended

    def admissible(self) -> list[str]:
        return list(self.bridge.state.admissible_commands)

    def expert_next(self) -> str | None:
        if self.proxy is None:
            return None
        plan = _unwrap(self.proxy.last_infos).get("extra.expert_plan")
        return str(plan[0]) if isinstance(plan, list) and plan else None

    def step_text(self, text: str) -> dict[str, Any]:
        resp = self.stack.step(Action(name="do", kwargs={"text": text}))
        blocked = bool((resp.observation.data or {}).get("blocked"))
        self.blocked += int(blocked)
        if resp.terminated or resp.truncated:
            self.ended = True
        self.actions.append(text)
        return {
            "blocked": blocked,
            "obs": resp.observation.text,
            "terminated": resp.terminated,
            "truncated": resp.truncated,
            "won": bool(getattr(self.bridge.state, "won", False)),
            "effective": bool((resp.info or {}).get("effective", True)),
        }

    def close(self) -> None:
        if self.close_fn is not None:
            self.close_fn()


_BRIDGES: dict[str, tuple[Any, RecordingProxy]] = {}


def _base_bridge(reset_options: dict[str, Any], seed: int) -> tuple[Any, RecordingProxy]:
    """One reused AlfworldEnv per process and per ``config_path`` (game scan paid once)."""
    from envharness.bridges.alfworld import AlfworldEnv

    key = str(reset_options.get("config_path") or "")
    if key not in _BRIDGES:
        os.environ.setdefault("ALFWORLD_DATA", str(Path.home() / "eh_alfworld_data"))
        bridge = AlfworldEnv()
        bridge.reset(seed=seed, options={**reset_options, "task_id": TASK_LABEL})
        proxy = RecordingProxy(bridge._env)
        bridge._env = proxy
        _BRIDGES[key] = (bridge, proxy)
    return _BRIDGES[key]


def open_session(
    candidate: Candidate | None, seed: int, reset_options: dict[str, Any] | None = None
) -> Session:
    """Build the stack exactly as ``build_env_stack`` does, over the reused bridge, and reset it."""
    from envharness.core.code_loader import load_rules_instance
    from envharness.harnesses.setup import Setup

    cand = candidate or Candidate()
    opts = dict(reset_options or DEFAULT_RESET_OPTIONS)
    bridge, proxy = _base_bridge(opts, seed)
    stack: Any = bridge
    if cand.in_env_actions:
        stack = Setup(inner=stack, actions=list(cand.in_env_actions))
    if (cand.rules_code or "").strip():
        stack = load_rules_instance(cand.rules_code, inner=stack)
    stack.reset(seed=seed, options={**opts, "task_id": TASK_LABEL})
    gamefile = str(_unwrap(proxy.last_infos).get("extra.gamefile") or "")

    def detach() -> None:  # drop harness layers from the reused bridge without closing it
        cur = stack
        while cur is not bridge and hasattr(cur, "_inner"):
            nxt = cur._inner
            cur._inner = None
            cur = nxt

    return Session(
        stack=stack, bridge=bridge, proxy=proxy, seed=seed, gamefile=gamefile, close_fn=detach
    )


@dataclass
class ReplayResult:
    ok: bool
    reason: str = ""
    step: int | None = None
    n_steps: int = 0
    actions: list[str] = field(default_factory=list)


def replay_actions(sess: Session, actions: list[str]) -> ReplayResult:
    """Execute a fixed action list verbatim; stop early on win or episode end."""
    for i, a in enumerate(actions):
        if sess.done:
            break
        try:
            r = sess.step_text(a)
        except Exception:
            return ReplayResult(False, "env_error", i, i, list(actions[: i + 1]))
        if r["won"]:
            break
    ok = sess.won
    reason = "pass" if ok else ("blocked" if sess.blocked else "verifier_fail")
    return ReplayResult(
        ok, reason, None if ok else len(sess.actions), len(sess.actions), list(sess.actions)
    )


def run_expert(sess: Session, max_steps: int, retry_blocked: int = 3) -> ReplayResult:
    """Closed-loop handcoded expert from the session's current state until won / done / cap."""
    start = len(sess.actions)
    consecutive_blocked = 0
    last_pair: tuple[str, str] | None = None
    same = 0
    for i in range(max_steps):
        if sess.won or sess.done:
            break
        nxt = sess.expert_next()
        if not nxt:
            return ReplayResult(
                False, "expert_error", start + i, len(sess.actions) - start, sess.actions[start:]
            )
        try:
            r = sess.step_text(nxt)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            reason = "expert_timeout" if ("Timeout" in msg or "HandCoded" in msg) else "env_error"
            return ReplayResult(
                False, reason, start + i, len(sess.actions) - start, sess.actions[start:]
            )
        pair = (nxt, str(r["obs"]))
        same = same + 1 if pair == last_pair else 1
        last_pair = pair
        if same >= EXPERT_STUCK_N and not r["won"]:
            return ReplayResult(
                False, "expert_stuck", start + i, len(sess.actions) - start, sess.actions[start:]
            )
        consecutive_blocked = consecutive_blocked + 1 if r["blocked"] else 0
        if consecutive_blocked >= retry_blocked:
            return ReplayResult(
                False, "blocked", start + i, len(sess.actions) - start, sess.actions[start:]
            )
    ok = sess.won
    return ReplayResult(
        ok,
        "pass" if ok else "verifier_fail",
        None if ok else len(sess.actions),
        len(sess.actions) - start,
        sess.actions[start:],
    )
