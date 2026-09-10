# E2 step 1 — zero side on Qwen3-8B (PREREG8-Z)

## Shared original-environment K=16 (defines zero for this run)

| task | p16 (shared) | class |
|---|---|---|
| 0 | 0.188 | marginal-low |
| 8 | 0.000 | zero |
| 9 | 0.000 | zero |
| 10 | 0.000 | zero |
| 11 | 0.000 | zero |
| 14 | 0.000 | zero |
| 17 | 0.000 | zero |
| 18 | 0.125 | marginal-low |
| 20 | 0.000 | zero |
| 27 | 0.000 | zero |

Zero tasks this run: ['8', '9', '10', '11', '14', '17', '20', '27'] (8).

## Z1 — learnable environments per 1,000 charged search rollouts

| arm | accepted envs | learnable | search rollouts | per 1,000 [95% CI, task bootstrap] |
|---|---|---|---|---|
| Z | 5 | 3 | 248 | 12.1 [0.0, 27.3] |
| G | 2 | 2 | 240 | 8.3 [0.0, 21.3] |
| R | 3 | 1 | 225 | 4.4 [0.0, 16.7] |

**Z1: Z > G holds; Z > R holds (point estimates).**

## Z2 — unlocked zero tasks

| arm | unlocked | tasks |
|---|---|---|
| Z | 3 | 8, 9, 27 |
| G | 2 | 9, 27 |
| R | 1 | 27 |
| Zfull (reference) | 0 | - |

**Z2: Z unlocks 3 (>= 3: yes); Z >= G: yes → holds.**

**Kill rule (Z unlocks <= 1 or fewer than G): not triggered.**

## Z3 — Z per-task learnability profile

| task | shared p16 | estimate (regime, p_hat, n) | certified / rejected states | probes (t: s/n cls) | skipped by cap | status | profile |
|---|---|---|---|---|---|---|---|
| 0 | 0.188 | zero, 0.062, 16 | 6 / 0 | 50: 0/4 dead; 50: 4/4 too_easy_stage; 50: 0/4 dead | 3 | unresolved_budget_limited | unresolved (budget) |
| 8 | 0.000 | zero, 0.000, 10 | 6 / 0 | 50: 0/4 dead; 50: 2/4 learnable | 1 | accepted_stage | late-learnable |
| 9 | 0.000 | zero, 0.000, 10 | 6 / 0 | 50: 2/4 learnable | 1 | accepted_stage | late-learnable |
| 10 | 0.000 | zero, 0.000, 10 | 1 / 5 | 50: 0/4 dead | 0 | unresolved | dead |
| 11 | 0.000 | zero, 0.000, 10 | 0 / 6 | - | 0 | unresolved | unresolved |
| 14 | 0.000 | zero, 0.000, 10 | 6 / 0 | 50: 0/4 dead; 50: 0/4 dead; 50: 0/4 dead; 38: 0/4 dead; 25: 0/4 dead | 1 | unresolved_budget_limited | unresolved (budget) |
| 17 | 0.000 | zero, 0.000, 10 | 6 / 0 | 50: 0/4 dead; 50: 0/4 dead; 50: 0/4 dead; 38: 0/4 dead; 25: 0/4 dead | 1 | unresolved_budget_limited | unresolved (budget) |
| 18 | 0.125 | zero, 0.000, 10 | 4 / 2 | 50: 0/4 dead; 38: 0/4 dead; 25: 0/4 dead; 12: 1/4 learnable | 0 | accepted_stage | late-learnable |
| 20 | 0.000 | zero, 0.000, 10 | 5 / 1 | 50: 1/4 learnable | 0 | accepted_stage | late-learnable |
| 27 | 0.000 | zero, 0.000, 10 | 4 / 0 | 50: 2/4 learnable | 0 | accepted_stage | late-learnable |

Z-full (reference, uncharged): probe walk continued over the skipped candidates.

| task | probed | profile (t: s/n cls) | status | accepted t | confirmed p16 |
|---|---|---|---|---|---|
| 0 | 0 | - | no_candidate | - | - |
| 8 | 1 | 12: 0/4 dead | unresolved | - | - |
| 9 | 0 | - | no_candidate | - | - |
| 14 | 1 | 12: 0/4 dead | unresolved | - | - |
| 17 | 1 | 12: 0/4 dead | unresolved | - | - |

### Accepted environments and their p16

| arm | task | env | kind / t | p16 | learnable |
|---|---|---|---|---|---|
| Z | 8 | 8:dbb86058d7a21b34 | stage 50 | 0.438 | y |
| Z | 9 | 9:e4bbeceed777586e | stage 50 | 0.688 | y |
| Z | 18 | 18:8684abc8ff5471d3 | stage 12 | 0.062 | - |
| Z | 20 | 20:cf0e7fd92373aff0 | stage 50 | 0.188 | - |
| Z | 27 | 27:792b4af6d1661d9e | stage 50 | 0.562 | y |
| G | 9 | 9:acc0:d77fef012b0f27ed | accepted  | 0.500 | y |
| G | 27 | 27:acc0:9b450f767a43fa6d | accepted  | 0.625 | y |
| R | 18 | 18:acc0:685e7333309a4eb0 | accepted  | 0.125 | - |
| R | 20 | 20:acc0:9112afb5a4d09586 | accepted  | 0.000 | - |
| R | 27 | 27:acc0:61422989dec3c073 | accepted  | 0.562 | y |

## Z per-task budget breakdown (charged search rollouts by phase; certificates = expert sessions, 0 policy rollouts)

| task | estimate | probes | dose (drift) | hint | n_search | certificate sessions (states certified + rejected) |
|---|---|---|---|---|---|---|
| 0 | 32 | 12 | 0 | 0 | 28 | 6 |
| 8 | 10 | 8 | 0 | 0 | 18 | 6 |
| 9 | 30 | 4 | 0 | 0 | 14 | 6 |
| 10 | 30 | 4 | 0 | 0 | 14 | 6 |
| 11 | 10 | 0 | 0 | 0 | 10 | 6 |
| 14 | 14 | 20 | 0 | 0 | 30 | 6 |
| 17 | 14 | 20 | 0 | 0 | 30 | 6 |
| 18 | 14 | 16 | 0 | 0 | 26 | 6 |
| 20 | 14 | 4 | 0 | 0 | 14 | 6 |
| 27 | 14 | 4 | 0 | 0 | 14 | 4 |

## G and R per task (released orchestrator; Qwen policy, DeepSeek designer)

| arm | task | baseline rollouts | candidates tried | accepted | decision | accepted-env p16 |
|---|---|---|---|---|---|---|
| G | 0 | 5 | 5 | 0 | all_rejected | - |
| G | 8 | 5 | 5 | 0 | all_rejected | - |
| G | 9 | 5 | 2 | 1 | accepted | 0.500 |
| G | 10 | 5 | 3 | 1 | accepted | - |
| G | 11 | 5 | 0 | 0 | skipped | - |
| G | 14 | 5 | 5 | 0 | all_rejected | - |
| G | 17 | 5 | 5 | 0 | all_rejected | - |
| G | 18 | 5 | 3 | 1 | accepted | - |
| G | 20 | 5 | 5 | 0 | all_rejected | - |
| G | 27 | 5 | 5 | 1 | accepted | 0.625 |
| R | 0 | 5 | 5 | 0 | all_rejected | - |
| R | 8 | 5 | 5 | 0 | all_rejected | - |
| R | 9 | 5 | 0 | 0 | skipped | - |
| R | 10 | 5 | 5 | 0 | all_rejected | - |
| R | 11 | 5 | 5 | 0 | all_rejected | - |
| R | 14 | 5 | 5 | 0 | all_rejected | - |
| R | 17 | 5 | 5 | 0 | all_rejected | - |
| R | 18 | 5 | 3 | 1 | accepted | 0.125 |
| R | 20 | 5 | 5 | 1 | accepted | 0.000 |
| R | 27 | 5 | 1 | 1 | accepted | 0.562 |

## Spend (USD by run and budget)

| run | budgets |
|---|---|
| e2-G | confirm 1.75, designer 0.17, search 18.15 |
| e2-R | confirm 3.56, designer 0.16, search 15.56 |
| e2-Z | confirm 4.62, search 19.40 |
| e2-Zfull | search 0.76 |
| e2-probe | none 0.00 |
| e2-shared | confirm 12.71 |

E2 step-1 total USD 76.84 (cap 130; PREREG8-Z said 90, raised by the owner on 2026-09-09).

## Incidents and deviations (UTC timestamps in experiments/alfworld_e2/LOG.md)

- Per-episode cost ~USD 0.09 (zero tasks run to the 50-step cap), ~4x the PREREG8-Z projection; the run order was changed so the claim-bearing stages (Z, G, R, confirmations) ran before the Z-full reference; the owner raised the step-1 cap from USD 90 to 130.
- Z crashed once in in-process staging (TextWorld grammar parser under task concurrency 2) and was resumed at concurrency 1; seven Z tasks then failed on an upstream 429 throttle of the Alibaba Qwen endpoint and were re-run after a ledgered endpoint probe cleared; one machine reboot interrupted the re-run (resumed). Re-run tasks 0, 9, 10 carry their pre-crash estimate rollouts in the traces, so their estimate counts exceed 16 and Z1's denominator includes them (conservative for Z).
- G's candidates marked accepted on tasks 10 and 18 are empty (no rules, no setup actions) and are not transformed environments; they are excluded from Z1/Z2.
- Z-full could not rebuild the skipped states of tasks 0 and 9 (the failure sample changed once the re-run's estimate rollouts joined the pool); the skipped state of tasks 8, 14, 17 (t = 12) was probed and is dead.
- Guard incidents: 0.
