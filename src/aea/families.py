"""Families for the harden operator (docs/spec/AEA_v0.2.md, "Families and leverage").

A family is a parameterized wrapper ``w(d)``, d in [0, 1], harder with d: ``make(d, ctx)`` returns
the ``Candidate`` (rules code) or None when infeasible. The library holds the two exemplars
(FooterMask, O axis; HorizonSqueeze, T axis); the LLM proposer returns up to ``impl.proposer_cap``
new families per task under the dose contract, validated before any rollout (loads through the
released ``code_loader``, references DOSE, passes an LLM-free smoke at d = 1). The proposer never
decides acceptance. ``LeverageTable`` keeps one counter per family — the rate, over the tasks where
it was evaluated at d = 1, of not returning ``no_effect`` — orders families by it (proposer order
until a family has been seen) and yields the bracket start dose of a family with rate >=
``impl.prior_min_rate`` over >= ``impl.prior_min_tasks`` tasks (its last accepted dose).

References: ``harness_agent.py:124-198`` (the released ``propose_candidate`` tool schema; ours
mirrors its field names), ``rules.py:93-104`` (hook signatures), ``code_loader.py:68-107``.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from envharness.core.code_loader import RulesCodeError, load_rules_subclass
from envharness.core.types import Action, Candidate, EnvResponse, Observation

from aea import exemplars
from aea.llm.types import ChatMessage, ChatRequest

type Axis = Literal["O", "T", "A"]
type Source = Literal["library", "llm"]


@dataclass(frozen=True)
class FamilyContext:
    task_id: str
    success_lengths: tuple[int, ...] = ()


class Family(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def axis(self) -> Axis: ...
    @property
    def source(self) -> Source: ...

    def make(self, d: float, ctx: FamilyContext) -> Candidate | None: ...


# ---------------------------------------------------------------------------- library
def footer_bucket(task_id: str, step: int) -> int:
    return int(hashlib.sha256(f"{task_id}:{step}".encode()).hexdigest()[:8], 16) % 10000


def footer_masked(task_id: str, step: int, d: float) -> bool:
    return footer_bucket(task_id, step) < int(d * 10000)


def horizon_m(success_lengths: Sequence[int], d: float) -> int | None:
    """m(d) = the (1 - d) quantile (nearest rank) of success lengths: d=0 longest, d=1 shortest."""
    if not success_lengths:
        return None
    lengths = sorted(success_lengths)
    rank = max(1, math.ceil((1.0 - d) * len(lengths)))
    return lengths[min(rank, len(lengths)) - 1]


@dataclass(frozen=True)
class FooterMask:
    name: str = "footer_mask"
    axis: Axis = "O"
    source: Source = "library"

    def make(self, d: float, ctx: FamilyContext) -> Candidate | None:
        code = exemplars.render("footer_mask", dose=float(d), task_id=str(ctx.task_id))
        return Candidate(rules_code=code, rationale=f"footer_mask d={d}")


@dataclass(frozen=True)
class HorizonSqueeze:
    name: str = "horizon_squeeze"
    axis: Axis = "T"
    source: Source = "library"

    def make(self, d: float, ctx: FamilyContext) -> Candidate | None:
        m = horizon_m(ctx.success_lengths, d)
        if m is None:
            return None
        code = exemplars.render("horizon_squeeze", dose=float(d), m=int(m))
        return Candidate(rules_code=code, rationale=f"horizon_squeeze d={d} m={m}")


LIBRARY: tuple[Family, ...] = (FooterMask(), HorizonSqueeze())
LIBRARY_NAMES = ("footer_mask", "horizon_squeeze")


# ---------------------------------------------------------------------------- proposer
@dataclass(frozen=True)
class ProposedFamily:
    """A proposer-written Rules subclass with a ``DOSE`` class attribute (``__DOSE__``)."""

    name: str
    axis: Axis
    template: str
    source: Source = "llm"

    def make(self, d: float, ctx: FamilyContext) -> Candidate | None:
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


PROPOSE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "propose_families",
        "description": "Propose up to two dose-parameterised Rules subclasses for this task.",
        "parameters": {
            "type": "object",
            "properties": {
                "families": {
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
                        },
                        "required": ["name", "axis", "rules_code"],
                    },
                },
                "ranking": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "family names, most promising first (library names allowed)",
                },
            },
            "required": ["families"],
        },
    },
}

CONTRACT_TEXT = (
    "Dose contract: emit `class _Rules(Rules)` with a class attribute `DOSE = __DOSE__` "
    "(d in [0, 1]); difficulty must increase with DOSE; the task must stay solvable at DOSE = 1; "
    "only the names Rules, Action, Blocked, Observation, EnvResponse and the standard library are "
    "available; no Chain/Link. Acceptance is decided by rollouts, not by you. The library families "
    "are ALWAYS tried by the controller: do not re-propose them or trivial variants; propose NEW "
    "perturbation families for this task (or none)."
)


def proposer_messages(task_description: str, success_summary: str) -> tuple[ChatMessage, ...]:
    shots = "\n\n".join(f"### {n}\n{exemplars.prompt_text(n)}" for n in LIBRARY_NAMES)
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
                f"\n\nLibrary (few-shot):\n{shots}\n\nCall propose_families."
            ),
        ),
    )


def _is_library_copy(name: str, template: str) -> bool:
    if name in LIBRARY_NAMES:
        return True
    body = "".join(template.split())
    return any("".join(exemplars.prompt_text(n).split())[:400] in body for n in LIBRARY_NAMES)


def parse_proposals(
    arguments: dict[str, Any], *, cap: int
) -> tuple[list[ProposedFamily], list[str]]:
    """Validate a ``propose_families`` tool call; returns (accepted, rejection reasons)."""
    accepted: list[ProposedFamily] = []
    rejected: list[str] = []
    for raw in list(arguments.get("families") or arguments.get("knobs") or [])[:cap]:
        if not isinstance(raw, dict):
            rejected.append("family entry is not an object")
            continue
        template = str(raw.get("rules_code") or "")
        name = str(raw.get("name") or "llm_family")
        if _is_library_copy(name, template):
            rejected.append(f"{name}: duplicate of a library family (always tried anyway)")
            continue
        report = validate_rules_template(template)
        if not report.ok:
            rejected.append(f"{name}: " + "; ".join(report.reasons))
            continue
        axis = raw.get("axis")
        if axis not in ("O", "T", "A"):
            rejected.append(f"{name}: axis must be O, T or A")
            continue
        accepted.append(ProposedFamily(name=name, axis=axis, template=template))
    ranking = [str(x) for x in (arguments.get("ranking") or [])]
    return (
        sorted(accepted, key=lambda k: ranking.index(k.name) if k.name in ranking else 99),
        rejected,
    )


def propose_families(
    complete: Callable[[ChatRequest], Any],
    *,
    model: str,
    task_description: str,
    success_summary: str,
    cap: int,
    attribution: Any,
    seed: int = 0,
    record: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[ProposedFamily], list[str], list[str]]:
    """One proposer call (ledgered as budget=designer, not charged to the cap)."""
    request = ChatRequest(
        model=model,
        messages=proposer_messages(task_description, success_summary),
        temperature=0.7,
        seed=seed,
        max_tokens=4096,
        attribution=attribution,
        tools=(PROPOSE_TOOL,),
        tool_choice={"type": "function", "function": {"name": "propose_families"}},
    )
    response = complete(request)
    if not response.tool_calls:
        if record is not None:
            record({"content": response.content[:2000], "tool_calls": [], "rejected": ["no call"]})
        return [], ["proposer returned no tool call"], []
    args = response.tool_calls[0].arguments
    if isinstance(args, str):
        args = json.loads(args)
    families, rejected = parse_proposals(dict(args), cap=cap)
    ranking = [str(x) for x in (dict(args).get("ranking") or [])]
    if record is not None:
        record(
            {
                "arguments": dict(args),
                "accepted": [k.name for k in families],
                "rejected": rejected,
                "ranking": ranking,
            }
        )
    return families, rejected, ranking


# ---------------------------------------------------------------------------- leverage
@dataclass
class FamilyStats:
    tested: int = 0
    with_leverage: int = 0
    last_accepted_dose: float | None = None

    @property
    def rate(self) -> float | None:
        return self.with_leverage / self.tested if self.tested else None


class LeverageTable:
    """One counter per family, shared across the tasks of a run (thread-safe)."""

    def __init__(self, *, min_tasks: int = 5, min_rate: float = 0.9) -> None:
        self.min_tasks = min_tasks
        self.min_rate = min_rate
        self._stats: dict[str, FamilyStats] = {}
        self._lock = threading.Lock()

    def stats(self, family: str) -> FamilyStats:
        with self._lock:
            return self._stats.setdefault(family, FamilyStats())

    def record_leverage(self, family: str, has_leverage: bool) -> None:
        s = self.stats(family)
        with self._lock:
            s.tested += 1
            s.with_leverage += int(has_leverage)

    def record_accepted(self, family: str, dose: float) -> None:
        s = self.stats(family)
        with self._lock:
            s.last_accepted_dose = dose

    def order(self, families: Sequence[Family]) -> list[Family]:
        """By leverage rate, descending; unseen families keep their given (proposer) order."""
        with self._lock:
            rates = {k: v.rate for k, v in self._stats.items()}

        def key(p: tuple[int, Family]) -> tuple[float, int]:
            rate = rates.get(p[1].name)
            return (-(rate if rate is not None else 1.0), p[0])

        return [f for _, f in sorted(enumerate(families), key=key)]

    def start_dose(self, family: str) -> float | None:
        """The family's last accepted dose when its leverage rate qualifies, else None
        (midpoint)."""
        s = self.stats(family)
        with self._lock:
            rate = s.rate
            if s.tested >= self.min_tasks and rate is not None and rate >= self.min_rate:
                return s.last_accepted_dose
            return None

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                k: {
                    "tested": v.tested,
                    "with_leverage": v.with_leverage,
                    "rate": v.rate,
                    "last_accepted_dose": v.last_accepted_dose,
                }
                for k, v in self._stats.items()
            }
