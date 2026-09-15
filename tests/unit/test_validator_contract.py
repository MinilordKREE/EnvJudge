"""Offline conformance between advertised, real and structural-validation state."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

import pytest
from envharness.bridges.alfworld.bridge import AlfworldEnv, AlfworldEnvState
from envharness.core.code_loader import load_rules_subclass

import aea.families as families
from aea.designer import ENVIRONMENT_SURFACE, identity_at_zero
from aea.families import _SmokeInner, validate_rules_template

ROOT = Path(families.__file__).resolve().parents[2]
ARCHIVE = ROOT / "experiments/alfworld_e6/results/e6_iterative_low_semantic_smoke"
HISTORICAL = (
    (
        "candidate_126_D_C2.py.txt",
        "ee62c351c25cdb805f849447db5ac28dfad0678ef2e60aa460133a5c9fe220d8",
        "put a cool potato in garbagecan",
    ),
    (
        "candidate_129_D_C1.py.txt",
        "58529c8cffb9de778977d1984e0ee4a49dd4353512f38b49fe7be88004fc6008",
        "put a clean butterknife in countertop",
    ),
    (
        "candidate_129_I_C2.py.txt",
        "d1caa3b5014b7c637fd72f44a28cfe198878acfb8fb89fea42af38d2fd4f2466",
        "put a clean butterknife in countertop",
    ),
)


def _advertised_fields(contract: str) -> set[str]:
    paragraph = contract.split("- env_state ", 1)[1].split("\n- Hooks", 1)[0]
    declarations = re.findall(r"`([^`]+)`", paragraph)
    assert declarations, "state declarations must remain machine-auditable"
    assert all(re.fullmatch(r"[a-z_]\w*(?::\s*[^`]+)?", item) for item in declarations)
    return {item.split(":", 1)[0] for item in declarations}


def _assert_contract_supported(contract: str) -> None:
    advertised = _advertised_fields(contract)
    real = {field.name for field in fields(AlfworldEnvState)}
    assert advertised <= real, f"Advertised fields absent from real state: {advertised - real}"
    state = _SmokeInner().get_env_state()
    missing = {name for name in advertised if not hasattr(state, name)}
    assert not missing, f"Advertised fields absent from validation state: {missing}"


def _assert_value_type(value: Any, annotation: Any) -> None:
    if annotation is Any:
        return
    origin = get_origin(annotation)
    if origin is list:
        assert type(value) is list
        for item in value:
            _assert_value_type(item, get_args(annotation)[0])
    elif origin is dict:
        assert type(value) is dict
        key_type, value_type = get_args(annotation)
        for key, item in value.items():
            _assert_value_type(key, key_type)
            _assert_value_type(item, value_type)
    else:
        assert type(value) is annotation


def test_live_advertised_fields_and_bridge_schema_match_canonical_validation_state() -> None:
    _assert_contract_supported(ENVIRONMENT_SURFACE)
    documented = set(re.findall(r"(?m)^\s{2}([a-z_]\w*):", AlfworldEnv.env_state_schema()))
    real = {field.name for field in fields(AlfworldEnvState)}
    assert documented == real
    state = _SmokeInner().get_env_state()
    assert type(state) is AlfworldEnvState
    assert all(hasattr(state, name) for name in documented)


def test_new_advertised_field_requires_real_and_validation_support() -> None:
    changed_contract = ENVIRONMENT_SURFACE.replace(
        "`goal_text`", "`future_missing_field`, `goal_text`", 1
    )
    assert "future_missing_field" in _advertised_fields(changed_contract)
    with pytest.raises(AssertionError, match="future_missing_field"):
        _assert_contract_supported(changed_contract)


def test_canonical_types_defaults_and_existing_smoke_overrides() -> None:
    state = _SmokeInner().get_env_state()
    expected = asdict(AlfworldEnvState())
    expected.update(
        step_count=1, admissible_commands=["look", "go to a"], obs_text="You see a room."
    )
    assert asdict(state) == expected
    for name, annotation in get_type_hints(AlfworldEnvState).items():
        _assert_value_type(getattr(state, name), annotation)


def test_smoke_instances_do_not_share_per_episode_containers() -> None:
    first, second = _SmokeInner().get_env_state(), _SmokeInner().get_env_state()
    first.extras["counter"] = 1
    first.admissible_commands.append("test command")
    first.inventory.append("test item")
    assert second.extras == {}
    assert second.admissible_commands == ["look", "go to a"]
    assert second.inventory == []


def _set_smoke_state(
    monkeypatch: pytest.MonkeyPatch, *, goal: str, effective: bool, done: bool = False
) -> None:
    original = _SmokeInner.__init__

    def initialize(inner: _SmokeInner) -> None:
        original(inner)
        inner.state.goal_text = goal
        inner.state.last_action_was_effective = effective
        inner.state.done = done

    monkeypatch.setattr(_SmokeInner, "__init__", initialize)


ACCESS_ALLOWED = """class _Rules(Rules):
    DOSE = __DOSE__
    def filter_observation(self, obs, env_state):
        goal = env_state.goal_text
        done = env_state.done
        effective = env_state.last_action_was_effective
        if self.DOSE <= 0:
            return obs
        state_label = "effective" if effective else "ineffective"
        return Observation(text=obs.text + "|" + goal + "|" + state_label + "|" + str(done),
                           data=obs.data)
"""


@pytest.mark.parametrize("effective", [True, False])
@pytest.mark.parametrize("done", [True, False])
def test_allowed_goal_done_and_effective_fields_execute_and_preserve_identity(
    monkeypatch: pytest.MonkeyPatch, effective: bool, done: bool
) -> None:
    goal = "put a clean butterknife in countertop"
    _set_smoke_state(monkeypatch, goal=goal, effective=effective, done=done)
    report = validate_rules_template(ACCESS_ALLOWED)
    assert report.ok, report.reasons
    assert identity_at_zero(ACCESS_ALLOWED) == []
    inner = _SmokeInner()
    wrapper = load_rules_subclass(ACCESS_ALLOWED.replace("__DOSE__", "1.0"))(inner=inner)
    actual = wrapper.filter_observation(inner.observe(), inner.get_env_state())
    label = "effective" if effective else "ineffective"
    assert actual.text.endswith(f"|{goal}|{label}|{done}")


def test_truly_unsupported_state_attribute_still_fails_structural_validation() -> None:
    source = ACCESS_ALLOWED.replace("env_state.goal_text", "env_state.not_a_real_state_field")
    report = validate_rules_template(source)
    assert not report.ok
    assert any(
        "AttributeError" in reason and "not_a_real_state_field" in reason
        for reason in report.reasons
    )


@pytest.mark.parametrize("filename,expected_hash,goal", HISTORICAL)
@pytest.mark.parametrize("effective", [True, False])
def test_exact_frozen_candidates_use_supported_state_without_false_structural_failure(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    expected_hash: str,
    goal: str,
    effective: bool,
) -> None:
    raw = (ARCHIVE / filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_hash
    source = raw.decode()
    _set_smoke_state(monkeypatch, goal=goal, effective=effective)
    report = validate_rules_template(source)
    assert report.ok, report.reasons
    assert identity_at_zero(source) == []
    inner = _SmokeInner()
    wrapper = load_rules_subclass(source.replace("__DOSE__", "1.0"))(inner=inner)
    before = inner.observe()
    after = wrapper.filter_observation(before, inner.get_env_state())
    # Nonempty task-specific goals activate both historical goal guards. The task126
    # candidate intentionally changes output only on the ineffective-action branch.
    if filename == "candidate_126_D_C2.py.txt" and effective:
        assert after == before
    else:
        assert after != before
        assert "Hint:" in after.text or "Reminder:" in after.text


def test_validator_import_does_not_require_optional_simulator_packages() -> None:
    script = """import sys
class RejectOptional:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in {"alfworld", "textworld", "torch", "gym", "gymnasium"}:
            raise AssertionError("unexpected optional simulator import: " + fullname)
sys.meta_path.insert(0, RejectOptional())
from aea.families import _SmokeInner
assert _SmokeInner().get_env_state().goal_text == ""
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
