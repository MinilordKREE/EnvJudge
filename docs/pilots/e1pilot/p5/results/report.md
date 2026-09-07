# P5 report — CHS fork test, induction-mode control, bank-size dose — generated 2026-09-07 11:20 UTC

PREREG5 sha `804f958`; inputs P4 @ b22f07d; config sha256 (16 hex): vendored base_config `2fb5f24f344eaaf1`, alfworld_config_100 `0342a74443beae56`; policy openai/qwen/qwen3-8b via OpenRouter (provider Alibaba, 0.117/0.455 USD/M); induction DeepSeek V4 Pro; P5 spend USD 22.05 of 35 ({'p5_eval_embed': 0.0, 'p5_eval': 8.69, 'p5_induce': 0.06, 'p5_induce_embed': 0.0, 'p5_chs': 13.3}); pilot total USD 73.87 (hard 150 / soft 130).

## P5.1 Certified Hindsight Staging with the re-based budget (100-config; policy budget 50)

Certificates C_any3 recomputed for every prefix of the 24 P4.2 trajectories (expert ≤ 50 own steps). L_any3 = latest certified state; 'certified states' counts t > 0.

| task | trajectory | L_any3 (P4, residual budget) | L_any3 (P5, 100-config) | certified states P4 → P5 |
|---|---|---|---|---|
| 8 | 6353684e | 46 | 50 | 45 → 47 |
| 8 | 7e048535 | 45 | 50 | 42 → 48 |
| 8 | b48f2bb4 | 44 | 50 | 41 → 49 |
| 9 | 61cfdf70 | 48 | 50 | 48 → 50 |
| 9 | cd27c4f0 | 48 | 50 | 48 → 50 |
| 9 | e4b69a57 | 48 | 50 | 48 → 50 |
| 10 | 7473aeab | 3 | 3 | 3 → 3 |
| 10 | bf621a2c | 45 | 50 | 45 → 50 |
| 10 | c8a00bc6 | 11 | 11 | 11 → 11 |
| 11 | 0f5a2909 | 1 | 1 | 1 → 1 |
| 11 | 7fbda3f9 | 1 | 1 | 1 → 1 |
| 11 | cdad228a | 1 | 1 | 1 → 1 |
| 14 | 5a1b1931 | 46 | 50 | 46 → 50 |
| 14 | db3013da | 40 | 50 | 40 → 50 |
| 14 | e15d9f1a | 46 | 50 | 46 → 50 |
| 17 | 88268360 | 40 | 50 | 40 → 48 |
| 17 | bdad0a7b | 46 | 50 | 45 → 50 |
| 17 | d9876928 | 41 | 50 | 39 → 47 |
| 20 | 13df6f63 | 43 | 50 | 31 → 47 |
| 20 | 8a405c58 | 44 | 50 | 22 → 30 |
| 20 | cad4cab2 | 45 | 50 | 33 → 39 |
| 27 | 44b03a44 | 43 | 50 | 43 → 50 |
| 27 | 62d8c821 | 42 | 50 | 42 → 50 |
| 27 | 6acfcf6f | 43 | 50 | 43 → 50 |

States that gained a certificate under the 100-config: 118 (sum over trajectories of the increase in certified-state counts).

### Learnability profiles p̂_4(t) — ALL candidates probed (4 corpus-protocol rollouts each; 0/4 dead, 4/4 saturated, 1–3 learnable)

| task | t (kind): successes/4 … | learnable | dead | saturated | earliest learnable t | selected t | p̂_12 | confirmed | status |
|---|---|---|---|---|---|---|---|---|---|
| 8 | 50(L):3/4 50(L):0/4 38(3L/4):1/4 25(L/2):0/4 13(L/4):0/4 12(L/4):0/4 | 2 | 4 | 0 | 38 | 50 | 0.5833 | True | selected |
| 9 | 50(L):3/4 50(L):2/4 50(L):3/4 38(3L/4):2/4 25(L/2):4/4 13(L/4):4/4 | 4 | 0 | 2 | 38 | 50 | 0.6667 | True | selected |
| 10 | 50(L):1/4 38(3L/4):0/4 25(L/2):1/4 13(L/4):0/4 8(3L/4):0/4 3(L/4):0/4 | 2 | 4 | 0 | 25 | 50 | 0.0833 | False | selected |
| 11 | 1(L):0/4 1(L):0/4 1(L):0/4 | 0 | 3 | 0 |  |  |  | False | all_dead |
| 14 | 50(L):0/4 50(L):0/4 50(L):0/4 38(3L/4):0/4 25(L/2):0/4 13(L/4):0/4 | 0 | 6 | 0 |  |  |  | False | all_dead |
| 17 | 50(L):0/4 50(L):0/4 50(L):0/4 38(3L/4):0/4 25(L/2):0/4 13(L/4):0/4 | 0 | 6 | 0 |  |  |  | False | all_dead |
| 20 | 50(L):0/4 39(3L/4):0/4 38(3L/4):0/4 25(L/2):0/4 18(L/2):0/4 13(L/4):4/4 | 0 | 5 | 1 |  |  |  | False | mixed_dead_saturated |
| 27 | 50(L):2/4 50(L):4/4 50(L):3/4 38(3L/4):3/4 25(L/2):1/4 13(L/4):3/4 | 5 | 0 | 1 | 13 | 50 | 0.6667 | True | selected |

**K5: 3/8 zero tasks with a confirmed selected env (p̂_12 ∈ [0.2, 0.8]) → 2–3 → marginal: the design meeting decides with the profiles in hand.**

## P5.2 Induction-mode control (single_succ on both sides; matched items)

Banks: isat_ss 27 items, origc_isat_ss 27 items, all single_succ; matched = 27 (seed 20260914).

| condition | ID | OOD |
|---|---|---|
| nobank | 0.444 [0.300, 0.589] (n=90, tasks=30) | 0.322 [0.178, 0.478] (n=90, tasks=30) |
| orig_m | 0.589 [0.422, 0.756] (n=90, tasks=30) | 0.467 [0.311, 0.633] (n=90, tasks=30) |
| isat_m | 0.400 [0.244, 0.567] (n=90, tasks=30) | 0.256 [0.100, 0.422] (n=90, tasks=30) |
| origc_isat_m | 0.444 [0.289, 0.600] (n=90, tasks=30) | 0.578 [0.422, 0.733] (n=90, tasks=30) |
| isat_ss | 0.556 [0.389, 0.722] (n=90, tasks=30) | 0.544 [0.378, 0.711] (n=90, tasks=30) |
| origc_isat_ss | 0.433 [0.278, 0.589] (n=90, tasks=30) | 0.389 [0.244, 0.544] (n=90, tasks=30) |

**H5 (isat_ss(m) − origc_isat_ss(m), ID, paired): 0.122 [-0.044, 0.289] (n=30) → H5a: environment content not shown harmful; the P3/P4 deficits are attributed to induction mode and bank size; the interface/Goodhart claim is withdrawn from the method's claims.** OOD: 0.156 [0.022, 0.300] (n=30); P4 paired-diff comparison for reference: isat_m − origc_isat_m ID -0.044 [-0.189, 0.100] (n=30).

vs nobank (ID): isat_ss 0.111 [-0.044, 0.278] (n=30); origc_isat_ss -0.011 [-0.156, 0.133] (n=30).

## P5.3 Bank-size dose on orig_m (single_succ items; seeded subsamples 20260915)

Retrieval: top_k = 5 (mmr); banks with ≤ top_k items inject every item on every step (marked ★).

| bank size | ID | OOD | ID − nobank | OOD − nobank |
|---|---|---|---|---|
| 3 ★ | 0.478 [0.300, 0.644] (n=90, tasks=30) | 0.233 [0.100, 0.389] (n=90, tasks=30) | 0.033 [-0.089, 0.167] (n=30) | -0.089 [-0.200, 0.011] (n=30) |
| 6 | 0.389 [0.244, 0.544] (n=90, tasks=30) | 0.311 [0.167, 0.467] (n=90, tasks=30) | -0.056 [-0.167, 0.067] (n=30) | -0.011 [-0.144, 0.122] (n=30) |
| 9 | 0.344 [0.200, 0.500] (n=90, tasks=30) | 0.300 [0.133, 0.467] (n=90, tasks=30) | -0.100 [-0.222, 0.033] (n=30) | -0.022 [-0.178, 0.133] (n=30) |
| 15 | 0.489 [0.322, 0.656] (n=90, tasks=30) | 0.422 [0.256, 0.589] (n=90, tasks=30) | 0.044 [-0.100, 0.200] (n=30) | 0.100 [-0.067, 0.278] (n=30) |
| 23 | 0.589 [0.422, 0.756] (n=90, tasks=30) | 0.467 [0.311, 0.622] (n=90, tasks=30) | 0.144 [0.011, 0.289] (n=30) | 0.144 [-0.011, 0.311] (n=30) |
| 0 (nobank) | 0.444 [0.300, 0.589] (n=90, tasks=30) | 0.322 [0.178, 0.478] (n=90, tasks=30) | — | — |

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
