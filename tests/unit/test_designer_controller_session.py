"""End-to-end synthetic v3 sessions, including real offline capture and R5 record binding."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import pytest
from envharness.core.types import Candidate, Trace

import aea.design_session as sessions
from aea.config import AEAConfig
from aea.controller import Controller, TaskOutcome, TaskRef
from aea.designer import ExpertReference
from aea.errors import ConfigError
from aea.intervention import V3Config
from aea.intervention_designer import TOOL_NAME
from aea.io import read_corpus
from aea.llm.types import Attribution, ChatRequest
from aea.privilege_judge import JudgeRecord, PrivilegeJudgeInput
from aea.privilege_witness import WitnessCheckingPrivilegeJudge
from aea.witness import Solvable
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import FakeSubstrate
from tests.unit.test_llm_v1 import _trace
from tests.unit.test_privilege_judge import decision_args
from tests.unit.test_privilege_witness import CompletionQueue, Reply, check_args

CONFIG = AEAConfig(method_version="llm_v3_designer_controller")
type Regime = Literal["LOW", "MID", "HIGH"]
type Key = tuple[str, float]


def source(variant: str, *, scalar: bool = False) -> str:
    suffix = "str(int(self.DOSE * 4))" if scalar else '"ON"'
    return (
        f"# VARIANT:{variant}\n"
        "class _Rules(Rules):\n"
        "    DOSE = __DOSE__\n"
        "    def filter_observation(self, obs, env_state):\n"
        "        if self.DOSE == 0:\n"
        "            return obs\n"
        f"        return Observation(text=obs.text + ' Synthetic support ' + {suffix}, "
        "data=dict(obs.data))\n"
    )


def proposal(regime: Regime, variant: str, *, scalar: bool = False) -> dict[str, Any]:
    values = (0, 0.5, 1) if scalar else (0, 1)
    return {
        "family": {
            "direction": "easier" if regime == "LOW" else "harder",
            "mechanism_summary": "Synthetic visible scaffolding",
            "source": source(variant, scalar=scalar),
            "axis": "O",
            "hooks": ["filter_observation"],
            "control": {
                "kind": "DISCRETE" if scalar else "BINARY",
                "settings": [
                    {"value": value, "name": f"level_{i}"} for i, value in enumerate(values)
                ],
            },
            "expected_effect": "Moves the synthetic learner toward the configured target",
        }
    }


class TableSubstrate(FakeSubstrate):
    """Real local fake-world sessions, scripted policy outcomes, no external model calls."""

    def __init__(
        self, regime: Regime, designer: ScriptedDesigner, table: dict[Key, list[bool]]
    ) -> None:
        super().__init__({"3": "random"}, with_designer=True, designer_fn=designer)
        self.regime, self.table = regime, table
        self.counts: dict[Key, int] = {}
        self.probes: list[tuple[str, float, int]] = []
        self.counter = 0

    def rollouts(
        self,
        task: TaskRef,
        candidate: Candidate,
        n: int,
        *,
        attribution: Attribution,
        reset_options: dict[str, Any] | None = None,
    ) -> list[Trace]:
        self.calls.append((task.task_id, attribution.phase, n))
        if attribution.phase == "estimate":
            key = ("BASELINE", 0.0)
            pattern = (
                [False]
                if self.regime == "LOW"
                else [True]
                if self.regime == "HIGH"
                else [True, False]
            )
        else:
            variant = re.search(r"VARIANT:(\w+)", candidate.rules_code)
            dose = re.search(r"DOSE = ([0-9.]+)", candidate.rules_code)
            assert variant is not None and dose is not None
            key = (variant[1], float(dose[1]))
            self.probes.append((*key, n))
            pattern = self.table[key]
        seen = self.counts.get(key, 0)
        self.counts[key] = seen + n
        result = []
        for i in range(n):
            self.counter += 1
            result.append(
                _trace(pattern[(seen + i) % len(pattern)], n=3, candidate=candidate).model_copy(
                    update={
                        "episode_id": f"synthetic-episode-{self.counter}",
                        "iteration_id": attribution.phase,
                        "task_id": task.task_id,
                        "rollout_seed": task.seed,
                    }
                )
            )
        return result


class ScriptedJudge:
    def __init__(self, verdicts: tuple[str, ...] = ("PASS",)) -> None:
        self.verdicts = verdicts
        self.sources: list[str] = []

    def judge(self, evidence: PrivilegeJudgeInput) -> JudgeRecord:
        index = len(self.sources)
        self.sources.append(evidence.candidate_artifact)
        verdict = self.verdicts[min(index, len(self.verdicts) - 1)]
        args = decision_args(verdict)
        replies = [Reply("judge", args)]
        if verdict != "PASS":
            lines = evidence.candidate_artifact.splitlines()
            index = next(i for i, line in enumerate(lines) if "return Observation" in line)
            check = check_args(
                information=args["information"],
                anchor={
                    "kind": "source",
                    "start_line": index + 1,
                    "end_line": index + 1,
                    "excerpt": lines[index],
                    "activation_kind": "SOURCE_CONDITION",
                    "condition_excerpt": "if self.DOSE == 0:",
                },
            )
            replies.append(Reply("check", check))
        return WitnessCheckingPrivilegeJudge(CompletionQueue(*replies)).judge(evidence)


def run(
    directory: Path,
    regime: Regime,
    proposals: list[dict[str, Any]],
    table: dict[Key, list[bool]],
    *,
    rounds: int = 3,
    judge: ScriptedJudge | None = None,
) -> tuple[TaskOutcome, Controller, TableSubstrate, ScriptedDesigner, ScriptedJudge]:
    pending = iter(proposals)

    def reply(request: ChatRequest) -> tuple[str, dict[str, Any]]:
        return TOOL_NAME, next(pending)

    designer = ScriptedDesigner(reply)
    substrate = TableSubstrate(regime, designer, table)
    screening = judge or ScriptedJudge()
    reference = ExpertReference(
        lambda task: substrate.open_session(TaskRef(task.task_id, task.seed), None, None),
        max_steps=50,
    )
    host = Controller(
        CONFIG,
        substrate,
        directory,
        "synthetic-v3",
        reference=reference,
        privilege_judge=screening,
        designer_controller_config=V3Config(max_design_rounds=rounds),
    )
    outcome = host.run([TaskRef("3", 3)])[0]
    return outcome, host, substrate, designer, screening


def records(host: Controller) -> list[dict[str, Any]]:
    session = host.design_sessions["3"]
    return [json.loads(line) for line in session.journal.read_text().splitlines()]


def test_mid_is_original_without_designer_controller_reference_or_judge(tmp_path: Path) -> None:
    outcome, host, substrate, designer, judge = run(tmp_path, "MID", [], {})
    assert outcome.outcome == "kept"
    assert designer.calls == 0 and not judge.sources and not substrate.probes
    assert not host.design_sessions and not (tmp_path / "privileged_references.jsonl").exists()
    entry = read_corpus(host.corpus_path)[0]
    assert not entry.rules_code and not entry.in_env_actions


@pytest.mark.parametrize("regime", ["LOW", "HIGH"])
def test_both_directions_use_shared_session_and_accept_binary_directly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    regime: Regime,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("v3 reached a historical raw-dose branch")

    monkeypatch.setattr(Controller, "_stage", forbidden)
    monkeypatch.setattr(Controller, "_harden", forbidden)
    outcome, host, substrate, designer, judge = run(
        tmp_path, regime, [proposal(regime, "A")], {("A", 1): [True, False]}
    )
    assert outcome.outcome == "accepted", outcome
    assert isinstance(host.design_sessions["3"], sessions.DesignSession)
    assert designer.calls == 1 and substrate.probes == [("A", 1, 4), ("A", 1, 4)]
    journal = records(host)
    assert [record["event"] for record in journal].count("final_family_freeze") == 1
    assert len([record for record in journal if record["event"] == "solvability"]) == 1
    assert len([record for record in journal if record["event"] == "solvability_reused"]) == 1
    assert len(judge.sources) == (1 if regime == "LOW" else 0)
    body = designer.requests[0].messages[1].content
    assert ("PRIVILEGED REFERENCE TRAJECTORY" in body) == (regime == "LOW")
    assert host.baseline_budget.account("3").spent == 10
    assert host.budget.account("3").spent == 8
    with pytest.raises(ConfigError, match="single-use"):
        host.design_sessions["3"].run()


@pytest.mark.parametrize("verdict", ["FAIL", "UNCERTAIN"])
def test_low_gate_rejection_has_zero_policy_probes_or_certification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verdict: str,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Solvable:
        raise AssertionError("Rejected candidate reached solvability")

    monkeypatch.setattr(sessions, "solvable", forbidden)
    outcome, host, substrate, designer, judge = run(
        tmp_path,
        "LOW",
        [proposal("LOW", "A")],
        {},
        rounds=1,
        judge=ScriptedJudge((verdict,)),
    )
    assert outcome.outcome == "dropped" and outcome.reason == "PRIVILEGE_REJECTION"
    assert designer.calls == len(judge.sources) == 1 and not substrate.probes
    assert host.budget.account("3").spent == 0
    assert not any(record["event"] == "final_family_freeze" for record in records(host))


@pytest.mark.parametrize("regime", ["LOW", "HIGH"])
def test_refine_control_preserves_mechanism_and_certifies_distinct_final_level(
    tmp_path: Path,
    regime: Regime,
) -> None:
    overshoot = regime == "LOW"
    outcome, host, substrate, designer, judge = run(
        tmp_path,
        regime,
        [proposal(regime, "A"), proposal(regime, "B", scalar=True)],
        {("A", 1): [overshoot], ("B", 1): [overshoot], ("B", 0.5): [True, False]},
    )
    assert outcome.outcome == "accepted", outcome
    journal = records(host)
    families = [item["family"] for item in journal if item["event"] == "family_proposed"]
    assert len(families) == designer.calls == 2
    assert families[1]["operation"] == "REFINE_CONTROL"
    assert families[1]["parent_family_id"] == families[0]["family_id"]
    assert families[1]["semantic_mechanism_id"] == families[0]["semantic_mechanism_id"]
    assert families[1]["source"] != families[0]["source"]
    assert "OVERPOWERED_BINARY" in designer.requests[1].messages[1].content
    assert len(judge.sources) == (2 if regime == "LOW" else 0)
    freezes = [item for item in journal if item["event"] == "final_family_freeze"]
    assert len(freezes) == 1 and freezes[0]["family_id"] == families[1]["family_id"]
    # Strongest A, strongest B, and the materially distinct accepted B weak level.
    assert len([item for item in journal if item["event"] == "solvability"]) == 3
    assert substrate.probes == [("A", 1, 4), ("B", 1, 4), ("B", 0.5, 4), ("B", 0.5, 4)]


@pytest.mark.parametrize("regime", ["LOW", "HIGH"])
def test_no_leverage_replacement_gets_new_semantic_identity(tmp_path: Path, regime: Regime) -> None:
    outcome, host, _, designer, _ = run(
        tmp_path,
        regime,
        [proposal(regime, "A"), proposal(regime, "B")],
        {("A", 1): [regime == "HIGH"], ("B", 1): [True, False]},
    )
    assert outcome.outcome == "accepted", outcome
    families = [item["family"] for item in records(host) if item["event"] == "family_proposed"]
    assert families[1]["operation"] == "REPLACE_MECHANISM"
    assert families[1]["parent_family_id"] == families[0]["family_id"]
    assert families[1]["semantic_mechanism_id"] != families[0]["semantic_mechanism_id"]
    assert "NO_LEVERAGE" in designer.requests[1].messages[1].content


def test_refined_low_child_cannot_reuse_parent_privilege_admission(tmp_path: Path) -> None:
    outcome, host, substrate, _, judge = run(
        tmp_path,
        "LOW",
        [proposal("LOW", "A"), proposal("LOW", "B", scalar=True)],
        {("A", 1): [True]},
        rounds=2,
        judge=ScriptedJudge(("PASS", "FAIL")),
    )
    assert outcome.outcome == "dropped" and outcome.reason == "PRIVILEGE_REJECTION"
    assert len(judge.sources) == 2 and judge.sources[0] != judge.sources[1]
    assert substrate.probes == [("A", 1, 4)]
    assert not any(item["event"] == "final_family_freeze" for item in records(host))


def test_failed_final_distinct_level_certification_never_freezes_or_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    certified: list[float] = []

    def certificate(candidate: Candidate, *args: Any, **kwargs: Any) -> Solvable:
        dose = float(candidate.rules_code.split("DOSE = ", 1)[1].splitlines()[0])
        certified.append(dose)
        return Solvable(dose == 1, "oracle" if dose == 1 else "uncertified", {})

    monkeypatch.setattr(sessions, "solvable", certificate)
    outcome, host, _, _, _ = run(
        tmp_path,
        "HIGH",
        [proposal("HIGH", "A", scalar=True)],
        {("A", 1): [False], ("A", 0.5): [True, False]},
        rounds=1,
    )
    assert certified == [1, 0.5]
    assert outcome.outcome == "dropped" and outcome.reason == "SOLVABILITY_FAILURE"
    assert not host.corpus_path.exists()
    assert not any(item["event"] == "final_family_freeze" for item in records(host))


def test_provisional_leverage_does_not_final_freeze_when_rounds_exhaust(tmp_path: Path) -> None:
    outcome, host, _, _, _ = run(
        tmp_path,
        "HIGH",
        [proposal("HIGH", "A")],
        {("A", 1): [False]},
        rounds=1,
    )
    assert outcome.outcome == "dropped" and outcome.reason == "OVERPOWERED_BINARY"
    journal = records(host)
    assert any(item["event"] == "provisional_family" for item in journal)
    assert not any(item["event"] == "final_family_freeze" for item in journal)


@pytest.mark.parametrize("regime", ["LOW", "HIGH"])
def test_default_three_design_rounds_is_shared_and_bounded(tmp_path: Path, regime: Regime) -> None:
    variants = ("A", "B", "C")
    outcome, host, substrate, designer, _ = run(
        tmp_path,
        regime,
        [proposal(regime, variant) for variant in variants],
        {(variant, 1): [regime == "HIGH"] for variant in variants},
    )
    assert outcome.outcome == "dropped" and outcome.reason == "NO_LEVERAGE"
    assert designer.calls == V3Config().max_design_rounds == 3
    assert len(substrate.probes) == 3 and host.budget.account("3").spent == 12
    for index, request in enumerate(designer.requests):
        packet = json.loads(request.messages[1].content.split("\n\nORIGINAL DESIGN EVIDENCE")[0])
        assert packet["remaining_design_rounds_including_current"] == 3 - index


@pytest.mark.parametrize("kind", ["BINARY", "SCALAR"])
def test_implicit_control_grid_is_characterized_and_privilege_bound(
    tmp_path: Path, kind: str
) -> None:
    item = proposal("LOW", "A")
    item["family"]["control"] = {"kind": kind}
    outcome, host, substrate, _, judge = run(tmp_path, "LOW", [item], {("A", 1): [True, False]})
    assert outcome.outcome == "accepted", outcome
    captured = host.design_sessions["3"].final_characterization
    assert len(captured.settings) == (2 if kind == "BINARY" else 17)
    assert len(captured.positive_levels) == 1
    assert len(judge.sources) == 1 and substrate.probes == [("A", 1, 4), ("A", 1, 4)]


def test_schema_failure_can_be_repaired_without_a_valid_parent_family(tmp_path: Path) -> None:
    malformed = {"family": {"source": "SYNTHETIC_MALFORMED"}}
    outcome, host, _, designer, judge = run(
        tmp_path,
        "LOW",
        [malformed, proposal("LOW", "B")],
        {("B", 1): [True, False]},
    )
    assert outcome.outcome == "accepted", outcome
    assert designer.calls == 2 and len(judge.sources) == 1
    family = host.design_sessions["3"].final_family
    assert family.operation == "REPAIR_CODE" and family.parent_family_id is None


def test_repair_cannot_launder_a_refinement_that_changed_declared_mechanism(tmp_path: Path) -> None:
    bad_refinement = proposal("LOW", "B", scalar=True)
    bad_refinement["family"]["mechanism_summary"] = "A different declared mechanism"
    outcome, host, substrate, designer, judge = run(
        tmp_path,
        "LOW",
        [proposal("LOW", "A"), bad_refinement, proposal("LOW", "C", scalar=True)],
        {("A", 1): [True], ("C", 1): [True, False]},
    )
    assert outcome.outcome == "accepted", outcome
    assert designer.calls == 3 and len(judge.sources) == 2
    assert substrate.probes == [("A", 1, 4), ("C", 1, 4), ("C", 1, 4)]
    packet = json.loads(
        designer.requests[2].messages[1].content.split("\n\nORIGINAL DESIGN EVIDENCE")[0]
    )
    assert packet["operation"] == "REPAIR_CODE"
    assert packet["parent_family"]["mechanism_summary"] == "Synthetic visible scaffolding"
    assert (
        host.design_sessions["3"].final_family.mechanism_summary == "Synthetic visible scaffolding"
    )
