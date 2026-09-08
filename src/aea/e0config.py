"""Derive an E0 / arm-R corpus config from the released ``experiments/alfworld/corpus.yaml``.

Everything stays as released (env, extra_instructions, objective, budget, orchestrator, runner)
except: both client blocks become ``aea.llm.envharness_client:AeaLLMClient`` with the run's
``LLMConfig`` (designer block ``budget: designer``), and the storage / logging paths point into the
run directory. ``config_diff`` reports exactly which keys changed so a test can pin the set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from aea.core.config import LLMConfig
from aea.core.io import atomic_write_text

ALLOWED_CHANGES = frozenset(
    {
        "agent.client_factory",
        "agent.client_kwargs",
        "policy.client_factory",
        "policy.client_kwargs",
        "storage.trace_path",
        "logging.log_dir",
    }
)


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def config_diff(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Top-two-level keys whose values differ (client_kwargs compared as a whole)."""
    fa, fb = _flatten(a), _flatten(b)
    changed = {k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
    collapsed: set[str] = set()
    for key in changed:
        parts = key.split(".")
        collapsed.add(".".join(parts[:2]) if len(parts) > 2 else key)
    return sorted(collapsed)


def derive_corpus_config(
    released_yaml: Path,
    *,
    run_dir: Path,
    policy: LLMConfig,
    designer: LLMConfig,
    pricing_path: Path,
) -> dict[str, Any]:
    cfg: dict[str, Any] = dict(yaml.safe_load(released_yaml.read_text(encoding="utf-8")))
    common = {"ledger_dir": str(run_dir), "pricing_path": str(pricing_path)}
    cfg["agent"]["client_factory"] = "aea.llm.envharness_client:AeaLLMClient"
    cfg["agent"]["client_kwargs"] = {
        "llm": designer.model_dump(mode="json"),
        "budget": "designer",
        "phase": "designer",
        **common,
    }
    cfg["policy"]["client_factory"] = "aea.llm.envharness_client:AeaLLMClient"
    cfg["policy"]["client_kwargs"] = {"llm": policy.model_dump(mode="json"), **common}
    cfg["storage"]["trace_path"] = str(run_dir / "traces.jsonl")
    cfg["logging"]["log_dir"] = str(run_dir)
    released = yaml.safe_load(released_yaml.read_text(encoding="utf-8"))
    changed = set(config_diff(released, cfg))
    if not changed <= ALLOWED_CHANGES:
        raise ValueError(
            f"E0 config changes outside the allowed set: {sorted(changed - ALLOWED_CHANGES)}"
        )
    return cfg


def write_corpus_config(cfg: dict[str, Any], path: Path) -> Path:
    atomic_write_text(path, yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    return path
