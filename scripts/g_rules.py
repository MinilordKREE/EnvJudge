"""Export the accepted rules of the released-designer arms G and G+ (Round 1b, section 0.2).

For each accepted candidate: rules code, hooks overridden (filter_action = A axis,
modify_transition = T, filter_observation = O; envharness/harnesses/rules.py:34-36 and 93-102),
whether it raises ``Blocked(``, emits "Nothing happens", edits the admissible list, numeric
constants, the designer's one-line intent (rationale), setup actions, and the shared baseline p16
against the accepted-environment p16 (runs/r1-shared and runs/r1-<arm>/confirm_summary.json).
No LLM call. Writes experiments/alfworld_sl/results/r1/g_rules.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
OUT = ROOT / "experiments" / "alfworld_sl" / "results" / "r1" / "g_rules.md"
HOOKS = {"filter_action": "A", "modify_transition": "T", "filter_observation": "O"}


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def analyse(code: str) -> dict[str, Any]:
    hooks = [h for h in HOOKS if re.search(rf"def {h}\(", code)]
    numbers = sorted(
        {m for m in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", code) if m not in {"0", "1"}},
        key=float,
    )
    return {
        "hooks": hooks,
        "axes": "".join(HOOKS[h] for h in hooks) or "-",
        "blocked": "Blocked(" in code,
        "nothing_happens": "Nothing happens" in code,
        "admissible_edit": bool(re.search(r"[Aa]dmissible", code)),
        "numbers": numbers,
        "lines": len(code.splitlines()),
    }


def intent(rationale: str) -> str:
    line = re.split(r"(?<=[.!?])\s", rationale.strip().replace("\n", " "), maxsplit=1)[0]
    return line[:220]


def accepted(arm: str) -> list[dict[str, Any]]:
    traces = jsonl(RUNS / f"r1-{arm}" / "traces.jsonl")
    seen: dict[tuple[int, str], dict[str, Any]] = {}
    for t in traces:
        if t.get("kind") != "accepted":
            continue
        key = (int(t["rollout_seed"]), str(t["candidate_id"]))
        if key not in seen:
            seen[key] = {
                "task": key[0],
                "candidate_id": key[1],
                "candidate": t["candidate"],
                "n": 0,
                "won": 0,
            }
        seen[key]["n"] += 1
        seen[key]["won"] += int(bool(t.get("success")))
    return [seen[k] for k in sorted(seen)]


def p16(arm: str, task: int) -> tuple[float | None, float | None]:
    shared = json.loads((RUNS / "r1-shared" / "confirm_summary.json").read_text(encoding="utf-8"))
    conf = json.loads((RUNS / f"r1-{arm}" / "confirm_summary.json").read_text(encoding="utf-8"))
    base = shared.get(f"{task}:orig", {}).get("p16")
    env = next((e["p16"] for e in conf.values() if str(e["task"]) == str(task)), None)
    return base, env


def main() -> int:
    lines = [
        "# Accepted rules of the released-designer arms G and G+ (Round 1)",
        "",
        "Hooks: filter_action = A axis, modify_transition = T, filter_observation = O "
        "(envharness/harnesses/rules.py). p16 = successes/16 at the K=16 confirmation "
        "(baseline = shared original environment; env = the accepted environment). "
        "Intent = first sentence of the designer's rationale. No LLM call.",
        "",
        "## Taxonomy",
        "",
        "| arm | task | axes | Blocked( | Nothing happens | admissible edit | numeric constants | setup actions | baseline p16 | env p16 | learnable | intent |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    code_blocks: list[str] = []
    axis_counts: dict[str, dict[str, int]] = {}
    for arm in ("G", "Gplus"):
        for c in accepted(arm):
            cand = c["candidate"]
            code = cand.get("rules_code") or ""
            a = analyse(code)
            base, env = p16(arm, c["task"])
            learnable = env is not None and 4 / 16 <= env <= 12 / 16
            key = a["axes"]
            axis_counts.setdefault(arm, {}).setdefault(key, 0)
            axis_counts[arm][key] += 1
            setup = [x.get("kwargs", {}).get("text", "") for x in cand.get("in_env_actions") or []]
            lines.append(
                f"| {arm} | {c['task']} | {a['axes']} | {'y' if a['blocked'] else '-'} | "
                f"{'y' if a['nothing_happens'] else '-'} | {'y' if a['admissible_edit'] else '-'} | "  # noqa: E501
                f"{', '.join(a['numbers']) or '-'} | {len(setup)} | "
                f"{'-' if base is None else f'{base:.2f}'} | {'-' if env is None else f'{env:.2f}'} | "  # noqa: E501
                f"{'y' if learnable else '-'} | {intent(cand.get('rationale') or '').replace('|', '/')} |"  # noqa: E501
            )
            code_blocks += [
                "",
                f"### {arm} task {c['task']} (candidate {c['candidate_id']}; accepted at {c['won']}/{c['n']} in search)",  # noqa: E501
                "",
                f"Setup actions: {setup or 'none'}",
                "",
                "```python",
                code.rstrip() or "# (no rules code)",
                "```",
            ]
    lines += [
        "",
        "## Axis x leverage",
        "",
        "| arm | axes | accepted envs | learnable (B_L) |",
        "|---|---|---|---|",
    ]
    for arm in ("G", "Gplus"):
        for axes, n in sorted(axis_counts.get(arm, {}).items()):
            n_learn = 0
            for c in accepted(arm):
                if analyse(c["candidate"].get("rules_code") or "")["axes"] == axes:
                    _, env = p16(arm, c["task"])
                    n_learn += int(env is not None and 4 / 16 <= env <= 12 / 16)
            lines.append(f"| {arm} | {axes} | {n} | {n_learn} |")
    lines += ["", "## Code of every accepted candidate", *code_blocks, ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[: lines.index("## Code of every accepted candidate")]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
