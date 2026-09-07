"""Offline P5 tests: config-copy equivalence (only max_nb_steps_per_episode changed), candidate selection, seeded subsampling."""
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "p5")); sys.path.insert(0, str(ROOT.parent / "eobs"))
from p5.chs100 import select_candidates  # noqa: E402
from p5.banksize import subsample  # noqa: E402


def _strip(d):
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if k != "max_nb_steps_per_episode"}
    return d


def test_config_copy_only_changes_step_cap():
    base = yaml.safe_load((ROOT.parent.parent / "third_party" / "envharness" / "envharness" / "third_party" / "alfworld" / "base_config.yaml").read_text())
    copy = yaml.safe_load((ROOT / "p5" / "configs" / "alfworld_config_100.yaml").read_text())
    assert _strip(base) == _strip(copy)
    assert base["rl"]["training"]["max_nb_steps_per_episode"] == 50 and base["dagger"]["training"]["max_nb_steps_per_episode"] == 50
    assert copy["rl"]["training"]["max_nb_steps_per_episode"] == 100 and copy["dagger"]["training"]["max_nb_steps_per_episode"] == 100


def test_candidate_selection_anchors_and_cap():
    out = select_candidates({"a": [3, 5, 10, 20, 30, 40], "b": [2, 4, 8, 12, 16], "c": [1, 2]})
    assert len(out) == 6 and out[0] == ("a", 40, "L") and out == sorted(out, key=lambda x: -x[1])
    assert ("a", 20, "L/2") in out and ("b", 16, "L") in out
    one = select_candidates({"a": [8]})
    assert one == [("a", 8, "L")]                      # anchors collapse onto L when it is the only certified state
    assert select_candidates({"a": [], "b": [0]}) == []  # t = 0 never a candidate


def test_subsample_seeded_and_sized():
    items = [{"id": i} for i in range(23)]
    a = subsample(items, 6, 20260915); b = subsample(items, 6, 20260915)
    assert a == b and len(a) == 6 and len({x["id"] for x in a}) == 6
    assert subsample(items, 23, 20260915) == items and len(subsample(items, 3, 1)) == 3
