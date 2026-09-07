"""ChainEnv — a released-Link composition of two AlfworldEnvs, importable by the released runner via EnvSpec.import_path.

The runner calls `base_cls()` with no arguments and then `env.reset(seed, options={**reset_options, "task_id": label})`.
Link routes `options` only when it carries the reserved keys, so ChainEnv's reset_options must be
  {"a": {split, repetition_threshold, "task_id": label}, "b": {same}, "link": {"a_done_via": "terminated", "b_seed": <task_b>}}
and the runner's extra top-level "task_id" key is ignored by Link._split_options (link.py:227-239). Task A comes from the
runner's `reset_seed`; task B from link.b_seed. No file under third_party is modified."""

from __future__ import annotations

from envharness.bridges.alfworld import AlfworldEnv
from envharness.harnesses.link import Link


class ChainEnv(Link):
    def __init__(self) -> None:
        super().__init__(AlfworldEnv(), AlfworldEnv(), carry_context=True, a_done_via="terminated")

    @classmethod
    def tool_schemas(cls):          # the runner reads tool schemas from _base_env(env) = env_a, but keep the class consistent
        return AlfworldEnv.tool_schemas()

    @classmethod
    def env_state_schema(cls) -> str:
        return AlfworldEnv.env_state_schema()


def chain_reset_options(task_b: int, split: str = "train", label: str = "alfworld-corpus-ours-release") -> dict:
    base = {"split": split, "repetition_threshold": 0, "task_id": label}
    return {"a": dict(base), "b": dict(base), "link": {"a_done_via": "terminated", "b_seed": int(task_b), "carry_context": True}}
