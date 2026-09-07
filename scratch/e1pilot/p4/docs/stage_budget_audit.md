# Stage-budget audit: re-basing the underlying step limit from a staged ALFWorld state (Phase-A note)

Owner question (P4.3 gate, decision 5): can a staged ALFWorld env be instantiated with the underlying
`max_episode_steps` re-based to 50 from the staged state without editing `third_party/` (bridge option, vendored
config copy, or env kwargs)? Observe-only; no code under `src/`; no LLM rollouts (one LLM-free replay check).
All paths below are relative to `third_party/envharness` @ fab7d574 unless stated; site-packages versions:
textworld 1.7.0, alfworld as installed in `~/eobs_venv`.

## 1. Where the 50-step cap lives and why the Setup prefix is charged against it

1. The bridge reads the ALFWorld config once per bridge instance and split: `envharness/bridges/alfworld/bridge.py:149`
   takes `config_path` from `reset_options` (else `$ALFWORLD_CONFIG`), and `bridge.py:177-178` builds the underlying
   env only when `self._env is None or split != self._current_split`. `_lazy_init_env` (`bridge.py:492-547`) resolves
   the path (explicit arg > env var > vendored `envharness/third_party/alfworld/base_config.yaml` > alfworld's bundled
   copy), loads the YAML (`bridge.py:539-540`) and calls `AlfredTWEnv(config, train_eval=split).init_env(batch_size=1)`
   (`bridge.py:545-547`).
2. ALFWorld turns `rl.training.max_nb_steps_per_episode` (vendored `base_config.yaml:88`, value 50) into a TextWorld
   registration argument: `alfworld/agents/environment/alfred_tw_env.py:259` (dqn branch) and `:271-275`
   (`textworld.gym.register_games(..., max_episode_steps=max_nb_steps_per_episode, asynchronous=True, ...)`).
3. TextWorld enforces it with a per-game `Limit` wrapper created inside `_make_env`
   (`textworld/gym/envs/textworld_batch.py:23-26`). `Limit` (`textworld/envs/wrappers/limit.py`) keeps its own counter:
   `nb_steps = 0` only in `reset()`, `nb_steps += 1` and `done |= nb_steps >= max_episode_steps` in `step()`. With
   `asynchronous=True` the wrapper lives in a worker process behind the batch env, not in the bridge's process.
4. The Setup harness replays the S0 prefix through `inner.step` after `inner.reset`
   (`envharness/harnesses/setup.py:79-81`), so every replayed action increments `Limit.nb_steps`. It then calls
   `inner.notify_replay_complete()` (`setup.py:85`), which rewinds only the bridge's own bookkeeping
   (`bridge.py:427-429`: `state.step_count = 0`, repetition counters); nothing reaches the `Limit` counter.
5. The bridge itself has no step cap (its `step` at `bridge.py:275-290` only increments `step_count`, evaluates the
   repetition guard and passes through `engine_done`), and `AlfworldEnv()` takes no constructor arguments
   (`bridge.py:121`). The corpus-protocol budget of 50 policy steps is enforced by the runner
   (`envharness/orchestration/runner.py:122` default `max_steps = 50`, loop at `runner.py:231`), and the eval protocol
   by `experiments/alfworld/reasoning_bank_eval.py:104` (`cfg["policy"]["max_steps"]`). Both count policy steps only,
   because the Setup replay happens inside `reset`.

Net effect (verified in P4.2, LOG 23:33 UTC): a staged env with prefix length `L` gives the policy `50 − L` underlying
steps, while the runner still offers 50. This is the residual-budget artifact behind the first N-zero probe.

## 2. Routes that do not require editing `third_party/`

| route | mechanism | verdict |
|---|---|---|
| A. vendored config copy + `reset_options.config_path` | copy `base_config.yaml` outside `third_party/`, set `max_nb_steps_per_episode` to `50 + L_max` (or simply 100 = 50 + the 50-step prefix bound), pass its path in `env.reset_options.config_path` (runner passes `spec.env.reset_options` through at `runner.py:200`; the bridge honours it at `bridge.py:149`) | **feasible with released APIs; recommended** |
| B. `$ALFWORLD_CONFIG` env var | same file, selected at `bridge.py:149` when `config_path` is absent | feasible; process-wide, less explicit than A |
| C. per-episode value (exactly `50 + L` per staged state) | `_lazy_init_env` runs once per bridge instance and split (`bridge.py:177-178`); a different limit needs a new bridge instance (a new `SubprocessRunner` worker or a fresh in-process bridge) | feasible only with one bridge per prefix length; not needed if A uses a uniform bound (see §3) |
| D. mutate the `Limit` wrapper at runtime | `Limit.max_episode_steps` / `nb_steps` are plain attributes, but reachable only via private members (`bridge._env` → `TextworldBatchGymEnv.batch_env`) and, with `asynchronous=True` (`alfred_tw_env.py:273`), across a process boundary | not admissible (private attributes) and not reachable in-process |
| E. bridge or Setup option to rewind the underlying counter | none exists: `notify_replay_complete` (`bridge.py:412-429`) rewinds bridge counters only; no `AlfworldEnv` constructor or reset option touches `max_episode_steps` | would require a third_party edit; out of scope |

## 3. Route A checked (LLM-free replay, 2026-09-07)

A copy of the vendored config with both `max_nb_steps_per_episode` entries set to 100 was passed via
`reset_options.config_path` to a fresh `AlfworldEnv` wrapped in `Setup` with the 38-action staged prefix of the
task-8 N-zero state (t = 46, no-ops dropped). Policy actions (`look`) were issued until the stack reported done:

| config | prefix length | policy steps until engine done |
|---|---|---|
| vendored default (50) | 38 | 12 |
| copy with 100 | 38 | 62 |

So the underlying cap moves to `100 − L`, and the runner's own `max_steps = 50` (`runner.py:122, 231`) becomes the
binding budget for every staged episode with `L ≤ 50`, i.e. exactly 50 policy steps from the staged state. For
unstaged episodes nothing changes: the runner already stops at 50, and the P1/P2/P3 corpus and eval runs never
relied on the engine's step-50 `done` for anything but ending the episode (evaluation is `won`-based;
`bridge.py:296-300`).

Caveats for the formal CHS implementation:
- Use the uniform bound (100) rather than a per-state value, so one bridge per worker suffices (route C's constraint).
- Truncation semantics shift: with the default config the step-50 stop arrives as `terminated=True` from the engine;
  under route A the runner ends the loop after 50 policy steps without an engine `done`. Any statistic that reads the
  engine's `done` flag (e.g. "share of episodes ending at the cap", E1-pilot P1) must be recomputed from step counts.
- ALFWorld's `AlfredExpert` wrapper (`alfred_tw_env.py:263-267`, `extra.expert_plan`) is unaffected by the limit, so
  the recoverability certificates (`eobs.recover.c_at`) keep their meaning; but their own budget (expert steps from
  `s_t`) should be stated as 50 rather than `50 − t` once route A is in place.
- The eval protocol (`reasoning_bank_eval.py`) builds its env from the same bridge; passing the config copy through
  its `env.reset_options` gives the same behaviour there.

## 4. Answer

Yes. Without touching `third_party/`, a staged env gets a full 50-step policy budget by supplying a config copy with
`max_nb_steps_per_episode: 100` through the released `reset_options.config_path` (or `$ALFWORLD_CONFIG`) and letting
the runner's `max_steps = 50` bound the policy. Exact per-state re-basing (`50 + L`) is possible only with one bridge
instance per prefix length; runtime mutation of TextWorld's `Limit` wrapper is neither admissible nor reachable.
This note is for the formal CHS implementation; P4 keeps the residual-budget rule (t ≤ 30) decided at the gate.
