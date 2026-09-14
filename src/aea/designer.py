"""The ``llm_v1`` designer (docs/spec/AEA_llm_v1.md): regime-conditioned LLM intervention design.

One designer model, two regime-conditioned calls, no second agent. The controller measures
(``aea.estimate``), this module turns the measurement into bounded designer evidence and one tool
call, and the controller's existing empirical control (``_try_family`` on the saturated side, the
4 -> 8 probe on the zero side) accepts, rejects or calibrates what the designer proposed. The
designer never sees rollout results, never picks a final dose and never declares acceptance.

- HIGH (regime ``saturated``): :func:`serialize_high` (task goal, p_hat, representative successes
  and one failure, success lengths) + :data:`DESIGN_HIGH_TOOL` -> up to two dose-parameterised
  Rules families (``ProposedFamily``), validated by the same ``validate_rules_template`` as v0.4.
  The two library families appear as few-shot examples only.
- LOW (regime ``zero``): :func:`serialize_low` (task goal, p_hat, the sampled failed rollouts and,
  when available, the privileged reference) + :data:`DESIGN_LOW_TOOL` -> up to two grounded
  Stage cuts (``StageProposal``), each pointing at an actual step of a supplied failure or of the
  reference; ungrounded indices are rejected deterministically, never repaired.
- The reference (:class:`ExpertReference`) is the ALFWorld handcoded expert run from the task's
  reset state through the same locked in-process session the guards use (``aea.session``). It is
  privileged designer information: it reaches the designer prompt and the selected prefix only.
  ``Evidence.redacted`` (the reference block replaced by its metadata) is what the run directory
  keeps; the full text is hashed.

Evidence serialisation is LLM-free and deterministic under :class:`EvidenceBounds`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from envharness.core.code_loader import load_rules_subclass
from envharness.core.types import Action, Candidate, Trace

from aea import exemplars
from aea.families import (
    LIBRARY_NAMES,
    Axis,
    FamilyContext,
    ProposedFamily,
    Source,
    _is_library_copy,
    _SmokeInner,
    validate_rules_template,
)
from aea.llm.types import ChatMessage, ChatRequest
from aea.session import SESSION_LOCK, Session, run_expert

MAX_PROPOSALS = 2
REFERENCE_ID = "reference"


# ---------------------------------------------------------------------------- reference
@dataclass(frozen=True)
class ReferenceStep:
    """One simulator-visible step of the expert's successful trajectory: what it saw, what it
    could do, what it did. No reasoning of any kind is recorded (the expert has none)."""

    step: int
    observation: str
    admissible: tuple[str, ...]
    action: str


@dataclass(frozen=True)
class Reference:
    ok: bool
    reason: str
    actions: tuple[str, ...] = ()
    steps: tuple[ReferenceStep, ...] = ()
    """The rich trajectory (phase 3.2); empty when only the action list was captured."""

    @property
    def n_steps(self) -> int:
        return len(self.actions)

    @property
    def success(self) -> bool:
        return self.ok

    def as_record(self) -> dict[str, Any]:
        """The exact instance for ``privileged_references.jsonl`` (audit-side only)."""
        return {
            "reference_id": reference_id(self.actions) if self.ok else None,
            "success": self.ok,
            "reason": self.reason,
            "actions": list(self.actions),
            "n_steps": self.n_steps,
            "steps": [
                {
                    "step": s.step,
                    "observation": s.observation,
                    "admissible": list(s.admissible),
                    "action": s.action,
                }
                for s in self.steps
            ],
        }


class TaskLike(Protocol):
    """What a provider needs of the controller's ``TaskRef`` (no import cycle)."""

    @property
    def task_id(self) -> str: ...
    @property
    def seed(self) -> int: ...


class ReferenceProvider(Protocol):
    """Privileged reference for one task: a successful action list from the reset state, or
    ``ok=False`` with the reason (expert error, stuck, timeout, no success). Never charged.
    Constructing a provider runs nothing; the expert runs only when the controller calls it
    (``llm_v1`` and regime ``zero``)."""

    def __call__(self, task: TaskLike) -> Reference: ...


@dataclass
class ExpertReference:
    """The benchmark expert from reset, through a locked in-process session (``run_expert``)."""

    open_fn: Callable[[TaskLike], Session]
    max_steps: int

    def __call__(self, task: TaskLike) -> Reference:
        steps: list[ReferenceStep] = []

        def record(obs: str, admissible: list[str], action: str) -> None:
            steps.append(ReferenceStep(len(steps) + 1, obs, tuple(admissible), action))

        with SESSION_LOCK:
            sess: Session | None = None
            try:
                sess = self.open_fn(task)
                r = run_expert(sess, max_steps=self.max_steps, on_step=record)
            except Exception as exc:  # the expert must never take the task down
                return Reference(False, f"{type(exc).__name__}: {exc}")
            finally:
                if sess is not None:
                    sess.close()
        if not r.ok:
            return Reference(False, r.reason)
        actions = tuple(r.actions)
        rich = tuple(steps[: len(actions)])  # one recorded step per executed action
        if tuple(s.action for s in rich) != actions:
            rich = ()  # never keep a trajectory that does not match the executed actions
        return Reference(True, r.reason, actions, rich)


# ---------------------------------------------------------------------------- evidence
@dataclass(frozen=True)
class EvidenceBounds:
    """Deterministic size bound of the designer evidence (implementation constants)."""

    successes: int = 2
    failures: int = 1
    steps_head: int = 12
    steps_tail: int = 6
    obs_chars: int = 320
    think_chars: int = 240
    total_chars: int = 24_000


BOUNDS = EvidenceBounds()


@dataclass(frozen=True)
class Evidence:
    text: str
    """Exactly what the designer received (the reference block included on LOW)."""
    redacted: str
    """The same text with the reference block replaced by its metadata: what the run keeps."""
    sha256: str
    n_traces: int
    reference_used: bool
    trajectory_ids: dict[str, str] = field(default_factory=dict)
    """Label used in the text -> ``Trace.episode_id`` (LOW: the selectable failures)."""


_GOAL_PATTERNS = (re.compile(r"Your task is to:\s*(.+)"), re.compile(r"^Task:\s*(.+)", re.M))


def task_goal(traces: Sequence[Trace]) -> str:
    """The natural-language goal from the step-0 observation (ALFWorld: ``Your task is to:``)."""
    for t in traces:
        if not t.steps or t.steps[0].raw_observation is None:
            continue
        text = t.steps[0].raw_observation.text
        for pat in _GOAL_PATTERNS:
            m = pat.search(text)
            if m:
                return m.group(1).strip().rstrip(".")
        first = text.strip().splitlines()
        if first:
            return str(first[0][:200])
    return ""


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 3] + "..."


def _think(step: Any, n: int) -> str | None:
    """The policy's own reasoning, only when the response carries a separate ``<think>`` block;
    an action-only response (thinking off) yields nothing rather than its action echoed back as
    'reasoning'."""
    raw = step.policy_raw_response
    if not raw:
        return None
    m = re.search(r"<think>(.*?)</think>", raw, re.S)
    if not m or not m.group(1).strip():
        return None
    return _clip(m.group(1), n)


def _step_lines(step: Any, i: int, b: EvidenceBounds) -> list[str]:
    obs = step.filtered_observation or step.raw_observation
    act = str(step.raw_action.kwargs.get("text", ""))
    flags = []
    if step.blocked_reason:
        flags.append(f"blocked: {step.blocked_reason}")
    if step.info.get("effective") is False:
        flags.append("no effect")
    lines = [f"step {i}:"]
    think = _think(step, b.think_chars)
    if think:
        lines.append(f"  reasoning: {think}")
    lines.append(f"  action: {act}" + (f"  [{'; '.join(flags)}]" if flags else ""))
    lines.append(f"  observation: {_clip(obs.text if obs else '', b.obs_chars)}")
    return lines


def trajectory_text(label: str, trace: Trace, b: EvidenceBounds) -> str:
    n = len(trace.steps)
    head = [f"Trajectory {label} - {'SUCCESS' if trace.success else 'FAILURE'} ({n} steps)"]
    idx = list(range(n))
    if n > b.steps_head + b.steps_tail:
        idx = [*idx[: b.steps_head], -1, *idx[n - b.steps_tail :]]
    for i in idx:
        if i < 0:
            head.append(f"  ... {n - b.steps_head - b.steps_tail} steps omitted ...")
        else:
            head.extend(_step_lines(trace.steps[i], i + 1, b))
    return "\n".join(head)


def _bounded(parts: list[str], total: int) -> str:
    text = "\n\n".join(parts)
    if len(text) <= total:
        return text
    marker = "\n\n[... evidence truncated at the size bound ...]"
    return text[: total - len(marker)] + marker


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reference_id(actions: Sequence[str]) -> str:
    """The identity of one exact reference instance: sha256 of its action list (16 hex). Shown
    in the redacted evidence and written to ``privileged_references.jsonl`` so a post-run audit
    can check the exact reference used without running the expert again."""
    return _sha(json.dumps(list(actions)))[:16]


def representative(traces: Sequence[Trace], b: EvidenceBounds) -> tuple[list[Trace], list[Trace]]:
    """HIGH: the shortest and the longest success, and the first failure (episode order)."""
    ok = [t for t in traces if t.success and not t.error and t.steps]
    bad = [t for t in traces if not t.success and not t.error and t.steps]
    by_len = sorted(ok, key=lambda t: (len(t.steps), t.episode_id))
    picked: list[Trace] = []
    for t in (by_len[:1] + by_len[-1:]) if by_len else []:
        if t not in picked and len(picked) < b.successes:
            picked.append(t)
    return picked, bad[: b.failures]


def serialize_high(
    traces: Sequence[Trace], p_hat: float, n: int, b: EvidenceBounds = BOUNDS
) -> Evidence:
    ok, bad = representative(traces, b)
    lengths = sorted(len(t.steps) for t in traces if t.success and not t.error)
    parts = [
        f"TASK GOAL: {task_goal(traces)}",
        f"REGIME: HIGH (saturated)\np_hat: {p_hat:.3f}\nn: {n}\nsuccess lengths: {lengths}",
        "REPRESENTATIVE TRAJECTORIES",
        *[trajectory_text(f"S{i + 1}", t, b) for i, t in enumerate(ok)],
        *[trajectory_text(f"F{i + 1}", t, b) for i, t in enumerate(bad)],
    ]
    text = _bounded(parts, b.total_chars)
    return Evidence(text, text, _sha(text), len(ok) + len(bad), False)


def reference_text(reference: Reference, b: EvidenceBounds, *, rich: bool) -> str:
    """The reference block: the action list (llm_v1) or, when ``rich`` and the trajectory was
    captured, every step's observation and action (llm_v1_refalign). Rich steps are never
    head/tail-truncated (the designer must be able to align against any step); only each
    observation is clipped."""
    if rich and reference.steps:
        block = (
            "PRIVILEGED REFERENCE TRAJECTORY (a verified successful trajectory from reset, "
            f"observation then action at each step; selectable: trajectory_id {REFERENCE_ID}, "
            f"step 1..{reference.n_steps})"
        )
        for s in reference.steps:
            block += f"\nstep {s.step}:\n  observation: {_clip(s.observation, b.obs_chars)}"
            block += f"\n  action: {s.action}"
        return block
    block = "PRIVILEGED REFERENCE (a successful action sequence from reset; selectable: "
    block += f"trajectory_id {REFERENCE_ID}, step 1..{reference.n_steps})\n"
    block += "\n".join(f"step {i + 1}: {a}" for i, a in enumerate(reference.actions))
    return block


def serialize_low(
    failures: Sequence[Trace],
    p_hat: float,
    n: int,
    reference: Reference | None,
    b: EvidenceBounds = BOUNDS,
    *,
    rich: bool = False,
) -> Evidence:
    """The reference block comes BEFORE the failures, so the size bound (which truncates from
    the end) can only ever cut failure steps, never the reference; ``reference_used`` is read
    from the bounded text itself, so the metadata cannot claim a reference the designer did not
    receive. ``rich``: the observation/action trajectory instead of the action list."""
    ids = {f"F{i + 1}": t.episode_id for i, t in enumerate(failures)}
    head = [
        f"TASK GOAL: {task_goal(failures)}",
        f"REGIME: LOW (zero)\np_hat: {p_hat:.3f}\nn: {n}",
    ]
    fails = [
        "FAILED CURRENT-POLICY TRAJECTORIES (selectable: trajectory_id F1.., step 1..length)",
        *[trajectory_text(label, t, b) for label, t in zip(ids, failures, strict=True)],
    ]
    if reference is not None and reference.ok:
        block = reference_text(reference, b, rich=rich)
        meta = (
            f"PRIVILEGED REFERENCE: {reference.n_steps} actions"
            + (" with observations" if rich and reference.steps else "")
            + f", sha256 {reference_id(reference.actions)} [content withheld]"
        )
        text = _bounded([*head, block, *fails], b.total_chars)
        redacted = _bounded([*head, meta, *fails], b.total_chars)
        used = block in text
    else:
        text = _bounded([*head, *fails], b.total_chars)
        redacted, used = text, False
    return Evidence(text, redacted, _sha(text), len(failures), used, ids)


# ---------------------------------------------------------------------------- HIGH contract
DESIGN_HIGH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "propose_interventions",
        "description": (
            "Propose up to two dose-parameterised environment interventions (Rules subclasses) "
            "that challenge the current policy on this task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "families": {
                    "type": "array",
                    "maxItems": MAX_PROPOSALS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "short snake_case name"},
                            "axis": {"type": "string", "enum": ["O", "T", "A"]},
                            "mechanism_summary": {
                                "type": "string",
                                "description": (
                                    "one or two sentences: which cue, shortcut or affordance "
                                    "the policy depends on and how the intervention removes it"
                                ),
                            },
                            "rules_code": {
                                "type": "string",
                                "description": (
                                    "class _Rules(Rules) with a class attribute DOSE = __DOSE__"
                                ),
                            },
                        },
                        "required": ["name", "axis", "mechanism_summary", "rules_code"],
                    },
                }
            },
            "required": ["families"],
        },
    },
}

ENVIRONMENT_SURFACE = (
    "Environment surface (released envharness ALFWorld bridge; what your code actually sees):\n"
    '- Action: every policy action is `Action(name="do", kwargs={"text": "<command>"})`; '
    "the command text is a TextWorld command such as `go to shelf 1`, `take mug 1 from shelf 1`, "
    "`clean mug 1 with sinkbasin 1`, `use desklamp 1`. There are no per-verb action names: "
    'inspect `action.kwargs.get("text")`, never `action.name`.\n'
    "- Observation: `Observation(text, data)`. `text` is rendered as `Task: <goal>\\n\\n<room "
    'text>\\n\\nAdmissible commands: a, b, c`; `data["admissible_commands"]` holds the same '
    'list as structured data. The policy reads BOTH: it appends `data["admissible_commands"]` '
    "to its prompt and normalises its chosen command against that list. Rewriting `text` alone "
    "therefore does not remove an action hint; to hide or alter admissible commands, change "
    '`data["admissible_commands"]` as well (return a new Observation with both fields).\n'
    "- env_state (read-only view passed to every hook): `goal_text`, `obs_text`, "
    "`admissible_commands: list[str]`, `won`, `done`, `step_count` (1-based after the first "
    "step), `last_action_was_effective`, `extras: dict` (free-form per-episode storage for your "
    "own counters or RNG state). No engine handles, no object graph, no locations.\n"
    "- Hooks (override any subset): `filter_action(self, action, env_state) -> Action | Blocked` "
    "runs BEFORE the world step; return the (possibly rewritten) Action, or `Blocked(reason=...)` "
    "(an instance) to reject it: the world is unchanged and the policy sees `[blocked] <reason>` "
    "plus the current observation. `modify_transition(self, action, raw_response, env_state) -> "
    "EnvResponse` runs AFTER the world step on `EnvResponse(observation, reward, terminated, "
    "truncated, info)` (e.g. set `truncated=True` to end the episode; leave `reward` alone). "
    "`filter_observation(self, obs, env_state) -> Observation` runs on the reset observation and "
    "after every step (also after a block) and is the only hook that changes what the policy "
    "sees. Rules cannot move objects or edit the world: only actions, transitions and "
    "observations.\n"
    "- Success is checked by the unchanged verifier on the world state, so an observation "
    "rewrite never changes whether the goal is achieved."
)

HIGH_CONTRACT = (
    "Rules contract: emit `class _Rules(Rules)` with a class attribute `DOSE = __DOSE__` "
    "(d in [0, 1]); larger DOSE must increase the challenge and DOSE = 0 must leave the "
    "environment unchanged; the task goal and its verifier must stay the same and the task must "
    "stay solvable at DOSE = 1; the hooks are filter_action(action, env_state), "
    "modify_transition(action, raw_response, env_state) and filter_observation(obs, env_state); "
    "only the names Rules, Action, Blocked, Observation, EnvResponse and the standard library "
    "(imported inside the code) are available; no Chain/Link. Do not predict whether an "
    "intervention works and do not choose a dose: rollout measurements decide."
)

HIGH_OBJECTIVE = (
    "The current policy already solves this environment reliably. Diagnose which environmental "
    "cues, shortcuts or interaction affordances its successful behaviour depends on. Propose up "
    "to two NEW parameterised environment interventions that challenge the current policy "
    "without changing the task goal or the verifier. The two examples below are illustrations "
    "of the contract only; do not re-propose them or trivial variants. Return them in the order "
    "you would try them."
)


def high_messages(evidence: Evidence) -> tuple[ChatMessage, ...]:
    shots = "\n\n".join(f"### example: {n}\n{exemplars.prompt_text(n)}" for n in LIBRARY_NAMES)
    return (
        ChatMessage(
            role="system",
            content="You design environment interventions under a strict contract.\n"
            + HIGH_CONTRACT
            + "\n\n"
            + ENVIRONMENT_SURFACE,
        ),
        ChatMessage(
            role="user",
            content=(
                f"{HIGH_OBJECTIVE}\n\n{evidence.text}\n\n{shots}\n\nCall propose_interventions."
            ),
        ),
    )


@dataclass
class HighDesign:
    families: list[ProposedFamily]
    mechanisms: dict[str, str]
    rejected: list[str]
    arguments: dict[str, Any]


def parse_high(arguments: dict[str, Any]) -> HighDesign:
    """Validate a ``propose_interventions`` call: at most two, library copies rejected, the
    template must pass ``validate_rules_template`` (loader + LLM-free smoke at d = 1)."""
    out = HighDesign([], {}, [], dict(arguments))
    for raw in list(arguments.get("families") or [])[:MAX_PROPOSALS]:
        if not isinstance(raw, dict):
            out.rejected.append("family entry is not an object")
            continue
        name = re.sub(r"[^a-z0-9_]", "_", str(raw.get("name") or "llm_family").lower())[:40]
        template = str(raw.get("rules_code") or "")
        summary = str(raw.get("mechanism_summary") or "").strip()
        if not summary:
            out.rejected.append(f"{name}: missing mechanism_summary")
            continue
        if _is_library_copy(name, template):
            out.rejected.append(f"{name}: copy of a library example")
            continue
        report = validate_rules_template(template)
        if not report.ok:
            out.rejected.append(f"{name}: " + "; ".join(report.reasons))
            continue
        axis = raw.get("axis")
        if axis not in ("O", "T", "A"):
            out.rejected.append(f"{name}: axis must be O, T or A")
            continue
        if any(f.name == name for f in out.families):
            out.rejected.append(f"{name}: duplicate name")
            continue
        out.families.append(ProposedFamily(name=name, axis=axis, template=template))
        out.mechanisms[name] = summary
    return out


# ---------------------------------------------------------------------------- LOW contract
type StageSource = Literal["failure", "reference"]

DESIGN_LOW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "select_stages",
        "description": (
            "Select up to two grounded restart points (a trajectory and a step) from which the "
            "current policy should be restarted."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stages": {
                    "type": "array",
                    "maxItems": MAX_PROPOSALS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "enum": ["failure", "reference"]},
                            "trajectory_id": {
                                "type": "string",
                                "description": "F1.. for a failure, 'reference' for the reference",
                            },
                            "step": {
                                "type": "integer",
                                "description": (
                                    "restart AFTER this many actions of that trajectory (1-based)"
                                ),
                            },
                            "mechanism_summary": {
                                "type": "string",
                                "description": (
                                    "one or two sentences: where useful progress becomes "
                                    "inaccessible and which subproblem this restart isolates"
                                ),
                            },
                        },
                        "required": ["source", "trajectory_id", "step", "mechanism_summary"],
                    },
                }
            },
            "required": ["stages"],
        },
    },
}

LOW_OBJECTIVE = (
    "The current policy cannot obtain positive experience from reset. Compare its failed "
    "behaviour with the privileged successful reference when one is supplied. Identify where "
    "useful progress becomes inaccessible. Select up to two grounded restart points that could "
    "isolate a learnable subproblem, most promising first. You may only select a state that "
    "actually appears in one of the supplied trajectories (a trajectory_id and a step count); do "
    "not invent simulator states. The policy will be restarted after the selected actions and "
    "will never see the reference or any action beyond the selected step. Do not predict whether "
    "a restart works: rollout measurements decide."
)


def low_messages(evidence: Evidence) -> tuple[ChatMessage, ...]:
    return (
        ChatMessage(
            role="system",
            content="You diagnose a failing policy and design grounded restart interventions.",
        ),
        ChatMessage(
            role="user", content=f"{LOW_OBJECTIVE}\n\n{evidence.text}\n\nCall select_stages."
        ),
    )


@dataclass(frozen=True)
class StageProposal:
    source: StageSource
    trajectory_id: str
    """The label used in the evidence (``F1``.. or ``reference``)."""
    episode_id: str | None
    step: int
    mechanism_summary: str
    diagnosis: int | None = None
    """llm_v1_refalign: 1-based index of the diagnosis this cut answers (None = unlinked)."""


@dataclass
class LowDesign:
    stages: list[StageProposal]
    rejected: list[str]
    arguments: dict[str, Any]


def parse_low(
    arguments: dict[str, Any],
    *,
    failures: Sequence[Trace],
    trajectory_ids: dict[str, str],
    reference: Reference | None,
) -> LowDesign:
    """Validate a ``select_stages`` call: every proposal must point at an actual supplied failure
    (label and 1 <= step <= its length) or at the reference (1 <= step <= its length, only when
    one was supplied). Invalid entries are rejected; nothing is repaired."""
    out = LowDesign([], [], dict(arguments))
    by_id = {t.episode_id: t for t in failures}
    for raw in list(arguments.get("stages") or [])[:MAX_PROPOSALS]:
        if not isinstance(raw, dict):
            out.rejected.append("stage entry is not an object")
            continue
        source, tid = str(raw.get("source") or ""), str(raw.get("trajectory_id") or "")
        summary = str(raw.get("mechanism_summary") or "").strip()
        try:
            step = int(raw.get("step"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.rejected.append(f"{source} {tid}: step is not an integer")
            continue
        if source == "failure":
            eid = trajectory_ids.get(tid)
            if eid is None or eid not in by_id:
                out.rejected.append(f"failure {tid}: not a supplied failure trajectory")
                continue
            length = len(by_id[eid].steps)
        elif source == "reference":
            if reference is None or not reference.ok or tid != REFERENCE_ID:
                out.rejected.append(f"reference {tid}: no reference was supplied")
                continue
            eid, length = None, reference.n_steps
        else:
            out.rejected.append(f"{source} {tid}: source must be failure or reference")
            continue
        if not 1 <= step <= length:
            out.rejected.append(f"{source} {tid}: step {step} outside 1..{length}")
            continue
        if any(p.trajectory_id == tid and p.step == step for p in out.stages):
            out.rejected.append(f"{source} {tid}: duplicate of an earlier proposal")
            continue
        out.stages.append(StageProposal(source, tid, eid, step, summary))  # type: ignore[arg-type]
    return out


# ---------------------------------------------------------------------------- LOW refalign
DIAGNOSE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "diagnose_and_select_stages",
        "description": (
            "First diagnose where and why the failed trajectories consequentially diverge from "
            "the verified successful reference, then select up to two reference-grounded "
            "restart points."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "diagnoses": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "failure_id": {"type": "string", "description": "F1.."},
                            "failure_step": {
                                "type": "integer",
                                "description": (
                                    "the failed trajectory's first CONSEQUENTIAL divergence: "
                                    "the earliest step after which it can no longer be "
                                    "completing the task the way the reference does"
                                ),
                            },
                            "reference_step": {
                                "type": "integer",
                                "description": (
                                    "the reference step whose state the failure should have "
                                    "reached instead (the successful counterfactual)"
                                ),
                            },
                            "error_cause": {"type": "string"},
                            "fix_hint": {
                                "type": "string",
                                "description": "what capability or progress is missing",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "observations / actions that show it (short)",
                            },
                        },
                        "required": [
                            "failure_id",
                            "failure_step",
                            "reference_step",
                            "error_cause",
                            "fix_hint",
                        ],
                    },
                },
                "stages": {
                    "type": "array",
                    "maxItems": MAX_PROPOSALS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "reference_step": {
                                "type": "integer",
                                "description": (
                                    "restart AFTER this many reference actions (1-based)"
                                ),
                            },
                            "diagnosis": {
                                "type": "integer",
                                "description": "1-based index of the diagnosis this cut answers",
                            },
                            "mechanism_summary": {"type": "string"},
                        },
                        "required": ["reference_step", "diagnosis", "mechanism_summary"],
                    },
                },
            },
            "required": ["diagnoses", "stages"],
        },
    },
}

REFALIGN_OBJECTIVE = (
    "The current policy cannot obtain positive experience from reset. You are given its failed "
    "trajectories and a VERIFIED successful reference trajectory (observation and action at "
    "every step). First perform credit assignment: for at least one failed trajectory, find the "
    "first CONSEQUENTIAL divergence from the reference - the earliest step after which the "
    "failure has entered a state or course that materially departs from successful completion. "
    "A different action at the same step is NOT by itself a divergence: ALFWorld admits many "
    "valid action orders, so compare states and progress, not action strings. Report the failure "
    "step, the reference step that holds the successful counterfactual state, the error cause "
    "and a fix hint (which capability or progress is missing). Then select up to two "
    "reference-grounded restart points (a reference step count), most promising first, each "
    "linked to one diagnosis: the policy will be restarted after those reference actions and "
    "must be able to learn the missing piece from there. You may only select reference steps; "
    "do not invent states. The policy will never see the reference or any action beyond the "
    "selected step. Do not predict whether a restart works: rollout measurements decide."
)


def refalign_messages(evidence: Evidence) -> tuple[ChatMessage, ...]:
    return (
        ChatMessage(
            role="system",
            content=(
                "You diagnose a failing policy against a verified successful reference and "
                "design grounded restart interventions."
            ),
        ),
        ChatMessage(
            role="user",
            content=f"{REFALIGN_OBJECTIVE}\n\n{evidence.text}\n\nCall diagnose_and_select_stages.",
        ),
    )


@dataclass(frozen=True)
class Diagnosis:
    failure_id: str
    episode_id: str | None
    failure_step: int
    reference_step: int
    error_cause: str
    fix_hint: str
    evidence: str = ""


@dataclass
class RefalignDesign:
    diagnoses: list[Diagnosis]
    stages: list[StageProposal]
    rejected: list[str]
    arguments: dict[str, Any]


def parse_refalign(
    arguments: dict[str, Any],
    *,
    failures: Sequence[Trace],
    trajectory_ids: dict[str, str],
    reference: Reference,
) -> RefalignDesign:
    """Validate a ``diagnose_and_select_stages`` call. Diagnoses must name a supplied failure
    with a step in its range and a reference step in range (invalid ones are dropped and
    reported; they never block the stages). Stages must be reference-grounded (1 <= step <=
    len(reference)); the diagnosis link is checked and kept (an unlinked stage is still a valid
    grounded cut, reported as unlinked). At most two stages; nothing is repaired."""
    out = RefalignDesign([], [], [], dict(arguments))
    by_id = {t.episode_id: t for t in failures}
    for raw in list(arguments.get("diagnoses") or []):
        if not isinstance(raw, dict):
            out.rejected.append("diagnosis entry is not an object")
            continue
        fid = str(raw.get("failure_id") or "")
        eid = trajectory_ids.get(fid)
        try:
            fstep, rstep = int(raw.get("failure_step")), int(raw.get("reference_step"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.rejected.append(f"diagnosis {fid}: steps are not integers")
            continue
        if eid is None or eid not in by_id:
            out.rejected.append(f"diagnosis {fid}: not a supplied failure trajectory")
            continue
        if not 1 <= fstep <= len(by_id[eid].steps):
            out.rejected.append(
                f"diagnosis {fid}: failure_step {fstep} outside 1..{len(by_id[eid].steps)}"
            )
            continue
        if not 1 <= rstep <= reference.n_steps:
            out.rejected.append(
                f"diagnosis {fid}: reference_step {rstep} outside 1..{reference.n_steps}"
            )
            continue
        out.diagnoses.append(
            Diagnosis(
                fid,
                eid,
                fstep,
                rstep,
                str(raw.get("error_cause") or "").strip(),
                str(raw.get("fix_hint") or "").strip(),
                str(raw.get("evidence") or "").strip(),
            )
        )
    for raw in list(arguments.get("stages") or [])[:MAX_PROPOSALS]:
        if not isinstance(raw, dict):
            out.rejected.append("stage entry is not an object")
            continue
        try:
            step = int(raw.get("reference_step"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.rejected.append("stage: reference_step is not an integer")
            continue
        if not 1 <= step <= reference.n_steps:
            out.rejected.append(f"stage: reference_step {step} outside 1..{reference.n_steps}")
            continue
        if any(p.step == step for p in out.stages):
            out.rejected.append(f"stage: duplicate reference_step {step}")
            continue
        link: int | None
        try:
            link = int(raw.get("diagnosis"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            link = None
        if link is not None and not 1 <= link <= len(out.diagnoses):
            link = None
        out.stages.append(
            StageProposal(
                "reference",
                REFERENCE_ID,
                None,
                step,
                str(raw.get("mechanism_summary") or "").strip(),
                link,
            )
        )
    return out


def design_low_refalign(
    complete: Callable[[ChatRequest], Any],
    *,
    model: str,
    evidence: Evidence,
    failures: Sequence[Trace],
    reference: Reference,
    attribution: Any,
    seed: int,
) -> RefalignDesign:
    """One LOW designer call under llm_v1_refalign: diagnosis and reference-grounded stages in
    the same tool response (ledgered as budget=designer, never charged to the cap)."""
    response = complete(
        ChatRequest(
            model=model,
            messages=refalign_messages(evidence),
            temperature=0.7,
            seed=seed,
            max_tokens=3072,
            attribution=attribution,
            tools=(DIAGNOSE_TOOL,),
            tool_choice={"type": "function", "function": {"name": "diagnose_and_select_stages"}},
        )
    )
    args = _tool_arguments(response)
    if args is None:
        return RefalignDesign([], [], ["designer returned no tool call"], {})
    return parse_refalign(
        args, failures=failures, trajectory_ids=evidence.trajectory_ids, reference=reference
    )


# ---------------------------------------------------------------------------- LOW assistive Rules
DESIGN_ASSIST_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "diagnose_and_propose_assistance",
        "description": (
            "First diagnose where and why the failed trajectories consequentially diverge from "
            "the verified successful reference, then propose up to two parameterised ASSISTIVE "
            "Rules families (easier with DOSE) that address the diagnosed bottleneck."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "diagnoses": DIAGNOSE_TOOL["function"]["parameters"]["properties"]["diagnoses"],
                "families": {
                    "type": "array",
                    "maxItems": MAX_PROPOSALS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "short snake_case name"},
                            "axis": {"type": "string", "enum": ["O", "T", "A"]},
                            "mechanism_summary": {
                                "type": "string",
                                "description": (
                                    "one or two sentences: the support mechanism and how its "
                                    "amount / coverage / salience grows with DOSE"
                                ),
                            },
                            "why": {
                                "type": "string",
                                "description": "how this addresses the diagnosed bottleneck",
                            },
                            "rules_code": {
                                "type": "string",
                                "description": (
                                    "class _Rules(Rules) with a class attribute DOSE = __DOSE__; "
                                    "DOSE = 0 must be the unchanged environment"
                                ),
                            },
                            "direction": {"type": "string", "enum": ["easier_with_d"]},
                        },
                        "required": [
                            "name",
                            "axis",
                            "mechanism_summary",
                            "why",
                            "rules_code",
                            "direction",
                        ],
                    },
                },
            },
            "required": ["diagnoses", "families"],
        },
    },
}

ASSIST_CONTRACT = (
    "Assistive Rules contract: emit `class _Rules(Rules)` with a class attribute "
    "`DOSE = __DOSE__` (d in [0, 1]). DOSE = 0 must leave the environment EXACTLY unchanged "
    "(every hook returns its input); larger DOSE must give MORE assistance of the SAME support "
    "mechanism (more coverage, more salience, more steps helped), and DOSE = 1 is the strongest "
    "version of that same mechanism - never a switch to a different mechanism at some threshold. "
    "The task goal and its verifier must stay the same; the policy must still perform the "
    "task's actions itself. FORBIDDEN: replaying or listing the reference's actions (the policy "
    "must not receive 'do A then B then C'); copying reference observations; setting or "
    "changing won / success / reward / terminated to reach the goal; calling step on the inner "
    "environment; hard-coding object locations or facts that appear ONLY in the privileged "
    "reference (you may use what the task goal, the policy's own observations and the env_state "
    "expose through the hooks). Allowed scaffolding, as abstract examples only: highlight or "
    "reorder relevant affordances in the admissible list, reduce distractor salience, add "
    "observation support such as reminders of the goal's sub-steps or of what is being held, "
    "make a needed interaction easier to discover through feedback after an action. Only the "
    "names Rules, Action, Blocked, Observation, EnvResponse and the standard library (imported "
    "inside the code) are available; no Chain/Link. Do not predict whether a family works and "
    "do not choose a dose: rollout measurements decide."
)

ASSIST_OBJECTIVE = (
    "The current policy cannot obtain positive experience from reset. You are given its failed "
    "trajectories and a VERIFIED successful reference trajectory (observation and action at "
    "every step). First perform credit assignment exactly as before: for at least one failed "
    "trajectory find the first CONSEQUENTIAL divergence from the reference (compare states and "
    "progress, not action strings), the reference step holding the successful counterfactual, "
    "the error cause and a fix hint (which capability or progress is missing). Then propose up "
    "to two parameterised ASSISTIVE environment interventions, most promising first, each "
    "addressing that diagnosed bottleneck, under the contract in the system message. The policy "
    "will run under your Rules at doses chosen by measurement; it never sees the reference."
)


def assist_messages(evidence: Evidence) -> tuple[ChatMessage, ...]:
    return (
        ChatMessage(
            role="system",
            content="You design assistive environment interventions under a strict contract.\n"
            + ASSIST_CONTRACT
            + "\n\n"
            + ENVIRONMENT_SURFACE,
        ),
        ChatMessage(
            role="user",
            content=(
                f"{ASSIST_OBJECTIVE}\n\n{evidence.text}\n\nCall diagnose_and_propose_assistance."
            ),
        ),
    )


@dataclass(frozen=True)
class AssistFamily:
    """An LLM-generated assistive Rules family (easier with DOSE); the ``Family`` protocol."""

    name: str
    axis: Axis
    template: str
    mechanism_summary: str = ""
    why: str = ""
    source: Source = "llm"
    direction: str = "easier_with_d"

    def make(self, d: float, ctx: FamilyContext) -> Candidate | None:
        code = self.template.replace("__DOSE__", repr(float(d))).replace(
            "__TASK_ID__", repr(str(ctx.task_id))
        )
        return Candidate(rules_code=code, rationale=f"{self.name} d={d}")


def identity_at_zero(template: str, *, task_id: str = "0") -> list[str]:
    """LLM-free check that W(0) = E on the smoke inner env: every hook returns its input."""
    reasons: list[str] = []
    code = template.replace("__DOSE__", "0.0").replace("__TASK_ID__", repr(task_id))
    try:
        cls = load_rules_subclass(code)
        inst = cls(inner=_SmokeInner())
        state = inst.inner.get_env_state()
        act = Action(name="do", kwargs={"text": "look"})
        if inst.filter_action(act, state) != act:
            reasons.append("DOSE = 0 changes the action")
        raw = inst.inner.step(act)
        out = inst.modify_transition(act, raw, state)
        if out != raw:
            reasons.append("DOSE = 0 changes the transition")
        obs = inst.inner.observe()
        if inst.filter_observation(obs, state) != obs:
            reasons.append("DOSE = 0 changes the observation")
    except Exception as exc:
        reasons.append(f"identity check raised {type(exc).__name__}: {exc}")
    return reasons


_GOAL_TOKENS = re.compile(r"[a-z]+ \d+")


def privilege_check(
    template: str,
    *,
    reference: Reference,
    failures: Sequence[Trace],
    goal: str,
) -> list[str]:
    """Structural (no AST engine, no LLM judge): the code must not carry reference actions, a
    replay, a verifier / reward shortcut, or an object token that only the privileged reference
    exposes (present in the reference observations, absent from the goal and from every
    observation the policy itself saw)."""
    reasons: list[str] = []
    body = template
    for a in reference.actions:
        # only task-specific actions (naming a numbered object / receptacle) count: generic
        # verbs such as `look` or `inventory` are the policy's own vocabulary
        if a and _GOAL_TOKENS.search(a.lower()) and a in body:
            reasons.append(f"reference action embedded: {a!r}")
            break
    for pat, why in (
        (r"\.step\(", "calls step on the inner environment (disguised Stage)"),
        (r"\bwon\s*=", "sets won"),
        (r"\bsuccess\W*[=:]\s*True", "sets success"),
        (r"terminated\s*=\s*True", "terminates the episode"),
        (r"\breward\s*=", "changes the reward"),
        (r"in_env_actions", "uses Setup replay"),
    ):
        if re.search(pat, body):
            reasons.append(why)
    seen = set(_GOAL_TOKENS.findall(goal.lower()))
    for t in failures:
        for s in t.steps:
            obs = s.filtered_observation or s.raw_observation
            if obs is not None:
                seen.update(_GOAL_TOKENS.findall(obs.text.lower()))
    privileged: set[str] = set()
    for st in reference.steps:
        privileged.update(_GOAL_TOKENS.findall(st.observation.lower()))
    for a in reference.actions:
        privileged.update(_GOAL_TOKENS.findall(a.lower()))
    leaked = sorted(tok for tok in privileged - seen if tok in body.lower())
    if leaked:
        reasons.append(f"privileged constants from the reference: {leaked[:5]}")
    return reasons


@dataclass
class AssistDesign:
    diagnoses: list[Diagnosis]
    families: list[AssistFamily]
    rejected: list[str]
    arguments: dict[str, Any]


def parse_assist(
    arguments: dict[str, Any],
    *,
    failures: Sequence[Trace],
    trajectory_ids: dict[str, str],
    reference: Reference,
    goal: str,
) -> AssistDesign:
    """Validate a ``diagnose_and_propose_assistance`` call: diagnoses as ``parse_refalign``;
    each family must be an easier_with_d template that loads and survives the LLM-free smoke at
    d = 1, is the identity at d = 0, and passes the structural privilege check; at most two;
    nothing is repaired."""
    diag = parse_refalign(
        {"diagnoses": arguments.get("diagnoses") or [], "stages": []},
        failures=failures,
        trajectory_ids=trajectory_ids,
        reference=reference,
    )
    out = AssistDesign(diag.diagnoses, [], list(diag.rejected), dict(arguments))
    for raw in list(arguments.get("families") or [])[:MAX_PROPOSALS]:
        if not isinstance(raw, dict):
            out.rejected.append("family entry is not an object")
            continue
        name = re.sub(r"[^a-z0-9_]", "_", str(raw.get("name") or "assist_family").lower())[:40]
        template = str(raw.get("rules_code") or "")
        if str(raw.get("direction") or "") != "easier_with_d":
            out.rejected.append(f"{name}: direction must be easier_with_d")
            continue
        report = validate_rules_template(template)
        if not report.ok:
            out.rejected.append(f"{name}: " + "; ".join(report.reasons))
            continue
        zero = identity_at_zero(template)
        if zero:
            out.rejected.append(f"{name}: " + "; ".join(zero))
            continue
        priv = privilege_check(template, reference=reference, failures=failures, goal=goal)
        if priv:
            out.rejected.append(f"{name}: privilege: " + "; ".join(priv))
            continue
        axis = raw.get("axis")
        if axis not in ("O", "T", "A"):
            out.rejected.append(f"{name}: axis must be O, T or A")
            continue
        if any(f.name == name for f in out.families):
            out.rejected.append(f"{name}: duplicate name")
            continue
        out.families.append(
            AssistFamily(
                name,
                axis,
                template,
                str(raw.get("mechanism_summary") or "").strip(),
                str(raw.get("why") or "").strip(),
            )
        )
    return out


def design_low_assist(
    complete: Callable[[ChatRequest], Any],
    *,
    model: str,
    evidence: Evidence,
    failures: Sequence[Trace],
    reference: Reference,
    goal: str,
    attribution: Any,
    seed: int,
) -> AssistDesign:
    """One LOW designer call under llm_v1_assistive_rules (ledgered as budget=designer)."""
    response = complete(
        ChatRequest(
            model=model,
            messages=assist_messages(evidence),
            temperature=0.7,
            seed=seed,
            max_tokens=6144,
            attribution=attribution,
            tools=(DESIGN_ASSIST_TOOL,),
            tool_choice={
                "type": "function",
                "function": {"name": "diagnose_and_propose_assistance"},
            },
        )
    )
    args = _tool_arguments(response)
    if args is None:
        return AssistDesign([], [], ["designer returned no tool call"], {})
    return parse_assist(
        args,
        failures=failures,
        trajectory_ids=evidence.trajectory_ids,
        reference=reference,
        goal=goal,
    )


# ---------------------------------------------------------------------------- the calls
def _tool_arguments(response: Any) -> dict[str, Any] | None:
    if not response.tool_calls:
        return None
    args = response.tool_calls[0].arguments
    if isinstance(args, str):
        args = json.loads(args)
    return dict(args)


def design_high(
    complete: Callable[[ChatRequest], Any],
    *,
    model: str,
    evidence: Evidence,
    attribution: Any,
    seed: int,
) -> HighDesign:
    """One HIGH designer call (ledgered as budget=designer, never charged to the cap)."""
    response = complete(
        ChatRequest(
            model=model,
            messages=high_messages(evidence),
            temperature=0.7,
            seed=seed,
            max_tokens=4096,
            attribution=attribution,
            tools=(DESIGN_HIGH_TOOL,),
            tool_choice={"type": "function", "function": {"name": "propose_interventions"}},
        )
    )
    args = _tool_arguments(response)
    if args is None:
        return HighDesign([], {}, ["designer returned no tool call"], {})
    return parse_high(args)


def design_low(
    complete: Callable[[ChatRequest], Any],
    *,
    model: str,
    evidence: Evidence,
    failures: Sequence[Trace],
    reference: Reference | None,
    attribution: Any,
    seed: int,
) -> LowDesign:
    """One LOW designer call (ledgered as budget=designer, never charged to the cap)."""
    response = complete(
        ChatRequest(
            model=model,
            messages=low_messages(evidence),
            temperature=0.7,
            seed=seed,
            max_tokens=2048,
            attribution=attribution,
            tools=(DESIGN_LOW_TOOL,),
            tool_choice={"type": "function", "function": {"name": "select_stages"}},
        )
    )
    args = _tool_arguments(response)
    if args is None:
        return LowDesign([], ["designer returned no tool call"], {})
    return parse_low(
        args, failures=failures, trajectory_ids=evidence.trajectory_ids, reference=reference
    )
