# E3-SL — downstream skill evaluation of the E3 learner-facing sets (PREREG9 Addendum SL)

Banks: released single-success induction (`_build_bank`, success-only trajectories, shortest success per environment), DeepSeek V4 Pro extractor (thinking off) through the eval hook, embeddings through OpenRouter; two inductions per bank (i1 / i2, labelled by the addendum's seeds 20260920 / 20260921 — the released single-success induction samples at temperature 0, so i1 and i2 are replicate runs whose spread is the endpoint's own nondeterminism). Item matching: every learner-facing bank subsampled to k = 12 items (seed 20260922). Eval: released `reasoning_bank_eval.py` through the eval hook, Qwen3-8B consumer (alibaba pin, reasoning off), SkillOS prompt, history 4, temperature 0.4, top-5 MMR, ID 140 + OOD 134, seeds 0 / 1000 / 2000. Addendum @ f9623e2. Tables from scripts/make_tables_e3sl.py.

## Verdict

**E3-SL holds on in_distribution and out_of_distribution: item-matched, induction-averaged A_lf above G_lf and R_lf with 95% CIs excluding 0.**

Paired per-task differences (points; induction-averaged per episode, then averaged over a task's seed blocks; 10k task-level bootstrap over the 140 ID / 134 OOD tasks, as pre-registered — the episode-level intervals of the first version of this report were superseded and are kept in e3_sl_data.json; ≈ = gap within 3 points, * = CI excludes 0):

| difference | ID | OOD | n (ID / OOD) |
|---|---|---|---|
| A_lf - G_lf | +7.6 [+4.8, +10.4] * | +10.9 [+7.3, +14.3] * | 420 / 402 |
| A_lf - R_lf | +8.6 [+4.6, +12.4] * | +11.3 [+7.7, +15.0] * | 420 / 402 |
| A_lf - O | +3.1 [-0.1, +6.3] | +4.0 [+0.5, +7.5] * | 420 / 402 |
| A_lf - N | +12.7 [+8.7, +16.9] * | +18.4 [+13.9, +22.8] * | 420 / 402 |
| A_lf - placebo | +23.5 [+19.5, +27.4] * | +29.6 [+24.4, +35.0] * | 420 / 402 |
| G_lf - N | +5.1 [+1.4, +8.8] * | +7.5 [+3.4, +11.4] * | 420 / 402 |
| G_lf - placebo | +15.8 [+12.0, +19.5] * | +18.7 [+13.9, +23.5] * | 420 / 402 |
| R_lf - N | +4.2 [+0.1, +8.3] * | +7.1 [+2.5, +11.7] * | 420 / 402 |
| R_lf - placebo | +14.9 [+10.8, +19.0] * | +18.3 [+13.2, +23.5] * | 420 / 402 |
| O_lf - N | +9.6 [+5.8, +13.6] * | +14.4 [+10.2, +18.7] * | 420 / 402 |
| O_lf - placebo | +20.4 [+16.3, +24.5] * | +25.6 [+20.8, +30.6] * | 420 / 402 |
| placebo - N | -10.7 [-14.5, -7.1] * | -11.2 [-15.7, -6.7] * | 420 / 402 |

## Item-matched table (k = 12 items per bank; success %, n, per seed 0 / 1000 / 2000)

The mean row carries the between-induction standard error of the mean over the two replicate inductions (|i1 - i2| / 2). The released single-success induction samples at temperature 0, so this spread is the extractor endpoint's own nondeterminism (and, for the matched rows, the 12-item subsample), not sampling variance.

| bank | induction | ID | OOD |
|---|---|---|---|
| A_lf (matched) | i1 | 55.2 (n=420) [64.3 / 50.0 / 51.4] | 61.7 (n=402) [67.2 / 61.9 / 56.0] |
| A_lf (matched) | i2 | 45.5 (n=420) [51.4 / 44.3 / 40.7] | 47.8 (n=402) [50.0 / 49.3 / 44.0] |
| **A_lf (matched)** | mean ± SE(induction) | **50.4 ± 4.9** | **54.7 ± 7.0** |
| G_lf (matched) | i1 | 46.2 (n=420) [48.6 / 47.1 / 42.9] | 51.5 (n=402) [54.5 / 53.0 / 47.0] |
| G_lf (matched) | i2 | 39.3 (n=420) [41.4 / 38.6 / 37.9] | 36.1 (n=402) [37.3 / 36.6 / 34.3] |
| **G_lf (matched)** | mean ± SE(induction) | **42.7 ± 3.5** | **43.8 ± 7.7** |
| R_lf (matched) | i1 | 39.8 (n=420) [42.9 / 35.0 / 41.4] | 41.3 (n=402) [44.8 / 40.3 / 38.8] |
| R_lf (matched) | i2 | 43.8 (n=420) [50.0 / 40.0 / 41.4] | 45.5 (n=402) [50.7 / 44.8 / 41.0] |
| **R_lf (matched)** | mean ± SE(induction) | **41.8 ± 2.0** | **43.4 ± 2.1** |
| O_lf (matched) | i1 | 51.4 (n=420) [61.4 / 47.1 / 45.7] | 53.2 (n=402) [58.2 / 49.3 / 52.2] |
| O_lf (matched) | i2 | 43.1 (n=420) [47.9 / 37.1 / 44.3] | 48.3 (n=402) [52.2 / 47.8 / 44.8] |
| **O_lf (matched)** | mean ± SE(induction) | **47.3 ± 4.2** | **50.7 ± 2.5** |
| N | i1 | 37.6 (n=420) [47.1 / 34.3 / 31.4] | 36.3 (n=402) [35.8 / 38.1 / 35.1] |
| placebo | i1 | 26.9 (n=420) [31.4 / 27.1 / 22.1] | 25.1 (n=402) [26.9 / 26.1 / 22.4] |

## Supplementary paired differences (full-bank and released-cascade rows; same estimator)

| difference | ID | OOD | n (ID / OOD) |
|---|---|---|---|
| A_lf(full) - G_lf(full) | -0.0 [-3.6, +3.6] ≈ | +6.8 [+3.1, +10.7] * | 420 / 402 |
| A_lf(full) - R_lf(full) | +9.6 [+5.5, +13.7] * | +13.3 [+9.2, +17.5] * | 420 / 402 |
| A_lf(full) - O_lf(full) | +4.6 [+1.1, +8.0] * | +4.1 [+0.6, +7.7] * | 420 / 402 |
| A_cas - G_cas | +2.5 [-1.0, +6.0] ≈ | +2.7 [-1.1, +6.5] ≈ | 420 / 402 |
| A_cas - R_cas | +2.1 [-1.4, +5.7] ≈ | -6.8 [-10.7, -3.0] * | 420 / 402 |
| A_lf(full) - A_cas | +5.1 [+1.2, +9.2] * | +8.7 [+4.5, +12.9] * | 420 / 402 |

## Full-bank rows (supplementary)

| bank | induction | ID | OOD |
|---|---|---|---|
| A_lf (full) | i1 | 50.0 (n=420) [56.4 / 45.7 / 47.9] | 55.2 (n=402) [54.5 / 57.5 / 53.7] |
| A_lf (full) | i2 | 52.9 (n=420) [65.0 / 46.4 / 47.1] | 58.2 (n=402) [61.9 / 53.7 / 59.0] |
| **A_lf (full)** | mean ± SE(induction) | **51.4 ± 1.4** | **56.7 ± 1.5** |
| G_lf (full) | i1 | 54.3 (n=420) [64.3 / 45.0 / 53.6] | 51.7 (n=402) [55.2 / 51.5 / 48.5] |
| G_lf (full) | i2 | 48.6 (n=420) [53.6 / 45.7 / 46.4] | 48.0 (n=402) [50.7 / 45.5 / 47.8] |
| **G_lf (full)** | mean ± SE(induction) | **51.4 ± 2.9** | **49.9 ± 1.9** |
| R_lf (full = matched, 12 items) | i1 | 39.8 (n=420) [42.9 / 35.0 / 41.4] | 41.3 (n=402) [44.8 / 40.3 / 38.8] |
| R_lf (full = matched, 12 items) | i2 | 43.8 (n=420) [50.0 / 40.0 / 41.4] | 45.5 (n=402) [50.7 / 44.8 / 41.0] |
| **R_lf (full = matched, 12 items)** | mean ± SE(induction) | **41.8 ± 2.0** | **43.4 ± 2.1** |
| O_lf (full) | i1 | 50.5 (n=420) [56.4 / 45.0 / 50.0] | 50.7 (n=402) [49.3 / 53.7 / 49.3] |
| O_lf (full) | i2 | 43.1 (n=420) [54.3 / 37.1 / 37.9] | 54.5 (n=402) [58.2 / 52.2 / 53.0] |
| **O_lf (full)** | mean ± SE(induction) | **46.8 ± 3.7** | **52.6 ± 1.9** |

## Released-cascade rows (supplementary)

| bank | induction | ID | OOD |
|---|---|---|---|
| A_cas | i1 | 43.3 (n=420) [48.6 / 45.7 / 35.7] | 46.0 (n=402) [47.8 / 48.5 / 41.8] |
| A_cas | i2 | 49.3 (n=420) [51.4 / 47.9 / 48.6] | 50.0 (n=402) [50.7 / 47.8 / 51.5] |
| **A_cas** | mean ± SE(induction) | **46.3 ± 3.0** | **48.0 ± 2.0** |
| G_cas | i1 | 41.0 (n=420) [45.7 / 37.9 / 39.3] | 45.5 (n=402) [47.0 / 43.3 / 46.3] |
| G_cas | i2 | 46.7 (n=420) [49.3 / 43.6 / 47.1] | 45.0 (n=402) [49.3 / 45.5 / 40.3] |
| **G_cas** | mean ± SE(induction) | **43.8 ± 2.9** | **45.3 ± 0.2** |
| R_cas | i1 | 41.9 (n=420) [46.4 / 40.0 / 39.3] | 54.5 (n=402) [55.2 / 55.2 / 53.0] |
| R_cas | i2 | 46.4 (n=420) [52.1 / 45.7 / 41.4] | 55.2 (n=402) [55.2 / 53.7 / 56.7] |
| **R_cas** | mean ± SE(induction) | **44.2 ± 2.3** | **54.9 ± 0.4** |

## Banks — item counts and induction types

| bank | items | tasks | trajectories | induction types | extractor | note |
|---|---|---|---|---|---|---|
| A_cas_i1 | 67 | 30 | - | {'single_fail': 27, 'paired_diff': 11, 'single_succ': 29} | deepseek-v4-pro | released Stage 2 verbatim (per-task cascade, automatic mode) |
| A_cas_i2 | 68 | 30 | - | {'single_fail': 27, 'paired_diff': 11, 'single_succ': 30} | deepseek-v4-pro | released Stage 2 verbatim (per-task cascade, automatic mode) |
| A_lf_i1 | 27 | 9 | 45 | {'single_succ': 27} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| A_lf_i2 | 27 | 9 | 45 | {'single_succ': 27} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| G_cas_i1 | 60 | 30 | - | {'paired_diff': 15, 'single_succ': 27, 'single_fail': 18} | deepseek-v4-pro | released Stage 2 verbatim (per-task cascade, automatic mode) |
| G_cas_i2 | 60 | 30 | - | {'paired_diff': 15, 'single_succ': 27, 'single_fail': 18} | deepseek-v4-pro | released Stage 2 verbatim (per-task cascade, automatic mode) |
| G_lf_i1 | 42 | 14 | 37 | {'single_succ': 42} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| G_lf_i2 | 42 | 14 | 37 | {'single_succ': 42} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| O_lf_i1 | 62 | 22 | 277 | {'single_succ': 62} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| O_lf_i2 | 66 | 22 | 277 | {'single_succ': 66} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| R_cas_i1 | 72 | 30 | - | {'paired_diff': 9, 'single_succ': 42, 'single_fail': 21} | deepseek-v4-pro | released Stage 2 verbatim (per-task cascade, automatic mode) |
| R_cas_i2 | 72 | 30 | - | {'paired_diff': 9, 'single_succ': 42, 'single_fail': 21} | deepseek-v4-pro | released Stage 2 verbatim (per-task cascade, automatic mode) |
| R_lf_i1 | 12 | 4 | 11 | {'single_succ': 12} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| R_lf_i2 | 12 | 4 | 11 | {'single_succ': 12} | deepseek-v4-pro | released single-success induction (temperature 0), shortest success per env |
| placebo | 5 | 0 | - | - | deepseek-v4-pro | no ALFWorld object, receptacle or command-form verb |

Matched sizes: k = 12 from A_lf_i1 27, A_lf_i2 27, G_lf_i1 42, G_lf_i2 42, O_lf_i1 62, O_lf_i2 66, R_lf_i1 12, R_lf_i2 12.

## Spend (USD by run and budget/phase)

| run | budget/phase | total |
|---|---|---|
| e3sl-banks | eval/induce 1.46 | 1.46 |
| e3sl-eval | eval/eval 142.54 | 142.54 |

E3-SL total USD 144.00 (cap 180).

## Incidents (UTC timestamps in experiments/alfworld_e3/LOG.md)

- Guard incidents 1; ledgered retries 429 0, other 0; errored episodes re-run 3.
