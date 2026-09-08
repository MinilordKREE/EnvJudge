# E0 reproduction (e0-20260907)

## E0 protocol (PREREG7): single-success banks, ID n=140 / OOD n=134 per seed

Seeds: seeds-0, seeds-1000, seeds-2000; success % pooled (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| nobank (N) | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig (orig) | 68.6 (n=420) [74.3 / 60.7 / 70.7] | 69.2 (n=402) [70.1 / 72.4 / 64.9] | 63.3 | 61.4 |
| R (EnvHarness) | 68.6 (n=420) [72.9 / 64.3 / 68.6] | 63.2 (n=402) [66.4 / 64.9 / 58.2] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +6.9 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -6.0 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +6.9, OOD -0.7 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points):
- orig minus nobank: ID +6.9 ± 3.3, OOD +5.2 ± 3.3
- R minus orig: ID +0.0 ± 3.2, OOD -6.0 ± 3.3
- R minus nobank: ID +6.9 ± 3.3, OOD -0.7 ± 3.4

## Diagnosis (owner decision 1): released Stage 2 banks (per-task cascade, paired-diff where a failure exists), full banks as in reproduce.py's headline eval

Seeds: seeds-0, seeds-1000, seeds-2000; success % pooled (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| nobank (N) | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig_rel (orig) | 68.6 (n=420) [71.4 / 63.6 / 70.7] | 69.4 (n=402) [70.9 / 70.9 / 66.4] | 63.3 | 61.4 |
| R_rel (EnvHarness) | 68.1 (n=420) [72.1 / 65.0 / 67.1] | 68.9 (n=402) [72.4 / 69.4 / 64.9] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +6.9 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -0.5 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +6.4, OOD +5.0 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points):
- orig_rel minus nobank: ID +6.9 ± 3.3, OOD +5.5 ± 3.3
- R_rel minus orig_rel: ID -0.5 ± 3.2, OOD -0.5 ± 3.3
- R_rel minus nobank: ID +6.4 ± 3.3, OOD +5.0 ± 3.3

Corpus: 180 policy episodes, USD 4.30 (USD 0.0239 per episode); designer USD 0.06; induction USD 0.04 (released-pipeline induction USD 0.04).
Eval: 4110 episodes (E0 2466, diagnosis 1644), USD 49.27 (USD 0.0120 per episode).

Projection N=30: corpus USD 84 + confirmations USD 149 + evals USD 138 = USD 371
Projection N=50: corpus USD 140 + confirmations USD 248 + evals USD 138 = USD 526
Backbone rule: corpus episode USD 0.0239 <= 0.10 -> Flash-Lite stays.
