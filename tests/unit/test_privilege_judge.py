"""Independent judge schema, fresh requests, and exact evidence bindings; no API calls."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from aea.core.hashing import sha256_of
from aea.errors import ConfigError, InfraError
from aea.llm.types import Attribution, ChatRequest, ChatResponse, ToolCall, Usage
from aea.privilege_judge import (
    JUDGE_PROMPT,
    JUDGE_TOOL_NAME,
    JudgeConfig,
    LLMPrivilegeJudge,
    PrivilegeDecision,
    PrivilegeJudgeInput,
    canonical_json,
    judge_tool,
    text_sha256,
)


def judge_input(source: str = "generic artifact") -> PrivilegeJudgeInput:
    return PrivilegeJudgeInput(
        task_spec={"task_id": "t"},
        public_task_information="Public goal",
        designer_evidence_summary="HISTORICAL_DESIGN_ONLY",
        learner_authorized_evidence={
            "episode": "fresh",
            "step": 0,
            "observations": ["PUBLIC_CURRENT_ONLY"],
        },
        privileged_reference="PRIVATE_REFERENCE_ONLY",
        candidate_artifact=source,
        candidate_artifact_type="configuration",
        candidate_change_summary="Generic support",
        benchmark_contract_summary="Only current episode information is authorized.",
    )


def decision_args(verdict: str = "PASS") -> dict[str, Any]:
    return {
        "verdict": verdict,
        "leakage_score": 0.2,
        "information": "Generic support",
        "reference_evidence": "No private association used",
        "public_evidence_check": "Implied by the public goal",
        "candidate_evidence": "Artifact generic mechanism",
        "activation": "Every activation",
        "leak_type": "NONE" if verdict == "PASS" else "OTHER",
        "revision_reason": "No change required" if verdict == "PASS" else "Replace mechanism",
    }


def judge_response(request: ChatRequest, args: dict[str, Any] | None = None) -> ChatResponse:
    return ChatResponse(
        content="",
        reasoning=None,
        tool_calls=(
            ToolCall(
                id="judge-call",
                name=JUDGE_TOOL_NAME,
                arguments=decision_args() if args is None else args,
            ),
        ),
        finish_reason="tool_calls",
        usage=Usage(prompt_tokens=1, completion_tokens=1),
        model=request.model,
        provider=None,
        upstream_cost=None,
        response_id="offline-judge",
        request_sha256=sha256_of({"provider": "deepseek", "request": request.model_dump()}),
        latency_ms=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, True, "0.2"])
def test_score_is_finite_numeric_diagnostic(score: Any) -> None:
    with pytest.raises(ValidationError):
        PrivilegeDecision.model_validate({**decision_args(), "leakage_score": score})


def test_score_never_overrides_authoritative_verdict() -> None:
    judge = LLMPrivilegeJudge(
        lambda request: judge_response(request, {**decision_args(), "leakage_score": 1.0})
    )
    assert judge.judge(judge_input()).verdict == "PASS"


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "wrong_tool", "no_tool", "multiple", "length", "inconsistent"]
)
def test_malformed_output_is_audited_uncertain(mutation: str) -> None:
    def complete(request: ChatRequest) -> ChatResponse:
        args = decision_args()
        if mutation == "missing":
            args.pop("activation")
        elif mutation == "extra":
            args["analysis"] = "unrequested"
        elif mutation == "inconsistent":
            args["leak_type"] = "HIDDEN_ROUTE"
        response = judge_response(request, args)
        if mutation == "wrong_tool":
            response = response.model_copy(
                update={
                    "tool_calls": (
                        response.tool_calls[0].model_copy(update={"name": "designer_tool"}),
                    )
                }
            )
        elif mutation == "no_tool":
            response = response.model_copy(update={"tool_calls": ()})
        elif mutation == "multiple":
            response = response.model_copy(update={"tool_calls": response.tool_calls * 2})
        elif mutation == "length":
            response = response.model_copy(update={"finish_reason": "length"})
        return response

    result = LLMPrivilegeJudge(complete).judge(judge_input())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty
    assert result.request is not None and result.response is not None


@pytest.mark.parametrize("attribute", ["request_sha256", "model", "provider"])
def test_wrong_response_binding_is_correctness_error(attribute: str) -> None:
    def complete(request: ChatRequest) -> ChatResponse:
        return judge_response(request).model_copy(update={attribute: "wrong"})

    with pytest.raises(ConfigError):
        LLMPrivilegeJudge(complete).judge(judge_input())


def test_transport_error_is_never_semantic_feedback() -> None:
    def broken(request: ChatRequest) -> ChatResponse:
        raise InfraError("offline simulated provider failure")

    with pytest.raises(InfraError):
        LLMPrivilegeJudge(broken).judge(judge_input())


def test_fresh_requests_domains_and_optional_effects() -> None:
    requests: list[ChatRequest] = []

    def complete(request: ChatRequest) -> ChatResponse:
        requests.append(request)
        return judge_response(request)

    evidence = judge_input("SOURCE_ONLY_SENTINEL").model_copy(
        update={
            "optional_runtime_surface_deltas": {"before": "raw", "after": "RUNTIME_ONLY_SENTINEL"}
        }
    )
    judge = LLMPrivilegeJudge(complete)
    first, second = judge.judge(evidence), judge.judge(evidence)
    assert first.input_sha256 == second.input_sha256
    assert requests[0] == requests[1]
    for request in requests:
        assert [message.role for message in request.messages] == ["system", "user"]
        assert request.messages[0].content == JUDGE_PROMPT
        payload = request.messages[1].content
        assert "SOURCE_ONLY_SENTINEL" in payload and "RUNTIME_ONLY_SENTINEL" in payload
        assert "HISTORICAL_DESIGN_ONLY" not in canonical_json(evidence.learner_authorized_evidence)
        assert "PRIVATE_REFERENCE_ONLY" not in canonical_json(evidence.learner_authorized_evidence)
        assert "K16" not in payload
    assert first.source_sha256 == text_sha256(evidence.candidate_artifact)
    assert first.input_sha256 == text_sha256(canonical_json(evidence.model_dump(mode="json")))


@pytest.mark.parametrize("budget,phase", [("eval", "judge"), ("confirm", "judge"), ("none", "K16")])
def test_confirmation_attribution_is_rejected(budget: Any, phase: str) -> None:
    with pytest.raises(ConfigError):
        LLMPrivilegeJudge(judge_response, attribution=Attribution(budget=budget, phase=phase))


@pytest.mark.parametrize("kind", ["overflow", "capture"])
def test_missing_or_overlarge_payload_never_truncates_or_calls(kind: str) -> None:
    calls: list[ChatRequest] = []

    def complete(request: ChatRequest) -> ChatResponse:
        calls.append(request)
        return judge_response(request)

    evidence = judge_input()
    config = JudgeConfig(max_input_bytes=1 if kind == "overflow" else 750_000)
    if kind == "capture":
        evidence = evidence.model_copy(update={"capture_coverage": {"complete": False}})
    result = LLMPrivilegeJudge(complete, config=config).judge(evidence)
    assert result.verdict == "UNCERTAIN" and not calls
    assert result.input_sha256 == text_sha256(canonical_json(evidence.model_dump(mode="json")))
    assert result.request is None and result.response is None


@pytest.mark.parametrize("finish_reason", ["content_filter", "unknown", "stop"])
def test_unsuccessful_or_non_tool_completion_is_uncertain(finish_reason: str) -> None:
    def complete(request: ChatRequest) -> ChatResponse:
        return judge_response(request).model_copy(update={"finish_reason": finish_reason})

    result = LLMPrivilegeJudge(complete).judge(judge_input())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty


def test_complete_named_tool_schema_with_strict_local_admission() -> None:
    tool: Any = judge_tool()
    function = tool["function"]
    assert (
        "strict" not in function
    )  # DeepSeek server strict mode requires a different beta endpoint.
    parameters = function["parameters"]
    assert parameters["additionalProperties"] is False
    assert set(parameters["required"]) == set(PrivilegeDecision.model_fields)
