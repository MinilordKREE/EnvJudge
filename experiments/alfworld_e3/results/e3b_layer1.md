# E3b — aea v0.3 on the E3 task set (PREREG10), beside the E3 rows

Arm A_v0.3 = docs/spec/AEA_v0.3.md (population-seeded bracket, stage-side 4/4 top-up, quarter-point candidates) on seeds 0-29, Qwen3-8B policy (alibaba pin, reasoning off), DeepSeek V4 Pro proposer, cap 30. Reused from E3 and never re-run: the shared K16, arms G and R, the H100 control, and every confirmation E3 already made (kept tasks reuse the shared K16). A_v0.2 = the E3 arm A. PREREG10 @ 6d48728; tables from scripts/make_tables_e3b.py.

Task classes (shared K16): zero 8 (8, 9, 10, 11, 14, 17, 20, 27); band 6 (4, 5, 6, 16, 19, 26); saturated 14.

## C1 primary — learner-facing learnable environments per 1,000 charged search rollouts

| arm | learner-facing envs | learnable | charged rollouts | per 1,000 [95% CI, task bootstrap] |
|---|---|---|---|---|
| A_v0.3 | 6 | 6 | 738 | 8.1 [2.5, 15.8] |
| A_v0.2 | 9 | 9 | 730 | 12.3 [5.2, 21.3] |
| G | 14 | 10 | 655 | 15.3 [7.1, 25.9] |
| R | 4 | 3 | 330 | 9.1 [0.0, 20.6] |

## C1 secondary — transformed-only

| arm | transformed envs | learnable | charged rollouts | per 1,000 [95% CI] |
|---|---|---|---|---|
| A_v0.3 | 1 | 1 | 738 | 1.4 [0.0, 4.4] |
| A_v0.2 | 3 | 3 | 730 | 4.1 [0.0, 9.0] |
| G | 14 | 10 | 655 | 15.3 [7.1, 26.1] |
| R | 4 | 3 | 330 | 9.1 [0.0, 20.8] |

## Band preservation (6 originally learnable tasks)

| arm | preserved | tasks |
|---|---|---|
| A_v0.3 | 5 / 6 | 4, 5, 6, 16, 26 |
| A_v0.2 | 6 / 6 | 4, 5, 6, 16, 19, 26 |
| G | 5 / 6 | 4, 5, 6, 16, 26 |
| R | 2 / 6 | 6, 16 |

## Unlocked zero tasks (zero: 8, 9, 10, 11, 14, 17, 20, 27) and precision

| arm | unlocked | tasks | precision (learnable / accepted transformed) |
|---|---|---|---|
| A_v0.3 | 1 | 9 | 1 / 1 (100%) |
| A_v0.2 | 0 | - | 3 / 3 (100%) |
| G | 1 | 8 | 10 / 14 (71%) |
| R | 0 | - | 3 / 4 (75%) |

## Saturated subset (14 tasks) — learnable transformed environments per 1,000

| arm | transformed envs | learnable | charged rollouts on the subset | per 1,000 [95% CI] |
|---|---|---|---|---|
| A_v0.3 | 0 | 0 | 416 | 0.0 [0.0, 0.0] |
| A_v0.2 | 3 | 3 | 404 | 7.4 [0.0, 15.9] |
| G | 5 | 3 | 350 | 8.6 [0.0, 20.3] |
| R | 0 | 0 | 70 | 0.0 [0.0, 0.0] |

## H100 control (reused) next to the staged p16 of both A versions

| task | H100 s/n | H100 p | A_v0.3 staged p16 (t) | A_v0.2 staged p16 (t) | attribution (v0.3) |
|---|---|---|---|---|---|
| 8 | 0/8 | 0.000 | - (-) | - (-) | - |
| 9 | 0/8 | 0.000 | 0.688 (50) | - (-) | staging (H100 < staged) |
| 27 | 8/8 | 1.000 | - (-) | - (-) | - |

## PREREG10 claims

- E3b-1: A_v0.3 8.1 vs G 15.3 and R 9.1 per 1,000 (A_v0.2 12.3) → A_v0.3 > G fails, A_v0.3 > R fails → **fails**.
- E3b-3: saturated subset A_v0.3 0.0 vs G 8.6 per 1,000 (A_v0.2 7.4) → **fails**.
- Unlocked zero tasks: A_v0.3 1 (9), A_v0.2 0, G 1; H100 attribution: task 8: -; task 9: staging (H100 < staged); task 27: -.

## A per task — v0.3 beside v0.2

| task | class | v0.3 outcome | v0.3 reason | v0.3 n_search | v0.3 families (order) | v0.3 brackets (family: seed → status, doses) | v0.3 stage (certified/rejected; probes t: s/n verdict) | v0.2 outcome | v0.2 reason | v0.2 n_search | learner-facing envs v0.3 (p16) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | marginal-low | dropped | budget | 28 | - | - | 5/0; 50: 1/8 too_hard; 50: 0/4 too_hard | dropped | budget | 30 | - |
| 1 | saturated | dropped | budget | 30 | goal_obfuscation, action_noise, footer_mask, horizon_squeeze | goal_obfuscation: mid → exhausted, 1.0:0/4/0.5:0/4/0.25:4/4/0.375:0/4/0.3125:0/4 | - | accepted | - | 30 | - |
| 2 | saturated | dropped | budget | 30 | command_scramble, reward_noise, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.5:0/4 | - | dropped | budget | 30 | - |
| 3 | saturated | dropped | budget | 28 | command_permute, reward_delay, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4 | - | dropped | budget | 30 | - |
| 4 | band | kept | - | 8 | - | - | - | kept | - | 8 | kept 0.500* |
| 5 | band | kept | - | 8 | - | - | - | kept | - | 8 | kept 0.750* |
| 6 | band | kept | - | 10 | - | - | - | kept | - | 12 | kept 0.438* |
| 7 | saturated | dropped | budget | 30 | command_typo, footer_mask, horizon_squeeze, reward_noise | command_typo: mid → exhausted, 1.0:0/4/0.5:0/4/0.25:4/4/0.375:4/4/0.4375:4/4 | - | dropped | budget | 30 | - |
| 8 | zero | dropped | budget | 30 | - | - | 6/0; 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 9 | zero | accepted | - | 26 | - | - | 6/0; 50: 6/8 too_easy; 50: 5/8 in_band | dropped | too_easy | 26 | stage 0.688* |
| 10 | zero | dropped | dead | 14 | - | - | 1/5; 25: 0/4 too_hard | dropped | dead | 22 | - |
| 11 | zero | dropped | uncertified | 10 | - | - | 0/6; - | dropped | uncertified | 10 | - |
| 12 | saturated | dropped | budget | 30 | action_dropout, action_typo, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.46875:4/4/0.484375:4/4 | - | dropped | budget | 30 | - |
| 13 | saturated | dropped | budget | 30 | command_alias_swap, footer_mask, horizon_squeeze | command_alias_swap: mid → budget, 1.0:0/4/0.5:0/4/0.25:0/4/0.125:4/4 | - | dropped | budget | 30 | - |
| 14 | zero | dropped | budget | 30 | - | - | 6/0; 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 15 | saturated | dropped | budget | 30 | action_delay, footer_mask, horizon_squeeze, command_permute | footer_mask: mid → budget, 1.0:0/4/0.492188:4/4/0.496094:4/4/0.498047:4/4 | - | dropped | budget | 30 | - |
| 16 | band | kept | - | 8 | - | - | - | kept | - | 12 | kept 0.500* |
| 17 | zero | dropped | budget | 30 | - | - | 6/0; 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 | - |
| 18 | marginal-low | dropped | too_easy | 30 | - | - | 3/3; 50: 8/8 too_easy; 25: 1/8 too_hard; 12: 0/4 too_hard | dropped | dead | 28 | - |
| 19 | band | dropped | budget | 28 | action_alias_permute, reward_noise_scale, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4 | - | kept | - | 16 | - |
| 20 | zero | dropped | dead | 26 | - | - | 4/2; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | too_easy | 30 | - |
| 21 | saturated | dropped | budget | 30 | reward_perturb, footer_mask, horizon_squeeze, command_permute | footer_mask: mid → budget, 1.0:0/4/0.25:4/4/0.375:4/4/0.4375:4/4 | - | dropped | budget | 28 | - |
| 22 | saturated | dropped | budget | 30 | command_obfuscation, footer_mask, horizon_squeeze, reward_noise | footer_mask: mid → budget, 1.0:0/4/0.499024:4/4/0.499512:4/4 | - | dropped | budget | 30 | - |
| 23 | saturated | dropped | budget | 30 | command_alias_obfuscation, footer_mask, horizon_squeeze, reward_noise | footer_mask: mid → budget, 1.0:0/4/0.499756:4/4/0.499878:4/4/0.499939:4/4 | - | accepted | - | 28 | - |
| 24 | saturated | dropped | budget | 30 | command_alias_shift, success_label_noise, footer_mask, horizon_squeeze | footer_mask: mid → budget, 1.0:0/4/0.49997:4/4/0.499985:4/4 | - | accepted | - | 18 | - |
| 25 | saturated | dropped | budget | 30 | action_alias_shift, observation_noise_typos, footer_mask, horizon_squeeze | observation_noise_typos: mid → budget, 1.0:1/8/0.5:4/4/0.75:0/4 | - | dropped | budget | 30 | - |
| 26 | band | kept | - | 6 | - | - | - | kept | - | 8 | kept 0.625* |
| 27 | zero | dropped | budget | 30 | - | - | 3/0; 50: 6/8 too_easy; 25: 2/8 too_hard | dropped | too_easy | 26 | - |
| 28 | saturated | dropped | budget | 28 | footer_shuffle, reward_noise, footer_mask, horizon_squeeze | footer_shuffle: mid → budget, 1.0:0/4/0.5:0/4 | - | dropped | budget | 30 | - |
| 29 | saturated | dropped | budget | 30 | observation_noise, footer_mask, horizon_squeeze, action_dropout | footer_mask: mid → budget, 1.0:0/4/0.499993:4/4/0.499997:4/4/0.499999:4/4 | - | dropped | budget | 30 | - |

A_v0.3 outcomes: accepted 1, dropped:budget 20, dropped:dead 2, dropped:too_easy 1, dropped:uncertified 1, kept 5.
A_v0.2 outcomes: accepted 3, dropped:budget 15, dropped:dead 2, dropped:too_easy 3, dropped:uncertified 1, kept 6.

### Family of origin — A_v0.3's accepted environments

| task | kind | family | source | axis | dose | t | p8 | confirmed p16 | learnable |
|---|---|---|---|---|---|---|---|---|---|
| 9 | stage | - | - | - | - | 50 | 0.625 | 0.688 | y |

Origin counts v0.3: stage:-:- 1.
Origin counts v0.2: knob:proposer:command_noise_swap 1, knob:proposer:command_swap 1, knob:proposer:observation_noise 1.

### A_v0.3 per-task budget (charged search rollouts by phase)

| task | estimate | dose (harden) | probe (stage) | n_search | v0.2 n_search |
|---|---|---|---|---|---|
| 0 | 16 | 0 | 12 | 28 | 30 |
| 1 | 10 | 20 | 0 | 30 | 30 |
| 2 | 10 | 20 | 0 | 30 | 30 |
| 3 | 16 | 12 | 0 | 28 | 30 |
| 4 | 8 | 0 | 0 | 8 | 8 |
| 5 | 8 | 0 | 0 | 8 | 8 |
| 6 | 10 | 0 | 0 | 10 | 12 |
| 7 | 10 | 20 | 0 | 30 | 30 |
| 8 | 10 | 0 | 20 | 30 | 30 |
| 9 | 10 | 0 | 16 | 26 | 26 |
| 10 | 10 | 0 | 4 | 14 | 22 |
| 11 | 10 | 0 | 0 | 10 | 10 |
| 12 | 10 | 20 | 0 | 30 | 30 |
| 13 | 10 | 20 | 0 | 30 | 30 |
| 14 | 10 | 0 | 20 | 30 | 30 |
| 15 | 10 | 20 | 0 | 30 | 30 |
| 16 | 8 | 0 | 0 | 8 | 12 |
| 17 | 10 | 0 | 20 | 30 | 30 |
| 18 | 10 | 0 | 20 | 30 | 28 |
| 19 | 16 | 12 | 0 | 28 | 16 |
| 20 | 10 | 0 | 16 | 26 | 30 |
| 21 | 10 | 20 | 0 | 30 | 28 |
| 22 | 10 | 20 | 0 | 30 | 30 |
| 23 | 10 | 20 | 0 | 30 | 28 |
| 24 | 10 | 20 | 0 | 30 | 18 |
| 25 | 10 | 20 | 0 | 30 | 30 |
| 26 | 6 | 0 | 0 | 6 | 8 |
| 27 | 10 | 0 | 20 | 30 | 26 |
| 28 | 16 | 12 | 0 | 28 | 30 |
| 29 | 10 | 20 | 0 | 30 | 30 |

## Learner-facing environments of A_v0.3 and their K=16

| env | task | kind / t | s/n | p16 | learnable | source |
|---|---|---|---|---|---|---|
| 4:dc0ae181c7f957d8 | 4 | kept  | 8/16 | 0.500 | y | e3-confirm |
| 5:dc0ae181c7f957d8 | 5 | kept  | 12/16 | 0.750 | y | e3-confirm |
| 6:dc0ae181c7f957d8 | 6 | kept  | 7/16 | 0.438 | y | e3-confirm |
| 9:7aa3298cde8679a5 | 9 | stage 50 | 11/16 | 0.688 | y | new |
| 16:dc0ae181c7f957d8 | 16 | kept  | 8/16 | 0.500 | y | e3-confirm |
| 26:dc0ae181c7f957d8 | 26 | kept  | 10/16 | 0.625 | y | e3-confirm |

## Per-task diff v0.2 → v0.3 (outcome and reason; saturated tasks: family, seeded bracket, doses visited, accepted dose)

| task | class | v0.2 outcome:reason | v0.3 outcome:reason | changed | v0.3 family | v0.3 seed [lo_pop, hi_pop] | v0.3 doses (d: s/n) | v0.3 accepted d | v0.2 family / doses |
|---|---|---|---|---|---|---|---|---|---|
| 0 | marginal-low | dropped:budget | dropped:budget | - | - | - | - | - | - |
| 1 | saturated | accepted | dropped:budget | yes | goal_obfuscation | [0.0, 1.0] | 1.0:0/4/0.5:0/4/0.25:4/4/0.375:0/4/0.3125:0/4 | - | observation_noise: 1.0:0/4/0.5:6/8/0.75:3/8 |
| 2 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.0, 1.0] | 1.0:0/4/0.5:0/4 | - | observation_noise_insertion: 1.0:0/4/0.5:4/4/0.75:2/8 |
| 3 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.0, 1.0] | 1.0:0/4 | - | footer_mask: 1.0:0/4/0.5:4/4/0.75:4/4/0.875:4/4 |
| 4 | band | kept | kept | - | - | - | - | - | - |
| 5 | band | kept | kept | - | - | - | - | - | - |
| 6 | band | kept | kept | - | - | - | - | - | - |
| 7 | saturated | dropped:budget | dropped:budget | - | command_typo | [0.0, 1.0] | 1.0:0/4/0.5:0/4/0.25:4/4/0.375:4/4/0.4375:4/4 | - | footer_mask: 1.0:0/4/0.5:4/4/0.75:4/4 |
| 8 | zero | dropped:budget | dropped:budget | - | - | - | - | - | - |
| 9 | zero | dropped:too_easy | accepted | yes | - | - | - | - | - |
| 10 | zero | dropped:dead | dropped:dead | - | - | - | - | - | - |
| 11 | zero | dropped:uncertified | dropped:uncertified | - | - | - | - | - | - |
| 12 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.4375, 0.5] | 1.0:0/4/0.46875:4/4/0.484375:4/4 | - | footer_mask: 1.0:0/4/0.5:4/4/0.75:4/4/0.875:4/4 |
| 13 | saturated | dropped:budget | dropped:budget | - | command_alias_swap | [0.0, 1.0] | 1.0:0/4/0.5:0/4/0.25:0/4/0.125:4/4 | - | footer_mask: 1.0:0/4/0.5:6/8/0.75:7/8 |
| 14 | zero | dropped:budget | dropped:budget | - | - | - | - | - | - |
| 15 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.484375, 0.5] | 1.0:0/4/0.492188:4/4/0.496094:4/4/0.498047:4/4 | - | footer_mask: 1.0:0/4/0.5:2/8/0.25:7/8 |
| 16 | band | kept | kept | - | - | - | - | - | - |
| 17 | zero | dropped:budget | dropped:budget | - | - | - | - | - | - |
| 18 | marginal-low | dropped:dead | dropped:too_easy | yes | - | - | - | - | - |
| 19 | band | kept | dropped:budget | yes | footer_mask | [0.0, 1.0] | 1.0:0/4 | - | - |
| 20 | zero | dropped:too_easy | dropped:dead | yes | - | - | - | - | - |
| 21 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.0, 0.5] | 1.0:0/4/0.25:4/4/0.375:4/4/0.4375:4/4 | - | observation_noise: 1.0:1/8 |
| 22 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.498047, 0.5] | 1.0:0/4/0.499024:4/4/0.499512:4/4 | - | footer_mask: 1.0:0/4/0.5:4/4/0.75:4/4 |
| 23 | saturated | accepted | dropped:budget | yes | footer_mask | [0.499512, 0.5] | 1.0:0/4/0.499756:4/4/0.499878:4/4/0.499939:4/4 | - | command_swap: 1.0:0/4/0.5:5/8 |
| 24 | saturated | accepted | dropped:budget | yes | footer_mask | [0.499939, 0.5] | 1.0:0/4/0.49997:4/4/0.499985:4/4 | - | - |
| 25 | saturated | dropped:budget | dropped:budget | - | observation_noise_typos | [0.0, 1.0] | 1.0:1/8/0.5:4/4/0.75:0/4 | - | footer_mask: 1.0:0/4/0.5:7/8 |
| 26 | band | kept | kept | - | - | - | - | - | - |
| 27 | zero | dropped:too_easy | dropped:budget | yes | - | - | - | - | - |
| 28 | saturated | dropped:budget | dropped:budget | - | footer_shuffle | [0.0, 1.0] | 1.0:0/4/0.5:0/4 | - | observation_noise: 1.0:0/4/0.5:0/4/0.25:0/4/0.125:6/8 |
| 29 | saturated | dropped:budget | dropped:budget | - | footer_mask | [0.499985, 0.5] | 1.0:0/4/0.499993:4/4/0.499997:4/4/0.499999:4/4 | - | footer_mask: 1.0:0/4/0.5:4/4/0.75:4/4/0.875:4/4 |

## Attribution of the three rule changes (counted from runs/e3b-A/events.jsonl)

- (1) Population-seeded bracket: 7 tasks bracketed from a seed other than [0, 1] (12, 15, 21, 22, 23, 24, 29); 0 accepted through a seeded bracket (-); outcome changed from v0.2 because of it on 0 (-).
- (2) Stage-side 4/4 top-up: 1 staged candidates had a 4/4 first batch and were topped up, on 1 tasks (18); verdicts after the top-up: too_easy 1; accepted through a topped-up 4/4 candidate: 0 (-); outcome changed from v0.2 because of it on 0 (-).
- (3) Quarter-point candidates: a quarter state was certified on 3 tasks (0, 18, 27); accepted at a quarter state: 0 (-); outcome changed from v0.2 because of it on 0 (-).
- Tasks whose outcome:reason differs from v0.2: 8 (1, 9, 18, 19, 20, 23, 24, 27); explained by a rule change above: 0; lost relative to v0.2 (accepted or kept in v0.2, not in v0.3): 4 (1, 19, 23, 24); other (estimate regime, proposer families, sampling): 4 (9, 18, 20, 27).

## Charged search rollouts per task (the per-1,000 denominators)

| task | A_v0.3 | A_v0.2 | G | R |
|---|---|---|---|---|
| 0 | 28 | 30 | 30 | 25 |
| 1 | 30 | 30 | 15 | 5 |
| 2 | 30 | 30 | 30 | 5 |
| 3 | 28 | 30 | 30 | 5 |
| 4 | 8 | 8 | 25 | 5 |
| 5 | 8 | 8 | 15 | 5 |
| 6 | 10 | 12 | 15 | 15 |
| 7 | 30 | 30 | 30 | 5 |
| 8 | 30 | 30 | 20 | 25 |
| 9 | 26 | 26 | 25 | 15 |
| 10 | 14 | 22 | 30 | 30 |
| 11 | 10 | 10 | 30 | 30 |
| 12 | 30 | 30 | 25 | 5 |
| 13 | 30 | 30 | 30 | 5 |
| 14 | 30 | 30 | 5 | 30 |
| 15 | 30 | 30 | 30 | 5 |
| 16 | 8 | 12 | 10 | 10 |
| 17 | 30 | 30 | 30 | 10 |
| 18 | 30 | 28 | 10 | 15 |
| 19 | 28 | 16 | 10 | 5 |
| 20 | 26 | 30 | 30 | 30 |
| 21 | 30 | 28 | 15 | 5 |
| 22 | 30 | 30 | 30 | 5 |
| 23 | 30 | 28 | 30 | 5 |
| 24 | 30 | 18 | 30 | 5 |
| 25 | 30 | 30 | 15 | 5 |
| 26 | 6 | 8 | 10 | 5 |
| 27 | 30 | 26 | 10 | 5 |
| 28 | 28 | 30 | 10 | 5 |
| 29 | 30 | 30 | 30 | 5 |
| **total** | **738** | **730** | **655** | **330** |

## Learner-facing set of A_v0.3 (the deferred SL stage's input)

| task | kind | family | source | dose | t | p8 | p16 | learnable |
|---|---|---|---|---|---|---|---|---|
| 4 | kept | - | - | - | - | 0.625 | 0.500 | y |
| 5 | kept | - | - | - | - | 0.500 | 0.750 | y |
| 6 | kept | - | - | - | - | 0.400 | 0.438 | y |
| 9 | stage | - | - | - | 50 | 0.625 | 0.688 | y |
| 16 | kept | - | - | - | - | 0.375 | 0.500 | y |
| 26 | kept | - | - | - | - | 0.500 | 0.625 | y |

## Spend (USD by run and budget; E3b runs only)

| run | budgets | total |
|---|---|---|
| e3b-A | designer 0.03, search 32.19 | 32.22 |
| e3b-confirm | eval 0.24 | 0.24 |

E3b total USD 32.46 (cap 60).

## Incidents (UTC timestamps in experiments/alfworld_e3/LOG.md)

- Guard incidents 0; ledgered retries 429 827, other 1; errored rollouts 0 (A_v0.3); A tasks ending infra_error: none.
