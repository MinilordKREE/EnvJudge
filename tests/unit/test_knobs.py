from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

from envharness.core.types import Action

from aea import exemplars
from aea.certs import replay_actions
from aea.knobs import (
    CONTRACT_TEXT,
    EXEMPLARS,
    Displacement,
    FooterMask,
    HorizonSqueeze,
    KnobContext,
    ProposedKnob,
    displacement_k,
    footer_bucket,
    footer_masked,
    horizon_m,
    order_families,
    parse_proposals,
    propose_knobs,
    validate_rules_template,
)
from aea.llm.types import Attribution, ChatRequest, ChatResponse, ToolCall, Usage
from tests.fixtures.fake_world import make_open

PLAN = ["go to a", "take x from a", "go to b", "move x to b"]


def test_exemplar_text_is_single_source() -> None:
    template = exemplars.prompt_text("footer_mask")
    assert "__DOSE__" in template and "__TASK_ID__" in template
    code = exemplars.render("footer_mask", dose=0.5, task_id="7")
    assert (
        "DOSE = 0.5" in code
        and "TASK_ID = '7'" in code
        and "__" not in code.replace("__init__", "")
    )
    assert validate_rules_template(template).ok


def test_footer_buckets_nested_deterministic_and_cross_process() -> None:
    steps = range(200)
    m_half = {s for s in steps if footer_masked("7", s, 0.5)}
    m_full = {s for s in steps if footer_masked("7", s, 1.0)}
    m_quarter = {s for s in steps if footer_masked("7", s, 0.25)}
    assert m_quarter <= m_half <= m_full == set(steps)
    assert 60 < len(m_half) < 140
    script = (
        "from aea.knobs import footer_bucket; import json; "
        "print(json.dumps([footer_bucket('7', s) for s in range(50)]))"
    )
    out = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    ).stdout
    assert json.loads(out) == [footer_bucket("7", s) for s in range(50)]


def test_footer_mask_hides_footer_and_data_at_d1() -> None:
    cand = FooterMask().make(1.0, KnobContext(task_id="7"))
    assert cand is not None
    sess = make_open(PLAN)(cand)
    r = sess.step_text("go to a")
    assert "Admissible commands" not in r["obs"]
    obs = sess.stack.observe()
    assert "admissible_commands" not in obs.data and "Admissible commands" not in obs.text
    assert replay_actions(sess, PLAN[1:]).ok  # still solvable by construction


def test_horizon_quantile_and_boundary() -> None:
    lengths = [4, 6, 8, 10]
    assert (
        horizon_m(lengths, 0.0) == 10
        and horizon_m(lengths, 1.0) == 4
        and horizon_m(lengths, 0.5) == 6
    )
    assert horizon_m([], 0.5) is None
    ctx = KnobContext(task_id="7", success_lengths=(4, 6))
    cand = HorizonSqueeze().make(1.0, ctx)  # m = 4 = the shortest success
    assert cand is not None and "M = 4" in cand.rules_code
    open_fn = make_open(PLAN)
    sess = open_fn(cand)
    r = replay_actions(sess, PLAN)  # completes at exactly step m
    assert r.ok and sess.won
    last = open_fn(cand)
    for a in PLAN:
        resp = last.step_text(a)
    assert resp["won"] and resp["terminated"] and not resp["truncated"]  # success at step m stands
    sess = open_fn(cand)
    out = replay_actions(sess, ["look", *PLAN])  # one step late: truncated, not terminated, not won
    assert not out.ok and sess.ended and not sess.won
    resp = None
    sess2 = open_fn(cand)
    for a in ["look", "go to a", "take x from a", "go to b"]:
        resp = sess2.step_text(a)
    assert resp is not None and resp["truncated"] and not resp["terminated"]


def test_displacement_and_k() -> None:
    assert [displacement_k(d) for d in (1 / 3, 2 / 3, 1.0)] == [1, 2, 3]
    ctx = KnobContext(task_id="7", setup_builder=lambda d: ["go to a", "look"] if d < 1 else None)
    cand = Displacement().make(0.5, ctx)
    assert cand is not None and [a.kwargs["text"] for a in cand.in_env_actions] == [
        "go to a",
        "look",
    ]
    assert (
        Displacement().make(1.0, ctx) is None
        and Displacement().make(0.5, KnobContext(task_id="7")) is None
    )


def test_validation_rejects_bad_proposals() -> None:
    assert not validate_rules_template("class _Rules(Rules):\n    pass\n").ok  # no DOSE
    bad = validate_rules_template(
        "class _Rules(Rules):\n    DOSE = __DOSE__\n"
        "    def filter_observation(self, obs, env_state):\n        return 1/0\n"
    )
    assert not bad.ok and "smoke" in bad.reasons[0]
    assert not validate_rules_template("class Other(Rules):\n    DOSE = __DOSE__\n").ok
    good = (
        "class _Rules(Rules):\n    DOSE = __DOSE__\n"
        "    def filter_action(self, action, env_state):\n"
        "        return Blocked(reason='x') if self.DOSE > 2 else action\n"
    )
    knobs, rejected = parse_proposals(
        {
            "knobs": [
                {"name": "k1", "axis": "A", "rules_code": good, "nested": True},
                {"name": "k2", "axis": "Z", "rules_code": good},
                {"name": "k3", "axis": "O", "rules_code": "x = 1"},
            ],
            "ranking": ["k1"],
        },
        max_families=2,
    )
    assert [k.name for k in knobs] == ["k1"] and len(
        rejected
    ) == 1  # k3 cut by max_families, k2 bad axis
    made = knobs[0].make(0.5, KnobContext(task_id="9"))
    assert made is not None and "DOSE = 0.5" in made.rules_code


def test_proposer_call_and_ordering() -> None:
    good = "class _Rules(Rules):\n    DOSE = __DOSE__\n"
    seen: list[ChatRequest] = []

    def complete(request: ChatRequest) -> ChatResponse:
        seen.append(request)
        return ChatResponse(
            content="",
            reasoning=None,
            tool_calls=(
                ToolCall(
                    id="c",
                    name="propose_knobs",
                    arguments={
                        "knobs": [
                            {"name": "lamp", "axis": "O", "rules_code": good, "nested": False}
                        ],
                        "ranking": ["horizon_squeeze", "lamp"],
                    },
                ),
            ),
            finish_reason="stop",
            usage=Usage(prompt_tokens=1, completion_tokens=1),
            model="m",
            provider="fake",
            upstream_cost=None,
            response_id=None,
            request_sha256="s",
            latency_ms=0,
            created_at=datetime.now(UTC),
        )

    knobs, rejected, ranking = propose_knobs(
        complete,
        model="m",
        task_description="put x in b",
        success_summary="4 steps",
        max_families=2,
        attribution=Attribution(budget="designer"),
    )
    assert (
        [k.name for k in knobs] == ["lamp"]
        and not rejected
        and ranking == ["horizon_squeeze", "lamp"]
    )
    assert seen[0].tools and seen[0].attribution.budget == "designer"
    assert (
        "footer_mask" in seen[0].messages[1].content and "__DOSE__" in seen[0].messages[1].content
    )
    ordered = order_families(knobs, ranking)
    assert [k.name for k in ordered[:2]] == ["horizon_squeeze", "lamp"]
    assert [k.name for k in order_families(knobs, [])] == [k.name for k in EXEMPLARS] + ["lamp"]
    assert isinstance(ordered[1], ProposedKnob)


def test_horizon_squeeze_success_signals_exist_on_the_bridge_contract() -> None:
    """The exemplar guards on ``raw_response.info["success"]`` and ``env_state.won``; the fake
    bridge mirrors the real one (bridge.py:300-330). A renamed bridge field must fail here."""
    template = exemplars.prompt_text("horizon_squeeze")
    assert 'info.get("success")' in template and '"won"' in template
    sess = make_open(PLAN)(None)
    resp = sess.stack.step(Action(name="do", kwargs={"text": "look"}))
    assert "success" in resp.info and hasattr(sess.bridge.state, "won")


def test_exemplar_copies_are_rejected_and_calls_recorded() -> None:
    copy = exemplars.prompt_text("footer_mask")
    knobs, rejected = parse_proposals(
        {"knobs": [{"name": "my_mask", "axis": "O", "rules_code": copy, "nested": True}]},
        max_families=2,
    )
    assert not knobs and "duplicate of an exemplar" in rejected[0]
    knobs, rejected = parse_proposals(
        {
            "knobs": [
                {
                    "name": "horizon_squeeze",
                    "axis": "T",
                    "rules_code": "class _Rules(Rules):\n    DOSE = __DOSE__\n",
                    "nested": True,
                }
            ]
        },
        max_families=2,
    )
    assert not knobs and "duplicate" in rejected[0]
    recorded: list[dict[str, Any]] = []

    def complete(request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content="",
            reasoning=None,
            tool_calls=(
                ToolCall(id="c", name="propose_knobs", arguments={"knobs": [], "ranking": []}),
            ),
            finish_reason="stop",
            usage=Usage(prompt_tokens=1, completion_tokens=1),
            model="m",
            provider="fake",
            upstream_cost=None,
            response_id=None,
            request_sha256="s",
            latency_ms=0,
            created_at=datetime.now(UTC),
        )

    knobs, rejected, _ranking = propose_knobs(
        complete,
        model="m",
        task_description="t",
        success_summary="s",
        max_families=2,
        attribution=Attribution(budget="designer"),
        record=recorded.append,
    )
    assert knobs == [] and recorded and recorded[0]["arguments"] == {"knobs": [], "ranking": []}
    assert "do not re-propose" in CONTRACT_TEXT
