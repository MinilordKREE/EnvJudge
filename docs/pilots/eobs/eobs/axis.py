"""Candidate axis classifier (offline, AST-based).

axis(c) ⊆ {S0, A, T, O}: S0 iff in_env_actions non-empty; A/T/O iff the `_Rules` class in rules_code
defines filter_action / modify_transition / filter_observation. `blocked_possible` iff the A hook's
source mentions `Blocked(` (the hook can return a Blocked)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

HOOK_AXIS = {"filter_action": "A", "modify_transition": "T", "filter_observation": "O"}


@dataclass(frozen=True)
class AxisInfo:
    axes: frozenset[str]
    hooks: tuple[str, ...]
    blocked_possible: bool
    parse_error: str | None = None

    @property
    def label(self) -> str:
        order = ["S0", "A", "T", "O"]
        return "+".join(a for a in order if a in self.axes) or "none"


def classify(rules_code: str, in_env_actions: list | None) -> AxisInfo:
    axes: set[str] = set()
    hooks: list[str] = []
    blocked = False
    err = None
    if in_env_actions:
        axes.add("S0")
    code = rules_code or ""
    if code.strip():
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            err = f"SyntaxError: {e.msg} line {e.lineno}"
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "_Rules":
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in HOOK_AXIS:
                            hooks.append(item.name)
                            axes.add(HOOK_AXIS[item.name])
                            if item.name == "filter_action" and "Blocked" in ast.unparse(item):
                                blocked = True
    return AxisInfo(axes=frozenset(axes), hooks=tuple(hooks), blocked_possible=blocked, parse_error=err)
