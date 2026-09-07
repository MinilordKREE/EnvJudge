# Audit: `stage` (prefix staging with the re-based budget) and `probe` (learnability probes)

Contract — stage: compile prefix (drop ineffective, append `look`) → Setup with `stage_budget=100`
via `reset_options.config_path` → replay → certify that environment (expert ×3) → candidate id =
`task_id + sha256(compiled prefix)`; fidelity check per task. probe: latest-first, 4 rollouts each;
1–3/4 accept and stop; 4/4 → `too_easy_stage`; all non-learnable → `unresolved`.

## Reference

| what | where | reuse |
|---|---|---|
| Setup replays inside `reset` before the first observation, then `notify_replay_complete` | `setup.py:77-92` | import (the staged env IS a `Setup`) |
| `notify_replay_complete` rewinds bridge counters only; the engine's `Limit` keeps counting the prefix | `bridge.py:412-429`; TextWorld `Limit` (`textworld/envs/wrappers/limit.py`, per-game, counter reset only in `reset()`); registration `alfred_tw_env.py:259-275` | invariant → the 100-step config copy |
| `reset_options.config_path` reaches the bridge (`opts.get("config_path")`), read once per bridge instance and split | `bridge.py:149, 177-178, 492-547` | import; `io`/`stage` pass it in `EnvSpec.reset_options` (`runner.py:196-199` forwards it) |
| `effective` per step (`"nothing happens"` heuristic) | `bridge.py:284, 305, 324, 329` | import: the compile step keeps actions whose replayed step reports `effective`, exactly as the pilot's `staged_actions` |
| Pilot staging: no-ops dropped by replay, trailing `look`, budget-keyed bridge cache | `docs/pilots/e1pilot/p5/p5/chs100.py` (`staged_actions`, `RO100`), `docs/pilots/eobs/eobs/replay.py:133-160` (`_base_bridge` keyed by `config_path`, `open_session`) | port |
| Pilot candidate rule: L, 3L/4, L/2, L/4 per trajectory; union, latest-first, cap 6 by dropping the nearest-in-t | `docs/pilots/e1pilot/p5/p5/chs100.py` (`select_candidates`) | port with tests (`docs/pilots/e1pilot/p5/tests/test_p5_offline.py` cases) |
| Pilot certificates on prefixes: `c_at(seed, prefix, max_steps, reset_options)` (closed-loop expert after replay) | `docs/pilots/eobs/eobs/recover.py:13-27` | port into `certs` (R_exp on a staged env) |
| Pilot probe walk (replaced by "all candidates" in P5.1; the contract keeps latest-first with early stop) | `docs/pilots/e1pilot/p4/p4/chs.py` (`probe`), `p5/p5/chs100.py` (`probe`) | rewrite per contract |
| Fixtures: 12-vs-62 policy steps after the task-8 38-action prefix (default vs 100-config); P5.1 profiles | `docs/pilots/e1pilot/LOG.md` (23:33 UTC entry and P5 entries), `docs/pilots/e1pilot/p5/results/chs_profile.csv`, `chs_selected.csv`, `p4/results/nzero_probe.jsonl` (the staged action lists) | integration fixture (Phase C.1) and unit fixture (candidate rule, selection) |
| Config copy: only the two `max_nb_steps_per_episode` entries differ | `docs/pilots/e1pilot/p5/configs/alfworld_config_100.yaml`, test `test_config_copy_only_changes_step_cap` | copy to `configs/alfworld_config_100.yaml` with a provenance header |

## Invariants relied on

- ✓ Setup replays before the first observation (setup.py:79-92).
- ✓ `Observation.data["admissible_commands"]` is present after replay (bridge `_observe`, 737-745).
- ✓ A staged prefix of length L leaves `100 − L` engine steps; the runner's `max_steps=50` binds for
  L ≤ 50 (verified 12 vs 62 in the pilot; re-verified in Phase C.1).
- The staged candidate is `Candidate(rules_code="", in_env_actions=[Action("do", {"text": a}) …])`;
  the RL corpus entry carries `in_env_actions` plus the `aea` block with `stage_budget: 100`.

## Decisions

- Fidelity check per task: after `Setup.reset`, the observation text equals the observation recorded at
  the cut in the source trajectory (the pilot's check on three trajectories, docs/pilots/e1pilot/LOG.md).
- Candidate id = `f"{task_id}:{sha256(canonical_json(compiled_prefix))[:16]}"`.
- Candidate states are the fractions {1, 3/4, 1/2, 1/4} of each failed trajectory's length (spec §5);
  the pilot's L-based rule stays available as `select_candidates` for fixtures.
