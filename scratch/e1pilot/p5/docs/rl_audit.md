# P5.4 — Phase-A audit of `third_party/envharness/rl/` (no training runs, no code under `src/`)

Scope: what the released RL adapter integrates, how environments are consumed, the reward path, the hardware the released
configs assume, and what a one-80GB-GPU configuration would need. All paths relative to `third_party/envharness` @ fab7d574.
The RL dependency (verl-agent) is not vendored; fetching it would write under `third_party/envharness/third_party/`, so
everything about its internals below comes from the released README, the patches and the launcher, and is marked as such.

## 1. Trainer and dependency

| item | evidence |
|---|---|
| Trainer | verl-agent (the GiGPO repository), run through `verl.trainer.main_ppo` with `algorithm.adv_estimator=grpo` (`rl/scripts/run_grpo.sh:158-160`); verl-agent builds on verl (`rl/README.md:104-112`). |
| Pinned version | upstream commit `796ed310287fa605c9292a0fce07a86d79fde05e`, cloned by `rl/scripts/fetch_verl_agent.sh:37-40`; not checked in (`rl/README.md:18-33`). The verl / vLLM / flash-attn versions inside that tree are not verifiable here; the README states vLLM 0.11 and Python 3.12 (`rl/README.md:10-13`). |
| Patch surface | default fetch applies one additive env route in `agent_system/environments/env_manager.py` (`rl/integration/verl_agent_env_manager.patch:16-50`); `verl_agent_all_changes.patch` (544 lines) adds Qwen3 non-thinking chat template, DAPO dynamic sampling, transformers-5 fallbacks and a vLLM LoRA import shim (`rl/integration/ENVHARNESS_CHANGES.md`; LoRA shim at `verl_agent_all_changes.patch:496-502`). |
| License | verl-agent Apache-2.0 (`rl/README.md:106-108`); verl Apache-2.0 (upstream); the adapter itself Apache-2.0 (`rl/pyproject.toml:3-7`). Compatible with this project's use. |
| Adapter package | `envharness_rl` (deps: gymnasium, ray; `rl/pyproject.toml:19-22`). |

## 2. How environments are consumed

1. **Route.** `env.env_name=envharness_rl/alfworld` selects the adapter; the patch builds train and validation env pools
   with `build_envharness_alfworld_envs(alf_config_path, seed, train_batch_size, group_n, …)`
   (`verl_agent_env_manager.patch:16-50`). Validation uses `seed + 1000` (`:50`).
2. **Workers.** One Ray actor per environment slot, each holding one persistent `AlfworldEnv`
   (`rl/envharness_rl/alfworld/envs.py:63-116`, pool at `:296-337`). Members of a group share a seed so GRPO groups see
   the same task on the first reset (`envs.py:326-333`); later resets advance the engine's game queue (`envs.py:162-167`).
3. **Stack.** Per episode the worker composes `Rules(inner=AlfworldEnv)` when the active game has `rules_code`
   (`envs.py:194-199`) and replays S0 `in_env_actions` **in place** on the base env (`envs.py:184-190`). The released
   `Setup` harness is not used, so `notify_replay_complete` is never called: the bridge's `step_count` and the TextWorld
   `Limit` counter both keep counting the replayed prefix (the residual-budget effect audited in
   `p4/docs/stage_budget_audit.md` applies unchanged; the repetition guard is off, `repetition_threshold=0`,
   `envs.py:330`). `Link` (two-env chains) has no route: one engine per worker, `step` targets `self._rules` or `self._env`
   (`envs.py:232-236`).
4. **Corpus.** Mutations come from a JSONL `{game_file, rules_code, in_env_actions}` keyed by absolute game file
   (`envs.py:119-146`), selected per reset by the game the worker landed on (`envs.py:178-181`). Train-only; validation
   workers always run the vanilla env (`verl_agent_env_manager.patch:35-39`, `envs.py:314-320`). A staged curriculum for
   the 8 zero tasks is therefore expressible: `train_subset_path` = their game files, corpus = their staged prefixes
   (`rules_code` empty).
5. **`reset_options` and the 100-config.** The worker builds reset options itself
   (`envs.py:149-158`: split, repetition threshold, obs style, subset flags) — there is no `config_path` passthrough.
   The ALFWorld config reaches the bridge through `$ALFWORLD_CONFIG`, which the pool sets with `setdefault` from the
   patch's `alf_config_path` (`envs.py:308-310`; `verl_agent_env_manager.patch:27-28` points at verl-agent's own
   `config_tw.yaml`) and which the launcher exports unconditionally (`run_grpo.sh:148`). Consequences:
   - the bridge honours `$ALFWORLD_CONFIG` (`envharness/bridges/alfworld/bridge.py:149`), so the 100-step copy can be
     used by a launcher that exports it **after** line 148 — i.e. a launcher copy outside `third_party/`, not an edit;
   - verl-agent's `config_tw.yaml` is not readable here; its `max_nb_steps_per_episode` is unknown, and the policy budget
     is set separately by `env.max_steps` (`run_grpo.sh:57,71,195`).
6. **Action format.** `<think>…</think><action>…</action>` required; the action is normalized against the admissible
   commands (`rl/envharness_rl/alfworld/projection.py:71-84`, `:48`); `ENVHARNESS_DISABLE_THINKING=1` is exported for
   Qwen3 non-thinking rollouts (`run_grpo.sh:109`).

## 3. Reward / verifier path

- Episode reward = `10.0 * float(info["won"])` computed in the adapter to match verl-agent's `compute_reward`
  (`envs.py:361-364`); `won` is the bridge's flag (`bridge.py:293-300`), recovered defensively if a `Rules` hook corrupts
  it (`envs.py:246-258`). The harness-level `evaluate()` is not consulted, so Link-style conjunctive success has no RL
  analogue.
- Invalid-action penalty 0.1 on the actor side (`run_grpo.sh:191-192`); KL to the reference 0.01, lr 1e-6, prompt/response
  4096/512 tokens (`run_grpo.sh:164-175`).

## 4. Hardware assumed by the released configs

| mode | model | GPUs / TP | batch × group | max steps | epochs | evidence |
|---|---|---|---|---|---|---|
| smoke | Qwen2.5-1.5B-Instruct | 2 / 2 | 8 × 4 = 32 episodes per step | 15 | 2 | `run_grpo.sh:47-59,86` |
| full | Qwen3-8B (MODEL override; default stays 1.5B, exp name says qwen7b) | 8 / 4 | 16 × 8 = 128 episodes per step, ppo mini 256 | 50, history 50 | 150 | `run_grpo.sh:61-75` |

FSDP parameter and optimizer offload are on, vLLM takes 60% of GPU memory (`run_grpo.sh:178-183`). EnvHarness App. F
(per the owner brief) ran Qwen3-8B-base GRPO on 8×H100, consistent with the full mode.

## 5. One-80GB-GPU configuration (estimate, not measured)

What must change: `N_GPUS=1 TP=1`; either Qwen3-4B full-parameter with FSDP CPU offload (bf16 weights 8 GB, fp32 Adam
states 48 GB offloaded to host RAM) or Qwen3-8B with LoRA (verl's `actor_rollout_ref.model.lora_rank`; the all-changes
patch already carries the vLLM LoRA import shim, `verl_agent_all_changes.patch:496-502`, so the LoRA rollout path is
expected to load); vLLM share ≈ 48 GB (8B bf16 weights 16 GB + KV cache); `TRAIN_BS=8 GROUP_N=8` (64 episodes per step),
`MAX_STEPS=30`, `PPO_MINI_BS=64`, micro batch 1–2, gradient checkpointing (already on). One verl "epoch" here is one
step over the `TRAIN_BS`-row parquet (`run_grpo.sh:151-155`), so epochs = optimizer steps.

Throughput assumptions (single H100/A100-80GB, 8B model, vLLM ≈ 1.5–2.5k generated tok/s across 64 concurrent episodes,
≈ 30 steps × 60–80 tokens of `<think>`-free action text plus prompt growth up to 4k tokens): generation ≈ 4–7 min per step,
log-prob + LoRA update over ≈ 64 × 30 samples ≈ 3–5 min, validation every 5 steps on 128 episodes ≈ 8–10 min.
Roughly 10–15 min per step → 150 steps ≈ 25–40 h per run.

| run | env | GPU-hours (est.) | cloud cost at USD 2.5/h (est.) | wall time on 1 GPU |
|---|---|---|---|---|
| A: original env (control), 150 steps, Qwen3-8B + LoRA | vanilla, train subset = the P1 30 tasks or full TRAIN | 25–40 | 65–100 | 1–2 days |
| B: staged curriculum (CHS prefixes from P5.1 on the 8 zero tasks, 100-config via `$ALFWORLD_CONFIG`), same budget | corpus = staged prefixes; validation vanilla | 25–40 | 65–100 | 1–2 days |
| both, full released recipe (8×H100, 128 episodes/step, 150 steps) | as above | 8 × ~40 = ~320 each | ~800 each at USD 2.5/GPU-h | ~40 h each |

Uncertainties that only a GPU smoke can remove: the true generation throughput with 4k-token prompts, whether the pinned
verl-agent's LoRA path works with vLLM 0.11 weight sync (the patch touches exactly that file, `fsdp_vllm.py`), and the
`max_nb_steps_per_episode` inside verl-agent's `config_tw.yaml`.

## 6. Summary for the design meeting

- The released RL path trains GRPO on `AlfworldEnv + Rules` with S0 replayed in place; Setup/Link are not plumbed, and
  the stage budget is charged to the episode exactly as in the corpus protocol before P5 — a staged curriculum needs the
  100-config through `$ALFWORLD_CONFIG` from a launcher outside `third_party/` (no edit required).
- Reward is binary `won` × 10 with an invalid-action penalty; no shaping and no chain evaluation.
- Released hardware: 2 GPUs (smoke) / 8 GPUs (full, Qwen3-8B). A single 80 GB GPU can run a reduced recipe
  (Qwen3-8B + LoRA or Qwen3-4B + offload, 64 episodes per step, 30-step horizon) in an estimated 1–2 days per run; two
  runs (original vs staged) ≈ USD 130–200 of cloud time at the estimate above, before any smoke-test corrections.
