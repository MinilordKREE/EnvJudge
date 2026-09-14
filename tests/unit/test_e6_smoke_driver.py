"""Offline checks of the E6 smoke driver (experiments/alfworld_e6/PREREG_SMOKE.md) before any
paid call: the frozen task selection, and the wiring (driver config == substrate config ==
controller config == llm_v1, reference provider non-None) on a recording fake substrate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from aea.config import AEAConfig
from aea.designer import ExpertReference
from aea.errors import ConfigError
from tests.fixtures.fake_substrate import FakeSubstrate

ROOT = Path(__file__).resolve().parents[2]


def _load() -> Any:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("e6_smoke", ROOT / "scripts" / "e6_smoke.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frozen_selection_is_deterministic() -> None:
    e6 = _load()
    records = e6.frozen_k16()
    assert len(records) == 30
    high, low = e6.select_tasks(records, exclude=())
    assert high == [1, 7, 12] and low == [8, 9, 10]  # smoke 1's selection, unchanged
    for t in high:
        assert records[str(t)]["successes"] == 16 and records[str(t)]["errors"] == 0
    for t in low:
        assert records[str(t)]["successes"] == 0 and records[str(t)]["errors"] == 0
    with pytest.raises(ConfigError):
        e6.select_tasks({k: v for k, v in records.items() if v["successes"] != 0})


def _no_designer(request: Any) -> Any:
    raise AssertionError("the wiring test never calls the designer")


def test_wiring_is_llm_v1_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e6 = _load()
    captured: dict[str, Any] = {}

    class Recorder(FakeSubstrate):
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)
            super().__init__({"1": "expert"}, with_designer=True, designer_fn=_no_designer)

        def reference_provider(self, config: AEAConfig) -> Any:
            from aea.substrate import reference_provider

            return reference_provider(config, self.open_session)

    monkeypatch.setattr(e6, "AeaSubstrate", Recorder)
    cfg = e6.config()
    assert cfg.method_version == "llm_v1"
    sub, ctrl = e6.build(cfg, tmp_path / "run", "e6-test", concurrency=1)
    assert captured["aea_config"] is cfg and captured["aea_config"].method_version == "llm_v1"
    assert ctrl.config is cfg and ctrl.config.method_version == "llm_v1"
    assert isinstance(ctrl.reference, ExpertReference)
    assert ctrl.use_proposer and ctrl.substrate is sub
    # the default config would be refused
    with pytest.raises(ConfigError):
        e6.check_wiring(AEAConfig(), ctrl)


def test_reused_models_and_cap() -> None:
    e6 = _load()
    e3 = e6.e3
    assert e3.policy_qwen().model == "qwen/qwen3-8b" and e3.policy_qwen().provider_pin == "alibaba"
    assert e3.designer_deepseek().model == "deepseek-v4-pro"
    assert e6.CAP_USD == 30.0 and e3.CAP_USD == 30.0 and e3.SPEND_GLOB == "e6-*"
    assert e6.SMOKES[1]["method_sha"] == "47a0091" and e6.SMOKES[1]["prereg_sha"] == "dd0d914"


def test_smoke2_selection_excludes_smoke1_tasks() -> None:
    e6 = _load()
    records = e6.frozen_k16()
    assert e6.select_tasks(records, exclude=()) == ([1, 7, 12], [8, 9, 10])  # smoke 1, unchanged
    high, low = e6.select_tasks(records, exclude=(1, 7, 12, 8, 9, 10))
    assert high == [13, 15, 22] and low == [11, 14, 17]
    assert e6.SMOKE == 2 and e6.ORDER == (13, 15, 22, 11, 14, 17)
    assert e6.RUN_ID == "e6-smoke2-llm-v1" and e6.SMOKES[1]["run_id"] == "e6-smoke-llm-v1"


def test_audit_uses_the_recorded_reference_and_never_recomputes(tmp_path: Path) -> None:
    """The task-9 failure mode of smoke 1: the expert returns a different valid solution on a
    second call. The LOW task used reference A; the audit must use the recorded A and pass."""
    from aea.controller import Controller, TaskRef
    from aea.designer import Reference
    from tests.fixtures.fake_designer import ScriptedDesigner
    from tests.fixtures.fake_substrate import PLAN

    e6 = _load()
    calls: list[int] = []
    variant_a = tuple(PLAN)
    variant_b = ("look", *PLAN)  # a different, equally valid solution

    def flaky_expert(task: Any) -> Reference:
        calls.append(1)
        if len(calls) > 1:
            raise AssertionError("the auditor recomputed the expert")
        return Reference(True, "pass", variant_a)

    designer = ScriptedDesigner(
        (
            "select_stages",
            {
                "stages": [
                    {
                        "source": "reference",
                        "trajectory_id": "reference",
                        "step": 2,
                        "mechanism_summary": "m",
                    }
                ]
            },
        )
    )
    sub = FakeSubstrate({"9": "staged"}, seed=3, with_designer=True, designer_fn=designer)
    cfg = AEAConfig(method_version="llm_v1")
    ctrl = Controller(cfg, sub, tmp_path / "run", "r1", arm="L", reference=flaky_expert)
    o = ctrl.run([TaskRef("9", 9)])[0]
    assert o.outcome == "accepted" and calls == [1]
    audit = e6.leakage_audit(tmp_path / "run")
    assert calls == [1]  # no second expert session
    rec = audit["tasks"]["9"]
    assert audit["ok"] and rec["leaks"] == [] and rec["provenance_intact"]
    assert rec["reference_id"] == e6.reference_id(variant_a) != e6.reference_id(variant_b)
    assert rec["reference_cuts"] == [2] and rec["reference_steps"] == len(variant_a)
    # a tampered record is caught by the integrity check
    p = tmp_path / "run" / "privileged_references.jsonl"
    row = json.loads(p.read_text().splitlines()[0])
    row["actions"] = list(variant_b)
    p.write_text(json.dumps(row) + "\n")
    tampered = e6.leakage_audit(tmp_path / "run")
    assert not tampered["ok"] and not tampered["tasks"]["9"]["provenance_intact"]


def test_refalign_audit_uses_provenance_not_string_overlap(tmp_path: Path) -> None:
    """The phase-3.2 false positives: the compiler's trailing ``look`` and a failure prefix that
    shares an action with the reference's future are NOT leaks; a reference prefix past its own
    cut IS; two reference cuts are each checked against their own cut."""
    from aea.controller import Controller, TaskRef
    from aea.designer import Reference
    from tests.fixtures.fake_designer import ScriptedDesigner
    from tests.fixtures.fake_substrate import PLAN

    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "e6_refalign", ROOT / "scripts" / "e6_refalign.py"
    )
    assert spec and spec.loader
    er = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(er)
    # reference = PLAN plus a trailing look (so 'look' is a post-cut reference action)
    ref_actions = (*PLAN, "look")

    def provider(task: Any) -> Reference:
        return Reference(True, "pass", ref_actions)

    reply = (
        "select_stages",
        {
            "stages": [
                {"source": "failure", "trajectory_id": "F1", "step": 3, "mechanism_summary": "m"},
                {
                    "source": "reference",
                    "trajectory_id": "reference",
                    "step": 2,
                    "mechanism_summary": "m",
                },
            ]
        },
    )
    designer = ScriptedDesigner(reply)
    sub = FakeSubstrate({"9": "random"}, seed=3, with_designer=True, designer_fn=designer)
    cfg = AEAConfig(method_version="llm_v1")
    ctrl = Controller(cfg, sub, tmp_path / "run", "r1", arm="L", reference=provider)
    ctrl.run([TaskRef("9", 9)])
    audit = er.leakage_audit(tmp_path / "run")
    rec = audit["tasks"]["9"]
    assert audit["ok"] and rec["leaks"] == [], rec
    assert rec["prefixes_by_provenance"]["failure"] >= 1
    assert rec["prefixes_by_provenance"]["reference"] >= 1 and rec["reference_cuts"] == [2]
    # tamper: make the reference prefix carry an action past its cut -> leak
    p = tmp_path / "run" / "traces.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    for r in rows:
        pre = [a["kwargs"]["text"] for a in r["candidate"]["in_env_actions"]]
        if pre[:2] == list(PLAN[:2]):
            r["candidate"]["in_env_actions"].insert(2, {"name": "do", "kwargs": {"text": PLAN[2]}})
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    tampered = er.leakage_audit(tmp_path / "run")
    assert not tampered["ok"] and any(
        "exceeds its cut" in x or "unattributed" in x for x in tampered["tasks"]["9"]["leaks"]
    )
