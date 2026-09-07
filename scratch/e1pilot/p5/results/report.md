# P5 report — CHS fork test, induction-mode control, bank-size dose — generated 2026-09-07 07:21 UTC

PREREG5 sha `804f958`; inputs P4 @ b22f07d; config sha256 (16 hex): vendored base_config `2fb5f24f344eaaf1`, alfworld_config_100 `0342a74443beae56`; policy openai/qwen/qwen3-8b via OpenRouter (provider Alibaba, 0.117/0.455 USD/M); induction DeepSeek V4 Pro; P5 spend USD 0.24 of 35 ({'p5_eval_embed': 0.0, 'p5_eval': 0.18, 'p5_induce': 0.06, 'p5_induce_embed': 0.0}); pilot total USD 52.06 (hard 150 / soft 130).

## P5.1 Certified Hindsight Staging with the re-based budget (100-config; policy budget 50)

Certificates C_any3 recomputed for every prefix of the 24 P4.2 trajectories (expert ≤ 50 own steps). L_any3 = latest certified state; 'certified states' counts t > 0.

| task | trajectory | L_any3 (P4, residual budget) | L_any3 (P5, 100-config) | certified states P4 → P5 |
|---|---|---|---|---|
| 8 | 6353684e | 46 | 27 | 45 → 25 |
| 8 | 7e048535 | 45 | 50 | 42 → 48 |
| 8 | b48f2bb4 | 44 | 50 | 41 → 49 |

States that gained a certificate under the 100-config: 14 (sum over trajectories of the increase in certified-state counts).

(probe not run yet)

## P5.4 RL Phase-A audit (p5/docs/rl_audit.md)

verl-agent (GiGPO; Apache-2.0) @ 796ed310 on verl, GRPO; env route `envharness_rl/alfworld` = Ray actors holding one AlfworldEnv each, Rules composed per episode, S0 replayed in place (no Setup/Link; prefix charged to the step cap); reward 10 × won with a 0.1 invalid-action penalty; released hardware 2 GPUs (smoke, Qwen2.5-1.5B) / 8 GPUs (full, Qwen3-8B, 128 episodes per step, 150 steps). The 100-config reaches the bridge only through $ALFWORLD_CONFIG exported after the launcher's own export, i.e. a launcher copy outside third_party.

| run (1 × 80 GB GPU, Qwen3-8B + LoRA, 64 episodes/step, 30-step horizon, 150 steps) | GPU-hours (est.) | cloud USD at 2.5/h (est.) | wall time |
|---|---|---|---|
| A original env | 25–40 | 65–100 | 1–2 days |
| B staged curriculum (P5.1 prefixes, 100-config) | 25–40 | 65–100 | 1–2 days |
| full released recipe, 8×H100, per run | ~320 | ~800 | ~40 h |

## Measurement notes

- Every staged session (certificates, probes, bank rollouts) used the 100-config via reset_options.config_path; the LLM-free replay check gave 12 policy steps (default) vs 62 (copy) after a 38-action prefix. Unstaged sessions and all held-out evals use the default config.
- P5.1 probed every candidate (no walk rule); selection = latest learnable; p̂_12 pools the 4 probe and 8 bank rollouts.
- P5.2 induction = released `_build_bank` fed success-only trajectories, so `_pick_pair` yields the shortest success and `induce_memory_items(success=True)` runs on both sides; P5.3 subsamples the P3b orig_m bank without re-induction.
- Held-out evals: released protocol, 30 ID + 30 OOD, 3 same-task replicates; nobank / orig_m / P4 arms reused from their runs; paired per-task differences with a 10k task-level bootstrap.

## Caveats

- Single benchmark, N = 30 train tasks, 8 zero tasks with 3 trajectories each, Qwen3-8B via API, one consumer protocol; bank-size curve on one bank; no method proposals.
- The 100-config changes truncation semantics (engine done no longer coincides with the runner's 50-step stop); step-cap statistics are computed from step counts.
- The RL cost table is an estimate from released hyper-parameters, not a measurement.
