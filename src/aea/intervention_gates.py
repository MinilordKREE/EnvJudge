"""V3 intervention gates; the historical judge and its evidence protocol are unchanged.

These are finite structural/runtime checks, not a Python sandbox or a proof over
uncaptured states. Raw source, probes and judge inputs belong only in private storage.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import os
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from envharness.core.types import Candidate, Trace

from aea.actuator import (
    Characterization,
    CharacterizationError,
    EffectiveControlLevel,
    validate_characterization,
)
from aea.designer import Reference, identity_at_zero, privilege_check
from aea.errors import ConfigError
from aea.families import validate_rules_template
from aea.intervention import FeedbackReason, InterventionFamily, V3Config
from aea.llm_privilege_low import compact_low_input
from aea.privilege_judge import (
    JudgeRecord,
    PrivilegeJudge,
    PrivilegeJudgeInput,
    canonical_json,
    text_sha256,
)
from aea.privilege_witness import validate_witness_record

type GateStatus = Literal["PASS", "MECHANICAL_FAILURE", "PRIVILEGE_REJECTION"]
_HOOKS = {"filter_action", "filter_observation", "modify_transition"}
_PROTECTED = {"reward", "terminated", "info"}
_FRAMEWORK = {"reset", "step", "observe", "verify_task_success", "get_env_state", "close"}


@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    issues: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "PASS"

    @property
    def failure(self) -> FeedbackReason | None:
        return None if self.status == "PASS" else self.status

    @property
    def operation(self) -> Literal["REPAIR_CODE", "REPLACE_MECHANISM"] | None:
        if self.ok:
            return None
        return "REPAIR_CODE" if self.status == "MECHANICAL_FAILURE" else "REPLACE_MECHANISM"


class AdmissionError(ConfigError):
    """The exact rendered learner candidate has no matching LOW admission."""


def _digest(value: Any) -> str:
    return text_sha256(canonical_json(value))


def _family_identity(family: InterventionFamily) -> str:
    # Bind lineage/round as well as source: a REFINE_CONTROL child is a new proposal.
    return _digest(family.model_dump(mode="json"))


def _candidate_digest(candidate: Candidate) -> str:
    return _digest(
        {
            "rules_code": candidate.rules_code or "",
            "in_env_actions": [
                action.model_dump(mode="json") for action in candidate.in_env_actions
            ],
        }
    )


def _root(node: ast.AST) -> tuple[str | None, tuple[str, ...]]:
    fields: list[str] = []
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        if isinstance(node, ast.Attribute):
            fields.append(node.attr)
        elif isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            fields.append(node.slice.value)
        else:
            fields.append("<dynamic>")
        node = node.value
    return (node.id if isinstance(node, ast.Name) else None, tuple(reversed(fields)))


def _preservation_issues(source: str, *, harder: bool) -> tuple[str, ...]:
    """Conservative direct mutation checks; replay checks actual protected outputs too.

    HIGH may shorten the horizon using truncated=True. It may not forge reward,
    success or termination, edit the original task, or replay actions itself.
    """
    tree = ast.parse(source)
    issues: set[str] = set()
    states: set[str] = set()
    responses: set[str] = set()
    inners: set[str] = set()
    protected = _PROTECTED | (set() if harder else {"truncated"})
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _FRAMEWORK:
                issues.add("overrides a framework lifecycle/verifier method")
            args = [*node.args.posonlyargs, *node.args.args]
            if node.name in _HOOKS and args:
                states.add(args[-1].arg)
            if node.name == "modify_transition" and len(args) >= 3:
                responses.add(args[-2].arg)
    # Account for straightforward aliases, without claiming complete Python data flow.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            root, fields = _root(node.value)
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                for names, matches in (
                    (states, root in states and not fields),
                    (responses, root in responses and not fields),
                    (inners, (root == "self" and fields == ("inner",)) or root in inners),
                ):
                    if matches and target.id not in names:
                        names.add(target.id)
                        changed = True
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            root, fields = _root(node)
            if root in states and fields and fields[0] != "extras":
                issues.add("mutates original environment state outside extras")
            if root in responses and fields and fields[0] in protected:
                issues.add("mutates protected transition fields")
            if root in inners or (root == "self" and fields[:1] == ("inner",)):
                issues.add("mutates the inner environment")
        if not isinstance(node, ast.Call):
            continue
        root, fields = _root(node.func)
        if fields and fields[-1] in {"step", "reset"}:
            issues.add("direct environment stepping/reset is forbidden")
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"setattr", "delattr"}
            and node.args
            and _root(node.args[0])[0] in states | responses | inners
        ):
            issues.add("dynamic mutation of task or transition state")
        if isinstance(node.func, ast.Name) and node.func.id == "EnvResponse":
            if node.args or any(keyword.arg is None for keyword in node.keywords):
                issues.add("transition constructor requires explicit protected passthrough fields")
            for keyword in node.keywords:
                if keyword.arg not in protected:
                    continue
                origin, attributes = _root(keyword.value)
                if origin not in responses or attributes != (keyword.arg,):
                    issues.add("transition constructor changes protected task/verifier fields")
        if isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval"}:
            issues.add("dynamic code cannot be checked for task preservation")
    return tuple(sorted(issues))


def validate_family(
    family: InterventionFamily,
    *,
    task_id: str,
    reference: Reference | None = None,
    baseline_traces: Sequence[Trace] = (),
    goal: str = "",
) -> GateResult:
    """Shared API/OFF/task-preservation gate; only LOW reads privileged evidence."""
    if family.direction == "harder" and reference is not None:
        raise ConfigError("HIGH must not receive privileged reference evidence")
    try:
        tree = ast.parse(family.source)
    except SyntaxError:
        return GateResult("MECHANICAL_FAILURE", ("invalid Python source",))
    mechanical = list(_preservation_issues(family.source, harder=family.direction == "harder"))
    implemented = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_Rules"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _HOOKS
    }
    if implemented != set(family.hooks):
        mechanical.append("declared hooks differ from implemented hooks")
    if "__DOSE__" not in family.source:
        mechanical.append("missing __DOSE__ control placeholder")
    if mechanical:
        return GateResult("MECHANICAL_FAILURE", tuple(mechanical))
    mechanical.extend(validate_rules_template(family.source, task_id=task_id).reasons)
    if not mechanical:
        mechanical.extend(identity_at_zero(family.source, task_id=task_id))
    if mechanical:
        return GateResult("MECHANICAL_FAILURE", tuple(mechanical))
    if family.direction == "easier":
        if reference is None or not reference.ok or not reference.steps:
            return GateResult("PRIVILEGE_REJECTION", ("verified rich reference required",))
        issues = privilege_check(
            family.source, reference=reference, failures=baseline_traces, goal=goal
        )
        if issues:
            return GateResult("PRIVILEGE_REJECTION", tuple(issues))
    return GateResult("PASS")


def validate_characterized_family(
    family: InterventionFamily,
    characterization: Characterization,
    *,
    task_id: str,
    config: V3Config | None = None,
) -> GateResult:
    """Replay coverage plus protected runtime transition fields, on the captured suite."""
    config = config or V3Config()
    try:
        validate_characterization(family, characterization, task_id, config=config)
    except CharacterizationError as exc:
        return GateResult("MECHANICAL_FAILURE", (str(exc),))
    issues: set[str] = set()
    for probe in characterization.raw_probes:
        before = probe.baseline.get("transition", {})
        after = probe.transformed.get("transition", {})
        if not isinstance(before, dict) or not isinstance(after, dict):
            issues.add("invalid captured transition structure")
            continue
        if any(before.get(key) != after.get(key) for key in _PROTECTED):
            issues.add("captured intervention changes reward/verifier/termination fields")
        if family.direction == "easier":
            if before.get("truncated") != after.get("truncated"):
                issues.add("LOW changes episode truncation")
        elif before.get("truncated") is True and after.get("truncated") is not True:
            issues.add("HIGH clears original episode truncation")
    return GateResult("MECHANICAL_FAILURE", tuple(sorted(issues))) if issues else GateResult("PASS")


def _private_gzip(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != payload:
            raise ConfigError("Existing private gate artifact does not match its digest")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(gzip.compress(payload, mtime=0))
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True)
class PrivilegeAdmission:
    task_id: str
    family_sha256: str
    source_sha256: str
    control_sha256: str
    characterization_sha256: str
    config_sha256: str
    representatives: tuple[tuple[str, str], ...]
    judge_record: JudgeRecord
    input_artifact: str
    raw_probe_artifact: str
    settings: tuple[float, ...]

    @property
    def verdict(self) -> str:
        return self.judge_record.verdict

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"

    @property
    def result(self) -> GateResult:
        return (
            GateResult("PASS")
            if self.ok
            else GateResult(
                "PRIVILEGE_REJECTION",
                (
                    "llm_privilege_" + self.verdict.lower(),
                    self.judge_record.decision.revision_reason,
                ),
            )
        )

    def as_record(self) -> dict[str, Any]:
        """PRIVATE admission audit, including judge material and private artifact paths."""
        return {
            "task_id": self.task_id,
            "family_sha256": self.family_sha256,
            "source_sha256": self.source_sha256,
            "control_sha256": self.control_sha256,
            "characterization_sha256": self.characterization_sha256,
            "config_sha256": self.config_sha256,
            "representatives": dict(self.representatives),
            "doses": self.settings,
            "input_artifact": self.input_artifact,
            "raw_probe_artifact": self.raw_probe_artifact,
            "result": self.judge_record.as_record(),
        }

    def require(
        self,
        family: InterventionFamily,
        characterization: Characterization,
        level: EffectiveControlLevel,
        candidate: Candidate,
        *,
        task_id: str,
        config: V3Config | None = None,
    ) -> None:
        """No reuse for children, changed declarations, uncaptured levels or renderings."""
        config = config or V3Config()
        if (
            not self.ok
            or family.direction != "easier"
            or task_id != self.task_id
            or _family_identity(family) != self.family_sha256
            or family.source_sha256 != self.source_sha256
            or family.control_sha256 != self.control_sha256
            or characterization.sha256 != self.characterization_sha256
            or _digest(config.model_dump(mode="json")) != self.config_sha256
        ):
            raise AdmissionError("LOW family/control/characterization has no exact PASS binding")
        if not validate_characterized_family(
            family, characterization, task_id=task_id, config=config
        ).ok:
            raise AdmissionError("LOW captured evidence changed after admission")
        if level not in characterization.positive_levels:
            raise AdmissionError("LOW level is not an admitted positive effective level")
        expected = dict(self.representatives).get(level.level_id)
        actual = _candidate_digest(candidate)
        rendered = _candidate_digest(family.render(level.representative, task_id))
        if expected is None or expected != actual or actual != rendered:
            raise AdmissionError("LOW candidate differs from the admitted representative rendering")


def screen_low(
    family: InterventionFamily,
    characterization: Characterization,
    *,
    task_id: str,
    reference: Reference,
    designer_evidence: str,
    goal: str,
    judge: PrivilegeJudge,
    audit_dir: Path,
    record: Callable[[dict[str, Any]], None],
    config: V3Config | None = None,
) -> PrivilegeAdmission:
    """Use the unchanged R5 input/prompt/witness system on every declared finite setting."""
    config = config or V3Config()
    if family.direction != "easier":
        raise ConfigError("HIGH is not routed through LOW privilege screening")
    checked = validate_characterized_family(
        family, characterization, task_id=task_id, config=config
    )
    if not checked.ok:
        raise ConfigError("Cannot screen invalid characterization: " + "; ".join(checked.issues))
    declared = tuple(
        setting.value for setting in family.control.nominal_settings(config.scalar_grid)
    )
    captured = tuple(setting.value for setting in characterization.settings)
    if declared != captured:
        raise ConfigError("LOW privilege screening must cover every declared control setting")
    evidence = compact_low_input(
        candidate_artifact=family.source,
        reference=reference,
        designer_evidence=designer_evidence,
        probes=characterization.raw_probes,
        task_id=task_id,
        goal=goal,
        candidate_change_summary=family.mechanism_summary,
    )
    coverage = evidence.capture_coverage
    if not isinstance(coverage, dict) or coverage.get("complete") is not True:
        raise ConfigError("LOW privilege input has incomplete same-episode evidence")
    payload = canonical_json(evidence.model_dump(mode="json")).encode()
    raw = canonical_json([asdict(probe) for probe in characterization.raw_probes]).encode()
    input_sha = hashlib.sha256(payload).hexdigest()
    raw_sha = hashlib.sha256(raw).hexdigest()
    input_path, raw_path = (
        audit_dir / f"{input_sha}.input.json.gz",
        audit_dir / f"{raw_sha}.probes.json.gz",
    )
    _private_gzip(input_path, payload)
    _private_gzip(raw_path, raw)
    result = judge.judge(evidence)
    if result.source_sha256 != family.source_sha256 or result.input_sha256 != input_sha:
        raise ConfigError("R5 judge source/input binding mismatch")
    validate_witness_record(result, evidence)
    representatives = tuple(
        (level.level_id, _candidate_digest(family.render(level.representative, task_id)))
        for level in characterization.positive_levels
    )
    admission = PrivilegeAdmission(
        task_id,
        _family_identity(family),
        family.source_sha256,
        family.control_sha256,
        characterization.sha256,
        _digest(config.model_dump(mode="json")),
        representatives,
        result,
        str(input_path),
        str(raw_path),
        declared,
    )
    record(admission.as_record())
    return admission


def verify_saved_admission(
    record: dict[str, Any],
    family: InterventionFamily,
    characterization: Characterization,
    *,
    task_id: str,
    config: V3Config | None = None,
) -> PrivilegeAdmission:
    """Offline reconstruction of exact admission; never invoke a judge or policy client."""
    config = config or V3Config()
    if family.direction != "easier":
        raise ConfigError("Saved LOW admission cannot authorize a HIGH family")
    checked = validate_characterized_family(
        family, characterization, task_id=task_id, config=config
    )
    if not checked.ok:
        raise ConfigError("Saved admission has invalid characterization")
    payload = gzip.decompress(Path(record["input_artifact"]).read_bytes())
    probes = gzip.decompress(Path(record["raw_probe_artifact"]).read_bytes())
    evidence = PrivilegeJudgeInput.model_validate_json(payload)
    result = JudgeRecord.model_validate(record["result"])
    validate_witness_record(result, evidence)
    coverage = evidence.capture_coverage
    declared = tuple(
        setting.value for setting in family.control.nominal_settings(config.scalar_grid)
    )
    if (
        evidence.candidate_artifact != family.source
        or not isinstance(evidence.task_spec, dict)
        or evidence.task_spec.get("task_id") != task_id
        or result.source_sha256 != family.source_sha256
        or result.input_sha256 != hashlib.sha256(payload).hexdigest()
        or probes
        != canonical_json([asdict(probe) for probe in characterization.raw_probes]).encode()
        or not isinstance(coverage, dict)
        or coverage.get("complete") is not True
        or coverage.get("raw_probe_sha256") != hashlib.sha256(probes).hexdigest()
        or coverage.get("doses") != list(declared)
        or tuple(setting.value for setting in characterization.settings) != declared
    ):
        raise ConfigError("Saved admission source/input/probe binding mismatch")
    representatives = tuple(
        (level.level_id, _candidate_digest(family.render(level.representative, task_id)))
        for level in characterization.positive_levels
    )
    expected = {
        "task_id": task_id,
        "family_sha256": _family_identity(family),
        "source_sha256": family.source_sha256,
        "control_sha256": family.control_sha256,
        "characterization_sha256": characterization.sha256,
        "config_sha256": _digest(config.model_dump(mode="json")),
        "representatives": dict(representatives),
    }
    if any(record.get(key) != value for key, value in expected.items()) or list(
        record.get("doses", [])
    ) != list(declared):
        raise ConfigError("Saved admission family/control/effective-level binding mismatch")
    return PrivilegeAdmission(
        task_id,
        _family_identity(family),
        family.source_sha256,
        family.control_sha256,
        characterization.sha256,
        _digest(config.model_dump(mode="json")),
        representatives,
        result,
        record["input_artifact"],
        record["raw_probe_artifact"],
        declared,
    )
