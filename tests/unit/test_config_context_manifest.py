from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aea.core.config import LLMConfig, RunConfig, config_sha256, load_run_config
from aea.core.context import create_run_context, git_state
from aea.core.manifest import (
    MANIFEST_SCHEMA_VERSION,
    load_run_context,
    read_manifest,
    write_manifest,
)
from aea.errors import ConfigError


def test_strict_config_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "run.yaml"
    path.write_text("schema_version: 1\nname: x\nbogus: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_run_config(path)
    path.write_text("schema_version: 1\nname: x\nkind: confirmatory\n", encoding="utf-8")
    cfg = load_run_config(path)
    assert cfg.require_clean_tree is True
    assert cfg.policy.provider_pin == "alibaba"
    with pytest.raises(ValidationError):
        cfg.policy.__setattr__("model", "z")  # frozen: StrictModel refuses mutation


def test_config_hash_covers_defaults() -> None:
    a = RunConfig(schema_version=1, name="a", require_clean_tree=False)
    b = RunConfig(
        schema_version=1, name="a", require_clean_tree=False, policy=LLMConfig(temperature=0.9)
    )
    assert config_sha256(a) != config_sha256(b)
    assert config_sha256(a) == config_sha256(
        RunConfig(schema_version=1, name="a", require_clean_tree=False)
    )


def test_run_context_and_manifest(git_repo: Path, run_config: RunConfig, tmp_path: Path) -> None:
    state = git_state(git_repo)
    assert not state.dirty
    ctx = create_run_context(
        run_config,
        runs_root=tmp_path / "runs",
        run_id="r1",
        repo_dir=git_repo,
        aea_config_sha256="abc",
    )
    assert ctx.git_sha == state.sha and ctx.out_dir.exists()
    manifest_path = write_manifest(ctx, run_config, envharness_sha="fab7d574", extra={"arm": "A"})
    manifest = read_manifest(manifest_path)
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.aea_config_sha256 == "abc" and manifest.envharness_sha == "fab7d574"
    assert (ctx.out_dir / "config.resolved.yaml").exists()
    ctx2, _ = load_run_context(ctx.out_dir)
    assert ctx2.run_id == "r1" and ctx2.config_sha256 == ctx.config_sha256
    with pytest.raises(ConfigError, match="already exists"):
        create_run_context(run_config, runs_root=tmp_path / "runs", run_id="r1", repo_dir=git_repo)


def test_confirmatory_refuses_dirty_tree(
    git_repo: Path, run_config: RunConfig, tmp_path: Path
) -> None:
    (git_repo / "dirty.txt").write_text("x", encoding="utf-8")
    confirmatory = run_config.model_copy(
        update={"kind": "confirmatory", "require_clean_tree": True}
    )
    with pytest.raises(ConfigError, match="dirty"):
        create_run_context(confirmatory, runs_root=tmp_path / "runs", repo_dir=git_repo)
