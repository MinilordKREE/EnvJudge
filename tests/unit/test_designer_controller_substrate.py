"""Offline mocked transports verify v3 accounting without any API or environment calls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from envharness.core.types import Action, Candidate, Trace
from pydantic import SecretStr

from aea.config import AEAConfig
from aea.controller import TaskRef
from aea.core.config import LLMConfig
from aea.core.io import read_jsonl
from aea.designer_controller_confirmation import candidate_hash
from aea.designer_controller_substrate import DesignerControllerSubstrate, physical_closed
from aea.errors import ConfigError, InfraError
from aea.llm.physical_audit import AuditedTransport
from aea.llm.types import Attribution, ChatMessage, ChatRequest
from aea.privilege_judge import JudgeConfig
from aea.privilege_witness import WitnessCheckingPrivilegeJudge
from tests.conftest import REPO_ROOT, FakeTransport, make_completion


def build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, designer: bool = True
) -> tuple[DesignerControllerSubstrate, FakeTransport, FakeTransport]:
    design_transport = FakeTransport(
        [
            make_completion(model="deepseek-v4-pro", provider=None),
            make_completion(model="deepseek-v4-pro", provider=None),
        ]
    )
    judge_transport = FakeTransport([make_completion(model="deepseek-v4-flash", provider=None)])
    settings = SimpleNamespace(require=lambda _: SecretStr("synthetic-test-key"))
    monkeypatch.setattr("aea.substrate.load_settings", lambda: settings)
    monkeypatch.setattr("aea.substrate.make_openai_transport", lambda **_: design_transport)
    monkeypatch.setattr("aea.designer_controller_substrate.load_settings", lambda: settings)
    monkeypatch.setattr(
        "aea.designer_controller_substrate.make_openai_transport", lambda **_: judge_transport
    )
    designer_config = LLMConfig(
        provider="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        provider_pin=None,
    )
    sub = DesignerControllerSubstrate(
        corpus_yaml=REPO_ROOT / "configs/corpus_aea.yaml",
        run_dir=tmp_path / "private",
        run_id="synthetic-run",
        policy_llm=LLMConfig(),
        designer_llm=designer_config if designer else None,
        aea_config=AEAConfig(method_version="llm_v3_designer_controller"),
        stage_config_path=tmp_path / "unused-stage.yaml",
        pricing_path=REPO_ROOT / "configs/pricing.yaml",
        judge_pricing_path=REPO_ROOT / "configs/privilege_judge_pricing.yaml",
    )
    return sub, design_transport, judge_transport


def request(model: str, phase: str = "v3_design") -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=(ChatMessage(role="user", content="synthetic only"),),
        attribution=Attribution(phase=phase, budget="designer", arm="AEA", task_id="9"),
        seed=9,
    )


def test_constructor_installs_accounting_without_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub, designer, judge = build(tmp_path, monkeypatch)
    assert designer.calls == judge.calls == []
    assert sub.policy_spec_kwargs["client_factory"] == "aea.llm.physical_audit:AuditedPolicyClient"
    kwargs = sub.policy_spec_kwargs["client_kwargs"]
    assert kwargs["audit_dir"] == str(sub.run_dir / "physical")
    assert kwargs["run_id"] == "synthetic-run"
    assert kwargs["ledger_dir"] == str(sub.run_dir)
    assert sub._designer is not None and isinstance(sub._designer._transport, AuditedTransport)
    assert sub._judge_client is None
    assert sub.physical_accounting()["attempts"] == 0


def test_designer_is_wrapped_once_and_retains_logical_raw_and_physical_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub, transport, _ = build(tmp_path, monkeypatch)
    for _ in range(2):
        complete = sub.designer()
        assert complete is not None
        complete(request("deepseek-v4-pro"))
    assert len(transport.calls) == 2
    assert sub.physical_accounting()["attempts"] == 2
    assert sub.physical_accounting()["returned"] == 2
    assert sub._designer is not None
    assert isinstance(sub._designer._transport, AuditedTransport)
    assert sub._designer._transport.transport is transport
    logical = [row for path in sub.run_dir.glob("ledger.*.jsonl") for row in read_jsonl(path)]
    assert len(logical) == 2 and all(row["event"] == "call" for row in logical)
    assert all(row["phase"] == "v3_design" and row["budget"] == "designer" for row in logical)
    raw = sub.run_dir / "raw/designer/requests.jsonl"
    assert len(read_jsonl(raw)) == 2
    assert raw.stat().st_mode & 0o777 == 0o600
    attempts = [
        row for p in (sub.run_dir / "physical").glob("attempts.*.jsonl") for row in read_jsonl(p)
    ]
    assert len(attempts) == 4
    assert all(row["attribution"]["task_id"] == "9" for row in attempts)
    assert all(row["seed"] == 9 for row in attempts)
    assert "synthetic-test-key" not in "".join(p.read_text() for p in sub.run_dir.rglob("*.json*"))


def test_judge_keeps_r5_config_and_separate_cached_audited_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub, design_transport, judge_transport = build(tmp_path, monkeypatch)
    attr = request("deepseek-v4-flash", "v3_privilege").attribution
    first, second = sub.privilege_judge(attr), sub.privilege_judge(attr)
    assert isinstance(first, WitnessCheckingPrivilegeJudge)
    assert first.config == second.config == JudgeConfig()
    assert sub._judge_client is not None and sub._designer is not None
    assert sub._judge_client is not sub._designer
    wrapped = sub._judge_client._transport
    assert isinstance(wrapped, AuditedTransport) and wrapped.transport is judge_transport
    # Exercise only the transport/accounting closure, without changing or invoking judge logic.
    first.complete(request("deepseek-v4-flash", "v3_privilege"))
    assert len(judge_transport.calls) == 1 and design_transport.calls == []
    assert sub.physical_accounting()["attempts"] == 1
    assert len(read_jsonl(sub.run_dir / "raw/judge/requests.jsonl")) == 1
    assert not (sub.run_dir / "raw/designer/requests.jsonl").exists()


def test_no_designer_is_lazy_and_constructor_rejects_historical_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub, transport, _ = build(tmp_path, monkeypatch, designer=False)
    assert sub.designer() is None and transport.calls == []
    with pytest.raises(ConfigError, match="v3 selector"):
        DesignerControllerSubstrate(
            corpus_yaml=tmp_path / "does-not-exist",
            run_dir=tmp_path,
            run_id="r",
            policy_llm=LLMConfig(),
            designer_llm=None,
            aea_config=AEAConfig(),
            stage_config_path=tmp_path / "none",
        )


@pytest.mark.parametrize(
    ("phase", "budget"),
    [("estimate", "search"), ("v3_control", "search"), ("confirmation", "eval")],
)
def test_rollouts_retain_effective_phase_logical_ledger_and_exact_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str, budget: Any
) -> None:
    sub, _, _ = build(tmp_path, monkeypatch, designer=False)
    candidate = Candidate(rules_code="class _Rules(Rules):\n    pass\n")
    attr = Attribution(phase=phase, budget=budget, arm="AEA", task_id="9")
    seen_specs: list[Any] = []

    def dispatch(_run: Any, specs: Any, **kwargs: Any) -> list[Trace]:
        assert kwargs["attribution"] == attr and kwargs["seed"] == 9
        seen_specs.extend(specs)
        return [
            Trace(
                episode_id=f"synthetic-{i}",
                iteration_id="i",
                task_id="9",
                candidate=candidate,
                rollout_seed=9,
                success=bool(i),
            )
            for i in range(len(specs))
        ]

    monkeypatch.setattr("aea.substrate.dispatch", dispatch)
    traces = sub.rollouts(TaskRef("9", 9), candidate, 2, attribution=attr)
    assert len(traces) == len(seen_specs) == 2
    batches = read_jsonl(sub.run_dir / "physical_batches.jsonl")
    assert [row["status"] for row in batches] == ["started", "returned"]
    assert all(row["phase"] == phase and row["budget"] == budget for row in batches)
    physical = read_jsonl(sub.run_dir / "all_physical_traces.jsonl")
    assert len(physical) == 2 and all(row["phase"] == phase for row in physical)
    logical = [row for path in sub.run_dir.glob("ledger.*.jsonl") for row in read_jsonl(path)]
    assert len(logical) == 2 and all(row["event"] == "rollout" for row in logical)
    assert all(row["phase"] == phase and row["budget"] == budget for row in logical)
    assert sub.physical_accounting()["attempts"] == 0  # fake dispatch, no hidden API
    with pytest.raises(ConfigError, match="reused"):
        sub.rollouts(TaskRef("9", 9), candidate, 2, attribution=attr)
    assert read_jsonl(sub.run_dir / "physical_batches.jsonl")[-1]["status"] == "failed"


@pytest.mark.parametrize("defect", ["incomplete", "wrong_seed", "wrong_candidate", "routing"])
def test_bad_returned_batches_are_recorded_before_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    sub, _, _ = build(tmp_path, monkeypatch, designer=False)
    candidate = Candidate()
    traces = [
        Trace(
            episode_id="fresh", iteration_id="i", task_id="9", candidate=candidate, rollout_seed=9
        )
    ]
    if defect == "incomplete":
        traces = []
    elif defect == "wrong_seed":
        traces[0].rollout_seed = 8
    elif defect == "wrong_candidate":
        traces[0].candidate = Candidate(rules_code="different")
    else:
        traces[0].error = "provider_mismatch"
    monkeypatch.setattr("aea.substrate.dispatch", lambda *args, **kwargs: traces)
    with pytest.raises((ConfigError, InfraError)):
        sub.rollouts(
            TaskRef("9", 9),
            candidate,
            1,
            attribution=Attribution(phase="v3_control", budget="search", arm="AEA", task_id="9"),
        )
    assert read_jsonl(sub.run_dir / "physical_batches.jsonl")[-1]["status"] == "failed"
    if traces:
        assert len(read_jsonl(sub.run_dir / "all_physical_traces.jsonl")) == 1


@pytest.mark.parametrize("field", ["inflight", "invalid_usage", "incomplete_journal_lines"])
def test_unresolved_physical_accounting_cannot_close(field: str) -> None:
    summary = {key: 0 for key in ("inflight", "invalid_usage", "incomplete_journal_lines")}
    summary[field] = 1
    with pytest.raises(ConfigError):
        physical_closed(summary)
    # Recorded ambiguous failures carry retained estimates and may close.
    physical_closed(
        {"inflight": 0, "invalid_usage": 0, "incomplete_journal_lines": 0, "ambiguous_failures": 1}
    )


@pytest.mark.parametrize("mutation", ["source", "nested_action"])
def test_candidate_mutation_cannot_rebind_returned_trace_or_batch_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    sub, _, _ = build(tmp_path, monkeypatch, designer=False)
    candidate = Candidate(
        rules_code="class _Rules(Rules):\n    pass\n",
        in_env_actions=[Action(name="do", kwargs={"text": "look"})],
    )
    original_hash = candidate_hash(candidate)

    def dispatch(*args: Any, **kwargs: Any) -> list[Trace]:
        if mutation == "source":
            candidate.rules_code += "# changed after dispatch\n"
        else:
            candidate.in_env_actions[0].kwargs["text"] = "wait"
        # An aliased or forged response now matches the MUTATED caller object.
        return [
            Trace(
                episode_id="mutation-attempt",
                iteration_id="i",
                task_id="9",
                candidate=candidate,
                rollout_seed=9,
            )
        ]

    monkeypatch.setattr("aea.substrate.dispatch", dispatch)
    with pytest.raises(ConfigError, match="candidate mutated"):
        sub.rollouts(
            TaskRef("9", 9),
            candidate,
            1,
            attribution=Attribution(phase="v3_control", budget="search", arm="AEA", task_id="9"),
        )
    rows = read_jsonl(sub.run_dir / "physical_batches.jsonl")
    assert [row["status"] for row in rows] == ["started", "failed"]
    assert all(row["candidate_sha256"] == original_hash for row in rows)
    physical = read_jsonl(sub.run_dir / "all_physical_traces.jsonl")
    assert physical[0]["candidate_sha256"] == original_hash
    assert (
        candidate_hash(Candidate.model_validate(physical[0]["trace"]["candidate"])) != original_hash
    )
