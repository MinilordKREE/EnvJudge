"""Offline checks of the E6 smoke driver (experiments/alfworld_e6/PREREG_SMOKE.md) before any
paid call: the frozen task selection, and the wiring (driver config == substrate config ==
controller config == llm_v1, reference provider non-None) on a recording fake substrate."""

from __future__ import annotations

import importlib.util
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
    high, low = e6.select_tasks(records)
    assert high == [1, 7, 12] and low == [8, 9, 10]
    assert e6.ORDER == (1, 7, 12, 8, 9, 10)
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
    assert e6.METHOD_SHA == "47a0091"
