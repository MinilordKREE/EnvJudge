# Audit: `io` (corpus / trace writers) and `controller` (the AEA loop)

Contracts: corpus entries `band | knob | stage` in the released `{game_file, rules_code, in_env_actions}`
shape plus an `aea` metadata block; corpus reader/writer round-trips through the RL corpus loader and
the orchestrator's `Candidate`; trace writer uses `TraceStore`; controller resumable per (task, phase,
attempt), task-level concurrency, unresolved/frozen to accounting only.

## Reference

| what | where | reuse |
|---|---|---|
| RL corpus loader: JSONL keyed by `game_file` (relative to `$ALFWORLD_DATA`), reads `in_env_actions` and `rules_code` only | `rl/envharness_rl/alfworld/envs.py:119-146, 178-199` | round-trip target (Phase C.5) |
| The orchestrator's corpus unit and `Candidate` fields | `types.py:137-141`; `_candidate_from_args` `harness_agent.py:982-1013` | import |
| `TraceStore` JSONL format | `storage.py:44-72` | import (rollouts are written with `TraceStore.add(Trace)`) |
| Event log style (`kind` + fields per line) | `orchestrator.py:224-254` | pattern; aea events use the M0 envelope |
| Game file per task: `info["extra.gamefile"]` at reset | `bridge.py:238-241` (reset info), pilot `open_session` (`replay.py:157-159`) | import (needed to key corpus entries) |
| Pilot: observe-only extraction of orchestrator artifacts | `docs/pilots/eobs/eobs/hooks.py` | pattern for the accounting table |
| Pilot controller rules (band classes, dose order, certificate-first) | `docs/pilots/e1pilot/e1/controller.py`, `p4/p4/nsat.py` (F_H search loop), `p5/p5/chs100.py` (zero path) | rewrite as one loop |

## Invariants relied on

- ✓ Corpus records with extra keys load (envs.py:131-141 store `rec` whole).
- ✓ `game_file` absolute paths are what the worker keys on (envs.py:140-142); `io` writes the
  path relative to `$ALFWORLD_DATA` as the bundled corpora do.
- A staged entry's `stage_budget` is metadata: the RL worker replays `in_env_actions` in place and does
  not read it (envs.py:184-190); the 100-config must be supplied through `$ALFWORLD_CONFIG` there
  (docs/pilots/e1pilot/p5/docs/rl_audit.md §2.5). The corpus-protocol runner takes it from
  `reset_options.config_path`.

## Decisions

- Corpus entry: `{"game_file", "rules_code", "in_env_actions", "aea": {"kind": "band|knob|stage",
  "task_id", "seed", "knob", "dose", "axis", "stage_budget", "candidate_id", "certificate", "p_hat",
  "n", "round"}}`.
- Resume key = `(task_id, phase, attempt)` recorded in `events.jsonl`; on restart the controller replays
  the events file and skips completed keys; ledger rows for an interrupted attempt stay and are marked
  by `rollout_uid`.
- Budget invariants checked after each task: `search` rows ≤ 30 per (task, round); `confirm` rows for
  an environment appear only after its corpus write (Phase C.6).
