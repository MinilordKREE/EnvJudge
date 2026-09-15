"""Phase 3.5a oracle actuators (docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md): the registry
of hand-verified, non-privileged assistive Rules families, one per phase-3.4 task with a
verified reference. Three mechanism classes, one coverage-dose semantics, goal-derived constants
only. ``write()`` materialises the frozen dossier files under
``experiments/alfworld_e6/oracle_actuators/``; ``provider()`` is the experiment-side assist
provider injected into the phase-3.4 controller (the LLM designer call is replaced, nothing
downstream changes). Privileged experimental assistance: never a method result.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from envharness.core.types import Trace

from aea.designer import (
    AssistDesign,
    AssistFamily,
    Reference,
    identity_at_zero,
    privilege_check,
)
from aea.families import validate_rules_template

ROOT = Path(__file__).resolve().parents[1]
DOSSIER = ROOT / "experiments" / "alfworld_e6" / "oracle_actuators"
TASKS: tuple[str, ...] = ("85", "86", "92", "97", "99", "107", "109")

type Cls = Literal["S", "P", "G"]


@dataclass(frozen=True)
class Spec:
    """One hand-verified family: the goal-derived constants of a class template plus the
    auditable diagnosis (all text fields are the dossier record)."""

    task: str
    cls: Cls
    name: str
    goal: str
    obj: str  # goal object TYPE (a word of the goal text)
    bottleneck: str
    contrast: str
    need: str
    fields: str  # which constants / state fields the code uses and where they come from
    relation: str  # to the phase-3.4 generated proposal (descriptive only)
    complete: str = ""  # class P: regex of the goal-completing action text
    precond: str = ""  # class P: "held" | "cleaned"
    reason: str = ""  # class P: the block reason (goal words)
    steps: str = ""  # class G: the decomposition line (goal words)


# --------------------------------------------------------------------------- class templates
# Every template: DOSE = __DOSE__ (the controller substitutes the dose); DOSE = 0 is the identity
# on every hook; the support set grows with DOSE (coverage); per-episode memory in
# env_state.extras (released field) with an instance fallback; nothing moves objects, ends the
# episode or touches reward / success.

_COMMON = """
    def _mem(self, env_state):
        ex = getattr(env_state, "extras", None)
        if not isinstance(ex, dict):
            ex = self.__dict__.setdefault("_oracle_extras", {})
        return ex.setdefault("oracle_%s", %s)

    @staticmethod
    def _body(text):
        return text.split("\\n\\nAdmissible commands:")[0]

    @staticmethod
    def _covered(k, dose):
        return math.floor(k * dose + 1e-9) > math.floor((k - 1) * dose + 1e-9)
"""

TEMPLATE_S = '''# ruff: noqa
import math
import re


class _Rules(Rules):
    """Oracle actuator, class S (explored-receptacle pruning): while the goal object is not in
    hand, `go to R` is removed from the admissible commands for receptacles R whose contents the
    policy has ALREADY SEEN without the goal object. Dose = fraction of those receptacles
    pruned (earliest inspected first). At dose 0 every hook is the identity."""

    DOSE = __DOSE__
    OBJ = __OBJ__  # goal object type, from the goal text
%s
    def _update(self, text, mem):
        if "Welcome to TextWorld" in text:
            mem["inspected"] = []
            mem["held"] = False
        body = self._body(text)
        if re.search(r"You pick up the %%s \\d+" %% self.OBJ, body):
            mem["held"] = True
        elif re.search(r"You move the %%s \\d+ to" %% self.OBJ, body):
            mem["held"] = False
        elif "You are carrying: " in body:
            mem["held"] = bool(re.search(r"\\b%%s \\d+" %% self.OBJ, body))
        elif "You are not carrying anything" in body:
            mem["held"] = False
        m = re.search(r"(?:You arrive at|You open the) ([a-z]+ \\d+)\\.", body)
        if m and ", you see " in body:
            recep = m.group(1)
            listing = body.split(", you see ", 1)[1]
            if not re.search(r"\\b%%s \\d+" %% self.OBJ, listing) and recep not in mem["inspected"]:
                mem["inspected"].append(recep)

    def filter_observation(self, obs, env_state):
        mem = self._mem(env_state)
        self._update(obs.text, mem)
        if self.DOSE <= 0 or mem["held"]:
            return obs
        k = int(self.DOSE * len(mem["inspected"]) + 1e-9)
        pruned = set(mem["inspected"][:k])
        if not pruned:
            return obs
        cmds = list((obs.data or {}).get("admissible_commands") or [])
        kept = [c for c in cmds if not (c.startswith("go to ") and c[6:] in pruned)]
        if kept == cmds:
            return obs
        text = self._body(obs.text) + "\\n\\nAdmissible commands: " + ", ".join(kept)
        data = dict(obs.data or {})
        data["admissible_commands"] = kept
        return Observation(text=text, data=data)
'''

TEMPLATE_P = '''# ruff: noqa
import math
import re


class _Rules(Rules):
    """Oracle actuator, class P (precondition gating): the goal-completing action is rejected
    with a reason in goal words while its goal precondition does not hold (the goal object is
    not in hand / not yet in the required state). Dose = fraction of premature attempts
    blocked (evenly, in order). At dose 0 every hook is the identity."""

    DOSE = __DOSE__
    OBJ = __OBJ__  # goal object type, from the goal text
    COMPLETE = __COMPLETE__  # goal-completing action pattern, from the goal text
    PRECOND = __PRECOND__  # "held" or "cleaned"
    REASON = __REASON__
%s
    def _update(self, text, mem):
        if "Welcome to TextWorld" in text:
            mem["held"] = None
            mem["cleaned"] = []
            mem["attempts"] = 0
        body = self._body(text)
        m = re.search(r"You pick up the (%%s \\d+)" %% self.OBJ, body)
        if m:
            mem["held"] = m.group(1)
        elif re.search(r"You move the %%s \\d+ to" %% self.OBJ, body):
            mem["held"] = None
        elif "You are carrying: " in body:
            c = re.search(r"\\b(%%s \\d+)" %% self.OBJ, body)
            mem["held"] = c.group(1) if c else None
        elif "You are not carrying anything" in body:
            mem["held"] = None
        c = re.search(r"You clean the (%%s \\d+) using" %% self.OBJ, body)
        if c and c.group(1) not in mem["cleaned"]:
            mem["cleaned"].append(c.group(1))

    def _satisfied(self, mem, text):
        if self.PRECOND == "held":
            return mem["held"] is not None
        inst = re.search(r"\\b(%%s \\d+)" %% self.OBJ, text)
        return bool(inst) and inst.group(1) in mem["cleaned"]

    def filter_observation(self, obs, env_state):
        self._update(obs.text, self._mem(env_state))
        return obs

    def filter_action(self, action, env_state):
        if self.DOSE <= 0:
            return action
        text = str((action.kwargs or {}).get("text", "")).strip().lower()
        if not re.match(self.COMPLETE, text):
            return action
        mem = self._mem(env_state)
        if self._satisfied(mem, text):
            return action
        mem["attempts"] += 1
        if self._covered(mem["attempts"], self.DOSE):
            return Blocked(reason=self.REASON)
        return action
'''

TEMPLATE_G = '''# ruff: noqa
import math


class _Rules(Rules):
    """Oracle actuator, class G (goal-decomposition annotation): the observation carries one
    line spelling the goal as its sub-steps in goal words. Dose = fraction of observations
    annotated (evenly, in order). At dose 0 every hook is the identity."""

    DOSE = __DOSE__
    LINE = __STEPS__  # the goal decomposed, goal words + task-template knowledge
%s
    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        mem = self._mem(env_state)
        if "Welcome to TextWorld" in obs.text:
            mem["k"] = 0
        mem["k"] += 1
        if not self._covered(mem["k"], self.DOSE):
            return obs
        parts = obs.text.split("\\n\\nAdmissible commands:", 1)
        text = parts[0] + "\\n\\n" + self.LINE
        if len(parts) > 1:
            text += "\\n\\nAdmissible commands:" + parts[1]
        return Observation(text=text, data=dict(obs.data or {}))
'''


def render(spec: Spec) -> str:
    """The family template (with the ``__DOSE__`` placeholder) for a spec."""
    if spec.cls == "S":
        common = _COMMON % ("S", '{"inspected": [], "held": False}')
        return TEMPLATE_S.replace("__OBJ__", repr(spec.obj)) % common
    if spec.cls == "P":
        common = _COMMON % ("P", '{"held": None, "cleaned": [], "attempts": 0}')
        code = TEMPLATE_P % common
        return (
            code.replace("__OBJ__", repr(spec.obj))
            .replace("__COMPLETE__", repr(spec.complete))
            .replace("__PRECOND__", repr(spec.precond))
            .replace("__REASON__", repr(spec.reason))
        )
    common = _COMMON % ("G", '{"k": 0}')
    return (TEMPLATE_G % common).replace("__STEPS__", repr(spec.steps))


# --------------------------------------------------------------------------- the registry
# Diagnoses are written from the frozen phase-3.4 evidence only (goal, failed trajectories,
# verified reference); no phase-3.4 policy-response measurement selects a mechanism or a dose.

SPECS: tuple[Spec, ...] = (
    Spec(
        task="85",
        cls="S",
        name="explored_receptacle_pruning",
        goal="heat some tomato and put it in diningtable",
        obj="tomato",
        bottleneck=(
            "All 10 failures open the fridge first, then walk the 23 cabinets and the drawers "
            "(re-visiting the fridge 5-15 times); 9 of 10 never visit diningtable 1, the only "
            "surface holding a tomato; the one rollout that reaches it (F6, step 45) takes the "
            "tomato and runs out of steps."
        ),
        contrast=(
            "The reference inspects each receptacle once (sinkbasin, microwave, garbagecan, "
            "fridge), reaches diningtable 1 at step 10, takes the tomato and heats it in the "
            "microwave."
        ),
        need=(
            "Exploration memory: the policy keeps returning to receptacles whose contents it has "
            "already seen; support = removing already-inspected, tomato-free receptacles from "
            "the navigation choices while no tomato is in hand."
        ),
        fields=(
            "OBJ = 'tomato' (goal text); the policy's own observation text ('You arrive at R' / "
            "'You open the R' + ', you see <listing>', 'You pick up the tomato N', 'You move the "
            "tomato N to', inventory lines); data['admissible_commands'] (released field); "
            "env_state.extras (released per-episode store). No location, no reference action, "
            "no numbered instance constant."
        ),
        relation=(
            "different: the phase-3.4 proposal (highlight_target_receptacle, rejected on a "
            "positional pydantic constructor) intended to highlight the diningtable itself, "
            "which would name the object's location; pruning names only what the policy has "
            "seen."
        ),
    ),
    Spec(
        task="86",
        cls="G",
        name="goal_decomposition_annotation",
        goal="put a hot plate in countertop",
        obj="plate",
        bottleneck=(
            "All 10 failures open cabinets 1-26 and the drawers for 50 steps; every rollout "
            "visits countertop 1 and SEES 'a plate 1' among 11 objects there (step ~28) and "
            "never takes it; no rollout heats anything; 'hot plate' is never decomposed into "
            "plate -> heat -> place."
        ),
        contrast=(
            "The reference, after inspecting the appliances and drawers, takes plate 1 from "
            "countertop 1, heats it in the microwave and moves it to countertop 1."
        ),
        need=(
            "Goal decomposition: the policy does not map the goal wording to the object type it "
            "must pick up and the transformation it must apply; support = spelling the goal as "
            "its sub-steps in the observation."
        ),
        fields=(
            "LINE built from the goal words 'hot plate' / 'countertop' plus task-template "
            "knowledge that 'hot' means heated in the microwave (the ALFWorld pick_heat family); "
            "no location, no reference action, no numbered instance constant; "
            "env_state.extras for the coverage counter."
        ),
        relation=(
            "same idea as the phase-3.4 proposal goal_substep_reminder (observation-side "
            "sub-step reminder), realised here as a fixed line with coverage dose."
        ),
        steps=(
            "Goal steps: (1) find a plate and take it; (2) heat it in the microwave; "
            "(3) put it on a countertop."
        ),
    ),
    Spec(
        task="92",
        cls="P",
        name="precondition_gating",
        goal="look at cellphone under the desklamp",
        obj="cellphone",
        bottleneck=(
            "All 10 failures go to desk 1 at step 1, 'use desklamp 1' at step 2 (the lamp is "
            "there, the cellphone is not), then alternate look / examine desk 1 / use desklamp 1 "
            "for the remaining 48 steps; at most one drawer is ever opened; no rollout holds a "
            "cellphone."
        ),
        contrast=(
            "The reference searches the dressers, drawers, desks and beds, takes cellphone 1 "
            "from armchair 1 at step 46 and only then goes to desk 1 and uses the desklamp."
        ),
        need=(
            "The policy treats 'use desklamp' as the completing action regardless of what it "
            "holds; support = rejecting that action while no cellphone is in hand, with the "
            "goal precondition as the reason."
        ),
        fields=(
            "OBJ = 'cellphone', COMPLETE = 'use desklamp N' (goal text: look at X under the "
            "desklamp), PRECOND = held (goal semantics: X must be in hand), REASON in goal "
            "words; state from the policy's own observation text (pick up / move / inventory); "
            "env_state.extras. No location, no reference action, no numbered instance constant."
        ),
        relation=(
            "related: the phase-3.4 proposal surface_relevancy_hint removed 'use desklamp' "
            "from the admissible list and added a search reminder (O axis, two components); "
            "this family blocks the premature action with a stated precondition (A axis, one "
            "component)."
        ),
        complete=r"^use desklamp \d+$",
        precond="held",
        reason=(
            "The goal needs the cellphone in hand before using the desklamp: find a cellphone "
            "and take it first."
        ),
    ),
    Spec(
        task="97",
        cls="P",
        name="precondition_gating",
        goal="put a clean potato in garbagecan",
        obj="potato",
        bottleneck=(
            "All 10 failures take potato 1 from the fridge by step 4 and move it to the "
            "garbagecan by step 6 without cleaning it; 9 of 10 then loop take / move / "
            "inventory / examine garbagecan for ~45 steps; 2 rollouts pass the sinkbasin without "
            "using it; no rollout issues 'clean potato'."
        ),
        contrast=(
            "The reference takes the potato, goes to the sinkbasin, cleans it, then moves it to "
            "the garbagecan."
        ),
        need=(
            "The policy skips the required state change ('clean'); support = rejecting the "
            "placing action while the held potato has not been cleaned, with the missing step "
            "as the reason."
        ),
        fields=(
            "OBJ = 'potato', COMPLETE = 'move potato N to garbagecan N' (goal text: put ... in "
            "garbagecan), PRECOND = cleaned (goal word 'clean'), REASON in goal words plus "
            "task-template knowledge that cleaning happens at the sinkbasin; state from the "
            "policy's own observation text ('You clean the potato N using'); env_state.extras. "
            "No location, no reference action, no numbered instance constant."
        ),
        relation=(
            "related: the phase-3.4 proposals (clean_before_place_reminder, "
            "clean_first_highlight) surfaced the clean command in the observation (O axis); "
            "this family gates the premature placement (A axis)."
        ),
        complete=r"^move potato \d+ to garbagecan \d+$",
        precond="cleaned",
        reason=(
            "The goal needs a CLEAN potato: clean it (at the sinkbasin) before putting it in the "
            "garbagecan."
        ),
    ),
    Spec(
        task="99",
        cls="P",
        name="precondition_gating",
        goal="look at pillow under the desklamp",
        obj="pillow",
        bottleneck=(
            "All 10 failures visit desk 1, desk 2, shelf 1, shelf 2, 'use desklamp 1' at step 7 "
            "and then 'look' 14-39 times in a row (a few re-visit shelf 3 and use the lamp "
            "again); bed 1, the only receptacle with a pillow, is never visited; no rollout "
            "holds a pillow."
        ),
        contrast=(
            "The reference goes to bed 1, takes pillow 1, goes to shelf 2 and uses the desklamp "
            "(6 steps)."
        ),
        need=(
            "Same as task 92: the completing action is issued without the object in hand and "
            "the policy then idles; support = rejecting 'use desklamp' while no pillow is in "
            "hand, with the precondition as the reason."
        ),
        fields=(
            "OBJ = 'pillow', COMPLETE = 'use desklamp N', PRECOND = held, REASON in goal "
            "words; state from the policy's own observation text; env_state.extras. No "
            "location (bed 1 is never named), no reference action, no numbered instance "
            "constant."
        ),
        relation=(
            "different: the phase-3.4 proposal surface_pillow_subgoal embedded the reference "
            "action 'go to bed 1' and the reference-only constant 'pillow 1' and was rejected; "
            "this family names neither."
        ),
        complete=r"^use desklamp \d+$",
        precond="held",
        reason=(
            "The goal needs the pillow in hand before using the desklamp: find a pillow and "
            "take it first."
        ),
    ),
    Spec(
        task="107",
        cls="P",
        name="precondition_gating",
        goal="look at newspaper under the desklamp",
        obj="newspaper",
        bottleneck=(
            "All 10 failures go to sidetable 1 (the desklamp's sidetable) at step 1, use the "
            "desklamp by step 2-12 and then alternate examine sidetable 1 / look / use desklamp "
            "1 for the rest of the episode; sidetables 2-5 are never visited; no rollout holds "
            "a newspaper."
        ),
        contrast=(
            "The reference visits the sofa and sidetables 1-3, takes newspaper 1 from sidetable "
            "3, returns to sidetable 1 and uses the desklamp (8 steps)."
        ),
        need=(
            "Same as tasks 92 / 99: premature completing action, then idling; support = "
            "rejecting 'use desklamp' while no newspaper is in hand, with the precondition as "
            "the reason."
        ),
        fields=(
            "OBJ = 'newspaper', COMPLETE = 'use desklamp N', PRECOND = held, REASON in goal "
            "words; state from the policy's own observation text; env_state.extras. No "
            "location (sidetable 3 is never named), no reference action, no numbered instance "
            "constant."
        ),
        relation=(
            "different: the phase-3.4 proposals (goal_substep_reminder, "
            "explore_sidetables_salience) added observation-side reminders / reordering; this "
            "family gates the premature action."
        ),
        complete=r"^use desklamp \d+$",
        precond="held",
        reason=(
            "The goal needs the newspaper in hand before using the desklamp: find a newspaper "
            "and take it first."
        ),
    ),
    Spec(
        task="109",
        cls="S",
        name="explored_receptacle_pruning",
        goal="cool some lettuce and put it in garbagecan",
        obj="lettuce",
        bottleneck=(
            "All 10 failures open the fridge at step 2 and then alternate fridge / cabinet N / "
            "examine fridge for 50 steps (the fridge is re-visited 15-25 times per rollout); "
            "sinkbasin 1, the surface holding the lettuce, is reached by one rollout (F2, step "
            "46), which takes and cools the lettuce and runs out of steps."
        ),
        contrast=(
            "The reference goes to the sinkbasin, takes lettuce 3, cools it in the fridge and "
            "moves it to the garbagecan (7 steps)."
        ),
        need=(
            "Exploration memory (as task 85): the policy fixates on the appliance named by the "
            "transformation ('cool' -> fridge) and re-inspects it; support = removing "
            "already-inspected, lettuce-free receptacles from the navigation choices while no "
            "lettuce is in hand (the fridge returns once the lettuce is held)."
        ),
        fields=(
            "OBJ = 'lettuce' (goal text); the policy's own observation text; "
            "data['admissible_commands']; env_state.extras. No location, no reference action, "
            "no numbered instance constant (the reference's 'lettuce 3' never appears)."
        ),
        relation=(
            "different: the phase-3.4 proposals (highlight_lettuce_and_take, "
            "guide_lettuce_acquisition, both rejected on an undefined name) intended to "
            "highlight the lettuce and the take action; pruning names only what the policy "
            "has seen."
        ),
    ),
)

SPEC_BY_TASK: dict[str, Spec] = {s.task: s for s in SPECS}


def template_path(task: str) -> Path:
    return DOSSIER / f"{task}.rules.py"


def record_path(task: str) -> Path:
    return DOSSIER / f"{task}.md"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def render_record(spec: Spec, template: str) -> str:
    cls_name = {
        "S": "explored-receptacle pruning (O axis)",
        "P": "precondition gating (A axis)",
        "G": "goal-decomposition annotation (O axis)",
    }[spec.cls]
    dose = {
        "S": "fraction of the already-inspected, goal-free receptacles pruned from `go to` "
        "(earliest inspected first): d = 0 none, d = 1 all",
        "P": "fraction of the premature goal-completing attempts blocked, evenly in order "
        "(the k-th attempt iff floor(k d) > floor((k - 1) d)): d = 0 none, d = 1 all",
        "G": "fraction of the observations annotated, evenly in order: d = 0 none, d = 1 all",
    }[spec.cls]
    d1 = {
        "S": "every inspected goal-free receptacle is absent from `go to` while the goal object "
        "is not in hand; all choices return once it is held",
        "P": "every premature completing attempt is rejected with the stated precondition; "
        "the action passes once the precondition holds",
        "G": "every observation carries the decomposition line",
    }[spec.cls]
    lines = [
        f"# Oracle actuator record — task {spec.task}",
        "",
        "Privileged experimental assistance (phase 3.5a); not a method result.",
        "",
        "| field | value |",
        "| --- | --- |",
        f"| task id | {spec.task} |",
        f"| task goal | {spec.goal} |",
        f"| learner bottleneck | {spec.bottleneck} |",
        f"| reference-derived evidence | {spec.contrast} |",
        f"| missing capability / support need | {spec.need} |",
        f"| chosen environmental mechanism | {cls_name}: `{spec.name}` |",
        "| why Rules rather than Stage | the support acts on the policy's own choices "
        "(observation / action surface) at every step of the policy's own trajectory; a Stage "
        "prefix would replace the policy's search with the reference's actions |",
        f"| dose definition | {dose} |",
        "| d = 0 semantics | identity: every hook returns its input |",
        f"| d = 1 semantics | {d1} |",
        "| expected direction | easier_with_d (more support with d) |",
        f"| normal environment fields used | {spec.fields} |",
        "| privilege analysis | no numbered object instance, no location, no reference "
        "action, no verifier / reward / termination edit, no inner step, no Setup prefix; "
        "constants are goal-type words and task-template knowledge; state is parsed from the "
        "policy's own observations |",
        f"| relation to the phase-3.4 generated proposal | {spec.relation} |",
        "| offline validity checks | see `validation.json` (written by "
        "`scripts/e6_oracle_offline.py` before the freeze) |",
        f"| family source | `{spec.task}.rules.py`, sha256[:16] `{sha(template)}` |",
        "",
    ]
    return "\n".join(lines)


def families() -> dict[str, AssistFamily]:
    """The seven families from the registry (rendered in memory)."""
    out: dict[str, AssistFamily] = {}
    for spec in SPECS:
        out[spec.task] = AssistFamily(
            name=spec.name,
            axis="A" if spec.cls == "P" else "O",
            template=render(spec),
            mechanism_summary=f"class {spec.cls}: {spec.need}",
            why=spec.bottleneck,
            source="oracle",
        )
    return out


def frozen_families() -> dict[str, AssistFamily]:
    """The seven families read from the frozen dossier files (what the experiment uses)."""
    out: dict[str, AssistFamily] = {}
    for spec in SPECS:
        template = template_path(spec.task).read_text(encoding="utf-8")
        out[spec.task] = AssistFamily(
            name=spec.name,
            axis="A" if spec.cls == "P" else "O",
            template=template,
            mechanism_summary=f"class {spec.cls}: {spec.need}",
            why=spec.bottleneck,
            source="oracle",
        )
    return out


def validate(
    fam: AssistFamily,
    *,
    task: str,
    failures: Sequence[Trace],
    reference: Reference,
    goal: str,
) -> list[str]:
    """The phase-3.4 validation applied to a frozen family: loader + LLM-free smoke at d = 1,
    identity at d = 0, the structural privilege check."""
    reasons: list[str] = []
    rep = validate_rules_template(fam.template, task_id=task)
    if not rep.ok:
        reasons.extend(rep.reasons)
    reasons.extend(identity_at_zero(fam.template, task_id=task))
    reasons.extend(privilege_check(fam.template, reference=reference, failures=failures, goal=goal))
    return reasons


def provider(task: Any, failures: Sequence[Trace], reference: Reference, goal: str) -> AssistDesign:
    """The experiment-side assist provider: the frozen family of the task, validated exactly as
    a generated family would be; anything invalid is rejected (never repaired)."""
    fams = frozen_families()
    task_id = str(task.task_id)
    if task_id not in fams:
        return AssistDesign([], [], [f"NO_ORACLE_FAMILY: task {task_id}"], {"oracle": True})
    fam = fams[task_id]
    reasons = validate(fam, task=task_id, failures=failures, reference=reference, goal=goal)
    if reasons:
        return AssistDesign(
            [], [], [f"{fam.name}: " + "; ".join(reasons)], {"oracle": True, "task": task_id}
        )
    return AssistDesign(
        [], [fam], [], {"oracle": True, "task": task_id, "code_sha256": sha(fam.template)}
    )


def write() -> dict[str, str]:
    """Materialise the dossier (templates + records); returns task -> template sha."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for spec in SPECS:
        template = render(spec)
        template_path(spec.task).write_text(template, encoding="utf-8")
        record_path(spec.task).write_text(render_record(spec, template), encoding="utf-8")
        out[spec.task] = sha(template)
    (DOSSIER / "REGISTRY.json").write_text(
        json.dumps(
            {
                "tasks": list(TASKS),
                "specs": [asdict(s) for s in SPECS],
                "template_sha256_16": out,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return out


if __name__ == "__main__":
    print(json.dumps(write(), indent=1))
    sys.exit(0)
