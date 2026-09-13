"""Compatibility pin for the v0.4 method (docs/design/AEA_LLM_FIRST_AUDIT.md, phase 2, step 1).

The golden in ``tests/fixtures/golden_v04.json`` was recorded at commit 05fc2fe (phase-1 audit,
before any ``llm_v1`` code) by :func:`observables` on the offline fake world: family source and
order, the proposer record, the stage candidate source, the event kinds, the corpus kinds and the
rollout phases of every task. ``method_version`` defaults to ``v0.4`` and an existing config with
no such field must reproduce the golden byte for byte; the E5 driver's configs must resolve to
``v0.4``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from aea.config import AEAConfig, load_aea_config
from aea.controller import Controller, TaskRef
from aea.core.trace import read_trace
from aea.io import read_corpus
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import FakeSubstrate

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden_v04.json"
ROOT = Path(__file__).resolve().parents[2]

POLICIES = {"2": "expert", "7": "footer", "9": "random", "1": "coin"}
CASE_FLIP = """
class _Rules(Rules):
    DOSE = __DOSE__

    def filter_observation(self, obs, env_state):
        if self.DOSE > 0.5:
            return Observation(text=obs.text.replace("Admissible", "admissible"), data=obs.data)
        return obs
"""
PROPOSAL = (
    "propose_families",
    {"families": [{"name": "case_flip", "axis": "O", "rules_code": CASE_FLIP}]},
)


def observables(run: Path, config: AEAConfig, *, with_designer: bool) -> dict[str, Any]:
    designer = ScriptedDesigner(PROPOSAL)
    sub = FakeSubstrate(POLICIES, seed=3, with_designer=with_designer, designer_fn=designer)
    ctrl = Controller(config, sub, run, "r1", arm="A", use_proposer=with_designer)
    outcomes = ctrl.run([TaskRef(t, int(t)) for t in POLICIES], concurrency=1)
    events = read_trace(run / "events.jsonl")
    keep = {"families", "proposer", "stage_candidates", "bracket", "no_leverage", "solvable"}
    corpus = read_corpus(run / "corpus.jsonl") if (run / "corpus.jsonl").exists() else []
    return {
        "outcomes": [[o.task.task_id, o.outcome, o.reason, o.regime, o.n_search] for o in outcomes],
        "event_kinds": [e.kind for e in events if e.kind not in ("run_start",)],
        "events": [_normalised(e.kind, e.payload) for e in events if e.kind in keep],
        "corpus": [
            [e.aea.task_id, e.aea.kind, e.aea.family, e.aea.source, e.aea.candidate_id, e.aea.t]
            for e in corpus
        ],
        "rollout_phases": [list(c) for c in sub.calls],
        "designer_calls": designer.calls,
    }


def _normalised(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Candidates of equal ``t`` are ordered by their (random) episode id in v0.4: compare the
    stage candidate SET, not that order."""
    out = {"kind": kind, **{k: v for k, v in payload.items() if k != "detail"}}
    if kind == "stage_candidates":
        out["certified"] = sorted(out["certified"])
        out["kinds"] = dict(sorted(out["kinds"].items()))
        out["rejected"] = sorted(out["rejected"], key=lambda r: str(r["id"]))
    return out


def _golden() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(GOLDEN.read_text(encoding="utf-8")))


def test_default_method_version_is_v04(tmp_path: Path) -> None:
    assert AEAConfig().method_version == "v0.4"
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 4, "k": 16}), encoding="utf-8")
    assert load_aea_config(path).method_version == "v0.4"  # no field in the file -> v0.4


def test_v04_high_and_low_paths_match_the_phase1_golden(tmp_path: Path) -> None:
    """Library order, proposer handling, leverage ordering, ``_try_family``, seeded failures and
    end/mid candidate states: unchanged (the golden was recorded before ``llm_v1`` existed)."""
    golden = _golden()
    for name, with_designer in (("library", False), ("proposer", True)):
        got = observables(tmp_path / name, AEAConfig(), with_designer=with_designer)
        assert got == golden[name], name
        explicit = observables(
            tmp_path / f"{name}-explicit",
            AEAConfig(method_version="v0.4"),
            with_designer=with_designer,
        )
        assert explicit == golden[name], f"{name} explicit v0.4"


def _load_script(name: str) -> Any:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_e5_driver_configs_resolve_to_v04() -> None:
    e5 = _load_script("e5")
    for arm in e5.ARMS:
        cfg = e5.config_for(arm)
        assert cfg.method_version == "v0.4" and cfg.schema_version == 4
        assert cfg.impl.warm_start_min_history == e5.ARMS[arm]
    e3 = _load_script("e3")
    assert AEAConfig().model_dump() == e3.AEAConfig().model_dump()


# ------------------------------------------------------------------ brief tests 33 to 36
def test_explicit_v04_never_enters_the_llm_v1_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every llm_v1 entry point (HIGH evidence + design, LOW reference + evidence + design) is
    replaced by a trap; the v0.4 golden still reproduces byte for byte with and without a
    designer, so v0.4 never reaches them."""
    import aea.controller as ctl

    def trap(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("llm_v1 path entered under v0.4")

    for name in ("serialize_high", "design_high", "serialize_low", "design_low"):
        monkeypatch.setattr(ctl, name, trap)
    monkeypatch.setattr(ctl.Controller, "_lazy_reference", trap)
    golden = _golden()
    for name, with_designer in (("library", False), ("proposer", True)):
        got = observables(
            tmp_path / name, AEAConfig(method_version="v0.4"), with_designer=with_designer
        )
        assert got == golden[name], name


def test_v04_families_and_candidate_states_are_unchanged(tmp_path: Path) -> None:
    """35: ``_families`` = proposer families ahead of the library, leverage-ordered; 36: the
    stage candidates are the end / mid states of the seeded failures."""
    from aea.stage import candidate_states

    golden = _golden()
    fam = [e for e in golden["proposer"]["events"] if e["kind"] == "families"]
    assert [e["order"] for e in fam if e["task_id"] == "2"] == [
        ["case_flip", "footer_mask", "horizon_squeeze"]
    ]
    assert all("source" not in e for e in fam)  # the llm_v1 marker never appears
    stage = [e for e in golden["library"]["events"] if e["kind"] == "stage_candidates"]
    assert stage and all(set(e["kinds"].values()) <= {"end", "mid"} for e in stage)
    assert all("source" not in e for e in stage)
    assert candidate_states({"a": 10, "b": 7}, 6) == [
        ("a", 10, "end"),
        ("b", 7, "end"),
        ("a", 5, "mid"),
        ("b", 3, "mid"),
    ]
