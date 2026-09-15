"""Bounded, LLM-free Rules surface probes on trusted original episode snapshots.

The actual released Rules reset/step loop and policy observation formatter execute here.
Each dose gets a fresh wrapper; hooks retain their own state throughout the raw prefix.
Snapshots are trusted original-session data, never the misleading ``raw_observation`` field
of a wrapped Trace. This is a replay diagnostic, not a Python security sandbox or proof over
unseen states. Unsupported transitions, histories or state mutations are explicit uncertainty.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from envharness.agents.policy import ActionFormat, PolicyAgent
from envharness.core.code_loader import load_rules_subclass
from envharness.core.types import Action, EnvResetResponse, EnvResponse, Observation

from aea.semantic_privilege import AuthorizedEvidence, SurfaceProbe
from aea.session import Session

DEFAULT_DOSES = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class RawSnapshot:
    """Reset at index zero; later entries are raw responses to their recorded action."""

    observation: Observation
    env_state: Any
    action: Action | None = None
    response: EnvResponse | None = None


@dataclass(frozen=True)
class ReplayEpisode:
    task_id: str
    episode_id: str
    goal: str
    snapshots: tuple[RawSnapshot, ...]
    seed: int | None = None
    reset_options: dict[str, Any] | None = None
    error: str | None = None
    task_prompt: str = ""
    action_format: str = "think_action"


def capture_episode(
    open_original_session: Callable[[], Session],
    *,
    task_id: str,
    episode_id: str,
    actions: tuple[str, ...],
    goal: str,
    max_steps: int = 50,
    task_prompt: str = "",
    action_format: str = "think_action",
) -> ReplayEpisode:
    """Replay only supplied actions in an original local session; no policy/model calls.

    A caller must provide the original environment, not a candidate stack. The identity
    check rejects wrapped sessions. Full observations and hook states are deep-copied while
    the original session owns its lock. Missing/shortened history is recorded, not invented.
    """
    snapshots: list[RawSnapshot] = []
    error: str | None = None
    seed: int | None = None
    reset_options: dict[str, Any] = {}
    session: Session | None = None
    try:
        if max_steps < 0 or len(actions) > max_steps:
            raise ValueError("requested raw history exceeds the bounded replay horizon")
        session = open_original_session()
        seed = session.seed
        if session.stack is not session.bridge:
            raise ValueError("authorized snapshots require an original unwrapped session")
        state_getter = cast(Any, session.bridge).get_env_state
        reset_args = getattr(session.bridge, "default_reset_args", None)
        if callable(reset_args):
            seed, options = reset_args()
            reset_options = copy.deepcopy(dict(options))
        observation = copy.deepcopy(session.stack.observe())
        snapshots.append(RawSnapshot(observation, copy.deepcopy(state_getter())))
        for text in actions:
            if session.done:
                raise ValueError("original episode ended before the requested history")
            action = Action(name="do", kwargs={"text": text})
            response = session.stack.step(copy.deepcopy(action))
            snapshots.append(
                RawSnapshot(
                    copy.deepcopy(response.observation),
                    copy.deepcopy(state_getter()),
                    action,
                    copy.deepcopy(response),
                )
            )
            if response.terminated or response.truncated:
                session.ended = True
    except Exception as exc:
        error = f"original replay unavailable: {type(exc).__name__}: {exc}"
    finally:
        if session is not None:
            session.close()
    return ReplayEpisode(
        task_id,
        episode_id,
        goal,
        tuple(snapshots),
        seed=seed,
        reset_options=reset_options,
        error=error,
        task_prompt=task_prompt,
        action_format=action_format,
    )


class _NoModel:
    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("surface capture must never call a policy model")


def _formatter(task_prompt: str, action_format: str) -> Any:
    selected = ActionFormat(action_format)
    if selected == ActionFormat.WEBARENA_RB:
        raise ValueError("WebArena policy formatter is outside the ALFWorld replay scope")
    # PolicyAgent validates this same single-tool schema without making a model call.
    return PolicyAgent(
        client=_NoModel(),
        tools=[{"function": {"name": "do", "parameters": {"properties": {"text": {}}}}}],
        task_prompt=task_prompt,
        action_format=selected,
    )


def _state_fields(state: Any) -> dict[str, Any]:
    if isinstance(state, dict):
        return dict(state)
    return dict(vars(state))


class _ReplayInner:
    """Serve trusted same-action snapshots, refusing fabricated remapped transitions."""

    def __init__(self, episode: ReplayEpisode) -> None:
        self.episode = copy.deepcopy(episode)
        self.index = 0
        self.state = copy.deepcopy(episode.snapshots[0].env_state)
        self.action: Action | None = None
        self.steps_this_turn = 0

    def reset(self, seed: int | None = None, options: Any = None) -> EnvResetResponse:
        self.index = 0
        self.state = copy.deepcopy(self.episode.snapshots[0].env_state)
        self.action = None
        return EnvResetResponse(observation=self.observe())

    def get_env_state(self) -> Any:
        return self.state

    def observe(self) -> Observation:
        return copy.deepcopy(self.episode.snapshots[self.index].observation)

    def state_mutated(self) -> bool:
        current = _state_fields(self.state)
        expected = _state_fields(self.episode.snapshots[self.index].env_state)
        current.pop("extras", None)
        expected.pop("extras", None)
        return current != expected

    def step(self, action: Action) -> EnvResponse:
        self.action = copy.deepcopy(action)
        self.steps_this_turn += 1
        if self.steps_this_turn != 1:
            raise ValueError(
                "candidate performed multiple inner transitions for one learner action"
            )
        if self.state_mutated():
            raise ValueError("non-extra environment-state mutation needs independent live replay")
        if self.index + 1 >= len(self.episode.snapshots):
            raise ValueError("missing original transition snapshot")
        next_snapshot = self.episode.snapshots[self.index + 1]
        if action != next_snapshot.action:
            raise ValueError("remapped action has no trusted same-state transition snapshot")
        if next_snapshot.response is None:
            raise ValueError("missing original response")
        # The ALFWorld bridge mutates a persistent state object. Preserve only the explicitly
        # free-form extras bag; never insert candidate facts into authorized observations.
        fields = _state_fields(self.state)
        extras = copy.deepcopy(fields.get("extras", {}))
        new_fields = copy.deepcopy(_state_fields(next_snapshot.env_state))
        if "extras" in fields or "extras" in new_fields:
            new_fields["extras"] = extras
        if isinstance(self.state, dict):
            self.state.clear()
            self.state.update(new_fields)
        else:
            vars(self.state).clear()
            vars(self.state).update(new_fields)
        self.index += 1
        return copy.deepcopy(next_snapshot.response)


def _surface(
    observation: Observation | None,
    response: EnvResponse | None,
    action: Action | None,
    formatter: Any,
    formatted_history: Sequence[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "final_prompt": formatter._format_obs(observation) if observation is not None else "",
        "observation": observation.model_dump(mode="json") if observation is not None else {},
        "admissible_commands": list((observation.data or {}).get("admissible_commands") or [])
        if observation is not None
        else [],
        "action": action.model_dump(mode="json") if action is not None else None,
        "feedback": {
            "blocked": bool(observation.data.get("blocked")) if observation is not None else False,
            "blocked_reason": observation.data.get("blocked_reason")
            if observation is not None
            else None,
        },
        "transition": {},
        "formatted_observation_history": list(formatted_history),
    }
    if response is not None:
        result["transition"] = {
            "reward": response.reward,
            "terminated": response.terminated,
            "truncated": response.truncated,
            "info": copy.deepcopy(response.info),
        }
    # Reject unsupported arbitrary objects instead of silently stringifying away a surface.
    json.dumps(result, sort_keys=True)
    return result


def _authorized(episode: ReplayEpisode, index: int) -> AuthorizedEvidence:
    prefix = episode.snapshots[: index + 1]
    return AuthorizedEvidence(
        task_id=episode.task_id,
        episode_id=episode.episode_id,
        step=index,
        goal=episode.goal,
        observations=tuple(snapshot.observation.text for snapshot in prefix),
        actions=tuple(
            str(snapshot.action.kwargs.get("text", ""))
            for snapshot in prefix
            if snapshot.action is not None
        ),
        admissible_commands=tuple(
            str(command)
            for command in (prefix[-1].observation.data.get("admissible_commands") or [])
        )
        if prefix
        else (),
    )


def _error_probe(episode: ReplayEpisode, dose: float, error: str) -> SurfaceProbe:
    return SurfaceProbe(_authorized(episode, 0), dose, {}, {}, error=error)


def _probe_episode(source: str, episode: ReplayEpisode, dose: float) -> list[SurfaceProbe]:
    if episode.error or not episode.snapshots:
        return [_error_probe(episode, dose, episode.error or "missing raw reset snapshot")]
    if episode.snapshots[0].action is not None or episode.snapshots[0].response is not None:
        return [_error_probe(episode, dose, "raw history must start at the original reset")]
    probes: list[SurfaceProbe] = []
    try:
        formatter = _formatter(episode.task_prompt, episode.action_format)
        inner = _ReplayInner(episode)
    except Exception as exc:
        return [
            _error_probe(episode, dose, f"unsupported replay inputs: {type(exc).__name__}: {exc}")
        ]
    baseline_history: list[str] = []
    transformed_history: list[str] = []
    hooks: list[str] = []
    observed: dict[str, Any] = {}
    try:
        cls = load_rules_subclass(
            source.replace("__DOSE__", repr(dose)).replace("__TASK_ID__", repr(episode.task_id))
        )
        wrapper = cls(inner=inner)
        for name in ("filter_action", "modify_transition", "filter_observation"):
            original = getattr(wrapper, name)

            def record(*args: Any, _name: str = name, _fn: Any = original, **kwargs: Any) -> Any:
                hooks.append(_name)
                result = _fn(*args, **kwargs)
                observed[_name] = copy.deepcopy(result)
                return result

            setattr(wrapper, name, record)
        for index, snapshot in enumerate(episode.snapshots):
            hooks.clear()
            observed.clear()
            inner.action = None
            inner.steps_this_turn = 0
            response: EnvResponse | None = None
            observation: Observation | None = None
            error: str | None = None
            try:
                if index == 0:
                    observation = wrapper.reset(
                        seed=episode.seed, options=episode.reset_options
                    ).observation
                else:
                    if snapshot.action is None or snapshot.response is None:
                        raise ValueError("missing original action/response within raw prefix")
                    response = wrapper.step(copy.deepcopy(snapshot.action))
                    observation = response.observation
                    if inner.index != index:
                        error = "blocked/diverged action: further raw-prefix replay unsupported"
                if inner.state_mutated():
                    error = "non-extra environment-state mutation needs independent live replay"
            except Exception as exc:
                error = f"hook replay unavailable: {type(exc).__name__}: {exc}"
                observation = observed.get("filter_observation")
            # A blocked/remapped action did not reveal the original next state. Authorization
            # therefore ends at the last actually reached raw snapshot, never at future data.
            authorized_index = min(index, inner.index)
            base = episode.snapshots[authorized_index] if error else snapshot
            baseline = _surface(
                base.observation, base.response, snapshot.action, formatter, baseline_history
            )
            transformed_action = inner.action
            filtered = observed.get("filter_action")
            if filtered is not None and isinstance(filtered, Action):
                transformed_action = filtered
            transformed = _surface(
                observation, response, transformed_action, formatter, transformed_history
            )
            coverage = (*hooks, "policy_formatter", "same_original_state")
            probes.append(
                SurfaceProbe(
                    _authorized(episode, authorized_index),
                    dose,
                    baseline,
                    transformed,
                    coverage,
                    error,
                )
            )
            baseline_history.append(str(baseline["final_prompt"]))
            transformed_history.append(str(transformed["final_prompt"]))
            if error:
                break
    except Exception as exc:
        probes.append(
            _error_probe(episode, dose, f"surface capture unavailable: {type(exc).__name__}: {exc}")
        )
    return probes


def probe_template(
    source: str,
    task_id: str,
    episodes: Sequence[ReplayEpisode],
    doses: Sequence[float] = DEFAULT_DOSES,
) -> tuple[SurfaceProbe, ...]:
    """Execute a bounded dose set; callers may supply reachable CONTROL or exact doses.

    Outputs contain only raw-prefix authorization, actual hook surfaces, and coverage/errors.
    Candidate bytes are never normalized or repaired. The default grid is a diagnostic;
    passing it cannot establish behavior at every real number or on unrecorded histories.
    """
    if episodes and "__DOSE__" not in source:
        return (_error_probe(episodes[0], 0.0, "missing family dose placeholder"),)
    if not episodes:
        empty = ReplayEpisode(task_id, "missing", "", (), error="missing raw episode history")
        return (_error_probe(empty, 0.0, empty.error or "missing history"),)
    if not doses or len(doses) > 33 or any(not 0 <= dose <= 1 for dose in doses):
        return (_error_probe(episodes[0], 0.0, "invalid or unbounded dose schedule"),)
    out: list[SurfaceProbe] = []
    for episode in episodes:
        if episode.task_id != task_id:
            out.append(_error_probe(episode, 0.0, "task identity mismatch"))
            continue
        if len(episode.snapshots) > 51:
            out.append(_error_probe(episode, 0.0, "raw history exceeds 50-step bound"))
            continue
        for dose in doses:
            out.extend(_probe_episode(source, episode, float(dose)))
    return tuple(out)
