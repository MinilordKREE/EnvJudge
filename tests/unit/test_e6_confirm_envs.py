"""Phase 3.4 audit-tool correction: the paired-protocol confirm stage must collect every
search-accepted environment of either arm, i.e. Setup prefixes (corpus kind ``stage``, arm A)
AND accepted Rules candidates at a dose (corpus kind ``knob``, arm B)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> Any:
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_accepted_envs_includes_stage_and_knob(tmp_path: Path, monkeypatch: Any) -> None:
    er = _load("e6_refalign")
    monkeypatch.setattr(er, "RUNS", tmp_path)
    monkeypatch.setattr(er, "ARM_IDS", {"A": "arm-A", "B": "arm-B"})
    (tmp_path / "arm-A").mkdir()
    (tmp_path / "arm-B").mkdir()
    (tmp_path / "arm-A" / "corpus.jsonl").write_text(
        json.dumps(
            {
                "aea": {"kind": "stage", "candidate_id": "85:abc", "task_id": "85", "t": 10},
                "rules_code": "",
                "in_env_actions": ["go to a"],
            }
        )
        + "\n"
    )
    (tmp_path / "arm-B" / "corpus.jsonl").write_text(
        "\n".join(
            json.dumps(r)
            for r in (
                {
                    "aea": {
                        "kind": "knob",
                        "candidate_id": "92:fam:1.0",
                        "task_id": "92",
                        "family": "fam",
                        "d": 1.0,
                    },
                    "rules_code": "class _Rules(Rules):\n    DOSE = 1.0\n",
                    "in_env_actions": [],
                },
                {"aea": {"kind": "seed", "candidate_id": "92:seed", "task_id": "92"}},
            )
        )
        + "\n"
    )
    a = er.accepted_envs("A")
    b = er.accepted_envs("B")
    assert [e["id"] for e in a] == ["A:85:abc"] and a[0]["kind"] == "stage" and a[0]["t"] == 10
    assert [e["id"] for e in b] == ["B:92:fam:1.0"]
    assert b[0]["kind"] == "knob" and b[0]["d"] == 1.0 and b[0]["family"] == "fam"
    assert b[0]["candidate"]["rules_code"].startswith("class _Rules")
    assert b[0]["candidate"]["in_env_actions"] == []
