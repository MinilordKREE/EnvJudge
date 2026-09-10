"""scripts/handoff_demos.py (an extension outside the v0.2 method) keeps its behaviour: the
oracle's shortest success rendered in the released trace format."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from aea.config import AEAConfig
from tests.fixtures.fake_substrate import PLAN
from tests.fixtures.fake_world import make_open

ROOT = Path(__file__).resolve().parents[2]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "handoff_demos", ROOT / "scripts" / "handoff_demos.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_handoff_renders_released_trace_format() -> None:
    hd = _load()
    cfg = AEAConfig()
    trace = hd.handoff(make_open(PLAN), cfg, task_label="lbl", task_seed=7)
    assert trace is not None and trace.success and trace.policy_model_id == hd.HANDOFF_POLICY_ID
    assert [s.filtered_action.kwargs["text"] for s in trace.steps if s.filtered_action] == PLAN
    assert trace.steps[0].policy_raw_response == "<action>go to a</action>"
    assert trace.rollout_seed == 7 and trace.candidate_id == "handoff"
    assert hd.handoff(make_open(PLAN, cap=2), cfg, task_label="lbl", task_seed=7) is None
    with pytest.raises(ValueError):
        hd.render_witness_trace("l", 1, ["a"], [])
