# P4 report — behavioral novelty vs interface difficulty — generated 2026-09-07 06:51 UTC

PREREG4 sha `319e5a6`; inputs E1-pilot @ 103b285; policy openai/qwen/qwen3-8b via OpenRouter (provider Alibaba, reasoning off, 0.117/0.455 USD/M); extractor DeepSeek V4 Pro; P4 spend USD 17.45 of 70 ({'p4_build': 2.99, 'p4_induce': 0.06, 'p4_induce_embed': 0.0, 'p4_eval_embed': 0.0, 'p4_eval': 14.39}); pilot total USD 51.82 (hard 115 / soft 100).

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

Candidate rule: owner Option A at the P4.3 gate — certified states with t ≤ 30 (residual budget ≥ 20 underlying steps): latest, nearest t = 15, nearest t = 25; walk latest-first (1–3/4 selects, 4/4 → earlier, 0/4 → later within the set). The first probe (latest certified states, t ≈ 43–48) is a residual-budget artifact and is archived in nzero_envs_v1_budget_artifact.csv.

| task | candidates | visited (t: successes/4) | status | selected t | p̂_12 | staged len |
|---|---|---|---|---|---|---|
| 8 | 3 | [[30, 0]] | dead_all_0of4 |  |  |  |
| 9 | 3 | [[30, 4], [25, 3]] | selected | 25 | 0.8333 | 26 |
| 10 | 3 | [[30, 0]] | dead_all_0of4 |  |  |  |
| 11 | 2 | [[1, 0]] | dead_all_0of4 |  |  |  |
| 14 | 3 | [[30, 0]] | dead_all_0of4 |  |  |  |
| 17 | 3 | [[30, 0]] | dead_all_0of4 |  |  |  |
| 20 | 3 | [[30, 0]] | dead_all_0of4 |  |  |  |
| 27 | 3 | [[30, 0]] | dead_all_0of4 |  |  |  |

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

### Supplementary arm F_H-mid (owner decision at the P4.3 gate; ω ∈ (0.5, 1]; H4 only)

| task | dose m | ω | certified by | p̂_8 | p̂_16 | confirmed |
|---|---|---|---|---|---|---|
| 2 | 12 | 0.8125 | R_pol | 0.625 | 0.5 | True |
| 7 | 7 | 0.625 | by_construction | 0.375 | 0.375 | True |
| 15 | 18 | 0.625 | by_construction | 0.500 | 0.6875 | True |

N-zero (residual-budget rule t ≤ 30, owner Option A): 1/8 tasks selected → arm NOT_BUILT (< 3 selected; H2b and H3 not evaluable; P4.6 skipped).

## P4.4 banks

{
 "isat": {
  "built": true,
  "tasks": [
   "12",
   "13",
   "15",
   "19",
   "21",
   "22",
   "23",
   "29",
   "7"
  ],
  "items": 9,
  "item_types": {
   "paired_diff": 9
  },
  "items_matched": 9
 },
 "origc_isat": {
  "built": true,
  "tasks": [
   "12",
   "13",
   "15",
   "19",
   "21",
   "22",
   "23",
   "29",
   "7"
  ],
  "items": 23,
  "item_types": {
   "single_succ": 21,
   "paired_diff": 2
  },
  "items_matched": 9
 },
 "pair_isat": {
  "matched_items": 9
 },
 "nsat": {
  "built": true,
  "tasks": [
   "15",
   "21"
  ],
  "items": 4,
  "item_types": {
   "single_succ": 3,
   "paired_diff": 1
  },
  "items_matched": 4
 },
 "origc_nsat": {
  "built": true,
  "tasks": [
   "15",
   "21"
  ],
  "items": 6,
  "item_types": {
   "single_succ": 6
  },
  "items_matched": 4
 },
 "pair_nsat": {
  "matched_items": 4
 },
 "nzero": {
  "built": false,
  "reason": "only 1 selected N-zero envs (< 3, owner rule at the P4.3 gate)"
 },
 "fhmid": {
  "built": true,
  "tasks": [
   "15",
   "2",
   "7"
  ],
  "items": 3,
  "item_types": {
   "paired_diff": 3
  },
  "items_matched": 3
 },
 "origc_fhmid": {
  "built": true,
  "tasks": [
   "15",
   "2",
   "7"
  ],
  "items": 9,
  "item_types": {
   "single_succ": 9
  },
  "items_matched": 3
 },
 "pair_fhmid": {
  "matched_items": 3
 }
}

## P4.5 held-out evals (released protocol; 30 ID + 30 OOD; 3 same-task replicates)

| condition | ID | OOD |
|---|---|---|
| nobank | 0.444 [0.300, 0.589] (n=90, tasks=30) | 0.322 [0.178, 0.478] (n=90, tasks=30) |
| orig | 0.422 [0.256, 0.589] (n=90, tasks=30) | 0.433 [0.267, 0.600] (n=90, tasks=30) |
| orig_m | 0.589 [0.422, 0.756] (n=90, tasks=30) | 0.467 [0.311, 0.622] (n=90, tasks=30) |
| ours | 0.344 [0.189, 0.511] (n=90, tasks=30) | 0.289 [0.144, 0.444] (n=90, tasks=30) |
| isat_m | 0.400 [0.244, 0.567] (n=90, tasks=30) | 0.256 [0.100, 0.422] (n=90, tasks=30) |
| origc_isat_m | 0.444 [0.289, 0.600] (n=90, tasks=30) | 0.578 [0.422, 0.733] (n=90, tasks=30) |
| isat_full | 0.422 [0.267, 0.567] (n=90, tasks=30) | 0.267 [0.133, 0.422] (n=90, tasks=30) |
| nsat_m | 0.211 [0.089, 0.356] (n=90, tasks=30) | 0.233 [0.100, 0.389] (n=90, tasks=30) |
| origc_nsat_m | 0.244 [0.111, 0.400] (n=90, tasks=30) | 0.256 [0.122, 0.400] (n=90, tasks=30) |
| nsat_full | 0.222 [0.089, 0.367] (n=90, tasks=30) | 0.244 [0.111, 0.389] (n=90, tasks=30) |
| fhmid_m | 0.400 [0.244, 0.556] (n=90, tasks=30) | 0.444 [0.289, 0.600] (n=90, tasks=30) |
| origc_fhmid_m | 0.578 [0.422, 0.733] (n=90, tasks=30) | 0.411 [0.256, 0.578] (n=90, tasks=30) |
| fhmid_full | 0.400 [0.256, 0.556] (n=90, tasks=30) | 0.400 [0.233, 0.567] (n=90, tasks=30) |

**H1 (interface replication, I-sat(m) − orig_c(I)(m) ≤ −0.02): holds** — -0.044 [-0.189, 0.100] (n=30); OOD -0.322 [-0.500, -0.156] (n=30).
**H2a (saturated-side novelty, N-sat(m) − orig_c(N-sat)(m) ≥ −0.02): fails** — PILOT-GRADE: N-sat bank = 2 envs, 4 matched items; 95% CI width 0.111. -0.033 [-0.089, 0.022] (n=30); OOD -0.022 [-0.122, 0.078] (n=30).
**H2b (zero-side novelty, N-zero(m) − orig_c(N-zero)(m) ≥ −0.02 and N-zero(m) − nobank ≥ 0): not evaluable (arm not built)** — vs control n/a; vs nobank n/a; OOD vs control n/a.

Descriptive: paired difference vs nobank (same seeds), ID / OOD:

| condition | ID − nobank | OOD − nobank |
|---|---|---|
| orig_m | 0.144 [0.011, 0.289] (n=30) | 0.144 [-0.011, 0.311] (n=30) |
| isat_m | -0.044 [-0.156, 0.056] (n=30) | -0.067 [-0.222, 0.089] (n=30) |
| origc_isat_m | 0.000 [-0.100, 0.122] (n=30) | 0.256 [0.089, 0.422] (n=30) |
| isat_full | -0.022 [-0.122, 0.078] (n=30) | -0.056 [-0.211, 0.100] (n=30) |
| nsat_m | -0.233 [-0.356, -0.122] (n=30) | -0.089 [-0.233, 0.056] (n=30) |
| origc_nsat_m | -0.200 [-0.300, -0.100] (n=30) | -0.067 [-0.211, 0.067] (n=30) |
| nsat_full | -0.222 [-0.333, -0.122] (n=30) | -0.078 [-0.233, 0.078] (n=30) |
| fhmid_m | -0.044 [-0.167, 0.078] (n=30) | 0.122 [-0.022, 0.278] (n=30) |
| origc_fhmid_m | 0.133 [-0.000, 0.278] (n=30) | 0.089 [-0.056, 0.244] (n=30) |
| fhmid_full | -0.044 [-0.167, 0.078] (n=30) | 0.078 [-0.078, 0.233] (n=30) |

**H4 (descriptive ω ordering: arms with ω ≤ 0.5 show ID gains ≥ arms with ω ≈ 1): supported (ω≤0.5 ≥ ω≈1); three-level ordering nsat ≥ fhmid ≥ isat does not hold** — ID gains vs own control: isat [ω≈1 (interface)]: -0.044 [-0.189, 0.100] (n=30); fhmid [ω∈(0.5,1] (F_H-mid, supplementary)]: -0.178 [-0.311, -0.056] (n=30); nsat [ω≤0.5 (novel)]: -0.033 [-0.089, 0.022] (n=30). F_H-mid is supplementary (owner decision at the P4.3 gate); it is excluded from H2a and K4.

## K4 outcome: **H2b not evaluable (N-zero NOT_BUILT under the ≥ 3-env rule); H2a fails → no SL evidence from the saturated side (pilot-grade, 2 envs / 4 items); K4 cannot be resolved until the zero side is evaluated with the formal CHS (stage budget re-based, p4/docs/stage_budget_audit.md)**

## Measurement notes

- Link audit: chain runs under the released runner via a two-env Link subclass (p4/docs/link_audit.md); Chain-3 not buildable with a two-env tree (reported, not substituted).
- Fidelity: Setup lists end with `look`; CHS prefixes reproduce the stored observation at the cut with and without no-op actions (3 trajectories).
- ω replays the policy's own P1 successes verbatim through the released stack; for O-axis envs ω = 1 as expected.
- Held-out evals reuse P3's nobank/orig/orig_m/ours runs; new arms run under the same protocol and seeds; paired differences with 10k task-level bootstrap.

## Caveats

- Single benchmark, N = 30 train tasks, 8 zero / 11 saturated tasks, Qwen3-8B via API, small banks (item-matched to the smaller side), one consumer protocol; no method proposals.
