# E-min verdict — generated 2026-09-05 07:48 UTC

Pre-registration: `PREREG.md` @ git sha `0a07fa23ebce6cdb10dc181fa8f783dcfc743757`. Rollouts per arm: A1=0, A1p=0, A2=0, A3=0, A4=0, A5=0, A6=0, A7=0, A8=0.
Spend so far: 20 API calls, USD 0.02 at the applicable tariff (USD 0.04 at the peak bound). Budget: hard 20 / soft 12.

## Overall (section 3 rule): **INCONCLUSIVE (arms missing)**

Rule: GO = P1 ∧ P2(Pro) ∧ P5-direction; CONDITIONAL = P1 ∧ ¬P2; NO-GO = ¬P1 ∧ ¬P2; P4 failure adds 'implementation-suspect'. Bold is used only for the overall call; every rate below carries a 10,000-resample task-level bootstrap 95% CI, and 'CI-decisive' means the CI excludes the threshold.

## Predictions

### P1 mixture: inconclusive

A1 not run.

### P2 interaction (Pro): unlock(L1) - unlock(L2) >= 0.25 and unlock(L1) >= 0.40 in E_all: inconclusive

A4 not run or a label group is empty (L1 n=0, L2 n=0).

### P3 dose: inconclusive

A2/A3/A4 not all run.

### P4 harmlessness: inconclusive

A4 not run or no task with p0 >= 0.875.

### P5 consumer (Flash): inconclusive

A7/A8 not run or a Flash label group is empty.

### P6 phi: inconclusive

A1/A4/A5 not all run.

### P7 baseline misrouting: inconclusive

A1 not run.

### P8 witness bias: inconclusive

witness_probe.csv missing.

## Regime counts (Pro labels from A1)

p0=0: 0; labels: {'n/a': 76}

Flash (A7) p0=0: 0; labels: {'n/a': 76}

## A/A (A1 vs A1', parent⁻, E_sub, Pro)

f_AA = P(p(A1') > 0 | p(A1) = 0) = nan [nan, nan] (n=0); reverse = nan [nan, nan] (n=0); zero-status flips = 0/76; regime-label flips = 0/76; mean |Δp| = nan; |Δp| quantiles (50/75/90/100) = []; histogram = {}.

## Per-arm summary (aa_band.csv)

| arm | agent | env | consumer | rollouts | mean p | zero share | full share | band [2..6]/8 share |
|---|---|---|---|---|---|---|---|---|

## Unlock rates (unlock_rates.csv)

| consumer | label | env | arm | n | unlocked | rate [CI] | rate − f_AA |
|---|---|---|---|---|---|---|---|

## Dose table (dose_table.csv)


## φ (phi.csv)


## Supplementary (not pre-registered): paired re-scoring of the A1 responses under the four env verdicts

The prompt does not depend on the env, so every A1 response can be re-scored under E_sub/E_c12/E_off/E_all; this is a paired estimate of the same quantities the independent arms A2–A4 estimate.


## Primary failure reasons per arm


## Extraction / c2 activity per arm (raw_extraction_ok, c1_ok, c2_fired) counts


## Caveats (section 7 of the brief)

- Single benchmark, single-program tasks (short horizon), self-written parent skill; temperature 0.7 is not comparable with the earlier temperature-0 protocol.
- L1/L2 depend on the substrate-path answer-condition cache (H_sub); R1 supplies part of the official-path labelling (H_off); the full witness regeneration protocol is left to M4.
- c2 ('save on exception') wraps the agent program; it is not a repair of environment state. Its contribution is reported separately (dose table, c2_fired counts).
- ALFWorld witness false-positive tests are outside E-min (M1/M4).
- Deviations and nulls: see LOG.md (LibreOffice via extracted AppImage instead of apt; vendored evaluator fetched from GitHub; venv additions).
