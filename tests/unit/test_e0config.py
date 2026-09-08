from __future__ import annotations

from pathlib import Path

import yaml

from aea.core.config import LLMConfig
from aea.e0config import ALLOWED_CHANGES, config_diff, derive_corpus_config, write_corpus_config

RELEASED = (
    Path(__file__).resolve().parents[2]
    / "third_party"
    / "envharness"
    / "experiments"
    / "alfworld"
    / "corpus.yaml"
)


def test_e0_config_changes_only_clients_and_paths(tmp_path: Path) -> None:
    policy = LLMConfig(
        provider="openrouter",
        model="google/gemini-3.1-flash-lite",
        provider_pin="google-ai-studio",
        thinking=None,
    )
    designer = policy.model_copy(update={"temperature": 0.7, "max_tokens": 4096})
    cfg = derive_corpus_config(
        RELEASED,
        run_dir=tmp_path / "run",
        policy=policy,
        designer=designer,
        pricing_path=tmp_path / "pricing.yaml",
    )
    released = yaml.safe_load(RELEASED.read_text(encoding="utf-8"))
    assert set(config_diff(released, cfg)) <= ALLOWED_CHANGES
    assert cfg["agent"]["extra_instructions"] == released["agent"]["extra_instructions"]
    assert cfg["policy"]["task_description"] == released["policy"]["task_description"]
    assert (
        cfg["orchestrator"] == released["orchestrator"]
        and cfg["objective"] == released["objective"]
        and cfg["budget"] == released["budget"]
    )
    assert (
        cfg["agent"]["client_kwargs"]["budget"] == "designer"
        and cfg["policy"]["client_kwargs"]["llm"]["provider_pin"] == "google-ai-studio"
    )
    assert (
        cfg["policy"]["client_kwargs"]["llm"]["thinking"] is None
    )  # provider default, as released
    path = write_corpus_config(cfg, tmp_path / "run" / "corpus_e0.yaml")
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == cfg


def test_derive_arm_config_changes_only_prompt_and_band(tmp_path: Path) -> None:
    from aea.e0config import ALLOWED_ARM_CHANGES, derive_arm_config

    released = (
        Path(__file__).resolve().parents[2]
        / "third_party/envharness/experiments/alfworld/corpus.yaml"
    )
    cfg, changed = derive_arm_config(
        released,
        run_dir=tmp_path,
        policy=LLMConfig(),
        designer=LLMConfig(),
        pricing_path=tmp_path / "p.yaml",
        extra_instructions="",
        target_band=(0.4, 0.6),
    )
    assert cfg["agent"]["extra_instructions"] == "" and cfg["objective"]["target_band"] == [
        0.4,
        0.6,
    ]
    assert set(changed) <= ALLOWED_ARM_CHANGES and "agent.extra_instructions" in changed
    assert cfg["orchestrator"]["skip_passthrough_candidates"] is True  # released behaviour kept
