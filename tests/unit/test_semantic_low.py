"""Admission integration: semantic outcomes precede every unchanged optimizer gate."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import aea.controller as ctl
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.designer import AssistFamily
from aea.semantic_low import LowPrivilegeScreen, SemanticAdmissionError, reachable_screen_doses
from aea.semantic_privilege import Decision, SemanticGateInput, screen_semantic_privilege
from aea.substrate import reference_provider
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import FakeSubstrate
from tests.unit.test_assistive_rules import HINT, _reply, _stream
from tests.unit.test_iterative_low import REF, _adaptation, _body, _run
from tests.unit.test_llm_v1 import HIGH_OK, TableSubstrate

SEMANTIC = AEAConfig(method_version="llm_v2_iterative_low_semantic_gate")


@pytest.mark.parametrize("verdict", ["FAIL", "UNCERTAIN"])
def test_rejected_candidate_never_reaches_solvability_or_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: Decision
) -> None:
    screens: list[str] = []

    def screen(self: LowPrivilegeScreen, family: AssistFamily) -> Any:
        screens.append(family.template)
        result = screen_semantic_privilege(SemanticGateInput(family.template, REF, "", (), "9"))
        return replace(
            result,
            decision=verdict,
            findings=tuple(replace(f, decision=verdict) for f in result.findings),
        )

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("semantic rejection reached solvability")

    monkeypatch.setattr(LowPrivilegeScreen, "screen", screen)
    monkeypatch.setattr(ctl, "solvable", forbidden)
    replies = (_reply(HINT), _reply(HINT + "\n")) if verdict == "FAIL" else (_reply(HINT),)
    outcome, sub, designer, _ = _run(tmp_path, {}, *replies, config=SEMANTIC)
    assert outcome.outcome == "dropped"
    assert _adaptation(sub) == 0 and not sub.probes
    records = [
        json.loads(line)
        for line in (tmp_path / "run/low_candidates.jsonl").read_text().splitlines()
    ]
    assert all(record["solvability"] is None and record["endpoint"] is None for record in records)
    if verdict == "FAIL":
        assert designer.calls == len(screens) == 2
        assert "REPLACE_MECHANISM" in _body(designer, 1)
        assert '"category": "privilege"' in _body(designer, 1)
    else:
        assert designer.calls == len(screens) == len(records) == 1
        assert records[0]["remaining_calls"] == 1
        assert outcome.detail["design_status"] == "inconclusive"


def test_screen_exception_stops_without_feedback_or_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("offline screen unavailable")

    monkeypatch.setattr(LowPrivilegeScreen, "screen", unavailable)
    outcome, sub, designer, _ = _run(tmp_path, {}, _reply(HINT), config=SEMANTIC)
    assert outcome.outcome == "dropped" and outcome.detail["design_status"] == "inconclusive"
    assert designer.calls == 1 and _adaptation(sub) == 0
    records = (tmp_path / "run/low_candidates.jsonl").read_text()
    assert "offline screen unavailable" in records and '"solvability": null' in records


def test_actual_offline_pass_precedes_guard_and_all_control_measurements(tmp_path: Path) -> None:
    table = {
        ("hint_a", 1.0): [True] * 4,
        ("hint_a", 0.5): [False] * 4,
        ("hint_a", 0.75): [True, False] * 4,
    }
    outcome, sub, designer, _ = _run(tmp_path, table, _reply(HINT), config=SEMANTIC)
    assert outcome.outcome == "accepted", outcome.reason
    assert outcome.detail["d"] == 0.75 and designer.calls == 1
    assert _adaptation(sub) == 16
    audits = [
        json.loads(line)
        for line in (tmp_path / "run/semantic_privilege.jsonl").read_text().splitlines()
    ]
    assert len(audits) == 1 and audits[0]["result"]["decision"] == "PASS"
    assert audits[0]["doses"] == list(reachable_screen_doses(4))
    payload = gzip.decompress(Path(audits[0]["input_artifact"]).read_bytes())
    assert hashlib.sha256(payload).hexdigest() == audits[0]["result"]["input_sha256"]
    request = json.loads(payload)
    assert "PRIVILEGED_REFERENCE_ONLY_SENTINEL" not in request["designer_evidence"]
    assert "PRIVILEGED_REFERENCE_ONLY_SENTINEL" in json.dumps(request["reference"])
    assert all(
        "PRIVILEGED_REFERENCE_ONLY_SENTINEL" not in json.dumps(probe["evidence"])
        for probe in request["probes"]
    )


def test_cheap_checks_precede_semantic_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    screens: list[str] = []
    original = LowPrivilegeScreen.screen

    def recording(self: LowPrivilegeScreen, family: AssistFamily) -> Any:
        screens.append(family.template)
        return original(self, family)

    monkeypatch.setattr(LowPrivilegeScreen, "screen", recording)
    outcome, _, designer, _ = _run(
        tmp_path,
        {("hint_a", 1.0): [True, False] * 4},
        _reply(HINT.replace("self.DOSE", "DOSE")),
        _reply(HINT),
        config=SEMANTIC,
    )
    assert outcome.outcome == "accepted", outcome.reason
    assert screens == [HINT] and designer.calls == 2
    assert "REPAIR_CODE" in _body(designer, 1)


def test_admission_bound_to_candidate_bytes_and_exact_dose(tmp_path: Path) -> None:
    screen = LowPrivilegeScreen(
        task_id="9",
        reference=REF,
        designer_evidence="",
        failures=(),
        goal="goal",
        open_original_session=lambda: FakeSubstrate({"9": "random"}).open_session(
            TaskRef("9", 9), None, None
        ),
        max_bisections=4,
        audit_dir=tmp_path,
        record=lambda record: None,
    )
    family = AssistFamily("hint", "O", HINT)
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass(family, 1.0)
    sha = hashlib.sha256(HINT.encode()).hexdigest()
    screen._admitted[sha] = reachable_screen_doses(4)
    screen.require_pass(family, 0.0625)
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass(family, 0.3)
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass(replace(family, template=HINT + "\n"), 1.0)
    assert screen.screen(family).decision == "UNCERTAIN"  # empty evidence fails closed
    with pytest.raises(SemanticAdmissionError):
        screen.require_pass(family, 1.0)  # a failed rescreen revokes an earlier admission


def test_new_variant_high_mid_and_old_low_remain_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unaffected path entered semantic gate")

    monkeypatch.setattr(LowPrivilegeScreen, "screen", forbidden)
    for config, tag in ((AEAConfig(method_version="llm_v1"), "old"), (SEMANTIC, "new")):
        designer = ScriptedDesigner(HIGH_OK)
        sub = FakeSubstrate({"7": "footer"}, seed=3, with_designer=True, designer_fn=designer)
        high = Controller(config, sub, tmp_path / f"high-{tag}", "r1", arm="X").run(
            [TaskRef("7", 7)]
        )[0]
        assert high.regime == "saturated" and designer.calls == 1
        mid_designer = ScriptedDesigner(HIGH_OK)
        mid = Controller(
            config,
            TableSubstrate({None: [True, False] * 8}, mid_designer),
            tmp_path / f"mid-{tag}",
            "r1",
            arm="X",
        ).run([TaskRef("5", 5)])[0]
        assert mid.outcome == "kept" and mid_designer.calls == 0
    assert _stream(tmp_path / "high-old") == _stream(tmp_path / "high-new")
    assert _stream(tmp_path / "mid-old") == _stream(tmp_path / "mid-new")
    outcome, _, _, _ = _run(
        tmp_path / "old-low", {("hint_a", 1.0): [True, False] * 4}, _reply(HINT)
    )
    assert outcome.outcome == "accepted"
    sub = FakeSubstrate({"9": "random"})
    assert reference_provider(SEMANTIC, sub.open_session) is not None


def test_replacement_feedback_cites_leak_probe_instead_of_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.semantic_privilege_benchmark import benchmark_cases, load_fixture, reference_from

    fixture = load_fixture()
    case = benchmark_cases(fixture)[0]
    # Exercise the real screen through the fake controller, rebinding the fixture's task ID.
    episode = replace(case.episode, task_id="9")
    monkeypatch.setattr(LowPrivilegeScreen, "_capture", lambda self: (episode,))
    outcome, sub, designer, _ = _run(
        tmp_path,
        {},
        _reply(case.source),
        _reply(case.source + "\n"),
        config=SEMANTIC,
        reference=reference_from(fixture),
    )
    assert outcome.outcome == "dropped" and designer.calls == 2 and not sub.probes
    feedback = _body(designer, 1).split("TYPED DESIGN FEEDBACK\n", 1)[1]
    packet = json.JSONDecoder().raw_decode(feedback)[0]
    reason = json.loads(packet["reason"].split(": ", 1)[1])
    assert packet["operation"] == "REPLACE_MECHANISM" and packet["category"] == "privilege"
    assert reason["findings"] and all(f["decision"] == "FAIL" for f in reason["findings"])
    assert any("sofa" in f["information"] for f in reason["findings"])
    assert all("dose=0;" not in f["activation"] for f in reason["findings"])
