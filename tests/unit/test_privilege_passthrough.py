"""Narrow reward-copy regression and protected-response mutation checks; no paid calls."""

from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest
from envharness.core.code_loader import load_rules_subclass
from envharness.core.types import Action, EnvResponse, Observation

from aea.designer import Reference, privilege_check

# Hand-written synthetic mechanism; no archived candidate or benchmark trajectory.
SYNTHETIC_FEEDBACK = """class _Rules(Rules):
    DOSE = __DOSE__

    def modify_transition(self, action, raw_response, env_state):
        if self.DOSE <= 0 or env_state.last_action_was_effective:
            return raw_response
        obs = raw_response.observation
        text = "The last action had no effect. " + obs.text
        return EnvResponse(
            observation=Observation(text=text, data=dict(obs.data)),
            reward=raw_response.reward,
            terminated=raw_response.terminated,
            truncated=raw_response.truncated,
            info=raw_response.info,
        )
"""


def _check(source: str) -> list[str]:
    return privilege_check(source, reference=Reference(True, "pass"), failures=[], goal="")


def _transition(body: str, *, parameter: str = "raw_response") -> str:
    return (
        "class _Rules(Rules):\n"
        "    DOSE = __DOSE__\n"
        f"    def modify_transition(self, action, {parameter}, env_state):\n"
        + textwrap.indent(body, "        ")
        + "\n"
    )


COPY = """return EnvResponse(
    observation=raw_response.observation,
    reward=raw_response.reward,
    terminated=raw_response.terminated,
    truncated=raw_response.truncated,
    info=raw_response.info,
)"""


def test_synthetic_feedback_preserves_protected_response_fields() -> None:
    assert _check(SYNTHETIC_FEEDBACK) == []
    cls = load_rules_subclass(SYNTHETIC_FEEDBACK.replace("__DOSE__", "1.0"))
    raw = EnvResponse(
        observation=Observation(text="A public observation", data={}),
        reward=0.375,
        terminated=True,
        truncated=True,
        info={"success": False, "won": False, "verifier": "original"},
    )
    out = cls().modify_transition(
        Action(name="do", kwargs={"text": "look"}),
        raw,
        SimpleNamespace(last_action_was_effective=False),
    )
    assert out.observation != raw.observation
    assert (out.reward, out.terminated, out.truncated, out.info) == (
        raw.reward,
        raw.terminated,
        raw.truncated,
        raw.info,
    )


@pytest.mark.parametrize("parameter", ["raw_response", "response", "original"])
def test_actual_hook_parameter_is_used_instead_of_its_spelling(parameter: str) -> None:
    assert _check(_transition(COPY.replace("raw_response", parameter), parameter=parameter)) == []


def test_unicode_prefix_and_multiline_keyword_positions() -> None:
    body = "label = '提醒'; " + COPY.replace("reward=", "reward =\n    ")
    assert _check(_transition(body)) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("reward=raw_response.reward", "reward=1.0"),
        ("reward=raw_response.reward", "reward=raw_response.reward + 1"),
        ("reward=raw_response.reward", "reward=float(raw_response.reward)"),
        ("reward=raw_response.reward", "reward=raw_response.reward if flag else 1.0"),
        ("reward=raw_response.reward", "reward=other.reward"),
        ("terminated=raw_response.terminated", "terminated=True"),
        ("terminated=raw_response.terminated", "terminated=False"),
        ("terminated=raw_response.terminated", "terminated=not raw_response.terminated"),
        ("truncated=raw_response.truncated", "truncated=True"),
        ("truncated=raw_response.truncated", "truncated=False"),
        ("info=raw_response.info", "info={'success': True}"),
        ("info=raw_response.info", "info={}"),
    ],
)
def test_modified_protected_constructor_fields_never_gain_the_exception(old: str, new: str) -> None:
    assert _check(_transition(COPY.replace(old, new)))


@pytest.mark.parametrize(
    "prefix",
    [
        "raw_response = other",
        "raw_response.reward += 1",
        "raw_response.terminated = flag",
        "raw_response.truncated = flag",
        "raw_response.info['success'] = True",
        "raw_response.info.update(success=True)",
        "alias = raw_response\nalias.reward = 1",
        "info_alias = raw_response.info\ninfo_alias['success'] = True",
        "mutate(raw_response)",
        "mutate(info=raw_response.info)",
        "setattr(raw_response, 'reward', 1)",
        "raw_response.__dict__['reward'] = 1",
        "for raw_response in others:\n    pass",
        "try:\n    pass\nexcept Exception as raw_response:\n    pass",
        "match other:\n    case {'response': raw_response}:\n        pass",
        "import spoof as raw_response",
        "def nested(raw_response):\n    return raw_response",
    ],
)
def test_reassignment_mutation_and_response_escape_retain_rejection(prefix: str) -> None:
    assert "changes the reward" in _check(_transition(prefix + "\n" + COPY))


@pytest.mark.parametrize(
    "prefix",
    [
        "EnvResponse = spoof\n",
        "from spoof import EnvResponse\n",
        "def EnvResponse(**kwargs):\n    return spoof(**kwargs)\n",
        "EnvResponse.model_construct = spoof\n",
        "alias = EnvResponse\nalias.model_construct = spoof\n",
        "mutate(EnvResponse)\n",
        "globals()['EnvResponse'] = spoof\n",
    ],
)
def test_constructor_shadowing_cannot_claim_response_provenance(prefix: str) -> None:
    assert "changes the reward" in _check(prefix + _transition(COPY))


@pytest.mark.parametrize(
    "source",
    [
        _transition(COPY, parameter="actual_response"),  # the convenient name is not the input
        _transition(COPY).replace("modify_transition", "helper"),
        _transition(COPY).replace("class _Rules", "class Helper"),
        _transition(COPY).replace(
            "    def modify_transition", "    @staticmethod\n    def modify_transition"
        ),
        _transition(
            COPY.replace("return EnvResponse", "out = EnvResponse")
            + "\nout.reward += 1\nreturn out"
        ),
        _transition(COPY.replace("return EnvResponse", "return alias")),
    ],
)
def test_only_direct_return_from_actual_transition_hook_qualifies(source: str) -> None:
    assert "changes the reward" in _check(source)


@pytest.mark.parametrize(
    "mutation",
    [
        "raw_response.reward = 1",
        "raw_response.reward += 1",
        "raw_response.reward *= 2",
        "raw_response.terminated = flag",
        "raw_response.truncated = flag",
    ],
)
def test_mutation_followed_by_original_return_is_rejected(mutation: str) -> None:
    assert _check(_transition(mutation + "\nreturn raw_response"))


@pytest.mark.parametrize(
    ("extra", "reason"),
    [
        ("env_state.won = True", "sets won"),
        ("success = True", "sets success"),
        ("self.inner.step(action)", "calls step on the inner environment (disguised Stage)"),
        ("in_env_actions = []", "uses Setup replay"),
    ],
)
def test_existing_shortcut_guards_are_preserved(extra: str, reason: str) -> None:
    assert reason in _check(_transition(extra + "\n" + COPY))


def test_direct_reference_copy_still_rejected_with_reward_passthrough() -> None:
    source = _transition("hint = 'take token 7 from alcove 2'\n" + COPY)
    reasons = privilege_check(
        source,
        reference=Reference(True, "pass", ("take token 7 from alcove 2",)),
        failures=[],
        goal="",
    )
    assert any(reason.startswith("reference action embedded:") for reason in reasons)
    assert any(reason.startswith("privileged constants from the reference:") for reason in reasons)


def test_unparseable_code_never_gains_exception() -> None:
    assert "changes the reward" in _check(_transition(COPY) + "invalid Python !!!")
