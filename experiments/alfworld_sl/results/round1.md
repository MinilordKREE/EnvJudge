# E1-SL Round 1 (PREREG7 + Amendments 1-2)

## C1 — learnable transformed environments per 1,000 charged search rollouts (Protocol T2)

| arm | transformed envs | learnable (B_L at K=16) | search rollouts | per 1,000 [95% CI, task bootstrap] | band tasks learnable (secondary) |
|---|---|---|---|---|---|
| R | 23 | 0 | 290 | 0.0 [0.0, 0.0] | 0 |
| G | 8 | 6 | 850 | 7.1 [2.3, 12.9] | 0 |
| G+ | 7 | 5 | 835 | 6.0 [1.2, 11.6] | 0 |
| A | 1 | 1 | 745 | 1.3 [0.0, 4.4] | 4 |
| A-ex | 3 | 3 | 696 | 4.3 [0.0, 9.5] | 4 |
| A+H | 1 | 1 | 745 | 1.3 [0.0, 4.3] | 4 |

**C1 outcome: A > R holds (1.3 vs 0.0); A > G fails (1.3 vs 7.1) (point estimates).**

## Per-arm task statuses

| arm | band | accepted_knob | accepted_stage | frozen_no_leverage | exhausted | unresolved | unresolved_budget_limited | budget_cap_hit | infra_error | no_failed_trajectory |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 6 | 1 | 0 | 0 | 0 | 1 | 0 | 22 | 0 | 0 |
| A-ex | 8 | 3 | 0 | 0 | 0 | 1 | 0 | 18 | 0 | 0 |
| A+H | 6 | 1 | 0 | 0 | 0 | 1 | 0 | 22 | 0 | 0 |

| arm | accepted | all_rejected | skipped |
|---|---|---|---|
| R | 24 | 0 | 6 |
| G | 8 | 22 | 0 |
| G+ | 7 | 23 | 0 |

Zero tasks at the shared K=16 (0/16 on the original environment): 11. Unlocked zero tasks (learnable accepted stage): A none; A-ex none.
Family of origin of accepted environments — A: {'exemplar:footer_mask': 1}; A-ex: {'exemplar:footer_mask': 3}.

## C2 — held-out success (released eval, %; pooled over seeds, per-seed in brackets)

| condition | seeds | ID | OOD |
|---|---|---|---|
| N | 6 | 59.2 (n=840) [63.6 / 57.1 / 64.3 / 52.9 / 60.0 / 57.1] | 62.9 (n=804) [66.4 / 67.2 / 58.2 / 61.9 / 57.5 / 66.4] |
| O_U | 6 | 62.4 (n=840) [69.3 / 60.0 / 60.0 / 55.0 / 67.9 / 62.1] | 61.1 (n=804) [62.7 / 60.4 / 59.7 / 64.9 / 58.2 / 60.4] |
| A_T2 | 6 | 68.7 (n=840) [71.4 / 65.0 / 67.1 / 65.7 / 70.0 / 72.9] | 69.8 (n=804) [73.9 / 70.9 / 66.4 / 71.6 / 65.7 / 70.1] |
| A_U | 6 | 62.5 (n=840) [64.3 / 62.1 / 65.7 / 58.6 / 64.3 / 60.0] | 69.9 (n=804) [73.9 / 73.1 / 65.7 / 66.4 / 69.4 / 70.9] |
| A_rel | 6 | 66.1 (n=840) [71.4 / 63.6 / 63.6 / 61.4 / 71.4 / 65.0] | 64.8 (n=804) [65.7 / 65.7 / 65.7 / 66.4 / 59.7 / 65.7] |
| Aex_T2 | 3 | 65.7 (n=420) [67.9 / 63.6 / 65.7] | 61.4 (n=402) [61.2 / 61.9 / 61.2] |
| Aex_U | 3 | 62.9 (n=420) [65.7 / 61.4 / 61.4] | 67.7 (n=402) [71.6 / 67.2 / 64.2] |
| AplusH_T2 | 3 | 75.0 (n=420) [80.0 / 69.3 / 75.7] | 78.9 (n=402) [79.1 / 79.9 / 77.6] |
| AplusH_U | 3 | 67.9 (n=420) [71.4 / 66.4 / 65.7] | 72.4 (n=402) [72.4 / 75.4 / 69.4] |
| G_T2 | 3 | 71.2 (n=420) [75.0 / 64.3 / 74.3] | 75.9 (n=402) [75.4 / 81.3 / 70.9] |
| G_U | 3 | 56.9 (n=420) [60.7 / 52.9 / 57.1] | 68.4 (n=402) [71.6 / 67.2 / 66.4] |
| Gplus_T2 | 3 | 65.2 (n=420) [67.1 / 63.6 / 65.0] | 67.7 (n=402) [65.7 / 70.1 / 67.2] |
| Gplus_U | 3 | 60.0 (n=420) [64.3 / 55.0 / 60.7] | 58.2 (n=402) [56.7 / 64.2 / 53.7] |
| R_T2 | 6 | 62.0 (n=840) [67.1 / 56.4 / 64.3 / 59.3 / 65.7 / 59.3] | 60.9 (n=804) [61.9 / 65.7 / 56.0 / 62.7 / 59.0 / 60.4] |
| R_U | 6 | 63.9 (n=840) [72.1 / 57.9 / 63.6 / 61.4 / 67.9 / 60.7] | 66.3 (n=804) [67.9 / 70.1 / 63.4 / 67.9 / 64.9 / 63.4] |
| R_rel | 6 | 62.4 (n=840) [67.1 / 53.6 / 67.1 / 61.4 / 60.0 / 65.0] | 65.2 (n=804) [61.9 / 73.9 / 59.7 / 64.9 / 64.2 / 66.4] |

Paired differences (points; pairs = same seed, split and episode; 10k bootstrap; SE = pooled normal):

| comparison | ID diff [95% CI] (SE) | OOD diff [95% CI] (SE) | pairs |
|---|---|---|---|
| A vs O (U; pre-registered) | +0.1 [-3.0, +3.2] (2.4) | +8.8 [+5.6, +12.1] (2.4) | 840 |
| A vs R (U; pre-registered inequality) | -1.4 [-4.4, +1.5] (2.4) | +3.6 [+0.6, +6.5] (2.3) | 840 |
| A vs R (T2; transformation-only) | +6.7 [+3.3, +10.0] (2.3) | +8.8 [+5.3, +12.3] (2.4) | 840 |
| A vs G (U) | +7.1 [+2.9, +11.2] (3.4) | +2.5 [-1.5, +6.5] (3.2) | 420 |
| A vs G (T2) | -3.3 [-7.6, +1.2] (3.2) | -5.5 [-10.2, -0.7] (3.1) | 420 |
| A vs N (U) | +3.3 [+0.6, +6.2] (2.4) | +7.0 [+3.6, +10.3] (2.3) | 840 |
| R vs N (U) | +4.8 [+1.4, +8.0] (2.4) | +3.4 [-0.1, +6.7] (2.4) | 840 |
| O vs N | +3.2 [+0.1, +6.2] (2.4) | -1.9 [-5.3, +1.6] (2.4) | 840 |
| A vs A-ex (U; ablation) | +1.2 [-2.4, +4.8] (3.3) | +3.2 [-0.7, +7.2] (3.3) | 420 |
| A vs A-ex (T2; ablation) | +2.1 [-2.4, +6.7] (3.2) | +9.0 [+4.2, +13.4] (3.3) | 420 |
| G+ vs G (U; ablation) | +3.1 [-1.0, +7.1] (3.4) | -10.2 [-14.4, -5.7] (3.4) | 420 |
| G+ vs G (T2; ablation) | -6.0 [-10.0, -1.7] (3.2) | -8.2 [-12.7, -3.7] (3.2) | 420 |
| A+H vs A (U) | +3.8 [+0.0, +7.4] (3.3) | +1.5 [-2.0, +5.0] (3.2) | 420 |
| A+H vs A (T2) | +7.1 [+3.3, +11.0] (3.1) | +8.5 [+4.5, +12.4] (3.1) | 420 |
| A vs R (released protocol) | +3.7 [+0.5, +6.8] (2.3) | -0.4 [-3.5, +2.9] (2.4) | 840 |
| A released vs A single-success (U) | +3.6 [+0.5, +6.7] (2.3) | -5.1 [-8.3, -1.9] (2.3) | 840 |
| R released vs R single-success (U) | -1.5 [-4.2, +1.1] (2.4) | -1.1 [-3.7, +1.4] (2.4) | 840 |

## A2.2 seed-extension decision

No extension: no ID gap of A - R (U) or A - O (U) lies between 1 and 2 SE.

## C2 outcome (round 1)

**A ≥ O (U): ID 0.1, OOD 8.8; A ≥ R (U): ID -1.4, OOD 3.6 → fails on point estimates; A - R 95% CI excluding 0 on ID or OOD: yes.**

## Stop rule (PREREG7)

A - R (U) on ID -1.4 and OOD 3.6 (both below -3.0: no); A's C1 rate below R's: no.

**Stop-rule verdict: PASS — rounds 2-3 may run on the owner's go.**

## Accounting

| arm / run | search rollouts (charged) | learnable transformed | per 1,000 | USD by budget |
|---|---|---|---|---|
| R | 290 | 0 | 0.0 | confirm 6.92 |
| G | 850 | 6 | 7.1 | confirm 5.43, designer 0.42, search 19.52 |
| G+ | 835 | 5 | 6.0 | confirm 2.81, designer 0.47, search 19.09 |
| A | 745 | 1 | 1.3 | confirm 0.56, designer 0.03, search 20.97 |
| A-ex | 696 | 3 | 4.3 | confirm 1.64, search 19.11 |
| A+H | 745 | 1 | 1.3 | - |
| O | 900 | - | - | search 22.84 |
| r1-shared | - | - | - | confirm 11.70 |
| r1-banks | - | - | - | eval 0.94 |
| r1-eval | - | - | - | eval 235.77 |

Round 1 spend USD 368.22 (Round-1 run ids; R's reused corpus USD 6.61 was counted in Phase 0); E1-SL total USD 467.30 against the soft gate 500 and hard cap 560.
