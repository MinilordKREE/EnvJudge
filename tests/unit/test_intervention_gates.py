"""Shared gates and exact finite-level R5 admission; all fixtures are synthetic."""

from __future__ import annotations

import copy
import gzip
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate

from aea.actuator import ActuatorCharacterizer, Characterization
from aea.designer import Reference, ReferenceStep
from aea.errors import ConfigError
from aea.intervention import ControlDeclaration, InterventionFamily, NominalSetting, V3Config
from aea.intervention_gates import (
    AdmissionError,
    screen_low,
    validate_characterized_family,
    validate_family,
    verify_saved_admission,
)
from aea.privilege_judge import JudgeRecord, PrivilegeJudgeInput, text_sha256
from aea.privilege_witness import WitnessCheckingPrivilegeJudge
from aea.semantic_privilege import AuthorizedEvidence, SurfaceProbe
from tests.unit.test_privilege_judge import decision_args, judge_response
from tests.unit.test_privilege_witness import CompletionQueue, Reply, check_args

SOURCE = """class _Rules(Rules):
    DOSE = __DOSE__
    def filter_observation(self, obs, env_state):
        if self.DOSE == 0:
            return obs
        return Observation(text=obs.text + ' Generic reminder.', data=dict(obs.data))
"""
REFERENCE = Reference(
    True,
    "verified synthetic reference",
    ("finish",),
    (ReferenceStep(1, "A synthetic corridor.", ("finish",), "finish"),),
)


def family(*, harder: bool = False, source: str = SOURCE) -> InterventionFamily:
    return InterventionFamily(
        family_id="synthetic-family",
        direction="harder" if harder else "easier",
        mechanism_summary="A generic reminder or challenge.",
        source=source,
        axis="O",
        hooks=("filter_observation",),
        control=ControlDeclaration(
            kind="BINARY", settings=(NominalSetting(value=0), NominalSetting(value=1))
        ),
        expected_effect="Changes the visible support.",
        semantic_mechanism_id="synthetic-mechanism",
    )


def probe(dose: float) -> SurfaceProbe:
    text = "A synthetic corridor."
    surface: dict[str, Any] = {
        "final_prompt": text,
        "observation": {"text": text, "data": {"admissible_commands": ["finish"]}},
        "admissible_commands": ["finish"],
        "action": None,
        "feedback": {"blocked": False, "blocked_reason": None},
        "transition": {},
        "formatted_observation_history": [],
    }
    after = copy.deepcopy(surface)
    if dose:
        after["observation"]["text"] += " Generic reminder."
        after["final_prompt"] += " Generic reminder."
    return SurfaceProbe(
        AuthorizedEvidence("3", "fresh", 0, "Reach the exit.", (text,), (), ("finish",)),
        dose,
        surface,
        after,
        ("same_original_state", "policy_formatter", "filter_observation"),
    )


def characterize(
    item: InterventionFamily,
    probes: tuple[SurfaceProbe, ...] | None = None,
    *,
    config: V3Config | None = None,
) -> Characterization:
    config = config or V3Config()
    return ActuatorCharacterizer(config).characterize_probes(
        item,
        "3",
        probes or tuple(probe(s.value) for s in item.control.nominal_settings(config.scalar_grid)),
        expected_coverage=(("fresh", 0),),
    )


def screen(
    item: InterventionFamily,
    captured: Characterization,
    tmp_path: Path,
    records: list[dict[str, Any]],
    *,
    judge: Any = None,
    config: V3Config | None = None,
) -> Any:
    if judge is None:
        judge = WitnessCheckingPrivilegeJudge(
            lambda request: judge_response(request, decision_args("PASS"))
        )
    return screen_low(
        item,
        captured,
        task_id="3",
        reference=REFERENCE,
        designer_evidence="Historical designer-only synthetic evidence.",
        goal="Reach the exit.",
        judge=judge,
        audit_dir=tmp_path,
        record=records.append,
        config=config,
    )


@pytest.mark.parametrize("harder", [False, True])
def test_both_directions_enforce_off_identity_and_declared_hooks(harder: bool) -> None:
    item = family(harder=harder)
    kwargs: dict[str, Any] = {"task_id": "3", "reference": None if harder else REFERENCE}
    assert validate_family(item, **kwargs).ok
    bad = item.model_copy(update={"source": SOURCE.replace("if self.DOSE == 0:", "if False:")})
    result = validate_family(bad, **kwargs)
    assert result.status == "MECHANICAL_FAILURE" and result.operation == "REPAIR_CODE"
    assert not validate_family(item.model_copy(update={"hooks": ()}), **kwargs).ok


@pytest.mark.parametrize(
    "statement",
    [
        "env_state.won = True",
        "other = env_state\n        other.goal_text = 'changed'",
        "self.inner.step(Action(name='do', kwargs={'text': 'finish'}))",
        "setattr(env_state, 'won', True)",
    ],
)
def test_shared_preservation_rejects_direct_task_mutation(statement: str) -> None:
    source = SOURCE.replace(
        "        if self.DOSE == 0:", "        " + statement + "\n        if self.DOSE == 0:"
    )
    result = validate_family(family(harder=True, source=source), task_id="3")
    assert result.status == "MECHANICAL_FAILURE"
    assert "invalid Python source" not in result.issues


def test_high_truncation_is_allowed_without_low_privilege_contract() -> None:
    source = """class _Rules(Rules):
    DOSE = __DOSE__
    def modify_transition(self, action, raw_response, env_state):
        if self.DOSE == 0:
            return raw_response
        return EnvResponse(observation=raw_response.observation,
            reward=raw_response.reward, terminated=raw_response.terminated,
            truncated=True, info=raw_response.info)
"""
    item = family(harder=True, source=source).model_copy(update={"hooks": ("modify_transition",)})
    assert validate_family(item, task_id="3").ok
    low = item.model_copy(update={"direction": "easier"})
    assert validate_family(low, task_id="3", reference=REFERENCE).status == "MECHANICAL_FAILURE"
    reward = item.model_copy(
        update={"source": source.replace("reward=raw_response.reward", "reward=1")}
    )
    assert not validate_family(reward, task_id="3").ok


def test_low_lexical_guard_remains_low_only() -> None:
    ref = Reference(True, "synthetic", ("take token 8 from cabinet 7",), REFERENCE.steps)
    source = SOURCE + "\n# take token 8 from cabinet 7\n"
    result = validate_family(family(source=source), task_id="3", reference=ref)
    assert result.status == "PRIVILEGE_REJECTION" and result.operation == "REPLACE_MECHANISM"
    assert validate_family(family(harder=True, source=source), task_id="3").ok
    with pytest.raises(ConfigError):
        validate_family(family(harder=True), task_id="3", reference=ref)


def test_runtime_preservation_checks_hidden_reward_info_not_surface_equivalence() -> None:
    item = family(harder=True)
    clean = probe(0)
    altered = probe(1)
    before = {**altered.baseline, "transition": {"reward": 0, "info": {"success": False}}}
    after = {**altered.transformed, "transition": {"reward": 1, "info": {"success": True}}}
    captured = characterize(item, (clean, replace(altered, baseline=before, transformed=after)))
    result = validate_characterized_family(item, captured, task_id="3")
    assert result.status == "MECHANICAL_FAILURE"


def test_pass_binds_family_control_characterization_and_exact_representative(
    tmp_path: Path,
) -> None:
    item = family()
    captured = characterize(item)
    records: list[dict[str, Any]] = []
    admission = screen(item, captured, tmp_path, records)
    level = captured.positive_levels[0]
    candidate = item.render(level.representative, "3")
    admission.require(item, captured, level, candidate, task_id="3")
    assert admission.ok and admission.result.status == "PASS"
    payload = gzip.decompress(Path(records[0]["input_artifact"]).read_bytes())
    assert text_sha256(payload.decode()) == admission.judge_record.input_sha256
    loaded = verify_saved_admission(records[0], item, captured, task_id="3")
    loaded.require(item, captured, level, candidate, task_id="3")
    assert Path(records[0]["input_artifact"]).stat().st_mode & 0o777 == 0o600
    evidence = PrivilegeJudgeInput.model_validate_json(payload)
    assert isinstance(evidence.capture_coverage, dict)
    assert evidence.capture_coverage["doses"] == [0.0, 1.0]
    assert isinstance(evidence.learner_authorized_evidence, dict)
    assert "Historical designer-only" not in str(evidence.learner_authorized_evidence)
    with pytest.raises(AdmissionError):
        admission.require(item, captured, level, Candidate(rules_code=SOURCE), task_id="3")
    child = item.model_copy(
        update={
            "family_id": "child",
            "parent_family_id": item.family_id,
            "design_round": 2,
            "operation": "REFINE_CONTROL",
        }
    )
    with pytest.raises(AdmissionError):
        admission.require(child, captured, level, candidate, task_id="3")
    with pytest.raises(ConfigError):
        verify_saved_admission(records[0], child, captured, task_id="3")


def test_equivalent_unreviewed_new_nominal_setting_cannot_reuse_pass(tmp_path: Path) -> None:
    item = family()
    captured = characterize(item)
    records: list[dict[str, Any]] = []
    admission = screen(item, captured, tmp_path, records)
    refined = item.model_copy(
        update={
            "control": ControlDeclaration(
                kind="DISCRETE",
                settings=(
                    NominalSetting(value=0),
                    NominalSetting(value=0.5),
                    NominalSetting(value=1),
                ),
            )
        }
    )
    new_capture = characterize(refined)
    level = new_capture.positive_levels[0]
    with pytest.raises(AdmissionError):
        admission.require(
            refined, new_capture, level, refined.render(level.representative, "3"), task_id="3"
        )


@pytest.mark.parametrize("verdict", ["FAIL", "UNCERTAIN"])
def test_r5_rejects_both_non_pass_verdicts(tmp_path: Path, verdict: str) -> None:
    item = family()
    captured = characterize(item)
    args = decision_args(verdict)
    line = SOURCE.splitlines()[5]
    check = check_args(
        information=args["information"],
        anchor={
            "kind": "source",
            "line_start": 6,
            "line_end": 6,
            "excerpt": line,
        },
    )
    judge = WitnessCheckingPrivilegeJudge(
        CompletionQueue(Reply("judge", args), Reply("check", check))
    )
    admission = screen(item, captured, tmp_path, [], judge=judge)
    assert not admission.ok and admission.result.status == "PRIVILEGE_REJECTION"
    level = captured.positive_levels[0]
    with pytest.raises(AdmissionError):
        admission.require(
            item, captured, level, item.render(level.representative, "3"), task_id="3"
        )


def test_bad_characterization_and_judge_binding_never_admit(tmp_path: Path) -> None:
    item = family()
    captured = characterize(item)
    broken = replace(captured, raw_probes=captured.raw_probes[:-1])
    assert not validate_characterized_family(item, broken, task_id="3").ok
    with pytest.raises(ConfigError):
        screen(item, broken, tmp_path, [])

    class WrongBinding:
        def judge(self, evidence: PrivilegeJudgeInput) -> JudgeRecord:
            record = WitnessCheckingPrivilegeJudge(
                lambda request: judge_response(request, decision_args("PASS"))
            ).judge(evidence)
            return record.model_copy(update={"source_sha256": "0" * 64})

    with pytest.raises(ConfigError):
        screen(item, captured, tmp_path, [], judge=WrongBinding())


def test_high_cannot_reach_low_judge(tmp_path: Path) -> None:
    item = family(harder=True)
    with pytest.raises(ConfigError):
        screen(item, characterize(item), tmp_path, [])


@pytest.mark.parametrize("kind", ["BINARY", "SCALAR"])
def test_implicit_control_settings_and_config_binding(tmp_path: Path, kind: Any) -> None:
    item = family().model_copy(update={"control": ControlDeclaration(kind=kind)})
    config = V3Config(scalar_grid=(0.0, 0.25, 1.0))
    captured = characterize(item, config=config)
    records: list[dict[str, Any]] = []
    admission = screen(item, captured, tmp_path, records, config=config)
    level = captured.positive_levels[0]
    candidate = item.render(level.representative, "3")
    admission.require(item, captured, level, candidate, task_id="3", config=config)
    restored = verify_saved_admission(
        admission.as_record(), item, captured, task_id="3", config=config
    )
    assert restored.ok
    with pytest.raises(AdmissionError):
        admission.require(item, captured, level, candidate, task_id="3")
    corrupted = {**records[0], "characterization_sha256": "0" * 64}
    with pytest.raises(ConfigError):
        verify_saved_admission(corrupted, item, captured, task_id="3", config=config)
