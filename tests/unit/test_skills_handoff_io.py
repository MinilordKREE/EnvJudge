from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from envharness.core.types import Action, Candidate
from envharness.reasoning_bank import bank as bank_module
from envharness.reasoning_bank.bank import Bank, MemoryItem

from aea.config import AEAConfig
from aea.handoff import HANDOFF_POLICY_ID, handoff, render_witness_trace
from aea.io import (
    AeaMeta,
    CorpusEntry,
    TraceWriter,
    entry_from_candidate,
    read_corpus,
    relative_game_file,
    write_accounting,
    write_corpus_entry,
)
from aea.policy_skills import inject, make_retriever, skills_block, task_line_from_observation
from tests.fixtures.fake_world import make_open

PLAN = ["go to a", "take x from a", "go to b", "move x to b"]
ENVHARNESS = Path(__file__).resolve().parents[2] / "third_party" / "envharness"


def test_skills_block_and_inject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        MemoryItem(
            title="Open first",
            description="closed containers",
            content="open before search",
            embedding=[1.0, 0.0],
            source={},
        ),
        MemoryItem(
            title="Lamp",
            description="look_at tasks",
            content="use the lamp",
            embedding=[0.0, 1.0],
            source={},
        ),
    ]
    Bank(items).save(tmp_path / "bank.jsonl")
    monkeypatch.setattr(
        bank_module, "embed_texts", lambda texts, model=None: [[1.0, 0.0] for _ in texts]
    )
    retriever = make_retriever(tmp_path / "bank.jsonl", top_k=1)
    block = skills_block(retriever, "put x in b")
    assert "Insight 1: Open first" in block and "Lamp" not in block
    prompt = inject("You are an agent.", block)
    assert (
        prompt.startswith("You are an agent.")
        and "## Past Relevant Skills" in prompt
        and prompt.rstrip().endswith("open before search")
    )
    assert inject("base", "") == "base"
    assert (
        task_line_from_observation(
            "-= Welcome =-\n\nYour task is to: put x in b.\n\nAdmissible commands: look"
        )
        == "put x in b."
    )
    assert skills_block(make_retriever(tmp_path / "bank.jsonl", top_k=0), "x") == ""


def test_handoff_renders_released_trace_format() -> None:
    cfg = AEAConfig()
    trace = handoff(make_open(PLAN), cfg, task_label="lbl", task_seed=7)
    assert trace is not None and trace.success and trace.policy_model_id == HANDOFF_POLICY_ID
    assert [s.filtered_action.kwargs["text"] for s in trace.steps if s.filtered_action] == PLAN
    assert trace.steps[0].policy_raw_response == "<action>go to a</action>" and "<think>" not in (
        trace.steps[0].policy_raw_response or ""
    )
    assert (
        trace.rollout_seed == 7 and trace.candidate_id == "handoff" and trace.kind == "exploration"
    )
    spec = importlib.util.spec_from_file_location(
        "induce_mod", ENVHARNESS / "envharness" / "reasoning_bank" / "induce.py"
    )
    assert spec and spec.loader
    induce = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(induce)
    text = induce.format_trajectory([s.model_dump() for s in trace.steps])
    assert "<action>go to a</action>" in text and "Observation:" in text
    assert (
        handoff(make_open(PLAN, cap=2), cfg, task_label="lbl", task_seed=7) is None
    )  # engine ends at 2
    with pytest.raises(ValueError):
        render_witness_trace("l", 1, ["a"], [])


def test_corpus_roundtrip_and_loader_contract(tmp_path: Path) -> None:
    meta = AeaMeta(
        kind="stage",
        task_id="7",
        seed=7,
        t=12,
        prefix_sha="abc",
        stage_budget=100,
        candidate_id="7:abc",
        certificate="R_exp",
        profile=[{"t": 12, "p4": 0.5}],
    )
    cand = Candidate(
        in_env_actions=[
            Action(name="do", kwargs={"text": "go to a"}),
            Action(name="do", kwargs={"text": "look"}),
        ]
    )
    entry = entry_from_candidate("json_2.1.1/train/x/game.tw-pddl", cand, meta)
    path = tmp_path / "corpus.jsonl"
    write_corpus_entry(path, entry)
    write_corpus_entry(
        path,
        entry_from_candidate(
            "g2",
            Candidate(rules_code="class _Rules(Rules):\n    pass\n"),
            AeaMeta(
                kind="knob",
                task_id="8",
                seed=8,
                family="footer_mask",
                source="exemplar",
                d=0.5,
                p8=0.5,
            ),
        ),
    )
    back = read_corpus(path)
    assert back[0] == entry and back[0].stage_budget == 100
    assert back[0].to_candidate().in_env_actions == cand.in_env_actions
    assert back[1].to_candidate().rules_code.startswith("class _Rules")
    # RL loader contract (envs.py:119-146, 186, 193): keyed by game_file; reads two keys
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    corpus = {rec["game_file"]: rec for rec in raw if rec.get("game_file")}
    rec = corpus["json_2.1.1/train/x/game.tw-pddl"]
    assert [Action(**a) for a in rec.get("in_env_actions") or []] == cand.in_env_actions and (
        rec.get("rules_code") or ""
    ) == ""
    assert "aea" in rec  # extra keys travel and are ignored by the loader
    assert (
        relative_game_file("/data/json_2.1.1/train/x/game.tw-pddl", Path("/data"))
        == "json_2.1.1/train/x/game.tw-pddl"
    )
    assert (
        relative_game_file("json_2.1.1/train/x/game.tw-pddl", Path("/data"))
        == "json_2.1.1/train/x/game.tw-pddl"
    )


def test_trace_writer_and_accounting(tmp_path: Path) -> None:
    from envharness.core.types import Trace
    from envharness.orchestration.storage import TraceStore

    writer = TraceWriter(tmp_path / "traces.jsonl")
    writer.add(
        Trace(episode_id="e1", iteration_id="i", task_id="t", candidate=Candidate(), success=True)
    )
    assert len(writer) == 1 and TraceStore(tmp_path / "traces.jsonl").all()[0].episode_id == "e1"
    write_accounting(tmp_path / "accounting.csv", [{"task_id": "7", "rollouts": 4}])
    assert (tmp_path / "accounting.csv").read_text(encoding="utf-8").splitlines() == [
        "task_id,rollouts",
        "7,4",
    ]
    write_accounting(tmp_path / "empty.csv", [])
    assert (tmp_path / "empty.csv").read_text(encoding="utf-8") == ""
    assert CorpusEntry.model_validate(
        {"game_file": "g", "aea": {"kind": "band", "task_id": "1", "seed": 1}}
    ).to_candidate() == Candidate(rationale="aea:band")


def test_corpus_entry_rejects_unknown_kind() -> None:
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError family
        AeaMeta.model_validate({"kind": "chain", "task_id": "1", "seed": 1})
