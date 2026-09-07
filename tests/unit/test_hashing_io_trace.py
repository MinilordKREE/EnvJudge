from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aea.core.hashing import canonical_json, sha256_dir, sha256_of, to_json_value
from aea.core.io import append_jsonl, atomic_write_json, read_json, read_jsonl
from aea.core.trace import TRACE_SCHEMA_VERSION, TraceWriter, read_trace
from aea.errors import InfraError


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})
    assert sha256_of({"a": 1}) == sha256_of({"a": 1})
    assert to_json_value(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        to_json_value(float("nan"))


def test_atomic_json_and_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    atomic_write_json(path, {"x": 1})
    assert read_json(path) == {"x": 1}
    assert not path.with_name(".a.json.tmp").exists()
    lines = tmp_path / "l.jsonl"
    append_jsonl(lines, {"k": 1})
    append_jsonl(lines, {"k": 2})
    assert [r["k"] for r in read_jsonl(lines)] == [1, 2]
    lines.write_text('{"k": 1}\nnot json\n', encoding="utf-8")
    with pytest.raises(InfraError) as info:
        read_jsonl(lines)
    assert info.value.kind == "corrupt_file"
    with pytest.raises(InfraError) as missing:
        read_json(tmp_path / "nope.json")
    assert missing.value.kind == "missing_file"


def test_sha256_dir_ignores_caches(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    first = sha256_dir(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"0")
    assert sha256_dir(tmp_path) == first
    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    assert sha256_dir(tmp_path) != first


def test_trace_envelope_seq_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with TraceWriter(path, "run-1") as writer:
        writer.write("start", {"n": 1})
        writer.write("step", {"n": 2})
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert set(raw[0]) == {"schema_version", "seq", "ts", "run_id", "kind", "payload"}
    assert [r["seq"] for r in raw] == [1, 2] and raw[0]["schema_version"] == TRACE_SCHEMA_VERSION
    with TraceWriter(path, "run-1") as resumed:
        assert resumed.seq == 2
        resumed.write("end", {})
    assert [e.kind for e in read_trace(path)] == ["start", "step", "end"]
    path.write_text(
        path.read_text(encoding="utf-8").replace('"seq": 2', '"seq": 5'), encoding="utf-8"
    )
    with pytest.raises(InfraError):
        read_trace(path)
