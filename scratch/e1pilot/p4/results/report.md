# P4 report — behavioral novelty vs interface difficulty — generated 2026-09-06 23:55 UTC

PREREG4 sha `319e5a6`; inputs E1-pilot @ 103b285; policy openai/qwen/qwen3-8b via OpenRouter (provider Alibaba, reasoning off, 0.117/0.455 USD/M); extractor DeepSeek V4 Pro; P4 spend USD 1.94 of 70 ({'p4_build': 1.94}); pilot total USD 36.31 (hard 115 / soft 100).

## P4.1 I-sat confirmation and K2b correction

| task | env | p̂_8 (P2b) | p̂_8 (new) | p̂_16 | confirmed | ω | primary |
|---|---|---|---|---|---|---|---|
| 7 | F_H:13 | 0.625 | 0.625 | 0.625 | True | 0.625 | True |
| 12 | F_O:0.875 | 0.625 | 0.625 | 0.625 | True | 1.0 | True |
| 13 | F_O:0.875 | 0.375 | 0.25 | 0.3125 | True | 1.0 | True |
| 15 | F_O:0.75 | 0.5 | 0.25 | 0.375 | True | 1.0 | True |
| 19 | F_O:0.75 | 0.375 | 0.625 | 0.5 | True | 1.0 | False |
| 21 | F_O:0.875 | 0.625 | 0.75 | 0.6875 | True | 1.0 | True |
| 22 | F_O:0.75 | 0.5 | 0.75 | 0.625 | True | 1.0 | True |
| 23 | F_O:0.75 | 0.625 | 0.375 | 0.5 | True | 1.0 | False |
| 29 | F_O:0.9688 | 0.625 | 0.875 | 0.75 | True | 1.0 | True |

Confirmed at K = 16: 9/9 envs = 1.000 [1.000, 1.000] (n=9, tasks=9); primary confirmed 7/7. **K2b correction: share of the 9 in-band envs confirmed ≥ 0.60 — K2b stands**

## P4.2 N-zero (CHS) environments

| task | candidates | visited (t: successes/4) | status | selected t | p̂_12 | staged len |
|---|---|---|---|---|---|---|
| 8 | 4 | [[46, 1]] | selected | 46 | 0.0833 | 38 |
| 9 | 4 | [[48, 0]] | dead_all_0of4 |  |  |  |
| 10 | 4 | [[45, 0]] | dead_all_0of4 |  |  |  |
| 11 | 3 | [[1, 0]] | dead_all_0of4 |  |  |  |
| 14 | 4 | [[46, 0]] | dead_all_0of4 |  |  |  |
| 17 | 4 | [[46, 0]] | dead_all_0of4 |  |  |  |
| 20 | 4 | [[45, 0]] | dead_all_0of4 |  |  |  |
| 27 | 4 | [[43, 0]] | dead_all_0of4 |  |  |  |

## P4.3 N-sat environments

| task | family | dose | ω | certified by | p̂ (4→8) | class | p̂_16 | confirmed |
|---|---|---|---|---|---|---|---|---|
| 1 | F_H | 9 | 1.0 | R_pol | 1.0 | NOEFFECT |  |  |
| 1 | F_H | 7 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 1 | F_H | 8 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 1 | Chain | 2 | 0.0 | concatenated_expert | 1.0 | NOEFFECT |  |  |
| 1 | Chain | 3 | None | None |  | NOT_BUILT |  |  |
| 2 | F_H | 12 | 0.8125 | R_pol | 0.625 | IN-BAND |  |  |
| 7 | F_H | 7 | 0.625 | by_construction | 0.375 | IN-BAND |  |  |
| 7 | Chain | 2 | 0.0 | concatenated_expert | 1.0 | NOEFFECT |  |  |
| 7 | Chain | 3 | None | None |  | NOT_BUILT |  |  |
| 12 | F_H | 12 | 1.0 | by_construction | 1.0 | NOEFFECT |  |  |
| 12 | F_H | 10 | 0.125 | by_construction | 0.0 | ZERO |  |  |
| 12 | F_H | 11 | 0.125 | by_construction | 0.0 | ZERO |  |  |
| 12 | Chain | 2 | 0.0 | concatenated_expert | 1.0 | NOEFFECT |  |  |
| 12 | Chain | 3 | None | None |  | NOT_BUILT |  |  |
| 13 | F_H | 30 | 0.9375 | by_construction | 1.0 | NOEFFECT |  |  |
| 13 | F_H | 28 | 0.25 | by_construction | 0.0 | ZERO |  |  |
| 13 | F_H | 29 | 0.25 | by_construction | 0.25 | NEAR_LOW |  |  |
| 15 | F_H | 18 | 0.625 | by_construction | 0.5 | IN-BAND |  |  |
| 15 | Chain | 2 | 0.0 | concatenated_expert | 0.5 | IN-BAND | 0.75 | True |
| 21 | F_H | 10 | 0.625 | by_construction | 0.75 | NEAR_HIGH |  |  |
| 21 | F_H | 8 | 0.25 | by_construction | 0.0 | ZERO |  |  |
| 21 | F_H | 9 | 0.375 | by_construction | 0.5 | IN-BAND | 0.4375 | True |
| 21 | Chain | 2 | None | None |  | INFEASIBLE |  |  |
| 22 | F_H | 13 | 1.0 | R_pol | 1.0 | NOEFFECT |  |  |
| 22 | F_H | 11 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 22 | F_H | 12 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 24 | F_H | 9 | 1.0 | R_pol | 0.875 | NOEFFECT |  |  |
| 24 | F_H | 7 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 24 | F_H | 8 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 25 | F_H | 5 | 1.0 | R_pol | 1.0 | NOEFFECT |  |  |
| 25 | F_H | 3 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 25 | F_H | 4 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 29 | F_H | 8 | 1.0 | R_pol | 1.0 | NOEFFECT |  |  |
| 29 | F_H | 6 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 29 | F_H | 7 | 0.0 | uncertified_post_hoc | 0.0 | ZERO |  |  |
| 29 | Chain | 2 | 0.0 | concatenated_expert | 1.0 | NOEFFECT |  |  |
| 29 | Chain | 3 | None | None |  | NOT_BUILT |  |  |

Per-family leverage (tasks moved out of NOEFFECT / tasks reached): F_H: 6/11; Chain: 1/5. Rollouts: 176; uncertified (incl. post-hoc): 10; infeasible/not built: 5; confirmed: 2.

## P4.4 banks

{}


## K4 outcome: **not evaluable (neither novelty arm built)**

## Measurement notes

- Link audit: chain runs under the released runner via a two-env Link subclass (p4/docs/link_audit.md); Chain-3 not buildable with a two-env tree (reported, not substituted).
- Fidelity: Setup lists end with `look`; CHS prefixes reproduce the stored observation at the cut with and without no-op actions (3 trajectories).
- ω replays the policy's own P1 successes verbatim through the released stack; for O-axis envs ω = 1 as expected.
- Held-out evals reuse P3's nobank/orig/orig_m/ours runs; new arms run under the same protocol and seeds; paired differences with 10k task-level bootstrap.

## Caveats

- Single benchmark, N = 30 train tasks, 8 zero / 11 saturated tasks, Qwen3-8B via API, small banks (item-matched to the smaller side), one consumer protocol; no method proposals.
