"""``manifest.json`` and ``config.resolved.yaml`` for a run directory.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/core/manifest.py (``Manifest``, ``build_manifest``, ``write_manifest``,
``read_manifest``)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; schema restarted at v1 with the fields aea needs (``aea_config_sha256``,
``envharness_sha``); the environment probe and the diagnosis/experiment blocks are dropped.
"""

from __future__ import annotations

import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import ValidationError

from aea.core.config import RunConfig, StrictModel
from aea.core.context import RunContext
from aea.core.hashing import JsonValue
from aea.core.io import atomic_write_text, read_json
from aea.errors import InfraError

MANIFEST_SCHEMA_VERSION: Final = 1
MANIFEST_FILENAME = "manifest.json"
RESOLVED_CONFIG_FILENAME = "config.resolved.yaml"


class Manifest(StrictModel):
    schema_version: Literal[1]
    run_id: str
    created_at: datetime
    seed: int
    config_sha256: str
    config_schema_version: int
    aea_config_sha256: str | None
    config_path: str | None
    git_sha: str
    git_dirty: bool
    envharness_sha: str | None
    aea_version: str
    python_version: str
    platform: str
    out_dir: str
    extra: dict[str, JsonValue] | None = None
    """Free-form block for experiment scripts (spec path and sha, arm, round)."""


def build_manifest(
    ctx: RunContext,
    *,
    config_path: Path | None = None,
    envharness_sha: str | None = None,
    extra: dict[str, JsonValue] | None = None,
) -> Manifest:
    return Manifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        run_id=ctx.run_id,
        created_at=ctx.created_at,
        seed=ctx.seed,
        config_sha256=ctx.config_sha256,
        config_schema_version=ctx.config_schema_version,
        aea_config_sha256=ctx.aea_config_sha256,
        config_path=str(config_path) if config_path is not None else None,
        git_sha=ctx.git_sha,
        git_dirty=ctx.git_dirty,
        envharness_sha=envharness_sha,
        aea_version=ctx.aea_version,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        out_dir=str(ctx.out_dir),
        extra=extra,
    )


def write_manifest(
    ctx: RunContext,
    config: RunConfig,
    *,
    config_path: Path | None = None,
    envharness_sha: str | None = None,
    extra: dict[str, JsonValue] | None = None,
) -> Path:
    """Write ``manifest.json`` and ``config.resolved.yaml`` atomically; return the manifest path."""
    manifest = build_manifest(
        ctx, config_path=config_path, envharness_sha=envharness_sha, extra=extra
    )
    manifest_path = ctx.out_dir / MANIFEST_FILENAME
    atomic_write_text(manifest_path, manifest.model_dump_json(indent=2) + "\n")
    resolved = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=True, allow_unicode=True)
    atomic_write_text(ctx.out_dir / RESOLVED_CONFIG_FILENAME, resolved)
    return manifest_path


def read_manifest(path: Path) -> Manifest:
    raw = read_json(path)
    try:
        return Manifest.model_validate(raw)
    except ValidationError as exc:
        raise InfraError(f"invalid manifest {path}:\n{exc}", kind="corrupt_file") from exc


def load_run_context(run_dir: Path) -> tuple[RunContext, Manifest]:
    """Rebuild a ``RunContext`` from an existing run directory (resume)."""
    manifest = read_manifest(run_dir / MANIFEST_FILENAME)
    ctx = RunContext(
        run_id=manifest.run_id,
        out_dir=run_dir.resolve(),
        seed=manifest.seed,
        config_sha256=manifest.config_sha256,
        config_schema_version=manifest.config_schema_version,
        aea_config_sha256=manifest.aea_config_sha256,
        git_sha=manifest.git_sha,
        git_dirty=manifest.git_dirty,
        created_at=manifest.created_at,
        aea_version=manifest.aea_version,
    )
    return ctx, manifest
