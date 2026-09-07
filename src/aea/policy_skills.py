"""Skill injection for corpus-generation rounds >= 2 (spec section 8).

The round-r policy is the backbone plus bank_{r-1}, injected exactly as the released evaluation
does:
one retrieval per episode on the task line (query embedding -> MMR top-5, ``bank.py:104-152``) and
the released memory block (``envharness/prompts/alfworld_skill_prompt.py:100-134``,
``build_memory_block``). The released ``PolicyAgent`` has no injection hook
(docs/reuse/policy_skills.md),
so the block is prepended to ``PolicySpec.task_prompt`` per task; the spec travels to subprocess
workers unchanged (``runner.py:333-347``). Identical for every arm.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from envharness.prompts.alfworld_skill_prompt import build_memory_block, extract_task
from envharness.reasoning_bank import Bank

type Retriever = Callable[[str], Sequence[Any]]
"""Given the task line, return the retrieved memory items (title/description/content)."""


def make_retriever(
    bank_path: Path, *, top_k: int = 5, mode: str = "mmr", mmr_lambda: float = 0.5
) -> Retriever:
    """The released retrieval over ``bank_path`` with the eval's settings."""
    bank = Bank.load(bank_path)

    def retrieve(task_line: str) -> Sequence[Any]:
        if top_k <= 0 or len(bank) == 0:
            return []
        return list(bank.retrieve(task_line, k=top_k, mode=mode, mmr_lambda=mmr_lambda))

    return retrieve


def task_line_from_observation(obs_text: str) -> str:
    """The released query: the task sentence of the initial observation."""
    return str(extract_task(obs_text))


def skills_block(retriever: Retriever, task_line: str, *, style: str = "soft") -> str:
    """The memory block the released eval would inject for this task ('' when nothing retrieved)."""
    items = retriever(task_line)
    return str(build_memory_block(list(items), style=style))


def inject(task_prompt: str, block: str) -> str:
    """``PolicySpec.task_prompt`` for the round: the base prompt followed by the skills block."""
    if not block:
        return task_prompt
    return f"{task_prompt.rstrip()}\n\n## Past Relevant Skills\n{block.rstrip()}\n"
