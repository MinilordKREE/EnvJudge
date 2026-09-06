"""Replay and expert probes on ALFWorld through the released envharness stack (observe-only).

Mechanics
- The env stack for a candidate is built EXACTLY as the released runner does
  (`envharness.orchestration.runner.build_env_stack`): base AlfworldEnv -> Setup (S0) -> Rules (A/T/O).
- Task selection mirrors run_episode: `stack.reset(seed=task_id, options={**reset_options, "task_id": <label>})`
  (the label matches no gamefile, so the bridge falls back to seed-based selection: seed(n) shuffles
  and plays the head; deterministic).
- Expert: ALFWorld's handcoded expert (config `expert_type: handcoded`) publishes its NEXT action as
  `infos["extra.expert_plan"]` on every underlying step. The bridge drops that key, so `RecordingProxy`
  wraps the bridge's private `_env` (the TextworldBatchGymEnv) and records the last infos; it delegates
  every attribute/call unchanged. Nothing under third_party is modified.
- "Expert plan from state s" therefore means: the stateful handcoded expert's closed-loop continuation
  after having observed the prefix that produced s (recover_mode = "handcoded_closed_loop").
- Verifier = `stack.evaluate().success` (the released verifier; == underlying `won`).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from envharness.core.types import Action, Candidate
from envharness.orchestration.runner import EnvSpec, EpisodeSpec, PolicySpec, build_env_stack, _base_env

from eobs.certs import ReplayResult

RESET_OPTIONS = {"split": "train", "repetition_threshold": 0}
TASK_LABEL = "alfworld-corpus-ours-release"        # OrchestratorConfig.task_id in corpus.yaml (not a gamefile)
EXPERT_MAX_STEPS = 150                              # alfworld base_config expert_timeout_steps
POLICY_MAX_STEPS = 50                               # orchestrator.max_episode_steps in corpus.yaml
RECOVER_MODE = "handcoded_closed_loop"


class RecordingProxy:
    """Observe-only proxy around the bridge's underlying TextworldBatchGymEnv: records the last infos."""

    def __init__(self, target):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "last_infos", None)
        object.__setattr__(self, "n_steps", 0)

    def step(self, *a, **kw):
        out = self._target.step(*a, **kw)
        object.__setattr__(self, "last_infos", out[3] if len(out) > 3 else None)
        object.__setattr__(self, "n_steps", self.n_steps + 1)
        return out

    def reset(self, *a, **kw):
        out = self._target.reset(*a, **kw)
        object.__setattr__(self, "last_infos", out[1] if isinstance(out, tuple) and len(out) > 1 else None)
        object.__setattr__(self, "n_steps", 0)
        return out

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_target"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_target"), name, value)

    def __delattr__(self, name):
        delattr(object.__getattribute__(self, "_target"), name)


def _unwrap(info: Any) -> dict:
    if not isinstance(info, dict):
        return {}
    return {k: (v[0] if isinstance(v, list) and len(v) > 0 else v) for k, v in info.items()}


def task_type_from_gamefile(gamefile: str) -> str:
    parts = str(gamefile or "").split(os.sep)
    t = next((p for p in parts if p.startswith("pick_") or p.startswith("look_")), "?")
    return t.split("-")[0]


@dataclass
class Session:
    """One reset-and-drive session on a candidate env stack."""
    stack: Any
    bridge: Any
    proxy: RecordingProxy
    seed: int
    gamefile: str = ""
    actions: list[str] = field(default_factory=list)
    blocked: int = 0
    errors: list[str] = field(default_factory=list)
    ended: bool = False          # set when the STACK reports terminated/truncated (e.g. a T-axis horizon squeeze); bridge.done alone misses it

    @property
    def won(self) -> bool:
        return bool(self.stack.evaluate().success)

    @property
    def done(self) -> bool:
        return bool(self.bridge.state.done) or self.ended

    def expert_next(self) -> str | None:
        info = _unwrap(self.proxy.last_infos)
        plan = info.get("extra.expert_plan")
        if isinstance(plan, list) and plan:
            return str(plan[0])
        return None

    def admissible(self) -> list[str]:
        return list(self.bridge.state.admissible_commands)

    def step_text(self, text: str) -> dict:
        resp = self.stack.step(Action(name="do", kwargs={"text": text}))
        blocked = bool((resp.observation.data or {}).get("blocked"))
        if blocked:
            self.blocked += 1
        if resp.terminated or resp.truncated:
            self.ended = True
        self.actions.append(text)
        return {"blocked": blocked, "obs": resp.observation.text, "terminated": resp.terminated, "truncated": resp.truncated,
                "won": bool(self.bridge.state.won), "effective": bool(resp.info.get("effective", True))}

    def close(self):
        """Detach harness layers from the reused bridge without closing the bridge itself."""
        cur = self.stack
        while cur is not self.bridge and hasattr(cur, "_inner"):
            nxt = cur._inner
            cur._inner = None
            cur = nxt


_CACHED: dict[str, Any] = {}   # per-process reusable base bridge (+proxy); the 8,810-file game scan is paid once


def _base_bridge(reset_options: dict, seed: int):
    """Return (bridge, proxy). Reuses one AlfworldEnv per process: `reset(seed, options)` on a live bridge
    re-selects the game deterministically (same `_safe_seed` path as a fresh instance) without re-scanning
    the game files; equivalence with fresh instances is checked in tests/test_integration.py."""
    from envharness.bridges.alfworld import AlfworldEnv
    if "bridge" not in _CACHED:
        b = AlfworldEnv()
        b.reset(seed=seed, options={**reset_options, "task_id": TASK_LABEL})
        proxy = RecordingProxy(b._env)
        b._env = proxy
        _CACHED["bridge"], _CACHED["proxy"] = b, proxy
    return _CACHED["bridge"], _CACHED["proxy"]


def open_session(candidate: Candidate | None, seed: int, reset_options: dict | None = None) -> Session:
    """Build the stack exactly as runner.build_env_stack does (base -> Setup -> Rules), over a reused base bridge."""
    from envharness.core.code_loader import load_rules_instance
    from envharness.harnesses.setup import Setup
    cand = candidate or Candidate(rules_code="", in_env_actions=[])
    opts = dict(reset_options or RESET_OPTIONS)
    bridge, proxy = _base_bridge(opts, seed)
    stack: Any = bridge
    if cand.in_env_actions:
        stack = Setup(inner=stack, actions=list(cand.in_env_actions))
    if (cand.rules_code or "").strip():
        stack = load_rules_instance(cand.rules_code, inner=stack)
    stack.reset(seed=seed, options={**opts, "task_id": TASK_LABEL})
    gf = _unwrap(proxy.last_infos).get("extra.gamefile") or ""
    return Session(stack=stack, bridge=bridge, proxy=proxy, seed=seed, gamefile=str(gf))


def replay_actions(sess: Session, actions: list[str]) -> ReplayResult:
    """Execute a fixed action list verbatim; stop early on episode end."""
    for i, a in enumerate(actions):
        if sess.done:
            break
        try:
            r = sess.step_text(a)
        except Exception as e:  # noqa: BLE001
            sess.errors.append(f"{type(e).__name__}: {e}"[:200])
            return ReplayResult(ok=False, reason="env_error", step=i, n_steps=i, actions=list(actions[: i + 1]))
        if r["won"]:
            break
    ok = sess.won
    return ReplayResult(ok=ok, reason="pass" if ok else ("blocked" if sess.blocked else "verifier_fail"),
                        step=None if ok else len(sess.actions), n_steps=len(sess.actions), actions=list(sess.actions))


EXPERT_STUCK_N = 4   # same expert action N times in a row with no observation change -> expert_stuck


def run_expert(sess: Session, max_steps: int = EXPERT_MAX_STEPS, retry_blocked: int = 3) -> ReplayResult:
    """Closed-loop handcoded expert from the session's CURRENT state until won / done / cap.

    Expert-failure classes (owner review 2026-09-05), reported separately from verifier_fail:
      expert_stuck    the expert repeats one action EXPERT_STUCK_N times with an unchanged observation (ALFWorld's
                      AlfredExpert falls back to ["look"] when its action is inadmissible, which would otherwise burn
                      the step cap and look like an unrecoverable state);
      expert_timeout  the handcoded expert raised (HandCodedAgentTimeout/Failed surface as Exception("Timeout") etc.);
      expert_error    no plan published.
    """
    start = len(sess.actions)
    consecutive_blocked = 0
    last_pair: tuple[str, str] | None = None
    same_count = 0
    for i in range(max_steps):
        if sess.won:
            break
        if sess.done:
            break
        nxt = sess.expert_next()
        if not nxt:
            return ReplayResult(ok=False, reason="expert_error", step=start + i, n_steps=len(sess.actions) - start,
                                actions=list(sess.actions[start:]))
        try:
            r = sess.step_text(nxt)
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"[:200]
            sess.errors.append(msg)
            reason = "expert_timeout" if ("Timeout" in msg or "HandCoded" in msg) else "env_error"
            return ReplayResult(ok=False, reason=reason, step=start + i, n_steps=len(sess.actions) - start,
                                actions=list(sess.actions[start:]))
        pair = (nxt, r["obs"])
        same_count = same_count + 1 if pair == last_pair else 1
        last_pair = pair
        if same_count >= EXPERT_STUCK_N and not r["won"]:
            return ReplayResult(ok=False, reason="expert_stuck", step=start + i, n_steps=len(sess.actions) - start,
                                actions=list(sess.actions[start:]))
        if r["blocked"]:
            consecutive_blocked += 1
            if consecutive_blocked >= retry_blocked:
                return ReplayResult(ok=False, reason="blocked", step=start + i, n_steps=len(sess.actions) - start,
                                    actions=list(sess.actions[start:]))
        else:
            consecutive_blocked = 0
    ok = sess.won
    return ReplayResult(ok=ok, reason="pass" if ok else "verifier_fail", step=None if ok else len(sess.actions),
                        n_steps=len(sess.actions) - start, actions=list(sess.actions[start:]))


def witness_base(seed: int, max_steps: int = EXPERT_MAX_STEPS) -> dict:
    """W_base(t): closed-loop expert from reset in the base env."""
    sess = open_session(None, seed)
    try:
        res = run_expert(sess, max_steps=max_steps)
        return {"task_id": seed, "gamefile": sess.gamefile, "type": task_type_from_gamefile(sess.gamefile),
                "W_base": res.ok, "reason": res.reason, "expert_plan_len": res.n_steps,
                "within_policy_cap": res.ok and res.n_steps <= POLICY_MAX_STEPS, "expert_actions": res.actions}
    finally:
        sess.close()


def r_old(candidate: Candidate, seed: int, base_expert_actions: list[str]) -> ReplayResult:
    """R_old(c): base expert plan replayed verbatim in E'_c."""
    sess = open_session(candidate, seed)
    try:
        return replay_actions(sess, base_expert_actions)
    finally:
        sess.close()


def r_exp(candidate: Candidate, seed: int, max_steps: int = EXPERT_MAX_STEPS) -> ReplayResult:
    """R_exp(c): expert re-planned step by step from E'_c's initial state (after Stage replay)."""
    sess = open_session(candidate, seed)
    try:
        return run_expert(sess, max_steps=max_steps)
    finally:
        sess.close()
