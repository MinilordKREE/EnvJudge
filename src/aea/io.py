"""Corpus and trace writers in the released formats (spec section 9).

Corpus entries are the RL loader's shape ``{game_file, rules_code, in_env_actions}``
(``rl/envharness_rl/alfworld/envs.py:119-146``; unknown keys ignored, verified) plus an ``aea``
metadata block; ``to_candidate`` round-trips an entry into the orchestrator's ``Candidate``
(``types.py:137-141``). Policy rollouts are written with the released ``TraceStore``
(``orchestration/storage.py:44-72``) so ``scripts/induce_pair.py`` reads them unchanged.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Literal

from envharness.core.types import Action, Candidate, Trace
from envharness.orchestration.storage import TraceStore
from pydantic import Field

from aea.core.config import StrictModel
from aea.core.hashing import JsonValue
from aea.core.io import append_jsonl, read_jsonl

type EntryKind = Literal["band", "knob", "stage"]


class AeaMeta(StrictModel):
    kind: EntryKind
    task_id: str
    seed: int
    round: int = 0
    regime: str | None = None
    family: str | None = None
    source: Literal["exemplar", "llm"] | None = None
    axis: str | None = None
    d: float | None = None
    p8: float | None = None
    t: int | None = None
    prefix_sha: str | None = None
    profile: list[dict[str, JsonValue]] | None = None
    stage_budget: int | None = None
    candidate_id: str | None = None
    certificate: str | None = None
    n_search: int | None = None


class CorpusEntry(StrictModel):
    game_file: str
    rules_code: str = ""
    in_env_actions: list[dict[str, Any]] = Field(default_factory=list)
    stage_budget: int | None = None
    aea: AeaMeta

    def to_candidate(self) -> Candidate:
        return Candidate(
            rules_code=self.rules_code,
            in_env_actions=[
                Action(name=str(a["name"]), kwargs=dict(a.get("kwargs") or {}))
                for a in self.in_env_actions
            ],
            rationale=f"aea:{self.aea.kind}",
        )


def relative_game_file(game_file: str, data_root: Path | None = None) -> str:
    """The bundled corpora store game files relative to ``$ALFWORLD_DATA`` (``envs.py:139-142``)."""
    root = data_root or Path(os.environ.get("ALFWORLD_DATA", ""))
    if root and game_file.startswith(str(root)):
        return os.path.relpath(game_file, root)
    return game_file


def entry_from_candidate(game_file: str, candidate: Candidate, meta: AeaMeta) -> CorpusEntry:
    return CorpusEntry(
        game_file=game_file,
        rules_code=candidate.rules_code or "",
        in_env_actions=[
            {"name": a.name, "kwargs": dict(a.kwargs)} for a in candidate.in_env_actions
        ],
        stage_budget=meta.stage_budget,
        aea=meta,
    )


def write_corpus_entry(path: Path, entry: CorpusEntry) -> None:
    append_jsonl(path, entry.model_dump(mode="json", exclude_none=True))


def read_corpus(path: Path) -> list[CorpusEntry]:
    return [CorpusEntry.model_validate(r) for r in read_jsonl(path)]


class TraceWriter:
    """Thin wrapper over the released ``TraceStore`` (append-only JSONL of ``Trace``)."""

    def __init__(self, path: Path) -> None:
        self._store = TraceStore(path)

    def add(self, trace: Trace) -> None:
        self._store.add(trace)

    def __len__(self) -> int:
        return len(self._store)


def write_accounting(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
