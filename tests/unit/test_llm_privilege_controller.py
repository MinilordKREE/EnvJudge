"""Production dispatch and fresh judge invocation, with deterministic model responses."""

from __future__ import annotations

import json
from itertools import count
from pathlib import Path
from typing import Any

import pytest

import aea.semantic_low as old_low
import aea.semantic_privilege as old_grammar
import tests.unit.test_assistive_rules as assist_fixtures
from aea.config import AEAConfig
from aea.controller import Controller, TaskRef
from aea.core.hashing import sha256_of
from aea.llm.types import Attribution, ChatRequest, ChatResponse
from aea.privilege_judge import LLMPrivilegeJudge
from aea.substrate import reference_provider
from tests.fixtures.fake_designer import ScriptedDesigner
from tests.fixtures.fake_substrate import FakeSubstrate
from tests.unit.test_assistive_rules import HINT, DoseSubstrate, _reply
from tests.unit.test_iterative_low import REF, _adaptation, _body, _replies
from tests.unit.test_llm_v1 import _trace

CONFIG = AEAConfig(method_version="llm_v2_iterative_low_llm_judge")


def _judge_reply(request: ChatRequest, verdict: str) -> tuple[str, dict[str, Any]]:
    assert request.tools is not None and len(request.tools) == 1
    tool: Any = request.tools[0]
    return str(tool["function"]["name"]), {
        "verdict": verdict,
        "leakage_score": 0.0 if verdict == "PASS" else 0.6,
        "information": "Generic prerequisite reminder"
        if verdict == "PASS"
        else "Unjustified ordering",
        "reference_evidence": "No private fact required"
        if verdict == "PASS"
        else "Private relation",
        "public_evidence_check": "Public goal is authorized; historical failures are not",
        "candidate_evidence": "filter_observation",
        "activation": "positive dose in the supplied current-episode prefix",
        "leak_type": "NONE" if verdict == "PASS" else "SOLUTION_ORDERING",
        "revision_reason": "Use public prerequisites or current-episode observations only.",
    }


@pytest.mark.parametrize("first", ["PASS", "FAIL", "UNCERTAIN"])
def test_production_judge_dispatch_and_bounded_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first: str
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("new production admission invoked the old local grammar")

    monkeypatch.setattr(old_grammar, "screen_semantic_privilege", forbidden)
    monkeypatch.setattr(old_low, "screen_semantic_privilege", forbidden)
    monkeypatch.setattr(old_low.LowPrivilegeScreen, "screen", forbidden)
    original_trace = _trace
    identifiers = count()

    def unique_trace(*args: Any, **kwargs: Any) -> Any:
        return original_trace(*args, **kwargs).model_copy(
            update={"episode_id": f"distinct-fixture-episode-{next(identifiers)}"}
        )

    monkeypatch.setattr(assist_fixtures, "_trace", unique_trace)
    verdicts = iter((first, "PASS"))
    transport = ScriptedDesigner(lambda request: _judge_reply(request, next(verdicts)))

    def complete(request: ChatRequest) -> ChatResponse:
        return transport(request).model_copy(
            update={
                "provider": None,
                "request_sha256": sha256_of(
                    {"provider": "deepseek", "request": request.model_dump()}
                ),
            }
        )

    judge = LLMPrivilegeJudge(
        complete,
        attribution=Attribution(phase="privilege_judge", budget="none", task_id="9"),
    )
    sub = DoseSubstrate(
        {("hint_a", 1.0): [True] * 4, ("hint_a", 0.5): [True, False] * 4},
        _replies(_reply(HINT), _reply(HINT + "\n")),
    )
    designer = sub._designer
    assert isinstance(designer, ScriptedDesigner)
    controller = Controller(
        CONFIG,
        sub,
        tmp_path / "run",
        "judge-production-test",
        reference=lambda task: REF,
        privilege_judge=judge,
    )
    result = controller.run([TaskRef("9", 9)])[0]
    assert result.outcome == "accepted", result.reason
    assert result.detail["d"] == 0.5
    expected = 1 if first == "PASS" else 2
    assert designer.calls == transport.calls == expected
    assert _adaptation(sub) == 12
    if first != "PASS":
        assert "REPLACE_MECHANISM" in _body(designer, 1)
        assert '"category": "privilege"' in _body(designer, 1)
    records = [
        json.loads(line)
        for line in (tmp_path / "run/low_candidates.jsonl").read_text().splitlines()
    ]
    if first != "PASS":
        assert records[0]["solvability"] is None and records[0]["endpoint"] is None
        assert records[1]["parent_candidate_id"] == records[0]["candidate_id"]
    for request in transport.requests:
        assert len(request.messages) == 2
        assert [message.role for message in request.messages] == ["system", "user"]
        assert request.messages[0] != designer.requests[0].messages[0]
        assert request.attribution.phase == "privilege_judge"
        assert request.attribution.budget == "none"
        assert "TYPED DESIGN FEEDBACK" not in request.messages[1].content
        payload = json.loads(request.messages[1].content)
        assert (
            payload["candidate_artifact"].startswith("\nclass _Rules")
            or "class _Rules" in payload["candidate_artifact"]
        )
        assert "PRIVILEGED_REFERENCE_ONLY_SENTINEL" in json.dumps(payload["privileged_reference"])
        assert "PRIVILEGED_REFERENCE_ONLY_SENTINEL" not in json.dumps(
            payload["learner_authorized_evidence"]
        )
        assert payload["optional_runtime_surface_deltas"]
    assert reference_provider(CONFIG, FakeSubstrate({"9": "random"}).open_session) is not None


def test_missing_independent_judge_blocks_before_design_or_policy(tmp_path: Path) -> None:
    sub = DoseSubstrate({}, _replies(_reply(HINT)))
    result = Controller(
        CONFIG,
        sub,
        tmp_path / "run",
        "missing-judge",
        reference=lambda task: REF,
    ).run([TaskRef("9", 9)])[0]
    assert result.outcome != "accepted"
    assert _adaptation(sub) == 0
    assert isinstance(sub._designer, ScriptedDesigner) and sub._designer.calls == 0
    assert "judge" in result.detail["error"]
