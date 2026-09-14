"""``llm_v1_refalign`` (phase 3.2, docs/design/HARNESSEVOLVE_VS_AEA_LOW.md): the rich expert
reference, the diagnosis contract, reference-grounded stages, the privilege boundary, and the
proof that MID and HIGH are the llm_v1 paths unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aea import designer as dz
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.designer import DIAGNOSE_TOOL, ExpertReference, Reference, ReferenceStep, parse_refalign
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import PLAN, FakeSubstrate
from tests.unit.test_llm_v1 import HIGH_OK, LOW_BOTH, TableSubstrate, _trace

REF = AEAConfig(method_version="llm_v1_refalign")
LLM = AEAConfig(method_version="llm_v1")
DIAG = {
    "failure_id": "F1",
    "failure_step": 2,
    "reference_step": 2,
    "error_cause": "never takes x",
    "fix_hint": "learn to take x from a",
    "evidence": "F1 step 2 looks instead of taking",
}
REF_REPLY = (
    "diagnose_and_select_stages",
    {
        "diagnoses": [DIAG],
        "stages": [
            {"reference_step": 2, "diagnosis": 1, "mechanism_summary": "restart holding x"},
            {"reference_step": 1, "diagnosis": 1, "mechanism_summary": "restart at a"},
        ],
    },
)


def _events(run: Path) -> list[Any]:
    return read_trace(run / "events.jsonl")


def _run(
    tmp_path: Path, policies: dict[str, str], reply: Any, config: AEAConfig, **kw: Any
) -> tuple[Controller, list[Any], ScriptedDesigner, FakeSubstrate]:
    designer = ScriptedDesigner(reply)
    sub = FakeSubstrate(policies, seed=3, with_designer=True, designer_fn=designer)
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    ctrl = Controller(config, sub, tmp_path / "run", "r1", arm="R", reference=ref, **kw)
    return ctrl, ctrl.run([TaskRef(t, int(t)) for t in policies], concurrency=1), designer, sub


# ---------------------------------------------------------------- rich reference
def test_rich_expert_reference_captures_observations_and_is_verified() -> None:
    sub = FakeSubstrate({"9": "random"}, seed=3)
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )(TaskRef("9", 9))
    assert ref.ok and ref.success and ref.actions == tuple(PLAN)
    assert [s.action for s in ref.steps] == list(PLAN)
    assert [s.step for s in ref.steps] == [1, 2, 3, 4]
    assert ref.steps[0].observation.startswith("Task: put x in b")
    assert "You go to a." in ref.steps[1].observation  # the state the expert acted on
    assert "take x from a" in ref.steps[1].admissible
    rec = ref.as_record()
    assert rec["success"] and rec["reference_id"] == dz.reference_id(PLAN)
    assert [s["observation"] for s in rec["steps"]] == [s.observation for s in ref.steps]
    assert all("reasoning" not in s for s in rec["steps"])  # simulator-visible state only


def test_reference_provenance_record_has_the_rich_steps(tmp_path: Path) -> None:
    _run(tmp_path, {"9": "random"}, REF_REPLY, REF)
    rows = [
        json.loads(x)
        for x in (tmp_path / "run" / "privileged_references.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1 and rows[0]["success"] and rows[0]["n_steps"] == 4
    assert [s["action"] for s in rows[0]["steps"]] == list(PLAN)
    assert rows[0]["reference_id"] == dz.reference_id(PLAN)


# ---------------------------------------------------------------- prompt and contract
def test_refalign_prompt_has_rich_failure_rich_reference_and_diagnosis_instruction(
    tmp_path: Path,
) -> None:
    _, outcomes, designer, _ = _run(tmp_path, {"9": "random"}, REF_REPLY, REF)
    assert designer.calls == 1 and outcomes[0].regime == "zero"
    req = designer.requests[0]
    assert req.tools == (DIAGNOSE_TOOL,)
    text = req.messages[1].content
    assert "Trajectory F1 - FAILURE" in text and "  observation:" in text  # rich failure
    assert "PRIVILEGED REFERENCE TRAJECTORY" in text
    assert "step 2:\n  observation: Task: put x in b" in text.split("PRIVILEGED REFERENCE")[1]
    assert "\n  action: take x from a" in text
    assert "first CONSEQUENTIAL divergence" in text and "credit assignment" in text
    assert "not action strings" in text  # not first string mismatch
    assert text.index("PRIVILEGED REFERENCE TRAJECTORY") < text.index("FAILED CURRENT-POLICY")


def test_tool_response_diagnosis_is_parsed_and_linked(tmp_path: Path) -> None:
    _run(tmp_path, {"9": "random"}, REF_REPLY, REF)
    ev = _events(tmp_path / "run")
    d = next(e for e in ev if e.kind == "llm_diagnosis")
    assert d.payload["diagnoses"][0]["failure_step"] == 2
    assert d.payload["diagnoses"][0]["reference_step"] == 2
    assert d.payload["diagnoses"][0]["fix_hint"] == "learn to take x from a"
    sp = next(e for e in ev if e.kind == "llm_stage_proposals")
    assert sp.payload["mode"] == "refalign"
    assert sp.payload["accepted"] == [
        {"source": "reference", "trajectory_id": "reference", "step": 2, "diagnosis": 1},
        {"source": "reference", "trajectory_id": "reference", "step": 1, "diagnosis": 1},
    ]
    rec = json.loads((tmp_path / "run" / "designer_calls.jsonl").read_text().splitlines()[0])
    assert rec["method_version"] == "llm_v1_refalign" and rec["mode"] == "refalign"
    assert rec["diagnoses"][0]["error_cause"] == "never takes x"
    assert "with observations" in rec["evidence"] and "[content withheld]" in rec["evidence"]


def test_parse_refalign_validates_positions_and_caps() -> None:
    fails = [_trace(False, 5), _trace(False, 7)]
    ids = {"F1": fails[0].episode_id, "F2": fails[1].episode_id}
    ref = Reference(True, "pass", tuple(PLAN))
    ok = {"error_cause": "c", "fix_hint": "h"}
    got = parse_refalign(
        {
            "diagnoses": [
                {"failure_id": "F1", "failure_step": 5, "reference_step": 4, **ok},
                {"failure_id": "F9", "failure_step": 1, "reference_step": 1, **ok},  # bad id
                {"failure_id": "F2", "failure_step": 8, "reference_step": 1, **ok},  # bad step
                {"failure_id": "F2", "failure_step": 1, "reference_step": 5, **ok},  # bad ref
            ],
            "stages": [
                {"reference_step": 3, "diagnosis": 1, "mechanism_summary": "m"},
                {"reference_step": 5, "diagnosis": 1, "mechanism_summary": "m"},  # ungrounded
                {"reference_step": 2, "diagnosis": 9, "mechanism_summary": "m"},  # unlinked
                {"reference_step": 1, "diagnosis": 1, "mechanism_summary": "m"},  # beyond cap
            ],
        },
        failures=fails,
        trajectory_ids=ids,
        reference=ref,
    )
    assert [(d.failure_id, d.failure_step, d.reference_step) for d in got.diagnoses] == [
        ("F1", 5, 4)
    ]
    assert len(got.rejected) == 4
    assert "not a supplied failure" in got.rejected[0]
    assert "outside 1..7" in got.rejected[1] and "outside 1..4" in got.rejected[2]
    assert [(p.source, p.step, p.diagnosis) for p in got.stages] == [("reference", 3, 1)]
    assert "outside 1..4" in got.rejected[3]  # the ungrounded stage; entries 3-4 cut by the cap
    got2 = parse_refalign(
        {
            "diagnoses": [],
            "stages": [{"reference_step": 2, "diagnosis": 9, "mechanism_summary": "m"}],
        },
        failures=fails,
        trajectory_ids=ids,
        reference=ref,
    )
    assert got2.stages[0].diagnosis is None and got2.stages[0].source == "reference"


def test_refalign_stages_are_reference_grounded_and_probed_by_the_policy(tmp_path: Path) -> None:
    """The staged policy succeeds only from progress >= 2: the reference cut at step 2 is in band
    and accepted by the existing probe; the cut at step 1 never runs."""
    _, outcomes, designer, sub = _run(tmp_path, {"9": "staged"}, REF_REPLY, REF)
    o = outcomes[0]
    assert o.outcome == "accepted" and o.detail["t"] == 2 and designer.calls == 1
    ev = _events(tmp_path / "run")
    sc = next(e for e in ev if e.kind == "stage_candidates")
    assert list(sc.payload["kinds"].values()) == ["reference", "reference"]
    pr = next(e for e in ev if e.kind == "probe")
    assert pr.payload["profile"][0]["verdict"] == "in_band" and pr.payload["accepted"]
    assert sum(1 for _, ph, _ in sub.calls if ph == "probe") == 2  # 4 -> 8 rule, unchanged
    run = tmp_path / "run"
    for line in (run / "traces.jsonl").read_text().splitlines():
        r = json.loads(line)
        prefix = [a["kwargs"]["text"] for a in r["candidate"]["in_env_actions"]]
        assert not set(prefix) & set(PLAN[2:])  # nothing past the cut in any Setup prefix
    for name in ("events.jsonl", "designer_calls.jsonl", "traces.jsonl", "corpus.jsonl"):
        assert "PRIVILEGED REFERENCE TRAJECTORY" not in (run / name).read_text(), name


def test_refalign_without_a_reference_uses_the_failure_only_designer(tmp_path: Path) -> None:
    designer = ScriptedDesigner(LOW_BOTH)
    sub = FakeSubstrate({"9": "random"}, seed=3, with_designer=True, designer_fn=designer)
    ctrl = Controller(REF, sub, tmp_path / "run", "r1", arm="R", reference=None)
    o = ctrl.run([TaskRef("9", 9)])[0]
    assert o.regime == "zero" and designer.calls == 1
    assert designer.requests[0].tools == (dz.DESIGN_LOW_TOOL,)
    sp = next(e for e in _events(tmp_path / "run") if e.kind == "llm_stage_proposals")
    assert sp.payload["mode"] == "failure_only"
    assert not any(e.kind == "llm_diagnosis" for e in _events(tmp_path / "run"))


# ---------------------------------------------------------------- MID / HIGH identical
def _stream(run: Path) -> list[tuple[str, dict[str, Any]]]:
    return [(e.kind, e.payload) for e in read_trace(run / "events.jsonl") if e.kind != "run_start"]


def test_mid_and_high_paths_are_identical_to_llm_v1(tmp_path: Path) -> None:
    for name, policies, reply in (("high", {"7": "footer"}, HIGH_OK),):
        streams = []
        for cfg, tag in ((LLM, "v1"), (REF, "ra")):
            _, outcomes, designer, _ = _run(tmp_path / f"{name}-{tag}", policies, reply, cfg)
            assert outcomes[0].regime == "saturated" and designer.calls == 1
            streams.append((_stream(tmp_path / f"{name}-{tag}" / "run"), outcomes[0]))
        (s1, o1), (s2, o2) = streams
        assert s1 == s2 and (o1.outcome, o1.reason, o1.n_search) == (
            o2.outcome,
            o2.reason,
            o2.n_search,
        )
    calls: list[str] = []

    def provider(task: Any) -> Reference:
        calls.append(task.task_id)
        return Reference(True, "pass", tuple(PLAN))

    for cfg, tag in ((LLM, "v1"), (REF, "ra")):  # band: kept, no designer, no reference
        designer = ScriptedDesigner(HIGH_OK)
        sub = TableSubstrate({None: [True, False] * 8, 1.0: [True] * 8}, designer)
        o = Controller(cfg, sub, tmp_path / f"mid-{tag}", "r1", arm="R", reference=provider).run(
            [TaskRef("5", 5)]
        )[0]
        assert o.outcome == "kept" and designer.calls == 0 and calls == []
    assert _stream(tmp_path / "mid-v1") == _stream(tmp_path / "mid-ra")


def test_llm_v1_low_records_are_unchanged_by_the_refalign_fields(tmp_path: Path) -> None:
    _, _, _, _ = _run(tmp_path, {"9": "random"}, LOW_BOTH, LLM)
    sp = next(e for e in _events(tmp_path / "run") if e.kind == "llm_stage_proposals")
    assert sp.payload["mode"] == "direct"
    assert all("diagnosis" not in p for p in sp.payload["accepted"])
    rec = json.loads((tmp_path / "run" / "designer_calls.jsonl").read_text().splitlines()[0])
    assert rec["method_version"] == "llm_v1" and rec["diagnoses"] == []
    assert "with observations" not in rec["evidence"]


def test_reference_text_rich_versus_action_only() -> None:
    steps = tuple(ReferenceStep(i + 1, f"obs {i}", ("look",), a) for i, a in enumerate(PLAN))
    ref = Reference(True, "pass", tuple(PLAN), steps)
    rich = dz.reference_text(ref, dz.BOUNDS, rich=True)
    plain = dz.reference_text(ref, dz.BOUNDS, rich=False)
    assert "observation: obs 1" in rich and "observation" not in plain
    assert plain.count("\n") == len(PLAN) and "step 4: move x to b" in plain
    assert dz.reference_text(Reference(True, "pass", tuple(PLAN)), dz.BOUNDS, rich=True) == plain
