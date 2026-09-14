# Used-task audit before pool 3 (phase 3.4; immutable; supersedes nothing, extends USED_TASKS_AUDIT.md)

Task universe: ALFWorld bridge seeds (see `USED_TASKS_AUDIT.md`). The exclusion set was derived
programmatically, not from memory: every `events.jsonl` `task_id` and every `rollout_seed` in the
`confirm.jsonl` / `traces.jsonl` files of every run directory of both worktrees
(`/home/kree/work/EnvJudge/runs/*` and `../EnvJudge-aea-llm/runs/*`) was collected.

| result | value |
| --- | --- |
| ids ever rolled out | 0..79 (80 ids, contiguous, no gaps, no other id) |
| provenance | 0..29: E2 / E3 / E3-SL / E3b / E4 / E5 / smokes 1-2 / phase 3.2 (`USED_TASKS_AUDIT.md`); 30..79: pool 2 K16 (`PREREG_LOW_POOL2.md`), of which 33, 43, 53, 54, 56, 58 were used by the phase-3.3a profile and 62, 66, 67, 70, 71, 73, 78, 79 by phase 3.3b |
| LOW_POOL_2 status | fully consumed (all 14 zero tasks used) |
| next 50 smallest unused ids | **80..129** (derived as the first 50 integers above the maximum used id that are not in the used set) |

No task's semantics were inspected before this selection.
