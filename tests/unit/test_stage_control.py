"""``llm_v1_stage_control`` (phase 3.3b, docs/design/AEA_LOW_STAGE_CONTROL.md): the pure integer
bracket, the controller branch on the fake world (t_max, first probe, updates, acceptance,
outcomes, budget), the privilege boundary, and MID / HIGH / refalign / v0.4 unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from envharness.core.types import Candidate, Trace

from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.designer import ExpertReference, Reference
from aea.errors import BudgetExhausted
from aea.evaluate import Eval
from aea.io import read_corpus
from aea.stage_control import DepthEval, InvalidStageError, ordering_contradiction, stage_bracket
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import PLAN, FakeSubstrate
from tests.unit.test_llm_v1 import HIGH_OK, _trace
from tests.unit.test_refalign import REF_REPLY

SC = AEAConfig(method_version="llm_v1_stage_control")
LLM = AEAConfig(method_version="llm_v1")
REF = AEAConfig(method_version="llm_v1_refalign")


# ---------------------------------------------------------------- pure bracket
def _ev(s: int, n: int) -> Eval:
    from aea.evaluate import verdict

    return Eval(s, n, verdict(s, n, AEAConfig()))


def _table_eval(table: dict[int, tuple[int, int]]) -> tuple[Any, list[int]]:
    probed: list[int] = []

    def evaluate_at(t: int) -> Eval:
        probed.append(t)
        s, n = table[t]
        return _ev(s, n)

    return evaluate_at, probed


def test_first_probe_is_t_max_and_in_band_accepts_immediately() -> None:
    ev, probed = _table_eval({7: (4, 8)})
    r = stage_bracket(ev, 7)
    assert probed == [7] and r.status == "accepted" and r.accepted and r.accepted.t == 7


def test_t_max_too_hard_is_no_stage_leverage() -> None:
    ev, probed = _table_eval({7: (0, 4)})
    r = stage_bracket(ev, 7)
    assert probed == [7] and r.status == "no_stage_leverage" and r.hi is None and r.lo == 0


def test_too_easy_updates_hi_too_hard_updates_lo_then_accepts() -> None:
    ev, probed = _table_eval({8: (4, 4), 4: (0, 4), 6: (3, 8)})
    r = stage_bracket(ev, 8)
    assert probed == [8, 4, 6]  # t_max, floor((0+8)/2), floor((4+8)/2)
    assert r.status == "accepted" and r.accepted and r.accepted.t == 6
    assert r.lo == 4 and r.hi == 8 and r.unique_cuts == 3


def test_mixed_first_batch_tops_up_and_8_of_8_classes() -> None:
    # 6..8 of 8 -> too_easy (hi), 0..2 of 8 -> too_hard (lo), 3..5 -> accept
    ev, probed = _table_eval({8: (7, 8), 4: (2, 8), 6: (5, 8)})
    r = stage_bracket(ev, 8)
    assert probed == [8, 4, 6] and r.status == "accepted" and r.accepted and r.accepted.t == 6
    assert [h.eval.verdict for h in r.history] == ["too_easy", "too_hard", "in_band"]


def test_one_action_gap_is_resolution_limited_and_no_depth_probed_twice() -> None:
    ev, probed = _table_eval({4: (4, 4), 2: (0, 4), 3: (4, 4)})
    r = stage_bracket(ev, 4)
    assert probed == [4, 2, 3] and r.status == "resolution_limited"
    assert r.lo == 2 and r.hi == 3 and len(probed) == len(set(probed))
    ev2, probed2 = _table_eval({1: (4, 4)})
    r2 = stage_bracket(ev2, 1)  # t_max = 1 too easy: lo 0, hi 1 -> no integer between
    assert probed2 == [1] and r2.status == "resolution_limited"


def test_injected_ordering_contradiction_is_nonmonotonic_profile() -> None:
    hist = [DepthEval(2, _ev(4, 4)), DepthEval(5, _ev(0, 4))]  # easy below hard
    assert ordering_contradiction(hist)
    assert not ordering_contradiction([DepthEval(5, _ev(4, 4)), DepthEval(2, _ev(0, 4))])
    # through the bracket the contradiction is structurally unreachable; the invariant is
    # exercised by feeding a history whose second verdict violates the first
    calls: list[int] = []

    def weird(t: int) -> Eval:
        calls.append(t)
        return _ev(4, 4) if t == 8 else _ev(0, 4)  # 8 easy, 4 hard: consistent bracket

    r = stage_bracket(weird, 8)
    assert r.status == "resolution_limited" and calls == [8, 4, 6, 7]
    assert not ordering_contradiction(r.history)


def test_budget_and_invalid_stage_end_the_search() -> None:
    def broke(t: int) -> Eval:
        raise BudgetExhausted("cap", budget="search", cap=30, spent=30, task_id="x")

    assert stage_bracket(broke, 5).status == "budget"

    def invalid(t: int) -> Eval:
        raise InvalidStageError("bad")

    assert stage_bracket(invalid, 5).status == "invalid_stage"


# ---------------------------------------------------------------- controller on the fake world
class DepthSubstrate(FakeSubstrate):
    """Probe outcomes read from a table keyed by the Setup prefix depth (plan actions in the
    candidate, ignoring the trailing look); the estimate (no candidate) is all failures."""

    def __init__(self, table: dict[int, list[bool]]) -> None:
        super().__init__(
            {"9": "random"}, seed=3, with_designer=True, designer_fn=ScriptedDesigner(REF_REPLY)
        )
        self.table = table
        self.seen: dict[int, int] = {}
        self.probed_depths: list[int] = []

    def rollouts(self, task: TaskRef, candidate: Candidate, n: int, **kw: Any) -> list[Trace]:
        self.calls.append((task.task_id, kw["attribution"].phase, n))
        depth = len([a for a in candidate.in_env_actions if a.kwargs.get("text") in PLAN])
        if kw["attribution"].phase == "estimate":
            return [_trace(False, 3, candidate=candidate) for _ in range(n)]
        self.probed_depths.append(depth)
        k = self.seen.get(depth, 0)
        self.seen[depth] = k + n
        pat = self.table[depth]
        return [_trace(pat[(k + i) % len(pat)], candidate=candidate) for i in range(n)]


def _run_sc(tmp_path: Path, table: dict[int, list[bool]]) -> tuple[Any, DepthSubstrate, list[Any]]:
    sub = DepthSubstrate(table)
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    ctrl = Controller(SC, sub, tmp_path / "run", "r1", arm="C", reference=ref)
    o = ctrl.run([TaskRef("9", 9)])[0]
    return o, sub, read_trace(tmp_path / "run" / "events.jsonl")


def test_t_max_excludes_the_terminal_full_reference_and_first_probe_is_t_max(
    tmp_path: Path,
) -> None:
    """PLAN has 4 actions; replaying all 4 wins the fake task, so t_max = 3."""
    o, sub, ev = _run_sc(tmp_path, {3: [True] * 8, 1: [False] * 8, 2: [True, False] * 4})
    fam = next(e for e in ev if e.kind == "stage_family")
    assert fam.payload["T"] == 4 and fam.payload["t_max"] == 3
    assert fam.payload["rejected"] == [{"t": 4, "reason": "terminal"}]
    assert sub.probed_depths == [3, 1, 2, 2]  # batches: t_max first, then 1, then 2 (4 + 4)
    sc = next(e for e in ev if e.kind == "stage_control")
    assert [h["t"] for h in sc.payload["history"]] == [3, 1, 2]
    assert sc.payload["t_max_verdict"] == "too_easy" and sc.payload["status"] == "accepted"
    assert sc.payload["accepted_t"] == 2 and abs(sc.payload["accepted_d"] - 2 / 3) < 1e-9
    assert o.outcome == "accepted" and o.detail["t"] == 2
    entry = read_corpus(tmp_path / "run" / "corpus.jsonl")[0]
    assert entry.aea.kind == "stage" and entry.aea.t == 2 and entry.stage_budget == 100
    assert [a["kwargs"]["text"] for a in entry.in_env_actions] == [*PLAN[:2], "look"]
    assert not any(e.kind in ("designer_evidence", "llm_stage_proposals") for e in ev)  # no LLM
    assert not (tmp_path / "run" / "designer_calls.jsonl").exists()


def test_no_stage_leverage_when_max_assistance_is_dead(tmp_path: Path) -> None:
    o, sub, _ = _run_sc(tmp_path, {3: [False] * 8})
    assert o.outcome == "dropped" and o.reason == "no_stage_leverage"
    assert sub.probed_depths == [3]  # one 4-rollout probe only


def test_resolution_limited_on_the_fake_world(tmp_path: Path) -> None:
    o, _sub, ev = _run_sc(tmp_path, {3: [True] * 8, 1: [False] * 8, 2: [True] * 8})
    assert o.outcome == "dropped" and o.reason == "resolution_limited"
    sc = next(e for e in ev if e.kind == "stage_control")
    assert sc.payload["lo"] == 1 and sc.payload["hi"] == 2 and sc.payload["unique_cuts"] == 3


def test_budget_is_capped_at_30_including_the_estimate(tmp_path: Path) -> None:
    """Estimate 10 (fake: 4 + 2 + 2 + 2 failures), then mixed probes of 8: 8 + 8 = 16 fits, a
    third 8-probe would exceed 30 -> the bracket ends as budget."""
    table = {
        3: [True, False, True, True, True, True, True, False],
        1: [True, False, True, False] * 2,
        2: [True, False, True, True, True, True, True, False],
    }
    o, _sub, ev = _run_sc(tmp_path, table)
    assert o.n_search <= 30
    sc = next(e for e in ev if e.kind == "stage_control")
    assert all(h["n"] == 8 for h in sc.payload["history"])
    assert o.outcome in ("accepted", "dropped")
    if o.outcome == "dropped":
        assert o.reason == "budget" and o.n_search + 4 > 30


def test_reference_unavailable_has_no_fallback(tmp_path: Path) -> None:
    sub = DepthSubstrate({3: [True] * 8})
    ctrl = Controller(
        SC,
        sub,
        tmp_path / "run",
        "r1",
        arm="C",
        reference=lambda task: Reference(False, "expert_stuck"),
    )
    o = ctrl.run([TaskRef("9", 9)])[0]
    assert o.outcome == "dropped" and o.reason == "reference_unavailable"
    assert not any(ph == "probe" for _, ph, _ in sub.calls)


def test_privilege_boundary_prefix_only(tmp_path: Path) -> None:
    _run_sc(tmp_path, {3: [True] * 8, 1: [False] * 8, 2: [True, False] * 4})
    run = tmp_path / "run"
    for line in (run / "traces.jsonl").read_text().splitlines():
        r = json.loads(line)
        pre = [a["kwargs"]["text"] for a in r["candidate"]["in_env_actions"]]
        assert pre in ([], [*PLAN[:1], "look"], [*PLAN[:2], "look"], [*PLAN[:3], "look"])
    for name in ("events.jsonl", "traces.jsonl", "corpus.jsonl"):
        assert "PRIVILEGED REFERENCE" not in (run / name).read_text()
    rows = [json.loads(x) for x in (run / "privileged_references.jsonl").read_text().splitlines()]
    assert rows[0]["success"] and rows[0]["actions"] == list(PLAN)


# ---------------------------------------------------------------- other paths unchanged
def _expert(sub: FakeSubstrate) -> ExpertReference:
    return ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )


def _stream(run: Path) -> list[tuple[str, dict[str, Any]]]:
    return [(e.kind, e.payload) for e in read_trace(run / "events.jsonl") if e.kind != "run_start"]


def test_high_and_mid_identical_to_llm_v1(tmp_path: Path) -> None:
    from tests.unit.test_llm_v1 import TableSubstrate

    for cfg, tag in ((LLM, "v1"), (SC, "sc")):
        designer = ScriptedDesigner(HIGH_OK)
        sub = FakeSubstrate({"7": "footer"}, seed=3, with_designer=True, designer_fn=designer)
        ref = _expert(sub)
        o = Controller(cfg, sub, tmp_path / f"high-{tag}", "r1", arm="X", reference=ref).run(
            [TaskRef("7", 7)]
        )[0]
        assert o.regime == "saturated" and designer.calls == 1
    assert _stream(tmp_path / "high-v1") == _stream(tmp_path / "high-sc")
    calls: list[str] = []

    def provider(task: Any) -> Reference:
        calls.append(task.task_id)
        return Reference(True, "pass", tuple(PLAN))

    for cfg, tag in ((LLM, "v1"), (SC, "sc")):
        designer = ScriptedDesigner(HIGH_OK)
        sub2 = TableSubstrate({None: [True, False] * 8, 1.0: [True] * 8}, designer)
        o = Controller(cfg, sub2, tmp_path / f"mid-{tag}", "r1", arm="X", reference=provider).run(
            [TaskRef("5", 5)]
        )[0]
        assert o.outcome == "kept" and designer.calls == 0 and calls == []
    assert _stream(tmp_path / "mid-v1") == _stream(tmp_path / "mid-sc")


def test_refalign_path_unchanged_by_the_new_variant(tmp_path: Path) -> None:
    designer = ScriptedDesigner(REF_REPLY)
    sub = FakeSubstrate({"9": "staged"}, seed=3, with_designer=True, designer_fn=designer)
    ref = ExpertReference(
        lambda task: sub.open_session(TaskRef(task.task_id, task.seed), None, None), max_steps=20
    )
    o = Controller(REF, sub, tmp_path / "run", "r1", arm="R", reference=ref).run([TaskRef("9", 9)])[
        0
    ]
    ev = read_trace(tmp_path / "run" / "events.jsonl")
    assert o.outcome == "accepted" and designer.calls == 1
    assert any(e.kind == "llm_diagnosis" for e in ev) and not any(
        e.kind == "stage_control" for e in ev
    )


def test_v04_never_reaches_stage_control(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import aea.controller as ctl

    def trap(*a: Any, **k: Any) -> Any:
        raise AssertionError("stage control entered under v0.4")

    monkeypatch.setattr(ctl, "stage_bracket", trap)
    sub = FakeSubstrate({"9": "random"}, seed=3)
    o = Controller(AEAConfig(), sub, tmp_path / "run", "r1", arm="A", use_proposer=False).run(
        [TaskRef("9", 9)]
    )[0]
    assert o.regime == "zero"
