"""Semantic-equivalence assertions for the experiment YAMLs (owner review 2026-09-05)."""

from __future__ import annotations

from pathlib import Path

import yaml

from eobs.settings import ENVHARNESS_ROOT, EOBS_ROOT

PERMITTED = {"agent.client_factory", "agent.client_kwargs", "policy.client_factory", "policy.client_kwargs",
             "storage.trace_path", "logging.log_dir"}


def _diff(a, b, path=""):
    out = []
    for k in set(a) | set(b):
        pk = f"{path}{k}"
        if k not in a or k not in b:
            out.append(pk)
        elif isinstance(a[k], dict) and isinstance(b[k], dict) and pk not in PERMITTED:
            out += _diff(a[k], b[k], pk + ".")
        elif a[k] != b[k]:
            out.append(pk)
    return sorted(out)


def test_corpus_eobs_only_permitted_keys_differ():
    orig = yaml.safe_load((ENVHARNESS_ROOT / "experiments/alfworld/corpus.yaml").read_text())
    ours = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs.yaml").read_text())
    assert set(_diff(orig, ours)) <= PERMITTED
    for block in ("agent", "policy"):
        ik = ours[block]["client_kwargs"]["inner_kwargs"]
        assert ik["model"] == "openai/deepseek-v4-pro" and ik["api_base"] == "https://api.deepseek.com"
        assert ik["extra_body"] == {"thinking": {"type": "disabled"}}
        assert set(ik) == {"model", "api_base", "extra_body", "drop_params"}


def test_H_config_differs_only_in_instructions_and_band():
    base = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs.yaml").read_text())
    h = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs_H.yaml").read_text())
    assert _diff(base, h) == ["agent.extra_instructions", "objective.target_band"]
    assert "extra_instructions" not in h["agent"] and h["objective"]["target_band"] == [0.4, 0.6]


def test_smoke_config_differs_only_in_max_k():
    base = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs.yaml").read_text())
    s = yaml.safe_load((EOBS_ROOT / "configs/corpus_eobs_smoke.yaml").read_text())
    assert _diff(base, s) == ["budget.max_k"] and s["budget"]["max_k"] == 1
