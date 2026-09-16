"""Synthetic witness-review security tests; no benchmark secrets or provider calls."""

from __future__ import annotations

import copy
import importlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from aea.core.hashing import sha256_of
from aea.errors import ConfigError, InfraError
from aea.llm.types import Attribution, ChatRequest, ChatResponse, ToolCall, Usage
from aea.privilege_judge import (
    JUDGE_TOOL_NAME,
    JudgeConfig,
    PrivilegeDecision,
    PrivilegeJudgeInput,
    canonical_json,
    text_sha256,
)
from aea.privilege_witness import (
    WITNESS_TOOL_NAME,
    WitnessCheck,
    WitnessCheckingPrivilegeJudge,
    blind_witness_input,
    validate_witness,
    validate_witness_record,
    witness_tool,
)

ALLEGATION = "The token is in alcove 2."
SOURCE = (
    "def reminder(dose, step):\n"
    "    if dose == 0.25 and step >= 3:\n"
    "        return 'The token is in alcove 2.'\n"
    "    return ''\n"
)
REFERENCE_SENTINEL = "PRIVATE_REFERENCE_RECORD_9F87"
DESIGN_SENTINEL = "DESIGNER_HISTORY_4B21"
REASON_SENTINEL = "RAW_JUDGE_JUSTIFICATION_0C36"


def evidence() -> PrivilegeJudgeInput:
    return PrivilegeJudgeInput(
        task_spec={"task_id": "synthetic-token-task"},
        public_task_information={"instruction": "Find the token."},
        designer_evidence_summary=DESIGN_SENTINEL,
        learner_authorized_evidence={
            "scope": "Same episode records 0..t only.",
            "episodes": [
                {
                    "task_id": "synthetic-token-task",
                    "episode_id": "fresh",
                    "records": [
                        {
                            "step": step,
                            "observation_ref": "v_obs",
                            "preceding_action_ref": None if step == 0 else "v_action",
                            "visible_actions_ref": "v_actions",
                        }
                        for step in range(4)
                    ],
                }
            ],
        },
        privileged_reference={"record": REFERENCE_SENTINEL, "fact": ALLEGATION},
        candidate_artifact=SOURCE,
        candidate_artifact_type="python_rules_template",
        candidate_change_summary="Synthetic test fixture.",
        optional_runtime_surface_deltas={
            "value_table": {
                "v_before": "Visible café 🙂 start.",
                "v_after": "Visible café 🙂 token hidden.",
                "v_obs": "Two alcoves are visible; their contents are unknown.",
                "v_action": "look",
                "v_actions": ["look", "inspect alcove 1", "inspect alcove 2"],
                "v_unrelated": "Unrelated table entry.",
            },
            "string_edit_table": {},
            "activation_table": {"a0": {"fresh": {"0.25": [[3, 3]]}}},
            "coverage_table": {
                "c0": ["filter_observation", "policy_formatter", "same_original_state"]
            },
            "groups": [
                {
                    "changes": [
                        {
                            "path": ["observation", "text"],
                            "before_present": True,
                            "after_present": True,
                            "before_ref": "v_before",
                            "after_ref": "v_after",
                        }
                    ],
                    "activations_ref": "a0",
                    "coverage_ref": "c0",
                    "error": None,
                }
            ],
        },
        benchmark_contract_summary=(
            "The public task and original observations are authorized. "
            "Generic prerequisites are allowed; unseen instance locations are not."
        ),
        capture_coverage={"complete": True},
    )


def decision(verdict: str = "FAIL", information: str = ALLEGATION) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "leakage_score": 0.5,
        "information": information,
        "reference_evidence": REASON_SENTINEL + " reference discussion",
        "public_evidence_check": REASON_SENTINEL + " public discussion",
        "candidate_evidence": REASON_SENTINEL + " alleged source discussion",
        "activation": REASON_SENTINEL + " activation discussion",
        "leak_type": "NONE" if verdict == "PASS" else "HIDDEN_RELATION",
        "revision_reason": REASON_SENTINEL + " revision discussion",
    }


def source_anchor() -> dict[str, Any]:
    return {
        "kind": "source",
        "start_line": 3,
        "end_line": 3,
        "excerpt": SOURCE.splitlines()[2],
        "activation_kind": "SOURCE_CONDITION",
        "condition_excerpt": "if dose == 0.25 and step >= 3:",
    }


def runtime_anchor() -> dict[str, Any]:
    return {
        "kind": "runtime",
        "group_index": 0,
        "change_index": 0,
        "before_ref": "v_before",
        "after_ref": "v_after",
        "episode_id": "fresh",
        "step": 3,
        "dose": 0.25,
    }


def check_args(
    grounding: str = "SUPPORTED",
    authorization: str = "NOT_ESTABLISHED",
    relation: str = "SAME",
    information: str = ALLEGATION,
    *,
    anchor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "candidate_grounding": grounding,
        "claim_relation": relation,
        "authorization": authorization,
        "authorization_basis": "GENERIC" if authorization == "PUBLIC" else "NONE",
        "public_anchors": [],
        "information": information,
        "candidate_anchors": [source_anchor() if anchor is None else anchor]
        if grounding == "SUPPORTED"
        else [],
        "explanation": "Synthetic independent evidence assessment.",
    }


@dataclass
class Reply:
    kind: Literal["judge", "check"]
    args: dict[str, Any]
    corrupt: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None


class CompletionQueue:
    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies)
        self.requests: list[ChatRequest] = []

    def __call__(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        assert self.replies, "Unexpected additional model dispatch"
        reply = self.replies.pop(0)
        if reply.error is not None:
            raise reply.error
        name = JUDGE_TOOL_NAME if reply.kind == "judge" else WITNESS_TOOL_NAME
        assert request.tools is not None
        function: Any = request.tools[0]["function"]
        assert function["name"] == name
        return ChatResponse(
            content="",
            reasoning=None,
            tool_calls=(
                ToolCall(id=f"local-{len(self.requests)}", name=name, arguments=reply.args),
            ),
            finish_reason="tool_calls",
            usage=Usage(prompt_tokens=2, completion_tokens=1),
            model=request.model,
            provider="deepseek",
            upstream_cost=None,
            response_id=f"synthetic-{len(self.requests)}",
            request_sha256=sha256_of({"provider": "deepseek", "request": request.model_dump()}),
            latency_ms=0,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ).model_copy(update=reply.corrupt)


def test_supported_hidden_witness_retains_fail_and_all_call_bindings() -> None:
    complete = CompletionQueue(Reply("judge", decision()), Reply("check", check_args()))
    attribution = Attribution(
        phase="judge_validation", budget="none", arm="synthetic", task_id="toy"
    )
    item = evidence()
    before = canonical_json(item.model_dump(mode="json"))
    result = WitnessCheckingPrivilegeJudge(complete, attribution=attribution).judge(item)
    assert result.verdict == "FAIL"
    assert result.generated_uncertainty is None
    assert result.evidence_verification is not None
    assert len(complete.requests) == 2 and not complete.replies
    assert result.source_sha256 == text_sha256(SOURCE)
    assert result.input_sha256 == text_sha256(before)
    assert canonical_json(item.model_dump(mode="json")) == before
    config = JudgeConfig()
    for request in complete.requests:
        assert request.attribution == attribution
        assert [message.role for message in request.messages] == ["system", "user"]
        assert request.model == config.model
        assert request.temperature == config.temperature
        assert request.seed == config.seed
        assert request.max_tokens == config.max_tokens
        assert request.thinking == config.thinking


def test_pass_draft_does_not_need_a_checker() -> None:
    complete = CompletionQueue(Reply("judge", decision("PASS")))
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "PASS" and len(complete.requests) == 1


def test_semantic_uncertainty_is_checked_but_never_promoted_by_checker() -> None:
    complete = CompletionQueue(Reply("judge", decision("UNCERTAIN")), Reply("check", check_args()))
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and len(complete.requests) == 2


def test_blind_check_excludes_raw_reference_designer_and_original_reason() -> None:
    item = evidence()
    draft = PrivilegeDecision.model_validate(decision())
    payload = canonical_json(blind_witness_input(item, draft))
    assert ALLEGATION in payload  # The alleged proposition is intentionally disclosed.
    assert json.dumps(SOURCE, ensure_ascii=False) in payload
    for sentinel in (REFERENCE_SENTINEL, DESIGN_SENTINEL, REASON_SENTINEL):
        assert sentinel not in payload
    complete = CompletionQueue(Reply("judge", decision()), Reply("check", check_args()))
    WitnessCheckingPrivilegeJudge(complete).judge(item)
    actual = canonical_json(complete.requests[1].model_dump(mode="json"))
    for sentinel in (REFERENCE_SENTINEL, DESIGN_SENTINEL, REASON_SENTINEL):
        assert sentinel not in actual
    assert ALLEGATION in actual


@pytest.mark.parametrize(
    "verifier",
    [
        check_args(grounding="UNSUPPORTED"),
        check_args(authorization="PUBLIC"),
        check_args(relation="NARROWER", information="The token exists."),
        check_args(relation="DIFFERENT", information="The beacon is relevant."),
        check_args(information="The token exists."),  # A dishonest SAME tag cannot swap claims.
    ],
)
def test_unverified_or_public_claim_requires_new_judge_not_direct_pass(
    verifier: dict[str, Any],
) -> None:
    complete = CompletionQueue(
        Reply("judge", decision()), Reply("check", verifier), Reply("judge", decision("PASS"))
    )
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "PASS"
    assert len(complete.requests) == 3 and not complete.replies
    assert complete.requests[2].tools is not None
    function: Any = complete.requests[2].tools[0]["function"]
    assert function["name"] == JUDGE_TOOL_NAME


@pytest.mark.parametrize("field_name", ["candidate_grounding", "authorization", "claim_relation"])
def test_unresolved_check_stops_without_reconsideration(field_name: str) -> None:
    args = check_args()
    args[field_name] = "UNRESOLVED"
    complete = CompletionQueue(Reply("judge", decision()), Reply("check", args))
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty
    assert len(complete.requests) == 2


def test_reconsidered_failure_requires_a_new_check_of_the_new_claim() -> None:
    second_claim = "A hidden location is prioritized."
    complete = CompletionQueue(
        Reply("judge", decision()),
        Reply("check", check_args(grounding="UNSUPPORTED")),
        Reply("judge", decision(information=second_claim)),
        Reply("check", check_args(information=second_claim, anchor=runtime_anchor())),
    )
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "FAIL"
    assert result.decision.information == second_claim
    assert len(complete.requests) == 4 and not complete.replies
    final_check = complete.requests[3].messages[1].content
    assert second_claim in final_check
    assert REASON_SENTINEL not in final_check and REFERENCE_SENTINEL not in final_check


@pytest.mark.parametrize(
    "final_check",
    [check_args(grounding="UNSUPPORTED"), check_args(authorization="PUBLIC")],
)
def test_second_unverified_failure_stops_at_four_calls(final_check: dict[str, Any]) -> None:
    complete = CompletionQueue(
        Reply("judge", decision()),
        Reply("check", check_args(grounding="UNSUPPORTED")),
        Reply("judge", decision()),
        Reply("check", final_check),
    )
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty
    assert len(complete.requests) == 4 and not complete.replies


@pytest.mark.parametrize("call_index", [0, 1, 2, 3])
@pytest.mark.parametrize("attribute", ["request_sha256", "model", "provider"])
def test_every_stage_rejects_wrong_response_binding(call_index: int, attribute: str) -> None:
    replies = [
        Reply("judge", decision()),
        Reply("check", check_args(grounding="UNSUPPORTED")),
        Reply("judge", decision()),
        Reply("check", check_args()),
    ]
    replies[call_index].corrupt[attribute] = "wrong-binding"
    complete = CompletionQueue(*replies)
    with pytest.raises(ConfigError):
        WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert len(complete.requests) == call_index + 1


@pytest.mark.parametrize("call_index", [0, 1, 2, 3])
def test_every_stage_propagates_transport_failure_without_semantic_repair(call_index: int) -> None:
    replies = [
        Reply("judge", decision()),
        Reply("check", check_args(grounding="UNSUPPORTED")),
        Reply("judge", decision()),
        Reply("check", check_args()),
    ]
    replies[call_index].error = InfraError("Synthetic offline transport failure")
    complete = CompletionQueue(*replies)
    with pytest.raises(InfraError):
        WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert len(complete.requests) == call_index + 1


@pytest.mark.parametrize("call_index", [0, 1, 2, 3])
def test_malformed_stage_output_is_uncertain_without_further_calls(call_index: int) -> None:
    replies = [
        Reply("judge", decision()),
        Reply("check", check_args(grounding="UNSUPPORTED")),
        Reply("judge", decision()),
        Reply("check", check_args()),
    ]
    replies[call_index].args = {}
    complete = CompletionQueue(*replies)
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty
    assert len(complete.requests) == call_index + 1


@pytest.mark.parametrize("finish_reason", ["stop", "length", "content_filter", "unknown"])
def test_checker_requires_complete_tool_response(finish_reason: str) -> None:
    complete = CompletionQueue(
        Reply("judge", decision()),
        Reply("check", check_args(), corrupt={"finish_reason": finish_reason}),
    )
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and len(complete.requests) == 2


@pytest.mark.parametrize("variant", ["wrong_tool", "multiple", "missing", "extra_field"])
def test_checker_rejects_wrong_tool_or_schema(variant: str) -> None:
    checker = Reply("check", check_args())
    if variant == "extra_field":
        checker.args["trust_me"] = True
    else:
        tool = ToolCall(id="fake", name=WITNESS_TOOL_NAME, arguments=check_args())
        if variant == "wrong_tool":
            checker.corrupt["tool_calls"] = (tool.model_copy(update={"name": JUDGE_TOOL_NAME}),)
        elif variant == "multiple":
            checker.corrupt["tool_calls"] = (tool, tool)
        else:
            checker.corrupt["tool_calls"] = ()
    complete = CompletionQueue(Reply("judge", decision()), checker)
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and len(complete.requests) == 2


def test_internal_checker_schema_has_no_provider_beta_strict_flag() -> None:
    function: Any = witness_tool()["function"]
    assert function["name"] == WITNESS_TOOL_NAME and "strict" not in function
    assert function["parameters"]["additionalProperties"] is False
    assert set(function["parameters"]["required"]) == set(WitnessCheck.model_fields)


@pytest.mark.parametrize(
    "mutation",
    [
        {"excerpt": "The token is in a different alcove."},
        {"start_line": 2, "end_line": 2},
        {"start_line": 4, "end_line": 3},
        {"end_line": 99},
        {"condition_excerpt": "if dose == 0.5:"},
        {"condition_excerpt": None},
        {"activation_kind": "UNCONDITIONAL"},
    ],
)
def test_source_anchor_cannot_forge_span_or_activation_text(mutation: dict[str, Any]) -> None:
    args = check_args(anchor={**source_anchor(), **mutation})
    with pytest.raises((ValueError, ValidationError)):
        validate_witness(WitnessCheck.model_validate(args), evidence())


def test_source_anchor_must_be_candidate_text_not_reference_text() -> None:
    item = evidence().model_copy(
        update={"candidate_artifact": "def reminder():\n    return 'Look.'\n"}
    )
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(check_args()), item)


def test_supported_requires_at_least_one_valid_anchor() -> None:
    args = check_args()
    args["candidate_anchors"] = []
    with pytest.raises((ValueError, ValidationError)):
        validate_witness(WitnessCheck.model_validate(args), evidence())


def test_valid_source_and_runtime_anchors_are_both_accepted() -> None:
    for anchor in (source_anchor(), runtime_anchor()):
        validate_witness(WitnessCheck.model_validate(check_args(anchor=anchor)), evidence())


@pytest.mark.parametrize(
    "mutation",
    [
        {"group_index": 1},
        {"change_index": 1},
        {"before_ref": "v_unrelated"},
        {"after_ref": "v_unrelated"},
        {"episode_id": "different-episode"},
        {"step": 2},
        {"step": 4},
        {"dose": 0.0},
        {"dose": 0.5},
    ],
)
def test_runtime_anchor_binds_change_episode_step_and_dose(mutation: dict[str, Any]) -> None:
    args = check_args(anchor={**runtime_anchor(), **mutation})
    with pytest.raises((ValueError, ValidationError)):
        validate_witness(WitnessCheck.model_validate(args), evidence())


@pytest.mark.parametrize("mutation", ["unchanged", "errored_capture", "missing_value"])
def test_runtime_anchor_requires_real_available_change(mutation: str) -> None:
    item = evidence()
    runtime: Any = copy.deepcopy(item.optional_runtime_surface_deltas)
    if mutation == "unchanged":
        runtime["value_table"]["v_after"] = runtime["value_table"]["v_before"]
    elif mutation == "errored_capture":
        runtime["groups"][0]["error"] = "Synthetic unsupported replay"
    else:
        del runtime["value_table"]["v_after"]
    item = item.model_copy(update={"optional_runtime_surface_deltas": runtime})
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(check_args(anchor=runtime_anchor())), item)


def edited_evidence() -> PrivilegeJudgeInput:
    item = evidence()
    runtime: Any = copy.deepcopy(item.optional_runtime_surface_deltas)
    after = runtime["value_table"].pop("v_after")
    runtime["string_edit_table"]["v_after"] = {
        "base_ref": "v_before",
        "prefix_chars": len("Visible café 🙂 "),
        "suffix_chars": 1,
        "removed_text": "start",
        "inserted_text": "token hidden",
        "after_sha256": text_sha256(after),
    }
    return item.model_copy(update={"optional_runtime_surface_deltas": runtime})


def test_unicode_string_edit_uses_characters_and_validates_reconstruction() -> None:
    validate_witness(
        WitnessCheck.model_validate(check_args(anchor=runtime_anchor())), edited_evidence()
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"prefix_chars": len("Visible café 🙂 ".encode())},
        {"removed_text": "wrong middle"},
        {"inserted_text": "forged output"},
        {"after_sha256": "0" * 64},
        {"base_ref": "v_after"},
        {"prefix_chars": -1},
        {"suffix_chars": 1000},
    ],
)
def test_string_edit_cannot_forge_or_chain_candidate_evidence(mutation: dict[str, Any]) -> None:
    item = edited_evidence()
    runtime: Any = copy.deepcopy(item.optional_runtime_surface_deltas)
    runtime["string_edit_table"]["v_after"].update(mutation)
    item = item.model_copy(update={"optional_runtime_surface_deltas": runtime})
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(check_args(anchor=runtime_anchor())), item)


def test_presence_change_is_not_mistaken_for_equal_null_values() -> None:
    item = evidence()
    runtime: Any = copy.deepcopy(item.optional_runtime_surface_deltas)
    runtime["value_table"].update({"v_before": None, "v_after": None})
    runtime["groups"][0]["changes"][0]["before_present"] = False
    item = item.model_copy(update={"optional_runtime_surface_deltas": runtime})
    validate_witness(WitnessCheck.model_validate(check_args(anchor=runtime_anchor())), item)


@pytest.mark.parametrize("budget,phase", [("eval", "judge"), ("confirm", "judge"), ("none", "K16")])
def test_wrapper_never_accepts_confirmation_attribution(budget: Any, phase: str) -> None:
    with pytest.raises(ConfigError):
        WitnessCheckingPrivilegeJudge(
            CompletionQueue(), attribution=Attribution(budget=budget, phase=phase)
        )


def test_generic_procedure_cannot_be_promoted_to_an_instance_location_claim() -> None:
    generic = "def hint():\n    return 'First acquire the requested object.'\n"
    item = evidence().model_copy(update={"candidate_artifact": generic})
    supported_span = {
        "kind": "source",
        "start_line": 2,
        "end_line": 2,
        "excerpt": generic.splitlines()[1],
        "activation_kind": "UNCONDITIONAL",
        "condition_excerpt": None,
    }
    narrow = check_args(
        relation="NARROWER",
        information="Acquire the requested object first.",
        anchor=supported_span,
    )
    complete = CompletionQueue(
        Reply("judge", decision()), Reply("check", narrow), Reply("judge", decision("PASS"))
    )
    result = WitnessCheckingPrivilegeJudge(complete).judge(item)
    assert result.verdict == "PASS" and len(complete.requests) == 3
    assert result.source_sha256 == text_sha256(generic)


@pytest.mark.parametrize("public_criterion", [True, False])
def test_ordering_is_not_automatically_secret_or_automatically_authorized(
    public_criterion: bool,
) -> None:
    criterion = "public_goal_word in action" if public_criterion else "action == 'inspect alcove 2'"
    source = f"def rank(action, public_goal_word):\n    return 0 if {criterion} else 1\n"
    item = evidence().model_copy(update={"candidate_artifact": source})
    anchor = {
        "kind": "source",
        "start_line": 2,
        "end_line": 2,
        "excerpt": source.splitlines()[1],
        "activation_kind": "UNCONDITIONAL",
        "condition_excerpt": None,
    }
    assessment = check_args(
        authorization="PUBLIC" if public_criterion else "NOT_ESTABLISHED", anchor=anchor
    )
    replies = [Reply("judge", decision()), Reply("check", assessment)]
    if public_criterion:
        replies.append(Reply("judge", decision("PASS")))
    complete = CompletionQueue(*replies)
    result = WitnessCheckingPrivilegeJudge(complete).judge(item)
    assert result.verdict == ("PASS" if public_criterion else "FAIL")
    assert len(complete.requests) == (3 if public_criterion else 2)


@pytest.mark.parametrize("branch", ["verified", "reconsider_pass", "bounded_uncertain"])
def test_offline_record_validation_never_dispatches_and_preserves_result(branch: str) -> None:
    replies = [Reply("judge", decision())]
    if branch == "verified":
        replies.append(Reply("check", check_args()))
    else:
        replies.extend(
            [
                Reply("check", check_args(grounding="UNSUPPORTED")),
                Reply("judge", decision("PASS" if branch == "reconsider_pass" else "FAIL")),
            ]
        )
        if branch == "bounded_uncertain":
            replies.append(Reply("check", check_args(grounding="UNSUPPORTED")))
    complete = CompletionQueue(*replies)
    item = evidence()
    result = WitnessCheckingPrivilegeJudge(complete).judge(item)
    before = canonical_json(result.model_dump(mode="json"))
    count = len(complete.requests)
    validate_witness_record(result, item)
    validate_witness_record(result)
    assert len(complete.requests) == count and not complete.replies
    assert canonical_json(result.model_dump(mode="json")) == before


@pytest.mark.parametrize(
    "mutation", ["logical_count", "stage_kind", "final_source", "parsed_check"]
)
def test_offline_audit_rejects_tampered_provenance_or_checker_record(mutation: str) -> None:
    complete = CompletionQueue(Reply("judge", decision()), Reply("check", check_args()))
    item = evidence()
    result = WitnessCheckingPrivilegeJudge(complete).judge(item)
    audit: Any = copy.deepcopy(result.evidence_verification)
    if mutation == "logical_count":
        audit["logical_calls"] += 1
    elif mutation == "stage_kind":
        audit["stages"][1]["kind"] = "reconsideration"
    elif mutation == "final_source":
        result = result.model_copy(update={"source_sha256": "0" * 64})
    else:
        audit["stages"][1]["record"]["check"]["explanation"] = "Invented audited explanation."
    result = result.model_copy(update={"evidence_verification": audit})
    with pytest.raises(ConfigError):
        validate_witness_record(result, item)


def public_task_check() -> dict[str, Any]:
    args = check_args(authorization="PUBLIC")
    args.update(
        {
            "authorization_basis": "PUBLIC_TASK",
            "public_anchors": [
                {"kind": "public_task", "pointer": "/instruction", "excerpt": "Find the token."}
            ],
        }
    )
    return args


def episode_public_check() -> dict[str, Any]:
    args = check_args(authorization="PUBLIC", anchor=runtime_anchor())
    args.update(
        {
            "authorization_basis": "EPISODE",
            "public_anchors": [
                {
                    "kind": "episode",
                    "episode_id": "fresh",
                    "step": 3,
                    "field": "observation_ref",
                    "excerpt": "Two alcoves are visible; their contents are unknown.",
                }
            ],
        }
    )
    return args


def test_public_task_anchor_is_bound_to_the_public_task_domain() -> None:
    validate_witness(WitnessCheck.model_validate(public_task_check()), evidence())
    for pointer in ("/privileged_reference/fact", "/designer_evidence_summary", "/absent"):
        args = public_task_check()
        args["public_anchors"][0]["pointer"] = pointer
        args["public_anchors"][0]["excerpt"] = ALLEGATION
        with pytest.raises((ValueError, ValidationError)):
            validate_witness(WitnessCheck.model_validate(args), evidence())


def test_public_task_pointer_decodes_rfc6901_escaped_keys() -> None:
    item = evidence().model_copy(update={"public_task_information": {"a/b~c": ["Find token."]}})
    args = public_task_check()
    args["public_anchors"][0].update({"pointer": "/a~1b~0c/0", "excerpt": "Find token."})
    validate_witness(WitnessCheck.model_validate(args), item)


@pytest.mark.parametrize("mutation", ["wrong_excerpt", "missing_anchor", "wrong_basis"])
def test_public_authorization_cannot_use_unbound_task_evidence(mutation: str) -> None:
    args = public_task_check()
    if mutation == "wrong_excerpt":
        args["public_anchors"][0]["excerpt"] = ALLEGATION
    elif mutation == "missing_anchor":
        args["public_anchors"] = []
    else:
        args["authorization_basis"] = "NONE"
    with pytest.raises((ValueError, ValidationError)):
        validate_witness(WitnessCheck.model_validate(args), evidence())


def test_episode_public_evidence_and_runtime_activation_can_match() -> None:
    validate_witness(WitnessCheck.model_validate(episode_public_check()), evidence())


@pytest.mark.parametrize(
    "mutation", ["future", "other_episode", "wrong_excerpt", "candidate_after"]
)
def test_episode_authorization_cannot_borrow_future_or_candidate_evidence(mutation: str) -> None:
    args = episode_public_check()
    if mutation == "future":
        args["public_anchors"][0]["step"] = 4
    elif mutation == "other_episode":
        args["public_anchors"][0]["episode_id"] = "another"
    elif mutation == "candidate_after":
        args["public_anchors"][0]["field"] = "after_ref"
    else:
        args["public_anchors"][0]["excerpt"] = "Visible café 🙂 token hidden."
    with pytest.raises((ValueError, ValidationError)):
        validate_witness(WitnessCheck.model_validate(args), evidence())


def test_future_record_exists_but_cannot_authorize_earlier_activation() -> None:
    item = evidence()
    public: Any = copy.deepcopy(item.learner_authorized_evidence)
    public["episodes"][0]["records"].append(
        {
            "step": 4,
            "observation_ref": "v_obs",
            "preceding_action_ref": "v_action",
            "visible_actions_ref": "v_actions",
        }
    )
    item = item.model_copy(update={"learner_authorized_evidence": public})
    args = episode_public_check()
    args["public_anchors"][0]["step"] = 4
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(args), item)


def test_source_only_anchor_cannot_establish_episode_public_authorization() -> None:
    args = episode_public_check()
    args["candidate_anchors"] = [source_anchor()]
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(args), evidence())


def test_late_public_evidence_cannot_launder_earlier_activation_of_same_change() -> None:
    item = evidence()
    runtime: Any = copy.deepcopy(item.optional_runtime_surface_deltas)
    runtime["activation_table"]["a0"]["fresh"]["0.25"] = [[1, 3]]
    item = item.model_copy(update={"optional_runtime_surface_deltas": runtime})
    args = episode_public_check()  # Cites step3; identical change already activated at step1.
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(args), item)


def test_one_episode_cannot_authorize_shared_delta_in_another_episode() -> None:
    item = evidence()
    runtime: Any = copy.deepcopy(item.optional_runtime_surface_deltas)
    runtime["activation_table"]["a0"]["other"] = {"0.25": [[3, 3]]}
    public: Any = copy.deepcopy(item.learner_authorized_evidence)
    other = copy.deepcopy(public["episodes"][0])
    other["episode_id"] = "other"
    public["episodes"].append(other)
    item = item.model_copy(
        update={"optional_runtime_surface_deltas": runtime, "learner_authorized_evidence": public}
    )
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(episode_public_check()), item)


@pytest.mark.parametrize(
    "field_name,value",
    [("step", True), ("group_index", True), ("change_index", "0"), ("dose", "0.25")],
)
def test_anchor_indices_and_dose_are_not_coerced(field_name: str, value: Any) -> None:
    args = check_args(anchor={**runtime_anchor(), field_name: value})
    with pytest.raises(ValidationError):
        WitnessCheck.model_validate(args)


def test_public_export_omits_nested_witness_requests_and_private_evidence() -> None:
    public_validation_result = importlib.import_module(
        "scripts.e6_iterative_low_llm_judge"
    ).public_validation_result

    complete = CompletionQueue(Reply("judge", decision()), Reply("check", check_args()))
    record = WitnessCheckingPrivilegeJudge(complete).judge(evidence()).as_record()
    private_payload = canonical_json(record)
    assert REFERENCE_SENTINEL in private_payload and DESIGN_SENTINEL in private_payload
    result = {
        "decision": "JUDGE_GATE_NOT_READY",
        "cases_completed": 1,
        "cases_expected": 21,
        "outcomes": [
            {
                "case_id": "generic_prerequisite",
                "role": "regression",
                "expected_verdict": "PASS",
                "result": record,
                "full_judge_record_sha256": text_sha256(private_payload),
            }
        ],
    }
    public = canonical_json(public_validation_result(result, private_result_sha256="a" * 64))
    for sentinel in (REFERENCE_SENTINEL, DESIGN_SENTINEL, REASON_SENTINEL, ALLEGATION):
        assert sentinel not in public
    assert '"request":' not in public and '"stages":' not in public


@pytest.mark.parametrize("field_name", ["candidate_grounding", "authorization", "claim_relation"])
def test_unresolved_claim_cannot_be_overridden_by_reconsideration_signals(field_name: str) -> None:
    args = check_args(grounding="UNSUPPORTED", information="A narrower operational statement.")
    args[field_name] = "UNRESOLVED"
    complete = CompletionQueue(Reply("judge", decision()), Reply("check", args))
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty
    assert len(complete.requests) == 2


def test_public_label_does_not_resolve_unknown_candidate_grounding() -> None:
    args = check_args(grounding="UNRESOLVED", authorization="PUBLIC")
    complete = CompletionQueue(Reply("judge", decision()), Reply("check", args))
    result = WitnessCheckingPrivilegeJudge(complete).judge(evidence())
    assert result.verdict == "UNCERTAIN" and result.generated_uncertainty
    assert len(complete.requests) == 2


@pytest.mark.parametrize("pointer", ["/label~", "/label~2", "/items/\u0660", "/items/00"])
def test_public_pointer_rejects_non_rfc6901_spellings(pointer: str) -> None:
    item = evidence().model_copy(
        update={
            "public_task_information": {"label~": "known", "label~2": "known", "items": ["known"]}
        }
    )
    args = public_task_check()
    args["public_anchors"][0].update({"pointer": pointer, "excerpt": "known"})
    with pytest.raises(ValueError):
        validate_witness(WitnessCheck.model_validate(args), item)
