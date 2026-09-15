"""Independent, offline semantic privilege screening for bounded ALFWorld surfaces.

This is an evidence-grounded *screen*, not a proof of non-interference.  It extracts
relations from ALFWorld observations/actions, compares them with the current learner's
raw evidence, and examines actual same-state hook deltas.  Unsupported changes fail
closed as UNCERTAIN.  Designer trajectories never enter the public fact set.

No model, network, policy rollout or simulator is invoked by this module.  PASS covers
only the supplied probes and the supported evidence grammar; the audit records that
scope explicitly.  The caller must collect probes before certification or measurement.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from aea.designer import Reference

SCREEN_VERSION = "alfworld-semantic-screen-v1"
type Decision = Literal["PASS", "FAIL", "UNCERTAIN"]


@dataclass(frozen=True)
class AuthorizedEvidence:
    """Trusted raw evidence for exactly one task, episode and prefix.

    ``observations`` excludes wrapper output and observations from other episodes.
    ``actions`` is the learner's observed prefix, not an expert or reference prefix.
    Admissible commands are the raw commands already displayed to this learner.
    The producer is responsible for provenance; strings cannot authenticate themselves.
    """

    task_id: str
    episode_id: str
    step: int
    goal: str
    observations: tuple[str, ...]
    actions: tuple[str, ...] = ()
    admissible_commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class SurfaceProbe:
    evidence: AuthorizedEvidence
    dose: float
    baseline: Mapping[str, Any]
    transformed: Mapping[str, Any]
    coverage: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class SemanticGateInput:
    source: str
    reference: Reference
    designer_evidence: str
    probes: tuple[SurfaceProbe, ...]
    task_id: str


@dataclass(frozen=True)
class Finding:
    decision: Decision
    information: str
    reference_evidence: tuple[str, ...]
    public_evidence_check: str
    candidate_evidence: tuple[str, ...]
    activation: str
    kind: str


@dataclass(frozen=True)
class SemanticGateResult:
    decision: Decision
    information: tuple[str, ...]
    reference_evidence: tuple[str, ...]
    public_evidence_check: tuple[str, ...]
    candidate_evidence: tuple[str, ...]
    activation: tuple[str, ...]
    findings: tuple[Finding, ...]
    version: str
    input_sha256: str
    source_sha256: str
    scope: str = "Supplied same-state probes; bounded ALFWorld grammar; no isolation guarantee."

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Fact:
    subject: str
    relation: str
    target: str
    evidence: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.subject, self.relation, self.target


_ENTITY = r"[a-z][a-z_-]*(?:\s+[0-9]+)?"
_ITEM = re.compile(r"\b(?:a|an|the)\s+(" + _ENTITY + r")\b", re.I)
_CONTENTS = re.compile(
    r"\b(?:on|in|inside|at)\s+(?:the\s+)?(" + _ENTITY + r"),?\s+you\s+see\s+([^.!\n]+)",
    re.I,
)
_LOCATED = re.compile(
    r"\b(?:a |an |the )?(" + _ENTITY + r")\s+(?:is\s+|was\s+)?"
    r"(?:on|in|inside|at|@)\s+(?:the\s+)?(" + _ENTITY + r")\b",
    re.I,
)
_TAKE = re.compile(
    r"\b(?:take|pick up)\s+(?:the\s+)?(" + _ENTITY + r")\s+from\s+"
    r"(?:the\s+)?(" + _ENTITY + r")\b",
    re.I,
)
_ACTION = re.compile(r"^(?:go to|take|put|use|open|close|examine|clean|heat|cool)\s+", re.I)
_GENERIC_WORDS_TEXT = (
    "a an the and or then before after first next now you your it its them they their goal "
    "task progress reminder remember hint support relevant available command commands action "
    "actions object objects target item items find search locate take pick up acquire hold "
    "held holding carry carrying have get obtain bring go to reach use using examine look at "
    "on in into from with for of by until need needs must should can may required "
    "prerequisite complete finish place put clean heat cool open close turn light under "
    "already observed seen known inventory explore room receptacle receptacles please is are "
    "be not yet has do done once if while check inspect navigate toward towards successfully "
    "forget which that this these those step steps subgoal subgoals prioritize focus select "
    "interact return start keep try only currently visible pickup "
)
_GENERIC_WORDS = frozenset(_GENERIC_WORDS_TEXT.split())


def _normal(text: str) -> str:
    return " ".join(text.lower().split())


def _kind(entity: str) -> str:
    return re.sub(r"\s+\d+$", "", _normal(entity))


def _mentions(text: str, entity: str) -> bool:
    # Number-less code ("go to sofa") can disclose a numbered reference entity.
    target_number = re.search(r"\d+$", entity)
    matches = re.finditer(r"\b" + re.escape(_kind(entity)) + r"\b(?:\s+(\d+))?", text.lower())
    return any(
        target_number is None or match[1] is None or match[1] == target_number[0]
        for match in matches
    )


def _facts(text: str, label: str) -> tuple[_Fact, ...]:
    facts: list[_Fact] = []
    # Negative statements never establish a positive public location.  This grammar
    # deliberately declines complex negation instead of laundering it into knowledge.
    text = ". ".join(
        sentence
        for sentence in re.split(r"[.!\n]", text)
        if not re.search(r"\b(?:not|no|nothing|cannot|can't|don't|doesn't|isn't)\b", sentence, re.I)
    )
    for match in _CONTENTS.finditer(text):
        location, contents = match.groups()
        for item in _ITEM.finditer(contents):
            facts.append(
                _Fact(_normal(item[1]), "located_at", _normal(location), label + ": " + match[0])
            )
    for pattern in (_LOCATED, _TAKE):
        for match in pattern.finditer(text):
            subject, target = map(_normal, match.groups())
            # Avoid interpreting prose such as "arrive at sofa" or "go to" as an object.
            if _kind(subject) in {"arrive", "arrived", "look", "looked", "you", "it", "go"}:
                continue
            facts.append(_Fact(subject, "located_at", target, label + ": " + match[0]))
    return tuple({fact.key: fact for fact in facts}.values())


def _matches(left: _Fact, right: _Fact) -> bool:
    def entity_matches(a: str, b: str) -> bool:
        # A public numbered entity does not authorize a different numbered instance.
        return a == b or (not re.search(r"\d", a + b) and _kind(a) == _kind(b))

    return (
        left.relation == right.relation
        and entity_matches(left.subject, right.subject)
        and entity_matches(left.target, right.target)
    )


def _discloses(reference: _Fact, disclosed: _Fact) -> bool:
    def compatible(a: str, b: str) -> bool:
        return a == b or (
            _kind(a) == _kind(b) and not (re.search(r"\d", a) and re.search(r"\d", b))
        )

    return (
        reference.relation == disclosed.relation
        and compatible(reference.subject, disclosed.subject)
        and compatible(reference.target, disclosed.target)
    )


def _without_goal_statements(text: str, goal: str = "") -> str:
    text = re.sub(
        r"(?:\bYour task is to\s*:|\bTask\s*:|\bGoal\s*:)[^.!\n]*",
        "",
        text,
        flags=re.I,
    )
    if goal:
        text = re.sub(re.escape(goal.strip().rstrip(".")), "", text, flags=re.I)
    return text


def _public_facts(evidence: AuthorizedEvidence) -> tuple[_Fact, ...]:
    # Goals describe intended end states even when repeated inside raw observations.
    facts = [
        fact
        for i, text in enumerate(evidence.observations)
        for fact in _facts(_without_goal_statements(text, evidence.goal), f"raw[{i}]")
    ]
    # A currently admissible TAKE-FROM reveals location; a PUT destination does not.
    facts.extend(
        fact
        for i, command in enumerate(evidence.admissible_commands)
        for match in _TAKE.finditer(command)
        for fact in _facts(match[0], f"raw.admissible_commands[{i}]")
    )
    return tuple(facts)


def _reference_facts(reference: Reference) -> tuple[_Fact, ...]:
    facts = [
        fact
        for step in reference.steps
        for fact in _facts(
            _without_goal_statements(step.observation), f"reference.step[{step.step}].observation"
        )
    ]
    facts.extend(
        fact
        for i, action in enumerate(reference.actions)
        for match in _TAKE.finditer(action)
        for fact in _facts(match[0], f"reference.actions[{i}]")
    )
    return tuple({fact.key: fact for fact in facts}.values())


def _flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            key: leaf
            for name, child in value.items()
            for key, leaf in _flatten(child, f"{path}.{name}" if path else str(name)).items()
        }
    # Command arrays must retain their ordering as a single surface.
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return {path: tuple(value)}
    if isinstance(value, (list, tuple)):
        return {
            key: leaf
            for index, child in enumerate(value)
            for key, leaf in _flatten(child, f"{path}[{index}]").items()
        }
    return {path: value}


def _addition(before: str, after: str) -> str:
    if before and before in after:
        return after.replace(before, "", 1).strip()
    old, new = before.split(), after.split()
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    return " ".join(
        " ".join(new[j:k])
        for operation, _, _, j, k in matcher.get_opcodes()
        if operation in {"insert", "replace"}
    )


def _prompt_without_commands(text: str) -> str:
    # Only the formatter's final admissible block; embedded observation text remains.
    matches = list(
        re.finditer(
            r"\n\nAdmissible actions: \[[^\n]*\]\."
            r"(?=\n\nReason about the current situation inside)",
            text,
        )
    )
    if not matches:
        return text
    match = matches[-1]
    return text[: match.start()] + text[match.end() :]


def _source_literals(source: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source.replace("__DOSE__", "1.0"))
    except SyntaxError:
        return ()
    return tuple(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _route_literals(source: str, reference: Reference) -> tuple[str, ...]:
    """Find an actual ordered literal container, not unordered string co-occurrence."""
    try:
        tree = ast.parse(source.replace("__DOSE__", "1.0"))
    except SyntaxError:
        return ()
    actions = tuple(map(_normal, reference.actions))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = _normal(node.value)
            for index in range(len(actions) - 1):
                first, second = actions[index : index + 2]
                if _ACTION.match(first) and _ACTION.match(second):
                    left, right = value.find(first), value.find(second)
                    if left >= 0 and right > left:
                        return first, second
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        values = tuple(
            _normal(child.value)
            for child in node.elts
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        )
        if len(values) != len(node.elts) or len(values) < 2:
            continue
        for start in range(len(values) - 1):
            first, second = values[start : start + 2]
            if not (_ACTION.match(first) and _ACTION.match(second)):
                continue
            for index in range(len(actions) - 1):
                if (first, second) == actions[index : index + 2]:
                    return values
    return ()


def _activation(probe: SurfaceProbe) -> str:
    evidence = probe.evidence
    return (
        f"task={evidence.task_id}; episode={evidence.episode_id}; step={evidence.step}; "
        f"dose={probe.dose:g}; hooks={','.join(probe.coverage)}"
    )


def _grounded_generic(text: str, evidence: AuthorizedEvidence) -> bool:
    """Conservative grammar for goal/prerequisite emphasis, without new assertions.

    Raw observation words are not a free vocabulary allowlist: merely seeing a sofa
    listed as a navigation destination does not license telling the learner to search it.
    """
    words = set(re.findall(r"[a-z][a-z_-]*", text.lower()))
    goal_words = set(re.findall(r"[a-z][a-z_-]*", evidence.goal.lower()))
    if not words <= _GENERIC_WORDS | goal_words:
        return False
    # Success, possession and completion assertions need their own observation grounding.
    if re.search(
        r"\b(?:you (?:have|hold|are carrying)|already (?:clean|heated|cooled)|"
        r"task (?:complete|done))\b",
        text,
        re.I,
    ):
        normalized = _normal(text)
        return any(normalized in _normal(obs) for obs in evidence.observations)
    return True


def _commands(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (tuple, list)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return None


def _changed_focus(before: tuple[str, ...], after: tuple[str, ...]) -> tuple[str, ...]:
    if before == after:
        return ()
    if set(before) == set(after) and tuple(sorted(before)) == after:
        return ()  # A fixed lexical ordering adds no task-specific preference.
    if set(after) < set(before):
        return after
    positions = {command: index for index, command in enumerate(before)}
    return tuple(
        command
        for index, command in enumerate(after)
        if command not in positions or index < positions[command]
    )


def _result(request: SemanticGateInput, findings: Sequence[Finding]) -> SemanticGateResult:
    items = tuple(findings)
    decision: Decision = (
        "FAIL"
        if any(item.decision == "FAIL" for item in items)
        else "UNCERTAIN"
        if any(item.decision == "UNCERTAIN" for item in items)
        else "PASS"
    )
    payload = json.dumps(asdict(request), sort_keys=True, ensure_ascii=False, default=str)
    return SemanticGateResult(
        decision=decision,
        information=tuple(item.information for item in items),
        reference_evidence=tuple(text for item in items for text in item.reference_evidence),
        public_evidence_check=tuple(item.public_evidence_check for item in items),
        candidate_evidence=tuple(text for item in items for text in item.candidate_evidence),
        activation=tuple(item.activation for item in items),
        findings=items,
        version=SCREEN_VERSION,
        input_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        source_sha256=hashlib.sha256(request.source.encode()).hexdigest(),
    )


def screen_semantic_privilege(request: SemanticGateInput) -> SemanticGateResult:
    """Screen executed surfaces using privileged facts and temporally scoped public evidence.

    FAIL is a concrete leak witness; UNCERTAIN is missing evidence, execution failure,
    an unsupported surface change, or a dormant reference-specific code dependency.
    Neither result admits a candidate to certification or a policy probe.
    """
    findings: list[Finding] = []

    def uncertain(
        reason: str, activation: str = "candidate", evidence: tuple[str, ...] = ()
    ) -> None:
        findings.append(
            Finding("UNCERTAIN", reason, (), "Not established", evidence, activation, "UNSUPPORTED")
        )

    if not request.probes:
        uncertain("No aligned learner-facing surface probes were supplied")
    if not request.reference.ok or not request.reference.steps:
        uncertain("A successful privileged reference with observations is required")
    try:
        ast.parse(request.source.replace("__DOSE__", "1.0"))
    except SyntaxError:
        uncertain("Candidate source is not parseable Python")
    reference_facts = _reference_facts(request.reference)
    route = _route_literals(request.source, request.reference)
    if route:
        findings.append(
            Finding(
                "FAIL",
                "An ordered reference action sequence is embedded in candidate code",
                tuple(
                    f"reference.actions[{i}]={action}"
                    for i, action in enumerate(request.reference.actions)
                ),
                "Public actions and goals do not authorize a privileged route sequence",
                (repr(route),),
                "candidate source; ordered literal container",
                "REFERENCE_ACTION",
            )
        )
    source_literals = _source_literals(request.source)
    activated_locations: set[str] = set()
    dormant_locations: dict[str, _Fact] = {}
    for probe in request.probes:
        public = probe.evidence
        activation = _activation(probe)
        if probe.error:
            uncertain("Surface execution failed: " + probe.error, activation)
        required_surfaces = {
            "final_prompt",
            "observation",
            "admissible_commands",
            "action",
            "feedback",
            "transition",
            "formatted_observation_history",
        }
        if not {"same_original_state", "policy_formatter"} <= set(probe.coverage):
            uncertain("Missing same-state execution or final policy formatter coverage", activation)
        if (
            not required_surfaces <= probe.baseline.keys()
            or not required_surfaces <= probe.transformed.keys()
        ):
            uncertain("Incomplete original/transformed learner-facing surfaces", activation)
        if (
            public.task_id != request.task_id
            or not public.episode_id
            or public.step < 0
            or not public.observations
            or len(public.observations) != public.step + 1
            or len(public.actions) != public.step
        ):
            uncertain("Missing or mismatched task/episode/step provenance", activation)
            continue
        if not 0 <= probe.dose <= 1:
            uncertain("Dose lies outside [0,1]", activation)
            continue
        public_facts = _public_facts(public)
        private = tuple(
            fact
            for fact in reference_facts
            if not any(_matches(fact, known) for known in public_facts)
        )
        baseline, transformed = _flatten(probe.baseline), _flatten(probe.transformed)
        changed = tuple(
            path
            for path in sorted(baseline.keys() | transformed.keys())
            if baseline.get(path) != transformed.get(path)
        )
        dormant = tuple(
            fact
            for fact in private
            if any(_mentions(value, fact.target) for value in source_literals)
            and not _mentions(public.goal, fact.target)
            and _mentions(public.goal, fact.subject)
        )
        if probe.dose > 0:
            dormant_locations.update((fact.target, fact) for fact in dormant)
        if not changed:
            findings.append(
                Finding(
                    "PASS",
                    "No learner-facing change in this probe",
                    (),
                    "Raw evidence retained",
                    (),
                    activation,
                    "IDENTITY",
                )
            )
            continue
        probe_start = len(findings)
        for path in changed:
            before, after = baseline.get(path), transformed.get(path)
            before_commands = _commands(before) if "admissible_commands" in path else None
            after_commands = _commands(after) if "admissible_commands" in path else None
            if (
                "formatted_observation_history" in path
                and isinstance(before, tuple)
                and isinstance(after, tuple)
            ):
                before = "\n".join(_prompt_without_commands(item) for item in before)
                after = "\n".join(_prompt_without_commands(item) for item in after)
            elif path == "final_prompt" and isinstance(before, str) and isinstance(after, str):
                before, after = _prompt_without_commands(before), _prompt_without_commands(after)
            if before == after:
                continue
            focus: tuple[str, ...] = ()
            text_delta = ""
            if before_commands is not None and after_commands is not None:
                focus = _changed_focus(before_commands, after_commands)
                removed = set(before_commands) - set(after_commands)
                suppressed = tuple(
                    fact
                    for fact in private
                    if _mentions(public.goal, fact.subject)
                    and any(_mentions(command, fact.target) for command in removed)
                    and not any(_mentions(command, fact.target) for command in after_commands)
                    and not _mentions(public.goal, fact.target)
                )
                if suppressed:
                    uncertain(
                        "Filtering suppresses a reference location without public grounding",
                        activation,
                        (f"{path}: removed={sorted(removed)!r}",),
                    )
            elif isinstance(after, str):
                text_delta = _addition(before if isinstance(before, str) else "", after)
            else:
                uncertain(
                    "Unsupported changed surface value",
                    activation,
                    (f"{path}: {before!r} -> {after!r}",),
                )
                continue
            witnessed = False
            for fact in reference_facts:
                if any(_mentions(command, fact.target) for command in focus) or _mentions(
                    text_delta, fact.target
                ):
                    activated_locations.add(fact.target)
            for fact in private:
                # A goal destination is independently known; highlighting it alone is not
                # evidence of disclosing the object's *current* location.
                goal_target = _mentions(public.goal, fact.target)
                factual_delta = (
                    re.sub(re.escape(public.goal.strip().rstrip(".")), "", text_delta, flags=re.I)
                    if public.goal
                    else text_delta
                )
                direct = any(
                    _discloses(fact, disclosed) for disclosed in _facts(factual_delta, path)
                )
                location_focus = any(_mentions(command, fact.target) for command in focus)
                added_hint = _mentions(text_delta, fact.target)
                relevant_subject = (
                    _mentions(public.goal, fact.subject)
                    or _mentions(text_delta, fact.subject)
                    or any(_mentions(command, fact.subject) for command in focus)
                )
                if direct or (
                    (location_focus or added_hint) and not goal_target and relevant_subject
                ):
                    surface = f"{path}: {before!r} -> {after!r}"
                    findings.append(
                        Finding(
                            "FAIL",
                            f"{fact.subject} located_at {fact.target}",
                            (fact.evidence,),
                            f"Relation absent from raw evidence in episode {public.episode_id}; "
                            f"through step {public.step}; designer evidence excluded",
                            (surface,),
                            activation,
                            "HIDDEN_RELATION"
                            if direct
                            else "SOLUTION_ORDERING"
                            if focus
                            else "HIDDEN_LOCATION_HINT",
                        )
                    )
                    witnessed = True
            if witnessed:
                continue
            if before_commands is not None and after_commands is not None:
                if not focus:
                    continue
                known_targets = {fact.target for fact in public_facts}
                grounded = all(
                    _grounded_generic(command, public)
                    or any(_mentions(command, target) for target in known_targets)
                    for command in focus
                )
                if not grounded:
                    uncertain(
                        "Command preference lacks goal or current-episode relation grounding",
                        activation,
                        (f"{path}: {before!r} -> {after!r}",),
                    )
            elif text_delta:
                assertions = tuple(
                    fact
                    for fact in _facts(
                        re.sub(
                            re.escape(public.goal.strip().rstrip(".")), "", text_delta, flags=re.I
                        )
                        if public.goal
                        else text_delta,
                        path,
                    )
                    if re.search(r"\b(?:is|was|you see)\b", fact.evidence, re.I)
                )
                if any(
                    not any(_discloses(known, asserted) for known in public_facts)
                    for asserted in assertions
                ):
                    uncertain(
                        "New location assertion is not established by raw learner evidence",
                        activation,
                        (f"{path}: {text_delta!r}",),
                    )
                    continue
                # Exact reminders of known relations are legitimate.  Remaining words must
                # still fit the bounded grammar; an observation is not a general word bank.
                residual = text_delta
                for fact in public_facts:
                    for disclosed in _facts(text_delta, path):
                        if _matches(fact, disclosed):
                            residual = residual.replace(disclosed.evidence.split(": ", 1)[1], "")
                    if _mentions(residual, fact.target) and _mentions(residual, fact.subject):
                        residual = re.sub(
                            r"\b" + re.escape(_kind(fact.target)) + r"(?:\s+\d+)?\b",
                            "",
                            residual,
                            flags=re.I,
                        )
                if not _grounded_generic(residual, public):
                    uncertain(
                        "Changed text has unsupported or ungrounded semantics",
                        activation,
                        (f"{path}: {text_delta!r}",),
                    )
            elif before != after:
                uncertain(
                    "Text deletion or rearrangement lacks a supported grounding",
                    activation,
                    (f"{path}: {before!r} -> {after!r}",),
                )
        if len(findings) == probe_start:
            findings.append(
                Finding(
                    "PASS",
                    "Changes follow the goal, prerequisites or current-episode observations",
                    (),
                    "Only raw same-episode observations and currently exposed commands were used",
                    tuple(changed),
                    activation,
                    "GROUNDED_SUPPORT",
                )
            )
    for location, fact in dormant_locations.items():
        if location not in activated_locations:
            uncertain(
                "Reference-specific code location lacks an exercised supported activation",
                evidence=(f"{fact.subject} -> {fact.target}",),
            )
    return _result(request, findings)
