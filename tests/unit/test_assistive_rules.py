"""``llm_v1_assistive_rules`` (phase 3.4, docs/design/AEA_LOW_ASSISTIVE_RULES.md): the mirrored
dose bracket, the assistive designer contract (identity at d = 0, privilege checks, <= 2
families), the controller branch on the fake world (d = 1 first, leverage, top-up, acceptance,
family handling, budget), the privilege boundary, and every other path unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

from aea import designer as dz
from aea.bracket import DoseEval
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.designer import (
    DESIGN_ASSIST_TOOL,
    ExpertReference,
    Reference,
    ReferenceStep,
    identity_at_zero,
    parse_assist,
    privilege_check,
)
from aea.errors import BudgetExhausted
from aea.evaluate import Eval, verdict
from aea.io import read_corpus
from aea.rules_control import assist_bracket, dose_order_violation
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import PLAN, FakeSubstrate
from tests.unit.test_llm_v1 import HIGH_OK, TableSubstrate, _trace
from tests.unit.test_refalign import DIAG, REF_REPLY

AR = AEAConfig(method_version="llm_v1_assistive_rules")
LLM = AEAConfig(method_version="llm_v1")
SC = AEAConfig(method_version="llm_v1_stage_control")

HINT = """
class _Rules(Rules):
    DOSE = __DOSE__

    def filter_observation(self, obs, env_state):
        if self.DOSE <= 0:
            return obs
        n = int(round(self.DOSE * 10))
        return Observation(text=obs.text + "\\nHint: " + "!" * n, data=obs.data)
"""
NOT_IDENTITY = """
class _Rules(Rules):
    DOSE = __DOSE__

    def filter_observation(self, obs, env_state):
        return Observation(text=obs.text + " (always changed)", data=obs.data)
"""
FAM = {
    "axis": "O",
    "mechanism_summary": "adds a hint whose length grows with DOSE",
    "why": "the policy never finds x",
    "direction": "easier_with_d",
}


def _reply(
    *codes: str, names: tuple[str, ...] = ("hint_a", "hint_b")
) -> tuple[str, dict[str, Any]]:
    return (
        "diagnose_and_propose_assistance",
        {
            "diagnoses": [DIAG],
            "families": [
                {"name": n, "rules_code": c, **FAM}
                for n, c in zip(names[: len(codes)], codes, strict=True)
            ],
        },
    )


def _ev(s: int, n: int) -> Eval:
    return Eval(s, n, verdict(s, n, AEAConfig()))


# ---------------------------------------------------------------- pure bracket
def _table_eval(table: dict[float, tuple[int, int]]) -> tuple[Any, list[float]]:
    probed: list[float] = []

    def evaluate_at(d: float) -> Eval:
        probed.append(d)
        return _ev(*table[d])

    return evaluate_at, probed


def test_bracket_refines_inward_from_maximum_assistance() -> None:
    # d = 1 too_easy (given), 0.5 too_hard -> lo, 0.75 mixed -> 4/8 accept
    ev, probed = _table_eval({0.5: (0, 4), 0.75: (4, 8)})
    r = assist_bracket(ev, AEAConfig(), leverage=DoseEval(1.0, _ev(4, 4)))
    assert probed == [0.5, 0.75] and r.status == "accepted" and r.accepted and r.accepted.d == 0.75
    assert r.lo == 0.5 and r.hi == 1.0
    ev2, probed2 = _table_eval({0.5: (4, 4), 0.25: (7, 8), 0.125: (0, 4), 0.1875: (1, 8)})
    r2 = assist_bracket(ev2, AEAConfig(), leverage=DoseEval(1.0, _ev(4, 4)))
    assert probed2 == [0.5, 0.25, 0.125, 0.1875] and r2.status == "exhausted"
    assert r2.lo == 0.1875 and r2.hi == 0.25  # 4 bisections, no in-band dose


def test_bracket_budget_and_order_violation() -> None:
    def broke(d: float) -> Eval:
        raise BudgetExhausted("cap", budget="search", cap=30, spent=30, task_id="x")

    assert assist_bracket(broke, AEAConfig(), leverage=DoseEval(1.0, _ev(4, 4))).status == "budget"
    assert dose_order_violation([DoseEval(0.25, _ev(4, 4)), DoseEval(0.75, _ev(0, 4))])
    assert not dose_order_violation([DoseEval(0.75, _ev(4, 4)), DoseEval(0.25, _ev(0, 4))])


# ---------------------------------------------------------------- contract checks
def test_identity_at_zero_and_privilege_checks() -> None:
    assert identity_at_zero(HINT) == []
    assert any("DOSE = 0 changes the observation" in r for r in identity_at_zero(NOT_IDENTITY))
    ref = Reference(
        True,
        "pass",
        tuple(PLAN),
        tuple(
            ReferenceStep(i + 1, f"You see shelf {i}.", ("look",), a) for i, a in enumerate(PLAN)
        ),
    )
    fails = [_trace(False, 3)]
    goal = "put x in b"
    assert privilege_check(HINT, reference=ref, failures=fails, goal=goal) == []
    leak = HINT.replace("Hint: ", "Hint: take x from a ")
    assert any(
        "reference action embedded" in r
        for r in privilege_check(leak, reference=ref, failures=fails, goal=goal)
    )
    stage = HINT + (
        "\n    def filter_action(self, action, env_state):"
        "\n        self.inner.step(action)"
        "\n        return action\n"
    )
    assert any(
        "disguised Stage" in r
        for r in privilege_check(stage, reference=ref, failures=fails, goal=goal)
    )
    cheat = HINT.replace("return obs", "env_state.won = True\n        return obs")
    assert any(
        "sets won" in r for r in privilege_check(cheat, reference=ref, failures=fails, goal=goal)
    )
    priv = HINT.replace("Hint: ", "Hint: look at shelf 2 ")  # 'shelf 2' only in the reference
    assert any(
        "privileged constants" in r
        for r in privilege_check(priv, reference=ref, failures=fails, goal=goal)
    )


def test_parse_assist_caps_validates_and_reports() -> None:
    fails = [_trace(False, 3)]
    ids = {"F1": fails[0].episode_id}
    ref = Reference(True, "pass", tuple(PLAN))
    args = {
        "diagnoses": [DIAG],
        "families": [
            {"name": "ok1", "rules_code": HINT, **FAM},
            {"name": "bad_dir", "rules_code": HINT, **{**FAM, "direction": "harder_with_d"}},
            {"name": "ok2", "rules_code": HINT.replace("!", "?"), **FAM},
        ],
    }
    got = parse_assist(args, failures=fails, trajectory_ids=ids, reference=ref, goal="put x in b")
    assert [f.name for f in got.families] == ["ok1"] and len(got.diagnoses) == 1
    assert any(
        "easier_with_d" in r for r in got.rejected
    )  # bad direction; the third is cut by the cap
    got2 = parse_assist(
        {"diagnoses": [], "families": [{"name": "nz", "rules_code": NOT_IDENTITY, **FAM}]},
        failures=fails,
        trajectory_ids=ids,
        reference=ref,
        goal="put x in b",
    )
    assert not got2.families and "DOSE = 0" in got2.rejected[0]


# ---------------------------------------------------------------- controller on the fake world
class DoseSubstrate(FakeSubstrate):
    """Probe outcomes from a table keyed by (family name, dose) parsed from the candidate's
    rules code; the estimate is all failures."""

    def __init__(self, table: dict[tuple[str, float], list[bool]], reply: Any) -> None:
        super().__init__(
            {"9": "random"}, seed=3, with_designer=True, designer_fn=ScriptedDesigner(reply)
        )
        self.table = table
        self.seen: dict[tuple[str, float], int] = {}
        self.probes: list[tuple[str, float, int]] = []

    def rollouts(self, task: TaskRef, candidate: Candidate, n: int, **kw: Any) -> list[Trace]:
        ph = kw["attribution"].phase
        self.calls.append((task.task_id, ph, n))
        if ph == "estimate":
            return [_trace(False, 3, candidate=candidate) for _ in range(n)]
        fam = ph.split(":", 1)[1]
        dose = round(float(candidate.rules_code.split("DOSE = ", 1)[1].split("\n", 1)[0]), 6)
        self.probes.append((fam, dose, n))
        key = (fam, dose)
        k = self.seen.get(key, 0)
        self.seen[key] = k + n
        pat = self.table[key]
        return [_trace(pat[(k + i) % len(pat)], candidate=candidate) for i in range(n)]


def _run_ar(
    tmp_path: Path, table: dict[tuple[str, float], list[bool]], reply: Any
) -> tuple[Any, DoseSubstrate, list[Any]]:
    sub = DoseSubstrate(table, reply)
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    ctrl = Controller(AR, sub, tmp_path / "run", "r1", arm="R", reference=ref)
    o = ctrl.run([TaskRef("9", 9)])[0]
    return o, sub, read_trace(tmp_path / "run" / "events.jsonl")


T, F = True, False


def test_d1_first_then_refine_and_accept(tmp_path: Path) -> None:
    table = {
        ("hint_a", 1.0): [T] * 8,
        ("hint_a", 0.5): [F] * 8,
        ("hint_a", 0.75): [T, F, T, F, T, F, F, T],
    }
    o, sub, ev = _run_ar(tmp_path, table, _reply(HINT))
    assert [(f, d) for f, d, _ in sub.probes] == [
        ("hint_a", 1.0),
        ("hint_a", 0.5),
        ("hint_a", 0.75),
        ("hint_a", 0.75),
    ]
    assert o.outcome == "accepted" and o.detail["d"] == 0.75 and o.detail["family"] == "hint_a"
    dc = next(e for e in ev if e.kind == "dose_control")
    assert dc.payload["direction"] == "easier_with_d" and dc.payload["status"] == "accepted"
    assert [h["verdict"] for h in dc.payload["history"]] == ["too_easy", "too_hard", "in_band"]
    entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
    assert entry.aea.kind == "knob" and entry.aea.regime == "zero" and entry.aea.d == 0.75
    assert "DOSE = 0.75" in entry.rules_code and entry.aea.source == "llm"
    assert (
        sub.designer is not None and sum(1 for _, ph, _ in sub.calls if ph.startswith("dose:")) == 4
    )
    assert not any(
        e.kind in ("families", "stage_candidates", "stage_family") for e in ev
    )  # no fallback
    guard = next(e for e in ev if e.kind == "solvable")
    assert guard.payload["family"] == "hint_a" and guard.payload["source"] == "oracle"


def test_d1_in_band_accepts_immediately(tmp_path: Path) -> None:
    o, sub, _ = _run_ar(tmp_path, {("hint_a", 1.0): [T, F] * 4}, _reply(HINT))
    assert o.outcome == "accepted" and o.detail["d"] == 1.0
    assert [(f, d) for f, d, _ in sub.probes] == [
        ("hint_a", 1.0),
        ("hint_a", 1.0),
    ]  # 4 then top-up 4


def test_second_family_only_after_first_has_no_leverage(tmp_path: Path) -> None:
    table = {("hint_a", 1.0): [F] * 8, ("hint_b", 1.0): [T, F, T, T, F, T, F, F]}
    o, sub, ev = _run_ar(tmp_path, table, _reply(HINT, HINT.replace("!", "?")))
    assert [f for f, _, _ in sub.probes] == ["hint_a", "hint_b", "hint_b"]
    assert any(e.kind == "llm_assist_proposals" for e in ev)
    assert o.outcome == "accepted" and o.detail["family"] == "hint_b"
    assert [e.payload["family"] for e in ev if e.kind == "no_leverage"] == ["hint_a"]


def test_leveraged_family_keeps_the_budget_and_no_leverage_everywhere(tmp_path: Path) -> None:
    # hint_a leveraged but exhausts 4 bisections without landing: the task ends there
    table = {
        ("hint_a", 1.0): [T] * 8,
        ("hint_a", 0.5): [T] * 8,
        ("hint_a", 0.25): [T] * 8,
        ("hint_a", 0.125): [T] * 8,
        ("hint_a", 0.0625): [T] * 8,
        ("hint_b", 1.0): [T, F] * 4,
    }
    o, sub, _ = _run_ar(tmp_path, table, _reply(HINT, HINT.replace("!", "?")))
    assert o.outcome == "dropped" and o.reason == "exhausted" and o.detail["family"] == "hint_a"
    assert all(f == "hint_a" for f, _, _ in sub.probes)  # hint_b never probed
    o2, _sub2, _ = _run_ar(
        tmp_path / "b",
        {("hint_a", 1.0): [F] * 8, ("hint_b", 1.0): [F] * 8},
        _reply(HINT, HINT.replace("!", "?")),
    )
    assert o2.outcome == "dropped" and o2.reason == "no_leverage"


def test_budget_cap_including_the_estimate(tmp_path: Path) -> None:
    mixed = [T, F, T, T, T, T, T, F]  # 6/8 too_easy after top-up, 8 rollouts each
    table = {("hint_a", 1.0): mixed, ("hint_a", 0.5): mixed, ("hint_a", 0.25): mixed}
    o, _sub, _ = _run_ar(tmp_path, table, _reply(HINT))
    assert o.n_search <= 30
    assert (
        o.outcome == "dropped" and o.reason == "budget"
    )  # 10 + 8 + 8 = 26, the next 4 fits, its top-up does not


def test_no_valid_proposal_and_reference_unavailable_have_no_fallback(tmp_path: Path) -> None:
    o, sub, _ = _run_ar(tmp_path, {}, _reply(NOT_IDENTITY))
    assert o.outcome == "dropped" and o.reason == "no_valid_proposal" and not sub.probes
    sub2 = DoseSubstrate({}, _reply(HINT))
    o2 = Controller(
        AR,
        sub2,
        tmp_path / "b",
        "r1",
        arm="R",
        reference=lambda task: Reference(False, "expert_stuck"),
    ).run([TaskRef("9", 9)])[0]
    assert o2.outcome == "dropped" and o2.reason == "reference_unavailable" and not sub2.probes


def test_one_designer_call_with_the_assist_tool_and_rich_evidence(tmp_path: Path) -> None:
    sub = DoseSubstrate({("hint_a", 1.0): [T, F] * 4}, _reply(HINT))
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    Controller(AR, sub, tmp_path / "run", "r1", arm="R", reference=ref).run([TaskRef("9", 9)])
    designer = sub._designer
    assert isinstance(designer, ScriptedDesigner) and designer.calls == 1
    req = designer.requests[0]
    assert req.tools == (DESIGN_ASSIST_TOOL,)
    assert "PRIVILEGED REFERENCE TRAJECTORY" in req.messages[1].content
    assert "DOSE = 0 must leave the environment EXACTLY unchanged" in req.messages[0].content
    assert 'Action(name="do", kwargs={"text": "<command>"})' in req.messages[0].content
    rec = json.loads((tmp_path / "run" / "designer_calls.jsonl").read_text().splitlines()[0])
    assert rec["mode"] == "assist" and rec["families"][0]["name"] == "hint_a" and rec["diagnoses"]


def test_reference_future_content_not_learner_facing(tmp_path: Path) -> None:
    table = {
        ("hint_a", 1.0): [T] * 8,
        ("hint_a", 0.5): [F] * 8,
        ("hint_a", 0.75): [T, F, T, F, T, F, F, T],
    }
    _run_ar(tmp_path, table, _reply(HINT))
    run = tmp_path / "run"
    for name in ("traces.jsonl", "corpus.jsonl", "events.jsonl"):
        blob = (run / name).read_text()
        assert "PRIVILEGED REFERENCE" not in blob
    for line in (run / "traces.jsonl").read_text().splitlines():
        r = json.loads(line)
        assert not r["candidate"]["in_env_actions"]  # no Setup prefix at all on this variant
        assert not any(a in r["candidate"]["rules_code"] for a in PLAN)
    entry = read_corpus(run / "corpus.jsonl")[0]
    assert not any(a in entry.rules_code for a in PLAN)


# ---------------------------------------------------------------- other paths unchanged
def _stream(run: Path) -> list[tuple[str, dict[str, Any]]]:
    return [(e.kind, e.payload) for e in read_trace(run / "events.jsonl") if e.kind != "run_start"]


def test_high_and_mid_identical_to_llm_v1(tmp_path: Path) -> None:
    from tests.unit.test_stage_control import _expert

    for cfg, tag in ((LLM, "v1"), (AR, "ar")):
        designer = ScriptedDesigner(HIGH_OK)
        sub = FakeSubstrate({"7": "footer"}, seed=3, with_designer=True, designer_fn=designer)
        ref = _expert(sub)
        o = Controller(cfg, sub, tmp_path / f"high-{tag}", "r1", arm="X", reference=ref).run(
            [TaskRef("7", 7)]
        )[0]
        assert o.regime == "saturated" and designer.calls == 1
    assert _stream(tmp_path / "high-v1") == _stream(tmp_path / "high-ar")
    calls: list[str] = []

    def provider(task: Any) -> Reference:
        calls.append(task.task_id)
        return Reference(True, "pass", tuple(PLAN))

    for cfg, tag in ((LLM, "v1"), (AR, "ar")):
        designer = ScriptedDesigner(HIGH_OK)
        sub2 = TableSubstrate({None: [True, False] * 8, 1.0: [True] * 8}, designer)
        o = Controller(cfg, sub2, tmp_path / f"mid-{tag}", "r1", arm="X", reference=provider).run(
            [TaskRef("5", 5)]
        )[0]
        assert o.outcome == "kept" and designer.calls == 0 and calls == []
    assert _stream(tmp_path / "mid-v1") == _stream(tmp_path / "mid-ar")


def test_stage_control_and_refalign_unchanged_by_the_new_variant(tmp_path: Path) -> None:
    from tests.unit.test_stage_control import DepthSubstrate

    sub = DepthSubstrate({3: [True] * 8, 1: [False] * 8, 2: [True, False] * 4})
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    o = Controller(SC, sub, tmp_path / "sc", "r1", arm="C", reference=ref).run([TaskRef("9", 9)])[0]
    assert o.outcome == "accepted" and o.detail["t"] == 2
    ev = read_trace(tmp_path / "sc" / "events.jsonl")
    assert any(e.kind == "stage_control" for e in ev) and not any(
        e.kind == "dose_control" for e in ev
    )
    designer = ScriptedDesigner(REF_REPLY)
    sub2 = FakeSubstrate({"9": "staged"}, seed=3, with_designer=True, designer_fn=designer)
    ref2 = ExpertReference(
        lambda task: sub2.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    o2 = Controller(
        AEAConfig(method_version="llm_v1_refalign"),
        sub2,
        tmp_path / "ra",
        "r1",
        arm="R",
        reference=ref2,
    ).run([TaskRef("9", 9)])[0]
    assert o2.outcome == "accepted" and designer.calls == 1


def test_v04_never_reaches_assistive_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import aea.controller as ctl

    def trap(*a: Any, **k: Any) -> Any:
        raise AssertionError("assistive rules entered under v0.4")

    monkeypatch.setattr(ctl, "design_low_assist", trap)
    monkeypatch.setattr(ctl, "assist_bracket", trap)
    sub = FakeSubstrate({"9": "random"}, seed=3)
    o = Controller(AEAConfig(), sub, tmp_path / "run", "r1", arm="A", use_proposer=False).run(
        [TaskRef("9", 9)]
    )[0]
    assert o.regime == "zero"
    assert (
        dz.DESIGN_ASSIST_TOOL["function"]["parameters"]["properties"]["families"]["maxItems"] == 2
    )
