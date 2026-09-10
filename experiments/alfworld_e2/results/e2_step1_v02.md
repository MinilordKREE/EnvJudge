# E2 step 1 under aea v0.2 (Phase D) — next to the v0.1 numbers

Same 10 tasks, same policy (Qwen3-8B, alibaba pin), same cap 30; the shared original-environment K=16 of the v0.1 run is reused.
v0.2 Z runs the box of docs/spec/AEA_v0.2.md (one 4 → 8 rule on the stage side, end + midpoint states, oracle guard).

## Z1 — learnable environments per 1,000 charged search rollouts

| arm | accepted envs | learnable | search rollouts | per 1,000 [95% CI] |
|---|---|---|---|---|
| Z (v0.2) | 2 | 2 | 224 | 8.9 [0.0, 22.9] |
| Z (v0.1) | 5 | 3 | 248 | 12.1 [0.0, 27.3] |
| G (v0.1) | 2 | 2 | 240 | 8.3 [0.0, 21.1] |
| R (v0.1) | 3 | 1 | 225 | 4.4 [0.0, 16.7] |

## Z2 — unlocked zero tasks

| arm | unlocked | tasks |
|---|---|---|
| Z (v0.2) | 2 | 9, 27 |
| Z (v0.1) | 3 | 8, 9, 27 |
| G (v0.1) | 2 | 9, 27 |
| R (v0.1) | 1 | 27 |

**v0.2: Z1 Z > G holds, Z > R holds; Z2 fails; kill rule not triggered.**

## Z3 — v0.2 per-task profile

| task | shared p16 | estimate (regime, p_hat, n) | guarded / rejected states | probes (t: s/n verdict) | outcome | reason | n_search |
|---|---|---|---|---|---|---|---|
| 0 | 0.188 | zero, 0.062, 16 | 4 / 0 | 50: 0/4 too_hard; 50: 4/4 too_easy; 50: 0/4 too_hard | dropped | budget | 28 |
| 8 | 0.000 | zero, 0.000, 10 | 6 / 0 | 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 |
| 9 | 0.000 | zero, 0.000, 10 | 5 / 0 | 50: 3/8 in_band | accepted | - | 18 |
| 10 | 0.000 | zero, 0.000, 10 | 1 / 5 | 25: 0/4 too_hard | dropped | dead | 14 |
| 11 | 0.000 | zero, 0.062, 16 | 0 / 6 | - | dropped | uncertified | 16 |
| 14 | 0.000 | zero, 0.000, 10 | 6 / 0 | 50: 0/4 too_hard; 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 |
| 17 | 0.000 | zero, 0.000, 10 | 5 / 1 | 50: 0/4 too_hard; 50: 1/8 too_hard; 25: 0/4 too_hard; 25: 0/4 too_hard | dropped | budget | 30 |
| 18 | 0.125 | zero, 0.000, 10 | 1 / 4 | 25: 0/4 too_hard | dropped | dead | 14 |
| 20 | 0.000 | zero, 0.000, 10 | 4 / 2 | 50: 0/4 too_hard; 50: 0/4 too_hard; 25: 4/4 too_easy; 25: 0/4 too_hard | dropped | too_easy | 26 |
| 27 | 0.000 | zero, 0.000, 10 | 3 / 0 | 50: 5/8 in_band | accepted | - | 18 |

### Accepted environments and their p16 (v0.2)

| task | env | t | p16 | learnable |
|---|---|---|---|---|
| 9 | 9:1dfb72010036fa22 | 50 | 0.625 | y |
| 27 | 27:5b87a603b0231541 | 50 | 0.500 | y |

Spend (v0.2 Z run, search + confirm): USD 18.45 (Phase-D cap 30.0).
