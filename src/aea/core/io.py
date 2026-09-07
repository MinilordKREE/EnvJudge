"""Atomic file writes and JSON / JSONL helpers.

Adapted from: MinilordKREE/agent_harnesses_diagnostic (Project One, ``ahd``) @
db5807f1f0608184b141c80d37488e1c842d1d49
Original path: src/ahd/core/io.py (whole file), itself adapted from microsoft/AutoSaddler @
30e20ce004486c58e7ee97c66182a8d0d41ec90e (src/autosaddler/v2/storage/local.py ``_atomic_write``;
lines 475-482; MIT) and RUCAIBox/Evo-Bench @ e1dc9386a193cab1ee8630824c085e5e26d0c730
(evobench/common/jsonl.py; lines 8-22; Apache-2.0)
License: MIT / Apache-2.0 as above -- see THIRD_PARTY_NOTICES.md
Changes: package rename only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aea.errors import InfraError


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file, fsync, and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        destination.write(text)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


def atomic_write_json(path: Path, value: Any, *, indent: int | None = 2) -> None:
    atomic_write_text(
        path, json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=True) + "\n"
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InfraError(f"file not found: {path}", kind="missing_file") from exc
    except OSError as exc:
        raise InfraError(f"cannot read {path}: {exc}", kind="io") from exc


def read_json(path: Path) -> Any:
    text = read_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InfraError(f"corrupt JSON in {path}: {exc}", kind="corrupt_file") from exc


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    """Append one JSON object as a line. Opens and closes the file per call (crash-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read every line as a JSON object; a malformed line is an :class:`InfraError`."""
    records: list[dict[str, Any]] = []
    for lineno, raw in enumerate(read_text(path).splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InfraError(
                f"corrupt JSONL in {path} at line {lineno}", kind="corrupt_file"
            ) from exc
        if not isinstance(parsed, dict):
            raise InfraError(f"JSONL line {lineno} in {path} is not an object", kind="corrupt_file")
        records.append(parsed)
    return records
