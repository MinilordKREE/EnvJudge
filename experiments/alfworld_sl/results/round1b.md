# E1-SL Round 1b (PREREG7 Amendment 3): corrections and additions to Round 1

## 1. Corrected Round-1 zero-task line (rendering fix, numbers unchanged)

Zero tasks at the shared K=16 (0/16 on the original environment): 1 (task 11). Unlocked zero tasks (learnable accepted stage): A none; A-ex none.

## 2. G / G+ accepted rules (results/r1/g_rules.md): axis x leverage


| arm | axes | accepted envs | learnable (B_L) |
|---|---|---|---|
| G | - | 1 | 1 |
| G | A | 2 | 1 |
| G | AO | 2 | 1 |
| G | O | 3 | 3 |
| Gplus | - | 1 | 0 |
| Gplus | O | 3 | 3 |
| Gplus | T | 1 | 1 |
| Gplus | TO | 2 | 1 |


## 3. Protocol U corrected (A3.1): A-family rows re-induced and re-evaluated

| condition | seeds | ID | OOD |
|---|---|---|---|
| N | 6 | 59.2 (n=840) [63.6 / 57.1 / 64.3 / 52.9 / 60.0 / 57.1] | 62.9 (n=804) [66.4 / 67.2 / 58.2 / 61.9 / 57.5 / 66.4] |
| O_U | 6 | 62.4 (n=840) [69.3 / 60.0 / 60.0 / 55.0 / 67.9 / 62.1] | 61.1 (n=804) [62.7 / 60.4 / 59.7 / 64.9 / 58.2 / 60.4] |
| R_U | 6 | 63.9 (n=840) [72.1 / 57.9 / 63.6 / 61.4 / 67.9 / 60.7] | 66.3 (n=804) [67.9 / 70.1 / 63.4 / 67.9 / 64.9 / 63.4] |
| A_U_v1 | 6 | 62.5 (n=840) [64.3 / 62.1 / 65.7 / 58.6 / 64.3 / 60.0] | 69.9 (n=804) [73.9 / 73.1 / 65.7 / 66.4 / 69.4 / 70.9] |
| A_U | 6 | 63.7 (n=840) [68.6 / 61.4 / 61.4 / 58.6 / 66.4 / 65.7] | 67.9 (n=804) [67.2 / 73.1 / 66.4 / 67.2 / 67.2 / 66.4] |
| Aex_U_v1 | 3 | 62.9 (n=420) [65.7 / 61.4 / 61.4] | 67.7 (n=402) [71.6 / 67.2 / 64.2] |
| Aex_U | 3 | 63.3 (n=420) [66.4 / 60.0 / 63.6] | 67.2 (n=402) [68.7 / 68.7 / 64.2] |
| AplusH_U_v1 | 3 | 67.9 (n=420) [71.4 / 66.4 / 65.7] | 72.4 (n=402) [72.4 / 75.4 / 69.4] |
| AplusH_U | 3 | 64.5 (n=420) [68.6 / 63.6 / 61.4] | 69.4 (n=402) [68.7 / 73.1 / 66.4] |

| comparison | ID diff [95% CI] (SE) | OOD diff [95% CI] (SE) | pairs |
|---|---|---|---|
| A vs O (U, corrected; pre-registered) | +1.3 [-1.5, +4.2] (2.4) | +6.8 [+4.0, +9.8] (2.4) | 840 |
| A vs R (U, corrected; pre-registered inequality) | -0.2 [-3.6, +3.0] (2.3) | +1.6 [-1.4, +4.6] (2.3) | 840 |
| A vs N (U, corrected) | +4.5 [+1.7, +7.5] (2.4) | +5.0 [+1.7, +8.2] (2.4) | 840 |
| A_U corrected vs Round-1 A_U | +1.2 [-1.8, +4.3] (2.4) | -2.0 [-4.7, +0.7] (2.3) | 840 |
| A-ex_U corrected vs Round-1 | +0.5 [-3.8, +4.8] (3.3) | -0.5 [-5.0, +3.7] (3.3) | 420 |
| A+H_U corrected vs Round-1 | -3.3 [-7.4, +0.7] (3.3) | -3.0 [-6.7, +0.7] (3.2) | 420 |
| A vs A-ex (U, corrected) | +0.5 [-4.0, +5.0] (3.3) | +1.7 [-2.7, +6.2] (3.3) | 420 |
| A+H vs A (U, corrected) | +0.7 [-2.6, +4.0] (3.3) | +0.5 [-2.2, +3.2] (3.3) | 420 |

## 4. Bank-size controls (A3.2)

| condition | seeds | ID | OOD |
|---|---|---|---|
| placebo | 6 | 57.4 (n=840) [62.1 / 52.1 / 58.6 / 57.9 / 55.7 / 57.9] | 55.2 (n=804) [59.0 / 55.2 / 52.2 / 53.7 / 51.5 / 59.7] |

Gain over N and over the placebo at matched item counts (points; 3 seeds unless the full bank; a bank smaller than the target is evaluated at its full size and flagged):

| bank | size | items | vs N: ID | vs N: OOD | vs placebo: ID | vs placebo: OOD |
|---|---|---|---|---|---|---|
| A_T2 | 8 | 2 (full, flagged) | +9.5 [+6.7, +12.5] | +6.8 [+4.0, +9.8] | +11.3 [+8.3, +14.2] | +14.6 [+11.6, +17.7] |
| A_T2 | 20 | 2 (full, flagged) | +9.5 [+6.5, +12.4] | +6.8 [+4.0, +9.7] | +11.3 [+8.5, +14.3] | +14.6 [+11.6, +17.5] |
| AplusH_T2 | 8 | 5 (full, flagged) | +13.3 [+9.8, +17.1] | +14.9 [+10.7, +19.2] | +17.4 [+13.1, +21.7] | +23.4 [+18.9, +27.9] |
| AplusH_T2 | 20 | 5 (full, flagged) | +13.3 [+9.8, +17.1] | +14.9 [+10.7, +19.2] | +17.4 [+13.1, +21.7] | +23.4 [+18.9, +28.1] |

"No content effect" = the bank's gain at matched size is not distinguishable from the placebo's (the vs-placebo CI covers 0).

## 5. A' (A3.3): cross-task family priors

A' has not run (pending the owner's budget decision).


## 6. What changed (PREREG7 Amendment 3)

A3.1 redefined Protocol U as T2 plus single-success induction over every task with at least one success during the arm's own search regardless of final status; Amendment 1's status list had excluded budget_cap_hit tasks, so Round 1's A_U, Aex_U and AplusH_U were rebuilt (the originals are archived as *_U_v1 with their evaluations) and re-evaluated. A3.2 added a placebo bank of five task-irrelevant items and item-matched evaluations at 8 and 20 items so that C2 gains can be read against bank size and content. A3.3 pre-registered A', the A controller with cross-task family priors (start dose = median accepted dose, the d = 1 leverage test skipped after five ZERO results, families with no leverage on five tasks moved to the end); A itself was not re-run. A3.4 set the hard cap to USD 650 and the soft gate to USD 600.

## 7. Spend

Round 1 + 1b spend USD 430.26 (Round-1/1b run ids); E1-SL total USD 529.34 against the soft gate 600 and hard cap 650 (A3.4).
