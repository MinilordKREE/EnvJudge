"""Hand-off for unresolved zero tasks (spec section 7) - the AEA+Handoff arm only.

The main method leaves an unresolved zero task in accounting. The second arm renders the expert's
shortest success as a demonstration in the released trace format so the released induction
(``scripts/induce_pair.py:81-134``: shortest success per task, ``single_succ``) reads it:
``Step.filtered_action.kwargs.text`` + ``Step.filtered_observation.text`` (+ a synthetic
``policy_raw_response`` of the form ``<action>cmd</action>`` only; no fabricated reasoning), see
``envharness/reasoning_bank/induce.py:162-201``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea.certs import Session, run_expert
from aea.config import AEAConfig

HANDOFF_CANDIDATE_ID = "handoff"
HANDOFF_POLICY_ID = "expert:handcoded"


def render_witness_trace(
    task_label: str, task_seed: int, actions: list[str], observations: list[str]
) -> Trace:
    """A success Trace in the released format from an action/observation list."""
    if len(actions) != len(observations):
        raise ValueError("actions and observations must align")
    steps = []
    for a, obs in zip(actions, observations, strict=True):
        act = Action(name="do", kwargs={"text": a})
        observation = Observation(text=obs)
        steps.append(
            Step(
                raw_action=act,
                filtered_action=act,
                raw_observation=observation,
                filtered_observation=observation,
                policy_raw_response=f"<action>{a}</action>",
            )
        )
    return Trace(
        episode_id=uuid.uuid4().hex[:10],
        iteration_id=HANDOFF_CANDIDATE_ID,
        task_id=task_label,
        candidate=Candidate(rationale="handoff witness"),
        candidate_id=HANDOFF_CANDIDATE_ID,
        rollout_seed=task_seed,
        steps=steps,
        final_reward=1.0,
        success=True,
        duration_steps=len(steps),
        kind="exploration",
        policy_model_id=HANDOFF_POLICY_ID,
    )


def _run_recording(sess: Session, max_steps: int) -> tuple[Any, list[str]]:
    """Run the expert while recording the observation text after each of its actions."""
    observations: list[str] = []
    original = sess.step_text

    def recording_step(text: str) -> dict[str, object]:
        r = original(text)
        observations.append(str(r["obs"]))
        return r

    sess.step_text = recording_step  # type: ignore[method-assign]
    try:
        return run_expert(sess, max_steps=max_steps), observations
    finally:
        sess.close()


def handoff(
    open_fn: Callable[[Candidate | None], Session],
    config: AEAConfig,
    *,
    task_label: str,
    task_seed: int,
) -> Trace | None:
    """Shortest expert success over ``expert_attempts`` runs, rendered as a demonstration."""
    best: tuple[list[str], list[str]] | None = None
    for _ in range(config.expert_attempts):
        r, observations = _run_recording(open_fn(None), config.expert_max_steps)
        if r.ok and (best is None or len(r.actions) < len(best[0])):
            best = (list(r.actions), list(observations[: len(r.actions)]))
    if best is None:
        return None
    return render_witness_trace(task_label, task_seed, best[0], best[1])
