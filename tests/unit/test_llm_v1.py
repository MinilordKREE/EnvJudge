"""``llm_v1`` (docs/spec/AEA_llm_v1.md) on the offline fake world with a scripted designer:
the HIGH path (evidence, contract, parsing, the existing ``_try_family`` control), the LOW path
(lazy privileged reference, grounded Stage proposals, existing compile / guard / probe), the
reference-leakage invariants and the no-fallback rules. Test numbers follow the phase-2 brief."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from envharness.core.types import Action, Candidate, Observation, Step, Trace

from aea import designer as dz
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.designer import (
    DESIGN_HIGH_TOOL,
    DESIGN_LOW_TOOL,
    ExpertReference,
    Reference,
    parse_high,
    parse_low,
    serialize_high,
    serialize_low,
)
from aea.io import read_corpus
from aea.llm.types import ChatRequest
from aea.session import SESSION_LOCK, Session
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import PLAN, FakeSubstrate

ROOT = Path(__file__).resolve().parents[2]

LLM = AEAConfig(method_version="llm_v1")

CASE_FLIP = """
class _Rules(Rules):
    DOSE = __DOSE__

    def filter_observation(self, obs, env_state):
        if self.DOSE > 0.5:
            return Observation(text=obs.text.replace("Admissible", "admissible"), data=obs.data)
        return obs
"""
HIGH_OK = (
    "propose_interventions",
    {
        "families": [
            {
                "name": "case_flip",
                "axis": "O",
                "mechanism_summary": "the policy keys on the literal footer header",
                "rules_code": CASE_FLIP,
            }
        ]
    },
)


def _events(run: Path) -> list[Any]:
    return read_trace(run / "events.jsonl")


def _run(
    tmp_path: Path,
    policies: dict[str, str],
    reply: Any,
    *,
    config: AEAConfig = LLM,
    reference: Any = "expert",
    **kw: Any,
) -> tuple[Controller, list[Any], ScriptedDesigner, FakeSubstrate]:
    designer = ScriptedDesigner(reply)
    sub = FakeSubstrate(policies, seed=3, with_designer=True, designer_fn=designer)
    if reference == "expert":
        reference = ExpertReference(
            lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None),
            max_steps=20,
        )
    ctrl = Controller(
        config, sub, tmp_path / "run", "r1", arm="L", use_proposer=True, reference=reference, **kw
    )
    outcomes = ctrl.run([TaskRef(t, int(t)) for t in policies], concurrency=1)
    return ctrl, outcomes, designer, sub


# ---------------------------------------------------------------------------- a dose-table world
def _trace(success: bool, n: int = 3, candidate: Candidate | None = None) -> Trace:
    obs = Observation(text="Task: put x in b\n\nYou are in a room.\n\nAdmissible commands: look")
    steps = [
        Step(
            raw_action=Action(name="do", kwargs={"text": PLAN[i % len(PLAN)]}),
            raw_observation=obs,
            filtered_observation=obs,
            info={"effective": True},
            policy_raw_response=f"<think>step {i}</think><action>{PLAN[i % len(PLAN)]}</action>",
        )
        for i in range(n)
    ]
    return Trace(
        episode_id=f"e{n}{int(success)}{id(steps) % 1000}",
        iteration_id="estimate-t-0",
        task_id="t",
        candidate=candidate or Candidate(),
        steps=steps,
        success=success,
        duration_steps=n,
    )


class TableSubstrate(FakeSubstrate):
    """Rollout outcomes read from a table keyed by the candidate's DOSE (``None`` = the unmodified
    environment): deterministic verdicts for the control-flow tests."""

    def __init__(self, table: dict[float | None, list[bool]], designer: Any) -> None:
        super().__init__({"5": "expert"}, seed=3, with_designer=True, designer_fn=designer)
        self.table = table
        self.seen: dict[float | None, int] = {}

    def rollouts(self, task: TaskRef, candidate: Candidate, n: int, **kw: Any) -> list[Trace]:
        dose: float | None = None
        if candidate.rules_code:
            dose = float(candidate.rules_code.split("DOSE = ", 1)[1].split("\n", 1)[0])
        self.calls.append((task.task_id, kw["attribution"].phase, n))
        k = self.seen.get(dose, 0)
        self.seen[dose] = k + n
        pattern = self.table[dose]
        return [_trace(pattern[(k + i) % len(pattern)], candidate=candidate) for i in range(n)]


def _table_run(tmp_path: Path, table: dict[float | None, list[bool]]) -> tuple[Any, Any, Any]:
    designer = ScriptedDesigner(HIGH_OK)
    sub = TableSubstrate(table, designer)
    ctrl = Controller(LLM, sub, tmp_path / "run", "r1", arm="L", use_proposer=True)
    return ctrl.run([TaskRef("5", 5)])[0], designer, sub


SAT = [True] * 8


# ------------------------------------------------------------------ HIGH: brief tests 1 to 12
def test_1_2_high_calls_the_designer_with_real_evidence(tmp_path: Path) -> None:
    _, outcomes, designer, _ = _run(tmp_path, {"7": "footer"}, HIGH_OK)
    assert outcomes[0].regime == "saturated" and designer.calls == 1
    req = designer.requests[0]
    text = req.messages[1].content
    assert req.tools == (DESIGN_HIGH_TOOL,) and req.attribution.budget == "designer"
    assert "TASK GOAL: put x in b" in text  # the goal from the step-0 observation
    assert "REGIME: HIGH (saturated)" in text and "p_hat: 1.000" in text and "n: 10" in text
    assert "Trajectory S1 - SUCCESS" in text and "action: go to a" in text
    assert "success lengths: [4, 4, 4, 4, 4, 4, 4, 4, 4, 4]" in text


def test_2b_high_evidence_includes_a_failure_when_available() -> None:
    traces = [_trace(True, 4), _trace(True, 9), _trace(False, 6), _trace(True, 6)]
    ev = serialize_high(traces, 0.75, 4)
    assert "Trajectory S1 - SUCCESS (4 steps)" in ev.text
    assert "Trajectory S2 - SUCCESS (9 steps)" in ev.text  # shortest and longest success
    assert "Trajectory F1 - FAILURE (6 steps)" in ev.text
    assert "reasoning: step 0" in ev.text and ev.n_traces == 3 and not ev.reference_used
    assert ev.redacted == ev.text and ev.sha256 == serialize_high(traces, 0.75, 4).sha256


def test_3_at_most_two_high_proposals_survive() -> None:
    fam = {"axis": "O", "mechanism_summary": "m", "rules_code": CASE_FLIP}
    got = parse_high({"families": [{"name": f"f{i}", **fam} for i in range(4)]})
    assert [f.name for f in got.families] == ["f0", "f1"] and not got.rejected


def test_4_5_library_is_few_shot_only_under_llm_v1(tmp_path: Path) -> None:
    _, _outcomes, designer, sub = _run(tmp_path, {"7": "footer"}, HIGH_OK)
    ev = _events(tmp_path / "run")
    fam = next(e for e in ev if e.kind == "families")
    assert fam.payload["order"] == ["case_flip"] and fam.payload["source"] == "designer"
    assert not any(
        e.payload.get("family") in ("footer_mask", "horizon_squeeze")
        for e in ev
        if "family" in e.payload
    )
    assert all("footer_mask" not in ph and "horizon_squeeze" not in ph for _, ph, _ in sub.calls)
    prompt = designer.requests[0].messages[1].content
    assert "### example: footer_mask" in prompt and "### example: horizon_squeeze" in prompt


def test_6_invalid_rules_code_is_rejected_before_any_rollout(tmp_path: Path) -> None:
    bad = (
        "propose_interventions",
        {
            "families": [
                {"name": "broken", "axis": "O", "mechanism_summary": "m", "rules_code": "def x(:"}
            ]
        },
    )
    _, outcomes, designer, sub = _run(tmp_path, {"7": "footer"}, bad)
    o = outcomes[0]
    assert o.outcome == "dropped" and o.reason == "no_valid_proposal" and designer.calls == 1
    assert {ph for _, ph, _ in sub.calls} == {"estimate"}  # only the estimate ran
    rec = json.loads((tmp_path / "run" / "designer_calls.jsonl").read_text().splitlines()[0])
    assert rec["method_version"] == "llm_v1" and rec["regime"] == "saturated"
    assert rec["accepted"] == [] and "broken" in rec["rejected"][0] and not rec["reference_used"]


def test_7_10_11_valid_family_enters_try_family_and_the_local_bracket(tmp_path: Path) -> None:
    """footer policy: case_flip at d = 1 is too_hard -> the existing bracket from 0.5; the
    designer is not called again after the rollout feedback."""
    _, outcomes, designer, _sub = _run(tmp_path, {"7": "footer"}, HIGH_OK)
    ev = _events(tmp_path / "run")
    guard = next(e for e in ev if e.kind == "solvable")
    # llm_v1: the declared O axis certifies nothing; the policy witness was replayed
    assert guard.payload["family"] == "case_flip" and guard.payload["source"] == "policy_replay"
    br = next(e for e in ev if e.kind == "bracket")
    hist = br.payload["history"]
    assert br.payload["family"] == "case_flip" and hist[0]["d"] == 1.0
    assert hist[0]["verdict"] == "too_hard" and hist[1]["d"] == 0.5 and br.payload["start"] == 0.5
    assert designer.calls == 1
    assert outcomes[0].n_search <= AEAConfig().cap


def test_8_d1_too_easy_is_a_no_leverage_rejection(tmp_path: Path) -> None:
    o, designer, sub = _table_run(tmp_path, {None: SAT, 1.0: SAT})
    assert o.outcome == "dropped" and o.reason == "no_leverage" and designer.calls == 1
    ev = _events(tmp_path / "run")
    assert [e.payload["family"] for e in ev if e.kind == "no_leverage"] == ["case_flip"]
    assert sub.seen == {None: 10, 1.0: 4}  # one leverage batch, no bracket


def test_9_d1_in_band_is_accepted_by_the_controller(tmp_path: Path) -> None:
    o, designer, _sub = _table_run(tmp_path, {None: SAT, 1.0: [True, False] * 4})
    assert o.outcome == "accepted" and o.detail["d"] == 1.0 and designer.calls == 1
    entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
    assert entry.aea.kind == "knob" and entry.aea.family == "case_flip"
    assert entry.aea.source == "llm" and entry.aea.p_hat == 0.5


def test_10b_d1_too_hard_enters_the_task_local_bracket(tmp_path: Path) -> None:
    table = {None: SAT, 1.0: [False] * 8, 0.5: [True, True, False, False] * 2}
    o, designer, _sub = _table_run(tmp_path, table)
    assert o.outcome == "accepted" and o.detail["d"] == 0.5 and o.detail["doses"] == [1.0, 0.5]
    assert designer.calls == 1


def test_12_no_valid_proposal_does_not_fall_back_to_the_library(tmp_path: Path) -> None:
    empty: tuple[str, dict[str, Any]] = ("propose_interventions", {"families": []})
    _, outcomes, _designer, sub = _run(tmp_path, {"7": "footer"}, empty)
    o = outcomes[0]
    assert o.outcome == "dropped" and o.reason == "no_valid_proposal"
    assert not any(e.kind in ("families", "solvable", "bracket") for e in _events(tmp_path / "run"))
    assert {ph for _, ph, _ in sub.calls} == {"estimate"}


def test_high_parse_rejects_library_copies_missing_summary_and_bad_axis() -> None:
    from aea import exemplars

    got = parse_high(
        {
            "families": [
                {
                    "name": "copy",
                    "axis": "O",
                    "mechanism_summary": "m",
                    "rules_code": exemplars.prompt_text("footer_mask"),
                },
                {"name": "nosum", "axis": "O", "mechanism_summary": "", "rules_code": CASE_FLIP},
            ]
        }
    )
    assert not got.families and len(got.rejected) == 2
    assert "library" in got.rejected[0] and "mechanism_summary" in got.rejected[1]
    got = parse_high(
        {
            "families": [
                {"name": "ax", "axis": "Z", "mechanism_summary": "m", "rules_code": CASE_FLIP}
            ]
        }
    )
    assert not got.families and "axis" in got.rejected[0]


def test_designer_failure_is_an_infra_error_not_a_fallback(tmp_path: Path) -> None:
    from aea.errors import InfraError

    def boom(request: ChatRequest) -> Any:
        raise InfraError("provider down", kind="provider")

    sub = FakeSubstrate({"7": "footer"}, seed=3, with_designer=True, designer_fn=boom)
    ctrl = Controller(LLM, sub, tmp_path / "run", "r1", arm="L")
    o = ctrl.run([TaskRef("7", 7)])[0]
    assert o.outcome == "infra_error" and ctrl.completed_tasks() == set()
    assert not any(e.kind == "families" for e in _events(tmp_path / "run"))
    sub2 = FakeSubstrate({"7": "footer"}, seed=3)  # no designer at all: also infra_error
    o2 = Controller(LLM, sub2, tmp_path / "run2", "r2", arm="L").run([TaskRef("7", 7)])[0]
    assert o2.outcome == "infra_error" and o2.detail["kind"] == "config"


# ------------------------------------------------------------------ LOW: brief tests 13 to 31
REF_STAGE = {
    "source": "reference",
    "trajectory_id": "reference",
    "step": 2,
    "mechanism_summary": "after pickup",
}
FAIL_STAGE = {
    "source": "failure",
    "trajectory_id": "F1",
    "step": 3,
    "mechanism_summary": "wandering",
}
LOW_BOTH = ("select_stages", {"stages": [REF_STAGE, FAIL_STAGE]})


def test_13_16_19_20_low_requests_the_reference_lazily_under_the_lock(tmp_path: Path) -> None:
    seen_locked: list[bool] = []
    designer = ScriptedDesigner(LOW_BOTH)
    sub = FakeSubstrate({"9": "random"}, seed=3, with_designer=True, designer_fn=designer)

    def open_fn(task: Any) -> Any:
        seen_locked.append(SESSION_LOCK._is_owned())  # type: ignore[attr-defined]
        return sub.open_session(TaskRef(task.task_id, task.seed), None, None)

    ref = ExpertReference(open_fn, max_steps=20)
    ctrl = Controller(LLM, sub, tmp_path / "run", "r1", arm="L", reference=ref)
    o = ctrl.run([TaskRef("9", 9)])[0]
    assert o.regime == "zero" and seen_locked == [True]  # 13, 16: once, under SESSION_LOCK
    ev = _events(tmp_path / "run")
    r = next(e for e in ev if e.kind == "reference")
    assert r.payload["available"] and r.payload["n_steps"] == len(PLAN)
    text = designer.requests[0].messages[1].content
    assert designer.requests[0].tools == (DESIGN_LOW_TOOL,)
    assert "REGIME: LOW (zero)" in text and "Trajectory F1 - FAILURE" in text  # 19
    assert "PRIVILEGED REFERENCE" in text and "step 4: move x to b" in text  # 20
    assert designer.calls == 1


def test_14_15_band_and_saturated_never_request_the_reference(tmp_path: Path) -> None:
    calls: list[str] = []

    def provider(task: Any) -> Reference:
        calls.append(task.task_id)
        return Reference(True, "pass", tuple(PLAN))

    designer = ScriptedDesigner(HIGH_OK)
    sub = TableSubstrate({None: [True, False] * 8, 1.0: SAT}, designer)
    o = Controller(LLM, sub, tmp_path / "band", "r1", arm="L", reference=provider).run(
        [TaskRef("5", 5)]
    )[0]
    assert o.outcome == "kept" and calls == [] and designer.calls == 0  # 14
    _, outcomes, _designer2, _ = _run(tmp_path, {"7": "footer"}, HIGH_OK, reference=provider)
    assert outcomes[0].regime == "saturated" and calls == []  # 15
    assert not any(e.kind == "reference" for e in _events(tmp_path / "run"))


def test_17_18_27_reference_never_reaches_learner_facing_artifacts(tmp_path: Path) -> None:
    """A reference cut at step 2: the staged prefix carries PLAN[:2] (+ look) and nothing past the
    cut appears in any rollout candidate, any trace step, the corpus, the events or the kept
    designer record."""
    _, outcomes, designer, sub = _run(
        tmp_path, {"9": "staged"}, ("select_stages", {"stages": [REF_STAGE]})
    )
    o = outcomes[0]
    assert o.outcome == "accepted" and o.regime == "zero"
    run = tmp_path / "run"
    beyond = PLAN[2:]
    for line in (run / "traces.jsonl").read_text().splitlines():
        r = json.loads(line)
        prefix = [a["kwargs"]["text"] for a in r["candidate"]["in_env_actions"]]
        assert prefix in ([], [*PLAN[:2], "look"])  # 27: the prefix up to the cut only
        for s in r["steps"]:
            assert s["raw_action"]["kwargs"]["text"] not in beyond or r["success"]  # 18
    entry = read_corpus(run / "corpus.jsonl")[0]
    assert [a["kwargs"]["text"] for a in entry.in_env_actions] == [*PLAN[:2], "look"]
    assert entry.aea.kind == "stage" and entry.aea.t == 2 and entry.stage_budget == 100
    for name in ("events.jsonl", "designer_calls.jsonl", "corpus.jsonl"):
        blob = (run / name).read_text()
        assert all(a not in blob for a in beyond), name
    rec = json.loads((run / "designer_calls.jsonl").read_text().splitlines()[0])
    assert rec["reference_used"] and "[content withheld]" in rec["evidence"]
    assert "move x to b" not in rec["evidence"] and rec["reference_steps"] == 4
    assert "move x to b" in designer.requests[0].messages[1].content  # 17: designer only
    # the policy prompt: the fake substrate has none; every rollout was on the compiled prefix
    assert all(ph in ("estimate", "probe") for _, ph, _ in sub.calls)


def test_21_failure_only_low_works_without_a_reference(tmp_path: Path) -> None:
    _, outcomes, designer, _ = _run(
        tmp_path, {"9": "random"}, ("select_stages", {"stages": [FAIL_STAGE]}), reference=None
    )
    o = outcomes[0]
    ev = _events(tmp_path / "run")
    r = next(e for e in ev if e.kind == "reference")
    assert r.payload == {
        "task_id": "9",
        "requested": True,
        "available": False,
        "reason": "no_provider",
    }
    text = designer.requests[0].messages[1].content
    assert "PRIVILEGED REFERENCE" not in text and "Trajectory F1 - FAILURE" in text
    assert o.outcome in ("accepted", "dropped") and o.reason != "no_valid_proposal"
    assert any(e.kind == "stage_candidates" and e.payload["source"] == "designer" for e in ev)
    failing = ExpertReference(
        lambda task: (_ for _ in ()).throw(RuntimeError("expert down")), max_steps=5
    )
    got = failing(TaskRef("9", 9))
    assert not got.ok and "expert down" in got.reason and got.n_steps == 0


def test_22_26_low_parsing_is_grounded_and_capped() -> None:
    fails = [_trace(False, 5), _trace(False, 7)]
    ids = {"F1": fails[0].episode_id, "F2": fails[1].episode_id}
    ref = Reference(True, "pass", tuple(PLAN))
    ok = {"mechanism_summary": "m"}
    got = parse_low(
        {
            "stages": [
                {"source": "failure", "trajectory_id": "F2", "step": 7, **ok},
                {"source": "reference", "trajectory_id": "reference", "step": 4, **ok},
                {"source": "failure", "trajectory_id": "F1", "step": 1, **ok},
            ]
        },
        failures=fails,
        trajectory_ids=ids,
        reference=ref,
    )
    assert [(p.source, p.trajectory_id, p.step) for p in got.stages] == [
        ("failure", "F2", 7),
        ("reference", "reference", 4),
    ]  # 22: at most two, designer order kept
    assert got.stages[0].episode_id == fails[1].episode_id and got.stages[1].episode_id is None
    bad = parse_low(
        {
            "stages": [
                {"source": "failure", "trajectory_id": "F9", "step": 1, **ok},  # 24
                {"source": "failure", "trajectory_id": "F1", "step": 6, **ok},  # 25
            ]
        },
        failures=fails,
        trajectory_ids=ids,
        reference=ref,
    )
    assert not bad.stages and len(bad.rejected) == 2
    assert "not a supplied failure" in bad.rejected[0] and "outside 1..5" in bad.rejected[1]
    bad = parse_low(
        {
            "stages": [
                {"source": "reference", "trajectory_id": "reference", "step": 5, **ok},  # 26
                {"source": "reference", "trajectory_id": "reference", "step": 0, **ok},
            ]
        },
        failures=fails,
        trajectory_ids=ids,
        reference=ref,
    )
    assert not bad.stages and all("outside 1..4" in r for r in bad.rejected)
    none = parse_low(
        {"stages": [{"source": "reference", "trajectory_id": "reference", "step": 1, **ok}]},
        failures=fails,
        trajectory_ids=ids,
        reference=None,
    )
    assert not none.stages and "no reference was supplied" in none.rejected[0]
    assert (
        "step is not an integer"
        in parse_low(
            {"stages": [{"source": "failure", "trajectory_id": "F1", "step": "x", **ok}]},
            failures=fails,
            trajectory_ids=ids,
            reference=None,
        ).rejected[0]
    )


def test_23_28_failure_stage_points_at_the_real_trace_and_is_compiled(tmp_path: Path) -> None:
    _, _outcomes, _designer, sub = _run(
        tmp_path, {"9": "random"}, ("select_stages", {"stages": [FAIL_STAGE]}), reference=None
    )
    run = tmp_path / "run"
    ev = _events(run)
    prop = next(e for e in ev if e.kind == "llm_stage_proposals")
    assert prop.payload["accepted"] == [{"source": "failure", "trajectory_id": "F1", "step": 3}]
    rec = json.loads((run / "designer_calls.jsonl").read_text().splitlines()[0])
    f1 = rec["evidence"].split("Trajectory F1")[1].split("Trajectory")[0]
    first3 = [
        ln.split("action: ", 1)[1].split("  [")[0] for ln in f1.splitlines() if "action: " in ln
    ][:3]
    sc = next(e for e in ev if e.kind == "stage_candidates")
    cid = sc.payload["certified"][0]
    # the compiled prefix = the effective actions among the first three of F1, then look
    assert any(ph == "probe" for _, ph, _ in sub.calls) and sc.payload["kinds"][cid] == "failure"
    traces = [json.loads(line) for line in (run / "traces.jsonl").read_text().splitlines()]
    staged = next(t for t in traces if t["candidate"]["in_env_actions"])
    prefix = [a["kwargs"]["text"] for a in staged["candidate"]["in_env_actions"]]
    assert prefix[-1] == "look" and all(a in first3 for a in prefix[:-1])


def test_29_30_only_the_policy_probe_accepts_a_stage(tmp_path: Path) -> None:
    """The expert certifies every reference cut (solvable by construction from its own path);
    the random policy is dead there -> dropped, and the staged policy is in band -> accepted."""
    _, dead, _, _ = _run(
        tmp_path / "a", {"9": "random"}, ("select_stages", {"stages": [REF_STAGE]})
    )
    o = dead[0]
    ev = _events(tmp_path / "a" / "run")
    sc = next(e for e in ev if e.kind == "stage_candidates")
    assert len(sc.payload["certified"]) == 1 and not sc.payload["rejected"]  # 29: certified ...
    assert o.outcome == "dropped" and o.reason == "dead"  # ... but not accepted
    pr = next(e for e in ev if e.kind == "probe")
    assert pr.payload["profile"][0]["verdict"] == "too_hard" and pr.payload["accepted"] is None
    _, alive, _, _ = _run(
        tmp_path / "b", {"9": "staged"}, ("select_stages", {"stages": [REF_STAGE]})
    )
    o = alive[0]
    assert o.outcome == "accepted" and o.detail["profile"][0]["verdict"] == "in_band"  # 30
    assert o.detail["profile"][0]["successes"] == 4 and o.detail["profile"][0]["n"] == 8


def test_31_no_valid_low_proposal_means_dropped_not_midpoint(tmp_path: Path) -> None:
    bad = (
        "select_stages",
        {
            "stages": [
                {"source": "failure", "trajectory_id": "F7", "step": 2, "mechanism_summary": "m"}
            ]
        },
    )
    _, outcomes, designer, sub = _run(tmp_path, {"9": "random"}, bad)
    o = outcomes[0]
    assert o.outcome == "dropped" and o.reason == "no_valid_proposal" and designer.calls == 1
    ev = _events(tmp_path / "run")
    assert not any(e.kind in ("stage_candidates", "probe") for e in ev)
    assert {ph for _, ph, _ in sub.calls} == {"estimate"}  # only the estimate ran


def test_low_ordering_is_the_designer_order(tmp_path: Path) -> None:
    both = ("select_stages", {"stages": [FAIL_STAGE, REF_STAGE]})
    _, _outcomes, _, _ = _run(tmp_path, {"9": "random"}, both)
    pr = next(e for e in _events(tmp_path / "run") if e.kind == "probe")
    assert [p["source"] for p in pr.payload["profile"]] == ["failure", "reference"]
    assert [p["t"] for p in pr.payload["profile"]] == [3, 2]


def test_evidence_is_bounded_and_deterministic() -> None:
    b = dz.EvidenceBounds(steps_head=2, steps_tail=1, obs_chars=20, total_chars=2000)
    long = _trace(False, 30)
    ev = serialize_low([long], 0.0, 10, Reference(True, "pass", tuple(PLAN)), b)
    assert "... 27 steps omitted ..." in ev.text and len(ev.text) <= 2000
    assert len(re.findall(r"^step \d+:", ev.text, re.M)) == 3 + len(PLAN)  # 2 + 1 kept, 4 ref
    assert ev.trajectory_ids == {"F1": long.episode_id}
    assert (
        ev.sha256 == serialize_low([long], 0.0, 10, Reference(True, "pass", tuple(PLAN)), b).sha256
    )
    small = serialize_low([long], 0.0, 10, None, dz.EvidenceBounds(total_chars=400))
    assert "evidence truncated" in small.text and len(small.text) <= 400
    assert dz.task_goal([long]) == "put x in b"
    assert dz.task_goal([]) == ""


# ------------------------------------------------------------------ phase 2.1: issues 1 to 3
ACTION_GATE = """
class _Rules(Rules):
    DOSE = __DOSE__

    def filter_action(self, action, env_state):
        if self.DOSE > 0.5 and action.kwargs.get("text") == "take x from a":
            return Blocked(reason="gated")
        return action
"""


def _long_trace(n: int) -> Trace:
    """A failure whose every step carries a full-length observation and reasoning."""
    t = _trace(False, n)
    for i, st in enumerate(t.steps):
        st.raw_observation = Observation(text=f"Task: put x in b\n\n{'x' * 400} {i}")
        st.filtered_observation = st.raw_observation
        st.policy_raw_response = f"<think>{'y' * 400}</think><action>look</action>"
    return t


def _guard_events(run: Path) -> list[Any]:
    return [e for e in _events(run) if e.kind == "solvable"]


def test_issue1_a_llm_declared_o_axis_does_not_grant_by_construction(tmp_path: Path) -> None:
    """A: an llm_v1 O-axis proposal goes through the real guard (witness replay here)."""
    _, _outcomes, _designer, _sub = _run(tmp_path, {"7": "footer"}, HIGH_OK)
    guards = _guard_events(tmp_path / "run")
    assert len(guards) == 1 and guards[0].payload["family"] == "case_flip"
    assert guards[0].payload["source"] == "policy_replay" and guards[0].payload["ok"]
    assert guards[0].payload["detail"] == {"n_steps": 4}  # the witness was actually replayed


def test_issue1_b_contradictory_axis_label_cannot_bypass_the_guard(tmp_path: Path) -> None:
    """B: axis = O declared, but the code gates an action (filter_action). The label is
    metadata; the guard runs, the witness is blocked, the oracle is consulted."""
    lying = (
        "propose_interventions",
        {
            "families": [
                {
                    "name": "gate",
                    "axis": "O",
                    "mechanism_summary": "declared O, actually blocks the pickup",
                    "rules_code": ACTION_GATE,
                }
            ]
        },
    )
    _, outcomes, _designer, _sub = _run(tmp_path, {"2": "expert"}, lying)
    guards = _guard_events(tmp_path / "run")
    assert len(guards) == 1 and guards[0].payload["source"] != "by_construction"
    assert guards[0].payload["source"] == "uncertified" and not guards[0].payload["ok"]
    assert "policy_replay" in guards[0].payload["detail"]  # replay tried and blocked
    assert any(k.startswith("oracle_") for k in guards[0].payload["detail"])  # oracle tried
    o = outcomes[0]
    assert o.outcome == "dropped" and o.reason == "no_leverage"  # skipped as uncertified
    assert not any(e.kind in ("bracket", "no_leverage") for e in _events(tmp_path / "run"))


def test_issue1_c_v04_o_axis_family_keeps_by_construction(tmp_path: Path) -> None:
    """C: the trusted v0.4 path is unchanged (the golden pins it too): a proposer O-axis family
    is solvable by construction there."""
    designer = ScriptedDesigner(("propose_families", HIGH_OK[1]))
    sub = FakeSubstrate({"7": "footer"}, seed=3, with_designer=True, designer_fn=designer)
    ctrl = Controller(AEAConfig(), sub, tmp_path / "run", "r1", arm="A", use_proposer=True)
    ctrl.run([TaskRef("7", 7)])
    src = {e.payload["family"]: e.payload["source"] for e in _guard_events(tmp_path / "run")}
    assert src["case_flip"] == "by_construction" and src["footer_mask"] == "by_construction"


def test_issue2_reference_survives_worst_case_truncation() -> None:
    """Three very long failures plus a reference under the default bound: the reference block
    is intact and precedes the failures; ``reference_used`` is read from the bounded text."""
    long = [_long_trace(400) for _ in range(3)]
    ref = Reference(True, "pass", tuple(PLAN))
    unbounded = serialize_low(long, 0.0, 16, ref, dz.EvidenceBounds(total_chars=10**7))
    assert len(unbounded.text) > dz.BOUNDS.total_chars  # the default bound really cuts
    ev = serialize_low(long, 0.0, 16, ref)
    assert len(ev.text) == dz.BOUNDS.total_chars and "evidence truncated" in ev.text
    block_start = ev.text.index("PRIVILEGED REFERENCE")
    fails_start = ev.text.index("FAILED CURRENT-POLICY TRAJECTORIES")
    assert block_start < fails_start
    for i, a in enumerate(PLAN):
        assert f"step {i + 1}: {a}" in ev.text[block_start:fails_start]
    assert ev.reference_used
    assert "Trajectory F1 - FAILURE (400 steps)" in ev.text  # failures are what got cut
    kept = ev.redacted[ev.redacted.index("PRIVILEGED") : ev.redacted.index("FAILED CURRENT")]
    assert "[content withheld]" in kept and "move x to b" not in kept  # metadata only
    # metadata matches presence in every case
    assert not serialize_low(long, 0.0, 16, None).reference_used
    assert not serialize_low(long, 0.0, 16, Reference(False, "expert_stuck")).reference_used
    tiny = dz.EvidenceBounds(total_chars=60)  # nothing but the header fits
    cut = serialize_low(long, 0.0, 16, ref, tiny)
    assert "PRIVILEGED REFERENCE (" not in cut.text and not cut.reference_used


def test_issue2_low_run_metadata_matches_the_designer_prompt(tmp_path: Path) -> None:
    _, _o, designer, _sub = _run(tmp_path, {"9": "random"}, LOW_BOTH)
    prompt = designer.requests[0].messages[1].content
    rec = json.loads((tmp_path / "run" / "designer_calls.jsonl").read_text().splitlines()[0])
    assert rec["reference_used"] and "PRIVILEGED REFERENCE (" in prompt
    assert prompt.index("PRIVILEGED REFERENCE") < prompt.index("FAILED CURRENT-POLICY")


def test_issue3_production_wiring_injects_the_expert_only_under_llm_v1(tmp_path: Path) -> None:
    """The substrate-level wiring the drivers call: None for v0.4 (never requested); under
    llm_v1 a lazy ExpertReference over the substrate's own sessions that runs only on zero."""
    from aea.substrate import reference_provider

    opened: list[str] = []
    designer = ScriptedDesigner(LOW_BOTH)
    sub = FakeSubstrate(
        {"9": "random", "7": "footer"}, seed=3, with_designer=True, designer_fn=designer
    )
    original = sub.open_session

    def counting(task: TaskRef, cand: Candidate | None, ro: dict[str, Any] | None) -> Session:
        if cand is None and ro is None:  # a reset-state session with no candidate: the expert
            opened.append(task.task_id)
        return original(task, cand, ro)

    sub.open_session = counting  # type: ignore[method-assign, assignment]
    assert reference_provider(AEAConfig(), sub.open_session) is None  # v0.4: nothing to inject
    provider = reference_provider(LLM, sub.open_session)
    assert isinstance(provider, ExpertReference) and opened == []  # constructing runs nothing
    ctrl = Controller(LLM, sub, tmp_path / "run", "r1", arm="L", reference=provider)
    ctrl.run([TaskRef("7", 7), TaskRef("9", 9)])  # saturated first, then zero
    assert opened == ["9"]  # the expert ran once, on the zero task only
    ev = _events(tmp_path / "run")
    refs = [e for e in ev if e.kind == "reference"]
    assert [e.payload["task_id"] for e in refs] == ["9"]
    assert refs[0].payload["requested"] and refs[0].payload["available"]
    assert refs[0].payload["n_steps"] == len(PLAN)
    de = next(e for e in ev if e.kind == "designer_evidence" and e.payload["task_id"] == "9")
    assert de.payload["reference_used"]
    low = next(r for r in designer.requests if r.tools == (DESIGN_LOW_TOOL,))
    assert "step 1: go to a" in low.messages[1].content
    # v0.4 on the same substrate: the wiring gives None and the run never emits a reference
    v04 = FakeSubstrate({"9": "random"}, seed=3)
    Controller(
        AEAConfig(),
        v04,
        tmp_path / "v04",
        "r2",
        arm="A",
        reference=reference_provider(AEAConfig(), v04.open_session),
    ).run([TaskRef("9", 9)])
    assert not any(e.kind in ("reference", "designer_evidence") for e in _events(tmp_path / "v04"))


def test_issue3_driver_site_wires_the_provider() -> None:
    """The E3 driver's Controller construction passes ``sub.reference_provider(cfg)``."""
    src = (ROOT / "scripts" / "e3.py").read_text(encoding="utf-8")
    assert "reference=sub.reference_provider(cfg)" in src
    assert "def reference_provider(self, config: AEAConfig)" in (
        ROOT / "src" / "aea" / "substrate.py"
    ).read_text(encoding="utf-8")


def test_leakage_reference_prefix_before_the_cut_only(tmp_path: Path) -> None:
    """Reference cut at k = 2: actions[:2] shape the Setup state (learner-visible by
    construction); actions[2:] appear nowhere the learner or E3-SL reads."""
    _, outcomes, designer, sub = _run(
        tmp_path, {"9": "staged"}, ("select_stages", {"stages": [REF_STAGE]})
    )
    run = tmp_path / "run"
    assert outcomes[0].outcome == "accepted"
    before, after = PLAN[:2], PLAN[2:]
    for line in (run / "traces.jsonl").read_text().splitlines():
        r = json.loads(line)
        prefix = [a["kwargs"]["text"] for a in r["candidate"]["in_env_actions"]]
        assert not set(prefix) & set(after)  # the Setup prefix stops at the cut
        if not r["success"]:  # a failed staged rollout never received an action past the cut
            assert not {s["raw_action"]["kwargs"]["text"] for s in r["steps"]} & set(after)
    entry = read_corpus(run / "corpus.jsonl")[0]
    assert not {x["kwargs"]["text"] for x in entry.in_env_actions} & set(after)
    assert [x["kwargs"]["text"] for x in entry.in_env_actions][:2] == before
    # the substrate's rollouts only ever saw the compiled prefix as the candidate
    assert all(ph in ("estimate", "probe") for _, ph, _ in sub.calls)
    assert designer.calls == 1
