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

from envharness.core.types import Trace

from aea import exemplars
from aea.families import LIBRARY_NAMES, ProposedFamily, _is_library_copy, validate_rules_template
from aea.llm.types import ChatMessage, ChatRequest
from aea.session import SESSION_LOCK, Session, run_expert

MAX_PROPOSALS = 2
REFERENCE_ID = "reference"


# ---------------------------------------------------------------------------- reference
@dataclass(frozen=True)
class Reference:
    ok: bool
    reason: str
    actions: tuple[str, ...] = ()

    @property
    def n_steps(self) -> int:
        return len(self.actions)


class ReferenceProvider(Protocol):
    """Privileged reference for one task: a successful action list from the reset state, or
    ``ok=False`` with the reason (expert error, stuck, timeout, no success). Never charged."""

    def __call__(self, task_id: str) -> Reference: ...


@dataclass
class ExpertReference:
    """The benchmark expert from reset, through a locked in-process session (``run_expert``)."""

    open_fn: Callable[[str], Session]
    max_steps: int

    def __call__(self, task_id: str) -> Reference:
        with SESSION_LOCK:
            sess: Session | None = None
            try:
                sess = self.open_fn(task_id)
                r = run_expert(sess, max_steps=self.max_steps)
            except Exception as exc:  # the expert must never take the task down
                return Reference(False, f"{type(exc).__name__}: {exc}")
            finally:
                if sess is not None:
                    sess.close()
        return Reference(r.ok, r.reason, tuple(r.actions) if r.ok else ())


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
    raw = step.policy_raw_response
    if not raw:
        return None
    m = re.search(r"<think>(.*?)</think>", raw, re.S)
    return _clip(m.group(1) if m else raw, n)


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


def serialize_low(
    failures: Sequence[Trace],
    p_hat: float,
    n: int,
    reference: Reference | None,
    b: EvidenceBounds = BOUNDS,
) -> Evidence:
    ids = {f"F{i + 1}": t.episode_id for i, t in enumerate(failures)}
    parts = [
        f"TASK GOAL: {task_goal(failures)}",
        f"REGIME: LOW (zero)\np_hat: {p_hat:.3f}\nn: {n}",
        "FAILED CURRENT-POLICY TRAJECTORIES (selectable: trajectory_id F1.., step 1..length)",
        *[trajectory_text(label, t, b) for label, t in zip(ids, failures, strict=True)],
    ]
    used = reference is not None and reference.ok
    if used and reference is not None:
        block = "PRIVILEGED REFERENCE (a successful action sequence from reset; selectable: "
        block += f"trajectory_id {REFERENCE_ID}, step 1..{reference.n_steps})\n"
        block += "\n".join(f"step {i + 1}: {a}" for i, a in enumerate(reference.actions))
        meta = (
            f"PRIVILEGED REFERENCE: {reference.n_steps} actions, "
            f"sha256 {_sha(json.dumps(list(reference.actions)))[:16]} [content withheld]"
        )
        text = _bounded([*parts, block], b.total_chars)
        redacted = _bounded([*parts, meta], b.total_chars)
    else:
        text = _bounded(parts, b.total_chars)
        redacted = text
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
            + HIGH_CONTRACT,
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
