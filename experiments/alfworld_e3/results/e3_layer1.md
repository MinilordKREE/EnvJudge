# E3 layer 1 — environment production at matched budget, Qwen3-8B, ALFWorld seeds 0-29 (PREREG9)

Policy Qwen3-8B (OpenRouter, alibaba pin, reasoning off); designer DeepSeek V4 Pro (thinking off) for every arm; cap 30 policy rollouts per task per arm; K = 16 confirmations (budget eval, never written back); B_L = [0.2, 0.8]. Shared original-environment K=16: 10 tasks reused from E2 (runs/e2-shared), 20 new (runs/e3-shared). Tables from scripts/make_tables_e3.py; PREREG9 @ 08a09b7.

## Shared original-environment K=16 per task

| task | p16 | s/n | class | source |
|---|---|---|---|---|
| 0 | 0.188 | 3/16 | marginal-low | e2-shared |
| 1 | 1.000 | 16/16 | saturated | e3-shared |
| 2 | 0.938 | 15/16 | saturated | e3-shared |
| 3 | 0.812 | 13/16 | saturated | e3-shared |
| 4 | 0.500 | 8/16 | band | e3-shared |
| 5 | 0.750 | 12/16 | band | e3-shared |
| 6 | 0.438 | 7/16 | band | e3-shared |
| 7 | 1.000 | 16/16 | saturated | e3-shared |
| 8 | 0.000 | 0/16 | zero | e2-shared |
| 9 | 0.000 | 0/16 | zero | e2-shared |
| 10 | 0.000 | 0/16 | zero | e2-shared |
| 11 | 0.000 | 0/16 | zero | e2-shared |
| 12 | 1.000 | 16/16 | saturated | e3-shared |
| 13 | 1.000 | 16/16 | saturated | e3-shared |
| 14 | 0.000 | 0/16 | zero | e2-shared |
| 15 | 1.000 | 16/16 | saturated | e3-shared |
| 16 | 0.500 | 8/16 | band | e3-shared |
| 17 | 0.000 | 0/16 | zero | e2-shared |
| 18 | 0.125 | 2/16 | marginal-low | e2-shared |
| 19 | 0.625 | 10/16 | band | e3-shared |
| 20 | 0.000 | 0/16 | zero | e2-shared |
| 21 | 0.938 | 15/16 | saturated | e3-shared |
| 22 | 1.000 | 16/16 | saturated | e3-shared |
| 23 | 1.000 | 16/16 | saturated | e3-shared |
| 24 | 1.000 | 16/16 | saturated | e3-shared |
| 25 | 1.000 | 16/16 | saturated | e3-shared |
| 26 | 0.625 | 10/16 | band | e3-shared |
| 27 | 0.000 | 0/16 | zero | e2-shared |
| 28 | 0.875 | 14/16 | saturated | e3-shared |
| 29 | 1.000 | 16/16 | saturated | e3-shared |

Classes: zero 8 (8, 9, 10, 11, 14, 17, 20, 27); marginal-low 2; band 6 (4, 5, 6, 16, 19, 26); saturated 14 (1, 2, 3, 7, 12, 13, 15, 21, 22, 23, 24, 25, 28, 29); unmeasured 0.

## C1 primary — learner-facing learnable environments per 1,000 charged search rollouts

| arm | learner-facing envs | learnable | charged rollouts | per 1,000 [95% CI, task bootstrap] |
|---|---|---|---|---|
| A | 9 | 9 | 730 | 12.3 [5.2, 21.5] |
| G | 14 | 10 | 655 | 15.3 [7.0, 25.9] |
| R | 4 | 3 | 330 | 9.1 [0.0, 21.1] |

## C1 secondary — transformed-only (PREREG7 definition)

| arm | transformed envs | learnable | charged rollouts | per 1,000 [95% CI] |
|---|---|---|---|---|
| A | 3 | 3 | 730 | 4.1 [0.0, 9.0] |
| G | 14 | 10 | 655 | 15.3 [7.2, 25.9] |
| R | 4 | 3 | 330 | 9.1 [0.0, 20.6] |

## Band preservation — originally learnable tasks (6: 4, 5, 6, 16, 19, 26) still learnable in the learner-facing set

| arm | preserved | tasks |
|---|---|---|
| A | 6 / 6 | 4, 5, 6, 16, 19, 26 |
| G | 5 / 6 | 4, 5, 6, 16, 26 |
| R | 2 / 6 | 6, 16 |

## Unlocked zero tasks (zero: 8, 9, 10, 11, 14, 17, 20, 27) and precision

| arm | unlocked | tasks | precision (learnable / accepted transformed) |
|---|---|---|---|
| A | 0 | - | 3 / 3 (100%) |
| G | 1 | 8 | 10 / 14 (71%) |
| R | 0 | - | 3 / 4 (75%) |

## Saturated subset (original p16 > 0.8: 14 tasks) — learnable transformed environments per 1,000

| arm | transformed envs | learnable | charged rollouts on the subset | per 1,000 [95% CI] |
|---|---|---|---|---|
| A | 3 | 3 | 404 | 7.4 [0.0, 15.8] |
| G | 5 | 3 | 350 | 8.6 [0.0, 20.3] |
| R | 0 | 0 | 70 | 0.0 [0.0, 0.0] |

## H100 control — 100-step success from the original start (tasks 8, 9, 27) next to the staged p16

| task | H100 s/n | H100 p | A staged env p16 (t) | E2 Phase D staged p16 (reference) | attribution |
|---|---|---|---|---|---|
| 8 | 0/8 | 0.000 | - (-) | - | - |
| 9 | 0/8 | 0.000 | - (-) | 0.625 | staging (H100 < staged) |
| 27 | 8/8 | 1.000 | - (-) | 0.500 | horizon (H100 >= staged) |

## PREREG9 claims

- E3-1 (primary): A 12.3 vs G 15.3 and R 9.1 per 1,000 → A > G fails, A > R holds → **fails** (point estimates; CIs above).
- E3-2 (band preservation): A 6, G 5, R 2 of 6 → **holds**.
- E3-3 (saturated subset): A 7.4 vs G 8.6 per 1,000 → **fails**.
- E3-4 (zero subset, reported, not a gate): A 0 vs G 1 unlocked → **fails** (E2 Phase D anchor: 2 vs 2).
- H100 (control): task 8: -; task 9: staging (H100 < staged); task 27: horizon (H100 >= staged). A task whose 100-step original-start success is >= its staged p16 is attributed to horizon, not staging.

**Stop rule for downstream:** E3-3 fails → the saturated side returns to design before any skill or RL evaluation; E3-1 fails → the downstream columns are not run under PREREG9 as frozen; PREREG9 Addendum SL (committed before these tables) replaces the E3-1 clause: the SL evaluation runs regardless of E3-1 and E3-3 and is reported as such.

## A per task (aea v0.2, proposer on, persistent priors)

| task | shared p16 (class) | estimate (regime, p_hat, n) | families (order) | brackets (family: start → status, doses) | stage (certified/rejected; probes t: s/n verdict) | outcome | reason | n_search | learner-facing envs (p16) |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.188 (marginal-low) | zero, 0.000, 10 | - | - | 6/0; 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 4/4 too_easy; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 1 | 1.000 (saturated) | saturated, 1.000, 10 | observation_noise, footer_mask, horizon_squeeze | observation_noise: mid → accepted, 1.0:0/4/0.5:6/8/0.75:3/8 | - | accepted | - | 30 | knob 0.438* |
| 2 | 0.938 (saturated) | saturated, 1.000, 10 | observation_noise_insertion, action_echo_swap, footer_mask, horizon_squeeze | observation_noise_insertion: mid → budget, 1.0:0/4/0.5:4/4/0.75:2/8 | - | dropped | budget | 30 | - |
| 3 | 0.812 (saturated) | saturated, 1.000, 10 | action_dropout, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:4/4/0.75:4/4/0.875:4/4 | - | dropped | budget | 30 | - |
| 4 | 0.500 (band) | band, 0.625, 8 | - | - | - | kept | - | 8 | kept 0.500* |
| 5 | 0.750 (band) | band, 0.500, 8 | - | - | - | kept | - | 8 | kept 0.750* |
| 6 | 0.438 (band) | band, 0.333, 12 | - | - | - | kept | - | 12 | kept 0.438* |
| 7 | 1.000 (saturated) | saturated, 1.000, 10 | command_permute_mask, reward_decay, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:4/4/0.75:4/4 | - | dropped | budget | 30 | - |
| 8 | 0.000 (zero) | zero, 0.000, 10 | - | - | 5/1; 50: 0/4 too_hard; 50: 6/8 too_easy; 50: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 9 | 0.000 (zero) | zero, 0.000, 10 | - | - | 4/0; 50: 4/4 too_easy; 50: 4/4 too_easy; 25: 4/4 too_easy; 25: 4/4 too_easy | dropped | too_easy | 26 | - |
| 10 | 0.000 (zero) | zero, 0.000, 10 | - | - | 3/3; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard | dropped | dead | 22 | - |
| 11 | 0.000 (zero) | zero, 0.000, 10 | - | - | 0/3; - | dropped | uncertified | 10 | - |
| 12 | 1.000 (saturated) | saturated, 1.000, 10 | reward_echo, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:4/4/0.75:4/4/0.875:4/4 | - | dropped | budget | 30 | - |
| 13 | 1.000 (saturated) | saturated, 1.000, 10 | footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:6/8/0.75:7/8 | - | dropped | budget | 30 | - |
| 14 | 0.000 (zero) | zero, 0.000, 10 | - | - | 6/0; 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 15 | 1.000 (saturated) | saturated, 1.000, 10 | footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:2/8/0.25:7/8 | - | dropped | budget | 30 | - |
| 16 | 0.500 (band) | band, 0.333, 12 | - | - | - | kept | - | 12 | kept 0.500* |
| 17 | 0.000 (zero) | zero, 0.000, 10 | - | - | 6/0; 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 18 | 0.125 (marginal-low) | zero, 0.062, 16 | - | - | 2/2; 50: 0/4 too_hard; 25: 1/8 too_hard | dropped | dead | 28 | - |
| 19 | 0.625 (band) | band, 0.812, 16 | - | - | - | kept | - | 16 | kept 0.625* |
| 20 | 0.000 (zero) | zero, 0.000, 10 | - | - | 4/2; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 7/8 too_easy; 25: 0/4 too_hard | dropped | too_easy | 30 | - |
| 21 | 0.938 (saturated) | saturated, 0.938, 16 | action_permutation, observation_noise, footer_mask, horizon_squeeze | observation_noise: mid → budget, 1.0:1/8 | - | dropped | budget | 28 | - |
| 22 | 1.000 (saturated) | saturated, 1.000, 10 | action_alias_swap, reward_echo_perturb, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:4/4/0.75:4/4 | - | dropped | budget | 30 | - |
| 23 | 1.000 (saturated) | saturated, 0.938, 16 | command_swap, reward_penalty, footer_mask, horizon_squeeze | command_swap: mid → accepted, 1.0:0/4/0.5:5/8 | - | accepted | - | 28 | knob 0.625* |
| 24 | 1.000 (saturated) | saturated, 1.000, 10 | command_noise_swap, reward_delay, footer_mask, horizon_squeeze | - | - | accepted | - | 18 | knob 0.312* |
| 25 | 1.000 (saturated) | saturated, 1.000, 10 | command_permutation, noise_observations, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:7/8 | - | dropped | budget | 30 | - |
| 26 | 0.625 (band) | band, 0.500, 8 | - | - | - | kept | - | 8 | kept 0.625* |
| 27 | 0.000 (zero) | zero, 0.000, 10 | - | - | 3/0; 50: 2/8 too_hard; 50: 4/4 too_easy; 25: 0/4 too_hard | dropped | too_easy | 26 | - |
| 28 | 0.875 (saturated) | saturated, 1.000, 10 | observation_noise, footer_mask, horizon_squeeze, action_dropout | observation_noise: mid → budget, 1.0:0/4/0.5:0/4/0.25:0/4/0.125:6/8 | - | dropped | budget | 30 | - |
| 29 | 1.000 (saturated) | saturated, 1.000, 10 | reward_noise, footer_mask, horizon_squeeze, command_permutation | footer_mask: mid → budget, 1.0:0/4/0.5:4/4/0.75:4/4/0.875:4/4 | - | dropped | budget | 30 | - |

A outcomes: accepted 3, dropped:budget 15, dropped:dead 2, dropped:too_easy 3, dropped:uncertified 1, kept 6.

### Family of origin — A's accepted environments

| task | kind | family | source | axis | dose | t | p8 | confirmed p16 | learnable |
|---|---|---|---|---|---|---|---|---|---|
| 1 | knob | observation_noise | proposer | O | 0.750 | - | 0.375 | 0.438 | y |
| 23 | knob | command_swap | proposer | O | 0.500 | - | 0.625 | 0.625 | y |
| 24 | knob | command_noise_swap | proposer | O | 1.000 | - | 0.375 | 0.312 | y |

Origin counts: knob:proposer:command_noise_swap 1, knob:proposer:command_swap 1, knob:proposer:observation_noise 1.

### A per-task budget (charged search rollouts by phase)

| task | estimate | dose (harden) | probe (stage) | n_search | infra errors (refunded) |
|---|---|---|---|---|---|
| 0 | 10 | 0 | 20 | 30 | 0 |
| 1 | 10 | 20 | 0 | 30 | 0 |
| 2 | 10 | 20 | 0 | 30 | 0 |
| 3 | 10 | 20 | 0 | 30 | 0 |
| 4 | 8 | 0 | 0 | 8 | 0 |
| 5 | 8 | 0 | 0 | 8 | 0 |
| 6 | 12 | 0 | 0 | 12 | 0 |
| 7 | 10 | 20 | 0 | 30 | 0 |
| 8 | 10 | 0 | 20 | 30 | 0 |
| 9 | 10 | 0 | 16 | 26 | 0 |
| 10 | 10 | 0 | 12 | 22 | 0 |
| 11 | 10 | 0 | 0 | 10 | 0 |
| 12 | 10 | 20 | 0 | 30 | 0 |
| 13 | 10 | 20 | 0 | 30 | 0 |
| 14 | 10 | 0 | 20 | 30 | 0 |
| 15 | 10 | 20 | 0 | 30 | 0 |
| 16 | 12 | 0 | 0 | 12 | 0 |
| 17 | 10 | 0 | 20 | 30 | 0 |
| 18 | 16 | 0 | 12 | 28 | 0 |
| 19 | 16 | 0 | 0 | 16 | 0 |
| 20 | 10 | 0 | 20 | 30 | 0 |
| 21 | 16 | 12 | 0 | 28 | 0 |
| 22 | 10 | 20 | 0 | 30 | 0 |
| 23 | 16 | 12 | 0 | 28 | 0 |
| 24 | 10 | 8 | 0 | 18 | 0 |
| 25 | 10 | 20 | 0 | 30 | 0 |
| 26 | 8 | 0 | 0 | 8 | 0 |
| 27 | 10 | 0 | 16 | 26 | 0 |
| 28 | 10 | 20 | 0 | 30 | 0 |
| 29 | 10 | 20 | 0 | 30 | 0 |

## G and R per task (released orchestrator; Qwen policy, DeepSeek designer)

| arm | task | shared class | baseline | candidates tried | accepted (non-empty) | decision | charged | accepted-env p16 |
|---|---|---|---|---|---|---|---|---|
| G | 0 | marginal-low | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 1 | saturated | 5 | 2 | 1 | accepted | 15 | 0.562* |
| G | 2 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 3 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 4 | band | 5 | 4 | 1 | accepted | 25 | 0.562* |
| G | 5 | band | 5 | 2 | 1 | accepted | 15 | 0.625* |
| G | 6 | band | 5 | 2 | 1 | accepted | 15 | 0.375* |
| G | 7 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 8 | zero | 5 | 3 | 1 | accepted | 20 | 0.375* |
| G | 9 | zero | 5 | 4 | 0 | accepted_empty | 25 | - |
| G | 10 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 11 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 12 | saturated | 5 | 4 | 1 | accepted | 25 | 1.000 |
| G | 13 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 14 | zero | 5 | 0 | 0 | skipped | 5 | - |
| G | 15 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 16 | band | 5 | 1 | 1 | accepted | 10 | 0.438* |
| G | 17 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 18 | marginal-low | 5 | 1 | 1 | accepted | 10 | 0.625* |
| G | 19 | band | 5 | 1 | 1 | accepted | 10 | 0.812 |
| G | 20 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 21 | saturated | 5 | 2 | 1 | accepted | 15 | 0.375* |
| G | 22 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 23 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 24 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |
| G | 25 | saturated | 5 | 2 | 1 | accepted | 15 | 0.188 |
| G | 26 | band | 5 | 1 | 1 | accepted | 10 | 0.438* |
| G | 27 | zero | 5 | 1 | 1 | accepted | 10 | 0.938 |
| G | 28 | saturated | 5 | 1 | 1 | accepted | 10 | 0.688* |
| G | 29 | saturated | 5 | 5 | 0 | all_rejected | 30 | - |

G decisions: accepted 14, accepted_empty 1, all_rejected 14, skipped 1.

| R | 0 | marginal-low | 5 | 4 | 0 | all_rejected | 25 | - |
| R | 1 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 2 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 3 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 4 | band | 5 | 0 | 0 | skipped | 5 | - |
| R | 5 | band | 5 | 0 | 0 | skipped | 5 | - |
| R | 6 | band | 5 | 2 | 1 | accepted | 15 | 0.438* |
| R | 7 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 8 | zero | 5 | 4 | 0 | all_rejected | 25 | - |
| R | 9 | zero | 5 | 2 | 0 | accepted_empty | 15 | - |
| R | 10 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| R | 11 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| R | 12 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 13 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 14 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| R | 15 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 16 | band | 5 | 1 | 1 | accepted | 10 | 0.500* |
| R | 17 | zero | 5 | 1 | 1 | accepted | 10 | 0.062 |
| R | 18 | marginal-low | 5 | 2 | 1 | accepted | 15 | 0.750* |
| R | 19 | band | 5 | 0 | 0 | skipped | 5 | - |
| R | 20 | zero | 5 | 5 | 0 | all_rejected | 30 | - |
| R | 21 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 22 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 23 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 24 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 25 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 26 | band | 5 | 0 | 0 | skipped | 5 | - |
| R | 27 | zero | 5 | 0 | 0 | skipped | 5 | - |
| R | 28 | saturated | 5 | 0 | 0 | skipped | 5 | - |
| R | 29 | saturated | 5 | 0 | 0 | skipped | 5 | - |

R decisions: accepted 4, accepted_empty 1, all_rejected 6, skipped 19.

## Learner-facing environments and their K=16 (deduplicated across arms)

| env | task | kind / t | arms | s/n | p16 | learnable |
|---|---|---|---|---|---|---|
| 1:b53fdd2c8a38adc1 | 1 | knob  | A | 7/16 | 0.438 | y |
| 1:f6bfb14d444ca56f | 1 | accepted  | G | 9/16 | 0.562 | y |
| 4:235a1defc7002a27 | 4 | accepted  | G | 9/16 | 0.562 | y |
| 4:dc0ae181c7f957d8 | 4 | kept  | A | 8/16 | 0.500 | y |
| 5:61659058f271a927 | 5 | accepted  | G | 10/16 | 0.625 | y |
| 5:dc0ae181c7f957d8 | 5 | kept  | A | 12/16 | 0.750 | y |
| 6:0c340222b8d60154 | 6 | accepted  | G | 6/16 | 0.375 | y |
| 6:c4bbfb75a9e9050c | 6 | accepted  | R | 7/16 | 0.438 | y |
| 6:dc0ae181c7f957d8 | 6 | kept  | A | 7/16 | 0.438 | y |
| 8:f0329533e3beaaa8 | 8 | accepted  | G | 6/16 | 0.375 | y |
| 12:a95f1c9977683e99 | 12 | accepted  | G | 16/16 | 1.000 | - |
| 16:a95f1c9977683e99 | 16 | accepted  | G | 7/16 | 0.438 | y |
| 16:dc0ae181c7f957d8 | 16 | kept  | A | 8/16 | 0.500 | y |
| 16:ffb7557736d75f9a | 16 | accepted  | R | 8/16 | 0.500 | y |
| 17:449f6f0a4e2e7984 | 17 | accepted  | R | 1/16 | 0.062 | - |
| 18:a670c5de2004910a | 18 | accepted  | R | 12/16 | 0.750 | y |
| 18:dd368f9a71343d3a | 18 | accepted  | G | 10/16 | 0.625 | y |
| 19:52b2ad350563aa5a | 19 | accepted  | G | 13/16 | 0.812 | - |
| 19:dc0ae181c7f957d8 | 19 | kept  | A | 10/16 | 0.625 | y |
| 21:a166ce1aef7f8444 | 21 | accepted  | G | 6/16 | 0.375 | y |
| 23:3f1585f0d2b86f3a | 23 | knob  | A | 10/16 | 0.625 | y |
| 24:cdcda546eeddfe8c | 24 | knob  | A | 5/16 | 0.312 | y |
| 25:6f0b9dbcd788564a | 25 | accepted  | G | 3/16 | 0.188 | - |
| 26:a1ef279b09f61ddf | 26 | accepted  | G | 7/16 | 0.438 | y |
| 26:dc0ae181c7f957d8 | 26 | kept  | A | 10/16 | 0.625 | y |
| 27:cf3a8bf8ea8a0e40 | 27 | accepted  | G | 15/16 | 0.938 | - |
| 28:f2d046a86e624384 | 28 | accepted  | G | 11/16 | 0.688 | y |

## Spend (USD by run and budget)

| run | budgets | total |
|---|---|---|
| e3-A | designer 0.03, search 33.24 | 33.27 |
| e3-G | designer 0.47, search 27.17 | 27.63 |
| e3-H100 | eval 5.23 | 5.23 |
| e3-R | designer 0.35, search 17.43 | 17.78 |
| e3-confirm | eval 16.50 | 16.50 |
| e3-probe | none 0.00 | 0.00 |
| e3-shared | eval 8.68 | 8.68 |

E3 total USD 109.08 (hard cap 330).

## Incidents (UTC timestamps in experiments/alfworld_e3/LOG.md)

- Guard incidents (usage.cost mismatch): 0. Ledgered retries: 429 2056, other 10.
- Errored rollouts (refunded, not charged): A 0, G 0, R 15. A tasks ending infra_error at the last attempt: none.
