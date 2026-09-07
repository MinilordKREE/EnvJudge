"""Dose contract, exemplar knobs and the few-shot proposer (spec section 3).

A knob is ``make(d) -> Candidate`` (rules code or a Setup action list) with an ``axis``,
``direction = harder_with_d`` and a ``nested`` declaration (d1 < d2 => M(d1) subset of M(d2)). The
three
exemplars are runnable knobs AND the few-shot text (``aea.exemplars``). Designer proposals are
validated before any rollout: the code loads through the released ``code_loader``
(``envharness/core/code_loader.py:68-107``), references ``DOSE``, passes an LLM-free smoke at d=1
on a fake inner env, and (unless O-axis) is certified at d=1 by the expert x3. The designer never
decides acceptance — the dose rule does (section 4).

References: ``harness_agent.py:124-198`` (the released ``propose_candidate`` tool schema; ours
mirrors its field names), ``rules.py:93-104`` (hook signatures). Pilot oracles:
docs/pilots/e1pilot/e1/operators/{o_footer,h_horizon,s0_displace}.py. Chain / Link are out of v1.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from envharness.core.code_loader import RulesCodeError, load_rules_subclass
from envharness.core.types import Action, Candidate, EnvResponse, Observation

from aea import exemplars
from aea.llm.types import ChatMessage, ChatRequest

type Axis = Literal["O", "T", "S0", "A"]
type Source = Literal["exemplar", "llm"]


@dataclass(frozen=True)
class KnobContext:
    """Per-task facts a knob may need: id, successful episode lengths, a Setup builder for S0."""

    task_id: str
    success_lengths: tuple[int, ...] = ()
    setup_builder: Callable[[float], list[str] | None] | None = None
    """S0 knobs: returns the validated action list for dose d (None = infeasible)."""


class Knob(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def axis(self) -> Axis: ...
    @property
    def source(self) -> Source: ...
    @property
    def nested(self) -> bool: ...

    def make(self, d: float, ctx: KnobContext) -> Candidate | None: ...


def footer_bucket(task_id: str, step: int) -> int:
    return int(hashlib.sha256(f"{task_id}:{step}".encode()).hexdigest()[:8], 16) % 10000


def footer_masked(task_id: str, step: int, d: float) -> bool:
    return footer_bucket(task_id, step) < int(d * 10000)


def horizon_m(success_lengths: Sequence[int], d: float) -> int | None:
    """m(d) = the (1 - d) quantile (nearest rank) of success lengths: d=0 longest, d=1 shortest."""
    if not success_lengths:
        return None
    lengths = sorted(success_lengths)
    q = 1.0 - d
    rank = max(1, math.ceil(q * len(lengths)))
    return lengths[min(rank, len(lengths)) - 1]


@dataclass(frozen=True)
class FooterMask:
    name: str = "footer_mask"
    axis: Axis = "O"
    source: Source = "exemplar"
    nested: bool = True

    def make(self, d: float, ctx: KnobContext) -> Candidate | None:
        code = exemplars.render("footer_mask", dose=float(d), task_id=str(ctx.task_id))
        return Candidate(rules_code=code, rationale=f"footer_mask d={d}")


@dataclass(frozen=True)
class HorizonSqueeze:
    name: str = "horizon_squeeze"
    axis: Axis = "T"
    source: Source = "exemplar"
    nested: bool = True

    def make(self, d: float, ctx: KnobContext) -> Candidate | None:
        m = horizon_m(ctx.success_lengths, d)
        if m is None:
            return None
        code = exemplars.render("horizon_squeeze", dose=float(d), m=int(m))
        return Candidate(rules_code=code, rationale=f"horizon_squeeze d={d} m={m}")


@dataclass(frozen=True)
class Displacement:
    name: str = "displacement"
    axis: Axis = "S0"
    source: Source = "exemplar"
    nested: bool = True

    def make(self, d: float, ctx: KnobContext) -> Candidate | None:
        if ctx.setup_builder is None:
            return None
        actions = ctx.setup_builder(d)
        if not actions:
            return None
        return Candidate(
            in_env_actions=[Action(name="do", kwargs={"text": a}) for a in actions],
            rationale=f"displacement d={d} k={displacement_k(d)}",
        )


def displacement_k(d: float) -> int:
    """d ∈ (0, 1] -> k ∈ {1, 2, 3} (thirds)."""
    return max(1, min(3, math.ceil(d * 3 - 1e-9)))


EXEMPLARS: tuple[Knob, ...] = (FooterMask(), HorizonSqueeze(), Displacement())


@dataclass(frozen=True)
class ProposedKnob:
    """A designer-proposed Rules subclass with a ``DOSE`` class attribute (``__DOSE__``
    placeholder)."""

    name: str
    axis: Axis
    template: str
    nested: bool
    direction: str = "harder_with_d"
    source: Source = "llm"

    def make(self, d: float, ctx: KnobContext) -> Candidate | None:
        code = self.template.replace("__DOSE__", repr(float(d))).replace(
            "__TASK_ID__", repr(str(ctx.task_id))
        )
        return Candidate(rules_code=code, rationale=f"{self.name} d={d}")


@dataclass
class ValidationReport:
    ok: bool
    reasons: list[str] = field(default_factory=list)


class _SmokeInner:
    """Minimal inner env for the LLM-free smoke: one observation, one transition."""

    class _State:
        step_count = 1
        won = False
        admissible_commands = ["look", "go to a"]
        obs_text = "You see a room."
        extras: dict[str, Any] = {}

    def __init__(self) -> None:
        self.state = self._State()

    def get_env_state(self) -> Any:
        return self.state

    def observe(self) -> Observation:
        return Observation(
            text="You see a room.\n\nAdmissible commands: look, go to a",
            data={"admissible_commands": ["look", "go to a"]},
        )

    def step(self, action: Action) -> EnvResponse:
        return EnvResponse(
            observation=self.observe(),
            reward=0.0,
            terminated=False,
            truncated=False,
            info={"success": None, "effective": True},
        )


def validate_rules_template(template: str, *, task_id: str = "0") -> ValidationReport:
    """Loads via code_loader, references DOSE, LLM-free smoke at d = 1 through the three hooks."""
    reasons: list[str] = []
    if "DOSE" not in template:
        reasons.append("source does not reference DOSE")
    code = template.replace("__DOSE__", "1.0").replace("__TASK_ID__", repr(task_id))
    try:
        cls = load_rules_subclass(code)
    except RulesCodeError as exc:
        return ValidationReport(False, [*reasons, f"code_loader: {exc}"])
    try:
        inst = cls(inner=_SmokeInner())
        state = inst.inner.get_env_state()
        act = inst.filter_action(Action(name="do", kwargs={"text": "look"}), state)
        raw = inst.inner.step(Action(name="do", kwargs={"text": "look"}))
        out = inst.modify_transition(
            act if isinstance(act, Action) else Action(name="do", kwargs={"text": "look"}),
            raw,
            state,
        )
        obs = inst.filter_observation(out.observation, state)
        if not isinstance(obs, Observation) or not isinstance(out, EnvResponse):
            reasons.append("hooks must return Observation / EnvResponse")
    except Exception as exc:
        reasons.append(f"smoke at d=1 raised {type(exc).__name__}: {exc}")
    return ValidationReport(not reasons, reasons)


PROPOSE_KNOBS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "propose_knobs",
        "description": "Propose up to two dose-parameterised Rules subclasses for this task.",
        "parameters": {
            "type": "object",
            "properties": {
                "knobs": {
                    "type": "array",
                    "maxItems": 2,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "axis": {"type": "string", "enum": ["O", "T", "A"]},
                            "rules_code": {
                                "type": "string",
                                "description": (
                                    "class _Rules(Rules) with a DOSE class attribute "
                                    "set to __DOSE__"
                                ),
                            },
                            "nested": {"type": "boolean"},
                            "direction": {"type": "string", "enum": ["harder_with_d"]},
                        },
                        "required": ["name", "axis", "rules_code", "nested"],
                    },
                },
                "ranking": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "family names, most promising first (exemplars may be included)",
                },
            },
            "required": ["knobs"],
        },
    },
}

CONTRACT_TEXT = (
    "Dose contract: emit `class _Rules(Rules)` with a class attribute `DOSE = __DOSE__` "
    "(d in [0, 1]); "
    "difficulty must increase with DOSE (direction harder_with_d); prefer nested perturbations "
    "(d1 < d2 => the perturbed step set at d1 is a subset of the set at d2); the task must stay "
    "solvable at DOSE = 1; only the names Rules, Action, Blocked, Observation, EnvResponse and the "
    "standard library are available; no Chain/Link. Acceptance is decided by rollouts, not by you."
)


def proposer_messages(task_description: str, success_summary: str) -> tuple[ChatMessage, ...]:
    shots = "\n\n".join(
        f"### {n}\n{exemplars.prompt_text(n)}"
        for n in ("footer_mask", "horizon_squeeze", "displacement")
    )
    return (
        ChatMessage(
            role="system",
            content="You design environment perturbations under a strict contract.\n"
            + CONTRACT_TEXT,
        ),
        ChatMessage(
            role="user",
            content=(
                f"Task: {task_description}\n\nPolicy successes (summary):\n{success_summary}"
                f"\n\nExemplars:\n{shots}\n\nCall propose_knobs."
            ),
        ),
    )


def parse_proposals(
    arguments: dict[str, Any], *, max_families: int
) -> tuple[list[ProposedKnob], list[str]]:
    """Validate a `propose_knobs` tool call; returns (accepted knobs, rejection reasons)."""
    accepted: list[ProposedKnob] = []
    rejected: list[str] = []
    for raw in list(arguments.get("knobs") or [])[:max_families]:
        if not isinstance(raw, dict):
            rejected.append("knob entry is not an object")
            continue
        template = str(raw.get("rules_code") or "")
        report = validate_rules_template(template)
        name = str(raw.get("name") or "llm_knob")
        if not report.ok:
            rejected.append(f"{name}: " + "; ".join(report.reasons))
            continue
        axis = raw.get("axis")
        if axis not in ("O", "T", "A"):
            rejected.append(f"{name}: axis must be O, T or A")
            continue
        accepted.append(
            ProposedKnob(
                name=name, axis=axis, template=template, nested=bool(raw.get("nested", False))
            )
        )
    ranking = [str(x) for x in (arguments.get("ranking") or [])]
    ordered = sorted(
        accepted, key=lambda k: ranking.index(k.name) if k.name in ranking else len(ranking)
    )
    return ordered, rejected


def propose_knobs(
    complete: Callable[[ChatRequest], Any],
    *,
    model: str,
    task_description: str,
    success_summary: str,
    max_families: int,
    attribution: Any,
    seed: int = 0,
) -> tuple[list[ProposedKnob], list[str], list[str]]:
    """One designer call (free of the rollout budget, ledgered as budget=designer)."""
    request = ChatRequest(
        model=model,
        messages=proposer_messages(task_description, success_summary),
        temperature=0.7,
        seed=seed,
        max_tokens=4096,
        attribution=attribution,
        tools=(PROPOSE_KNOBS_TOOL,),
        tool_choice={"type": "function", "function": {"name": "propose_knobs"}},
    )
    response = complete(request)
    if not response.tool_calls:
        return [], ["designer returned no tool call"], []
    args = response.tool_calls[0].arguments
    if isinstance(args, str):
        args = json.loads(args)
    knobs, rejected = parse_proposals(dict(args), max_families=max_families)
    return knobs, rejected, [str(x) for x in (dict(args).get("ranking") or [])]


def order_families(proposed: Sequence[Knob], ranking: Sequence[str]) -> list[Knob]:
    """Designer-proposed U exemplars in the designer's ranking; exemplars first if it is silent."""
    pool: list[Knob] = [*proposed, *EXEMPLARS]
    if not ranking:
        return [*EXEMPLARS, *proposed]
    return sorted(pool, key=lambda k: ranking.index(k.name) if k.name in ranking else len(ranking))
