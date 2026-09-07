"""Run identity: run id, output directory, seed, config hash, git state.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/core/context.py (whole file)
License: MIT (owner's own project) -- see THIRD_PARTY_NOTICES.md
Changes: package rename; the context also records the ``AEAConfig`` hash when one is given.
"""

from __future__ import annotations

import re
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from aea import __version__
from aea.core.config import CONFIG_SCHEMA_VERSION, RunConfig, StrictModel, config_sha256
from aea.errors import ConfigError, InfraError

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class GitState(StrictModel):
    sha: str
    dirty: bool


class RunContext(StrictModel):
    run_id: str
    out_dir: Path
    seed: int
    config_sha256: str
    config_schema_version: int
    aea_config_sha256: str | None
    git_sha: str
    git_dirty: bool
    created_at: datetime
    aea_version: str


def _git(repo_dir: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo_dir, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise InfraError("git executable not found", kind="git") from exc
    if completed.returncode != 0:
        raise InfraError(
            f"git {' '.join(args)} failed in {repo_dir}: {completed.stderr.strip()}", kind="git"
        )
    return completed.stdout


def git_state(repo_dir: Path) -> GitState:
    """HEAD sha and dirty flag. Untracked, unstaged and staged changes all count as dirty."""
    sha = _git(repo_dir, "rev-parse", "HEAD").strip()
    status = _git(repo_dir, "status", "--porcelain")
    return GitState(sha=sha, dirty=bool(status.strip()))


def new_run_id(now: datetime | None = None, *, prefix: str = "") -> str:
    """``[prefix]YYYYMMDDTHHMMSSZ-xxxxxx``: sortable, human-readable, collision-safe."""
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}{stamp}-{secrets.token_hex(3)}"


def create_run_context(
    config: RunConfig,
    *,
    runs_root: Path,
    run_id: str | None = None,
    repo_dir: Path | None = None,
    now: datetime | None = None,
    aea_config_sha256: str | None = None,
) -> RunContext:
    """Create the run directory and return its context.

    Refuses (``ConfigError``) when the tree is dirty and the config requires a clean one, when
    the run id is malformed, or when the run directory already exists.
    """
    repo = repo_dir or Path.cwd()
    state = git_state(repo)
    if config.require_clean_tree and state.dirty:
        raise ConfigError(
            f"refusing to start run '{config.name}': working tree at {repo} is dirty and "
            f"require_clean_tree is true (kind={config.kind}). Commit or stash, or set "
            "require_clean_tree: false for an exploratory run."
        )
    created_at = (now or datetime.now(UTC)).astimezone(UTC)
    resolved_id = run_id or new_run_id(created_at)
    if not _RUN_ID_RE.match(resolved_id):
        raise ConfigError(f"invalid run id {resolved_id!r}: use [A-Za-z0-9._-], max 128 chars")
    out_dir = (runs_root / resolved_id).resolve()
    if out_dir.exists():
        raise ConfigError(f"run directory already exists, refusing to overwrite: {out_dir}")
    out_dir.mkdir(parents=True)
    return RunContext(
        run_id=resolved_id,
        out_dir=out_dir,
        seed=config.seed,
        config_sha256=config_sha256(config),
        config_schema_version=CONFIG_SCHEMA_VERSION,
        aea_config_sha256=aea_config_sha256,
        git_sha=state.sha,
        git_dirty=state.dirty,
        created_at=created_at,
        aea_version=__version__,
    )
