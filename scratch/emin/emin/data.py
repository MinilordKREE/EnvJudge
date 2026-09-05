"""Task loading and prompt rendering (byte-identical to the substrate harness).

Reads only the local verified_400 copy used by the pilot. Held-out ids (val 39 / test 281)
are never rendered for rollouts; `pool_tasks()` refuses ids outside the frozen pool.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from emin.settings import config, ensure_pilot_importable

ensure_pilot_importable()

from rethinkskill_spreadsheetbench.harness import _spreadsheet_cases  # noqa: E402
from rethinkskill_spreadsheetbench.runtime import preview_workbook  # noqa: E402


@dataclass(frozen=True)
class Task:
    task_id: str
    instruction: str
    instruction_type: str
    answer_position: str          # "Sheet!A1:B2" form, as the harness normalises it
    input_path: Path
    golden_path: Path

    @property
    def preview(self) -> str:
        return preview_workbook(self.input_path)

    def task_markdown(self) -> str:
        return (
            "# SpreadsheetBench Task\n\n"
            f"Task ID: `{self.task_id}`\n\n"
            f"Instruction type: {self.instruction_type}\n\n"
            f"Answer position: `{self.answer_position}`\n\n"
            "## Instruction\n\n"
            f"{self.instruction}\n\n"
            "## First input workbook preview\n\n"
            f"```text\n{self.preview}\n```\n\n"
            "## Output contract\n\n"
            "Return exactly one complete Python program in a `python` code "
            "fence. The program receives `INPUT_PATH` and `OUTPUT_PATH`, "
            "loads the input workbook, applies the instruction, and saves the "
            "result to `OUTPUT_PATH`. Do not hardcode previewed values or row "
            "counts. Preserve unrelated workbook content. Do not access the "
            "network, subprocesses, or files other than the supplied workbook."
        )


INVOCATION = (
    "Read `.agents/skills/rethinkskill-target/SKILL.md` and "
    "`task.md`. Inspect the task-local input workbook only if "
    "useful. Return exactly one self-contained Python code fence "
    "that transforms `INPUT_PATH` into `OUTPUT_PATH`; do not run it."
)


def skill_markdown(skill_text: str) -> str:
    return (
        "---\n"
        'name: "rethinkskill-target"\n'
        'description: "Dynamic skill for native SpreadsheetBench '
        'code generation."\n'
        "---\n\n"
        f"{skill_text.strip()}\n"
    )


def render_prompt(task: Task, skill_text: str) -> str:
    """== rethinkskill.providers.common.embedded_prompt(harness.render(task, skill))."""
    return (
        f"# Skill\n\n{skill_markdown(skill_text)}\n\n"
        f"# Task\n\n{task.task_markdown()}\n\n"
        f"# Invocation\n\n{INVOCATION}\n"
    )


def _records() -> dict[str, dict]:
    cfg = config()
    with open(cfg["dataset_json"], encoding="utf-8") as fh:
        rows = json.load(fh)
    return {str(r["id"]): r for r in rows}


def read_ids(path: str | Path) -> list[str]:
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def pool_ids() -> list[str]:
    return read_ids(config()["pool_ids"])


def load_task(record: dict) -> Task:
    cfg = config()
    root = Path(cfg["asset_root"])
    task_id = str(record["id"])
    answer_position = str(record.get("answer_position", "")).strip()
    answer_sheet = str(record.get("answer_sheet", "")).strip()
    if answer_position and answer_sheet and "!" not in answer_position:
        answer_position = f"{answer_sheet}!{answer_position}"
    directory = (root / str(record.get("spreadsheet_path", f"spreadsheet/{task_id}"))).resolve()
    cases = _spreadsheet_cases(directory)
    if len(cases) != 1:
        raise ValueError(f"expected exactly one (input, golden) case for {task_id}, found {len(cases)}")
    _, input_path, golden_path = cases[0]
    return Task(
        task_id=task_id,
        instruction=str(record["instruction"]),
        instruction_type=str(record.get("instruction_type", "")),
        answer_position=answer_position,
        input_path=input_path,
        golden_path=golden_path,
    )


def pool_tasks(ids: list[str] | None = None) -> list[Task]:
    """Tasks of the frozen pool 76 (the only ids that may receive LLM rollouts)."""
    pool = pool_ids()
    wanted = pool if ids is None else list(ids)
    outside = sorted(set(wanted) - set(pool))
    if outside:
        raise PermissionError(f"ids outside the frozen pool 76 may not receive rollouts: {outside}")
    recs = _records()
    return [load_task(recs[i]) for i in wanted]


def all_records() -> list[dict]:
    """All verified_400 records (witness probe only; no LLM)."""
    return list(_records().values())


def split_of(task_id: str) -> str:
    cfg = config()
    for name, key in (("pool", "pool_ids"), ("val", "val_ids"), ("test", "test_ids")):
        if task_id in set(read_ids(cfg[key])):
            return name
    return "excluded"


def skill_text(agent: str) -> str:
    cfg = config()
    path = cfg["parent_skill"] if agent == "parent" else cfg["parent_minus_skill"]
    return Path(path).read_text(encoding="utf-8")
