# E-min verdict — generated 2026-09-05 09:09 UTC

Pre-registration: `PREREG.md` @ git sha `0a07fa23ebce6cdb10dc181fa8f783dcfc743757`. Rollouts per arm: A1=608, A1p=608, A2=608, A3=608, A4=608, A5=608, A6=608, A7=608, A8=608.
Spend so far: 5671 API calls, USD 7.36 at the applicable tariff (USD 14.72 at the peak bound). Budget: hard 20 / soft 12.

## Overall (section 3 rule): **CONDITIONAL + implementation-suspect (P4 failed: Contract harmed solved tasks)**

Rule: GO = P1 ∧ P2(Pro) ∧ P5-direction; CONDITIONAL = P1 ∧ ¬P2; NO-GO = ¬P1 ∧ ¬P2; P4 failure adds 'implementation-suspect'. Bold is used only for the overall call; every rate below carries a 10,000-resample task-level bootstrap 95% CI, and 'CI-decisive' means the CI excludes the threshold.

## Predictions

### P1 mixture (L1, L2 each >= 15% of p0=0 tasks): supported (CI not decisive)

p0=0 tasks (A1, Pro): 38/76. Shares: L0 0.026 [0.000, 0.079] (n=38); L1 0.684 [0.526, 0.816] (n=38); L2 0.158 [0.053, 0.289] (n=38); L? 0.132 [0.026, 0.237] (n=38). Counts: {'L2': 6, 'L1': 26, 'L?': 5, 'L0': 1}.

### P2 interaction (Pro): unlock(L1) - unlock(L2) >= 0.25 and unlock(L1) >= 0.40 in E_all: contradicted (CI not decisive)

Pro E_all (A4): unlock(L1) = 0.154 [0.038, 0.308] (n=26), unlock(L2) = 0.333 [0.000, 0.667] (n=6), difference = -0.179 [-0.590, 0.192]. f_AA (spurious unlock of an identical env) = 0.184; unlock(L1) - f_AA = -0.030; unlock(L2) - f_AA = 0.149. Thresholds: difference >= 0.25 and unlock(L1) >= 0.40 (after subtracting f_AA).

### P3 dose: unlock(L1) > 0 in both E_off and E_c12; E_all >= max: supported (CI-decisive)

unlock(L1): E_c12 (A2) = 0.154 [0.038, 0.308] (n=26); E_off (A3) = 0.154 [0.038, 0.308] (n=26); E_all (A4) = 0.154 [0.038, 0.308] (n=26). c3-alone share of the E_all L1 unlock = 1.000; c1+c2-alone share = 1.000.

### P4 harmlessness: tasks with p0 >= 0.875 keep p >= 0.75 in E_all for >= 90%: contradicted (CI not decisive)

Tasks with p0 >= 0.875 in A1: 6. Share with p(A4) >= 0.75: 0.333 [0.000, 0.667] (n=6). Mean p over these tasks: A1 0.875 -> A4 0.646.

### P5 consumer (Flash): P2 direction holds and unlock_Flash(L1) >= unlock_Pro(L1): contradicted (CI not decisive)

Flash labels from A7 (p0=0 tasks: 37; L1 n=24, L2 n=8). E_all (A8): unlock(L1) = 0.250 [0.083, 0.417] (n=24), unlock(L2) = 0.500 [0.125, 0.875] (n=8), difference = -0.250 [-0.625, 0.125]. unlock_Flash(L1) - unlock_Pro(L1) = 0.096 [-0.138, 0.304]. No Flash A/A arm was pre-registered, so no f_AA subtraction for Flash.

### P6 phi = G'/G >= 0.6: contradicted (CI not decisive)

G = mean p(A5 parent,E_sub) - mean p(A1 parent-,E_sub) = 0.054 [0.010, 0.099]; G' = mean p(A4 parent-,E_all) - mean p(A1) = -0.003 [-0.051, 0.043]; phi = G'/G (CI over resamples with G>0) = -0.061 [-2.333, 0.728]; A6 - A4 (skill increment on top of Contract) = 0.077 [0.038, 0.118]; A6 - A5 (Contract increment on top of skill) = 0.020 [-0.020, 0.059].

### P7 baseline misrouting: designer rule sr==0 -> SKIP skips every p0=0 task; L1 share among them: supported (CI-decisive)

envharness corpus.yaml Phase 1: 'baseline_sr == 0.0: SKIP'. All 38 p0=0 tasks are skipped by construction. Skipped L1 share = |L1|/|p0=0| = 26/38 = 0.684 [0.526, 0.816] (n=38); skipped L2 share = 0.158 [0.053, 0.289] (n=38).

### P8 witness bias: h(t) > 0 for >= 10% of pool 76: supported (CI-decisive)

pool 76: 0.237 [0.145, 0.329] (n=76); all evaluable verified_400 (396): 0.295 [0.253, 0.341] (n=396). Substrate path rejects recalc(golden) vs raw golden (sub_recalc_vs_raw == FAIL) for 5/76 pool tasks; W fails (L0 candidates) for 1/76 pool tasks.

## Regime counts (Pro labels from A1)

p0=0: 38; labels: {'L2': 6, 'solved': 38, 'L1': 26, 'L?': 5, 'L0': 1}

Flash (A7) p0=0: 37; labels: {'L2': 8, 'solved': 39, 'L1': 24, 'L?': 4, 'L0': 1}

## A/A (A1 vs A1', parent⁻, E_sub, Pro)

f_AA = P(p(A1') > 0 | p(A1) = 0) = 0.184 [0.079, 0.316] (n=38); reverse = 0.088 [0.000, 0.206] (n=34); zero-status flips = 10/76; regime-label flips = 10/76; mean |Δp| = 0.105; |Δp| quantiles (50/75/90/100) = ['0.000', '0.125', '0.250', '0.750']; histogram = {'0.000': 40, '0.125': 20, '0.500': 2, '0.375': 4, '0.250': 9, '0.750': 1}.

## Per-arm summary (aa_band.csv)

| arm | agent | env | consumer | rollouts | mean p | zero share | full share | band [2..6]/8 share |
|---|---|---|---|---|---|---|---|---|
| A1 | parent_minus | E_sub | pro | 608 | 0.248 | 0.500 | 0.000 | 0.329 |
| A1p | parent_minus | E_sub | pro | 608 | 0.248 | 0.447 | 0.000 | 0.382 |
| A2 | parent_minus | E_c12 | pro | 608 | 0.257 | 0.447 | 0.013 | 0.303 |
| A3 | parent_minus | E_off | pro | 608 | 0.248 | 0.487 | 0.013 | 0.342 |
| A4 | parent_minus | E_all | pro | 608 | 0.245 | 0.461 | 0.039 | 0.329 |
| A5 | parent | E_sub | pro | 608 | 0.303 | 0.421 | 0.039 | 0.382 |
| A6 | parent | E_all | pro | 608 | 0.322 | 0.421 | 0.026 | 0.316 |
| A7 | parent_minus | E_sub | flash | 608 | 0.212 | 0.487 | 0.000 | 0.342 |
| A8 | parent_minus | E_all | flash | 608 | 0.212 | 0.368 | 0.013 | 0.408 |

## Unlock rates (unlock_rates.csv)

| consumer | label | env | arm | n | unlocked | rate [CI] | rate − f_AA |
|---|---|---|---|---|---|---|---|
| pro | L0 | E_c12 | A2 | 1 | 1 | 1.000 [1.000, 1.000] | 0.816 |
| pro | L1 | E_c12 | A2 | 26 | 4 | 0.154 [0.038, 0.308] | -0.030 |
| pro | L2 | E_c12 | A2 | 6 | 2 | 0.333 [0.000, 0.667] | 0.149 |
| pro | L? | E_c12 | A2 | 5 | 1 | 0.200 [0.000, 0.600] | 0.016 |
| pro | all_zero | E_c12 | A2 | 38 | 8 | 0.211 [0.079, 0.342] | 0.026 |
| pro | L0 | E_off | A3 | 1 | 0 | 0.000 [0.000, 0.000] | -0.184 |
| pro | L1 | E_off | A3 | 26 | 4 | 0.154 [0.038, 0.308] | -0.030 |
| pro | L2 | E_off | A3 | 6 | 0 | 0.000 [0.000, 0.000] | -0.184 |
| pro | L? | E_off | A3 | 5 | 2 | 0.400 [0.000, 0.800] | 0.216 |
| pro | all_zero | E_off | A3 | 38 | 6 | 0.158 [0.053, 0.289] | -0.026 |
| pro | L0 | E_all | A4 | 1 | 0 | 0.000 [0.000, 0.000] | -0.184 |
| pro | L1 | E_all | A4 | 26 | 4 | 0.154 [0.038, 0.308] | -0.030 |
| pro | L2 | E_all | A4 | 6 | 2 | 0.333 [0.000, 0.667] | 0.149 |
| pro | L? | E_all | A4 | 5 | 1 | 0.200 [0.000, 0.600] | 0.016 |
| pro | all_zero | E_all | A4 | 38 | 7 | 0.184 [0.079, 0.316] | 0.000 |
| flash | L0 | E_all | A8 | 1 | 0 | 0.000 [0.000, 0.000] | -0.184 |
| flash | L1 | E_all | A8 | 24 | 6 | 0.250 [0.083, 0.417] | 0.066 |
| flash | L2 | E_all | A8 | 8 | 4 | 0.500 [0.125, 0.875] | 0.316 |
| flash | L? | E_all | A8 | 4 | 3 | 0.750 [0.250, 1.000] | 0.566 |
| flash | all_zero | E_all | A8 | 37 | 13 | 0.351 [0.216, 0.514] | 0.167 |

## Dose table (dose_table.csv)

- env: E_c12; arm: A2; unlock_L1: 0.154 [0.038, 0.308] n=26; unlock_L2: 0.333 [0.000, 0.667] n=6; unlock_L?: 0.200 [0.000, 0.600] n=5; unlock_L0: 1.000 [1.000, 1.000] n=1; unlock_all_zero: 0.211 [0.079, 0.342] n=38
- env: E_off; arm: A3; unlock_L1: 0.154 [0.038, 0.308] n=26; unlock_L2: 0.000 [0.000, 0.000] n=6; unlock_L?: 0.400 [0.000, 0.800] n=5; unlock_L0: 0.000 [0.000, 0.000] n=1; unlock_all_zero: 0.158 [0.053, 0.289] n=38
- env: E_all; arm: A4; unlock_L1: 0.154 [0.038, 0.308] n=26; unlock_L2: 0.333 [0.000, 0.667] n=6; unlock_L?: 0.200 [0.000, 0.600] n=5; unlock_L0: 0.000 [0.000, 0.000] n=1; unlock_all_zero: 0.184 [0.079, 0.316] n=38
- env: c3_alone_share_of_L1_unlock; arm: A3/A4; unlock_L1: 1.000
- env: c12_alone_share_of_L1_unlock; arm: A2/A4; unlock_L1: 1.000

## φ (phi.csv)

- G = mean p(A5 parent,E_sub) - mean p(A1 parent-,E_sub) = 0.054 [0.010, 0.099] (n=76)
- G' = mean p(A4 parent-,E_all) - mean p(A1) = -0.003 [-0.051, 0.043] (n=76)
- phi = G'/G (CI over resamples with G>0) = -0.061 [-2.333, 0.728] (n=9943)
- A6 - A4 (skill increment on top of Contract) = 0.077 [0.038, 0.118] (n=76)
- A6 - A5 (Contract increment on top of skill) = 0.020 [-0.020, 0.059] (n=76)
- mean p(A1 parent_minus,E_sub,pro) = 0.248 [0.181, 0.319] (n=76)
- mean p(A1p parent_minus,E_sub,pro) = 0.248 [0.186, 0.319] (n=76)
- mean p(A2 parent_minus,E_c12,pro) = 0.257 [0.188, 0.329] (n=76)
- mean p(A3 parent_minus,E_off,pro) = 0.248 [0.181, 0.319] (n=76)
- mean p(A4 parent_minus,E_all,pro) = 0.245 [0.178, 0.317] (n=76)
- mean p(A5 parent,E_sub,pro) = 0.303 [0.229, 0.378] (n=76)
- mean p(A6 parent,E_all,pro) = 0.322 [0.243, 0.403] (n=76)
- mean p(A7 parent_minus,E_sub,flash) = 0.212 [0.153, 0.276] (n=76)
- mean p(A8 parent_minus,E_all,flash) = 0.212 [0.161, 0.266] (n=76)

## Supplementary (not pre-registered): paired re-scoring of the A1 responses under the four env verdicts

The prompt does not depend on the env, so every A1 response can be re-scored under E_sub/E_c12/E_off/E_all; this is a paired estimate of the same quantities the independent arms A2–A4 estimate.

- env_verdict_on_A1_responses: E_sub; mean_p: 0.248; unlock_L0: 0.000 [0.000, 0.000] n=1; unlock_L1: 0.000 [0.000, 0.000] n=26; unlock_L2: 0.000 [0.000, 0.000] n=6; unlock_L?: 0.000 [0.000, 0.000] n=5; unlock_all_zero: 0.000 [0.000, 0.000] n=38
- env_verdict_on_A1_responses: E_c12; mean_p: 0.248; unlock_L0: 0.000 [0.000, 0.000] n=1; unlock_L1: 0.000 [0.000, 0.000] n=26; unlock_L2: 0.000 [0.000, 0.000] n=6; unlock_L?: 0.000 [0.000, 0.000] n=5; unlock_all_zero: 0.000 [0.000, 0.000] n=38
- env_verdict_on_A1_responses: E_off; mean_p: 0.266; unlock_L0: 0.000 [0.000, 0.000] n=1; unlock_L1: 0.154 [0.038, 0.308] n=26; unlock_L2: 0.000 [0.000, 0.000] n=6; unlock_L?: 0.400 [0.000, 0.800] n=5; unlock_all_zero: 0.158 [0.053, 0.289] n=38
- env_verdict_on_A1_responses: E_all; mean_p: 0.266; unlock_L0: 0.000 [0.000, 0.000] n=1; unlock_L1: 0.154 [0.038, 0.308] n=26; unlock_L2: 0.000 [0.000, 0.000] n=6; unlock_L?: 0.400 [0.000, 0.800] n=5; unlock_all_zero: 0.158 [0.053, 0.289] n=38

## Primary failure reasons per arm

- A1: {'workbook_missing': 273, 'value_mismatch': 184, 'pass': 151}
- A1p: {'workbook_missing': 294, 'value_mismatch': 163, 'pass': 151}
- A2: {'value_mismatch': 227, 'workbook_missing': 225, 'pass': 156}
- A3: {'workbook_missing': 293, 'value_mismatch': 159, 'pass': 151, 'sheet_missing': 5}
- A4: {'value_mismatch': 244, 'workbook_missing': 211, 'pass': 149, 'sheet_missing': 4}
- A5: {'value_mismatch': 214, 'workbook_missing': 210, 'pass': 184}
- A6: {'value_mismatch': 264, 'pass': 196, 'workbook_missing': 142, 'sheet_missing': 6}
- A7: {'workbook_missing': 332, 'value_mismatch': 147, 'pass': 129}
- A8: {'workbook_missing': 337, 'value_mismatch': 141, 'pass': 129, 'sheet_missing': 1}

## Extraction / c2 activity per arm (raw_extraction_ok, c1_ok, c2_fired) counts

- A1: {(True, True, False): 565, (True, True, True): 40, (False, True, False): 3}
- A1p: {(True, True, False): 544, (True, True, True): 61, (False, True, False): 3}
- A2: {(True, True, False): 557, (True, True, True): 49, (False, True, False): 2}
- A3: {(True, True, False): 557, (True, True, True): 50, (False, True, False): 1}
- A4: {(True, True, False): 560, (True, True, True): 45, (False, True, False): 3}
- A5: {(True, True, False): 540, (True, True, True): 66, (False, True, False): 2}
- A6: {(True, True, False): 539, (True, True, True): 65, (False, True, False): 4}
- A7: {(True, True, False): 540, (False, True, False): 27, (True, True, True): 41}
- A8: {(True, True, False): 530, (True, True, True): 49, (False, True, False): 29}

## Measurement notes (same rollouts, additional facts)

- P4 A/A reference: the same P4 statistic between A1 and A1' (identical env) = 0.667 [0.333, 1.000] (n=6); mean p over the 6 tasks: A1 0.875 -> A1' 0.708.
- P4 paired: on the A4 responses of those 6 tasks the E_sub and E_all verdicts agree rollout-for-rollout: True; on the A1 responses re-scored under E_all the P4 statistic = 1.000 [1.000, 1.000] (n=6).
- c2 fired on 466/5472 rollouts across all arms; passing sub_c12 verdicts among them: 3; passing off_c12: 5.
- substrate extraction failed on 74 rollouts (by arm: {'A4': 3, 'A2': 2, 'A7': 27, 'A1': 3, 'A1p': 3, 'A5': 2, 'A3': 1, 'A6': 4, 'A8': 29}); c1 recovered code on 74 of them, of which sub_c12 PASS: 0, off_c12 PASS: 0.
- c1 selected a different program than the substrate extractor on 277 rollouts where both extracted code; verdict changes (sub_raw -> sub_c12): {('FAIL', 'FAIL'): 230, ('PASS', 'PASS'): 7, ('PASS', 'FAIL'): 40}.
- Official vs substrate verdict on the same outputs, all 5472 rollouts: (sub, off) counts {('PASS', 'PASS'): 1295, ('FAIL', 'FAIL'): 3940, ('FAIL', 'PASS'): 162, ('PASS', 'FAIL'): 75}; substrate-PASS/official-FAIL tasks {'48257': 44, '59734': 12, '54144': 15, '22-47': 4}; substrate-FAIL/official-PASS tasks {'43657': 7, '52541': 13, '52807': 23, '55060': 34, '52216': 7, '49196': 10, '408-5': 8, '41601': 6, '10747': 6, '32337': 2, '183-8': 7, '36097': 5, '54242': 13, '40478': 3, '59196': 1, '31915': 11, '48608': 4, '46167': 1, '52917': 1}. Task 48257: LibreOffice evaluates the golden's array formulas to '#VALUE!' while the cached golden values equal the agent's output.
- R1/H_off on the 26 L1 tasks: 4 pass under E_all with the answer supplied (2 judged authentic); 22 remain unsolved after 5 answer-conditioned attempts.

## R1 (answer-conditioned regeneration under E_all on L1 tasks)

tasks 26; H_off pass 4; authentic 2; attempt histogram {5: 22, 2: 3, 4: 1}

## Caveats (section 7 of the brief)

- Single benchmark, single-program tasks (short horizon), self-written parent skill; temperature 0.7 is not comparable with the earlier temperature-0 protocol.
- L1/L2 depend on the substrate-path answer-condition cache (H_sub); R1 supplies part of the official-path labelling (H_off); the full witness regeneration protocol is left to M4.
- c2 ('save on exception') wraps the agent program; it is not a repair of environment state. Its contribution is reported separately (dose table, c2_fired counts).
- ALFWorld witness false-positive tests are outside E-min (M1/M4).
- Witness W(a) compares two recalculated golden copies, so a golden whose formulas LibreOffice cannot evaluate (48257, '#VALUE!') passes W while the official protocol rejects correct outputs; the witness column sub_recalc_vs_raw (5/76 pool tasks) is the closer detector for this defect class.
- The A/A arm shows the independent-arm design's noise floor: f_AA = 0.184 spurious unlocks and 10/76 zero-status flips between two identical runs. Every pre-registered unlock rate is at or below this floor; the paired re-scoring (supplementary) gives the noise-free version of the same quantities.
- Deviations and nulls: see LOG.md (LibreOffice via extracted AppImage instead of apt; vendored evaluator fetched from GitHub; venv additions; lane relaunch after a cache race; API seed not honoured).
