# E0 reproduction (e0d1-20260908)

## E0 protocol (PREREG7): single-success banks, ID n=140 / OOD n=134 per seed

Seeds: seeds-0, seeds-1000, seeds-2000; success % pooled (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| nobank (N) | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig (orig) | nan (n=0) [- / - / -] | nan (n=0) [- / - / -] | 63.3 | 61.4 |
| R (EnvHarness) | nan (n=0) [- / - / -] | nan (n=0) [- / - / -] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +nan pts (Table 2 +0.7) -> NOT reproduced
- EnvRigger > orig on OOD: ours +nan pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +nan, OOD +nan (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points):
- orig minus nobank: ID n/a, OOD n/a
- R minus orig: ID n/a, OOD n/a
- R minus nobank: ID n/a, OOD n/a

## Diagnosis (owner decision 1): released Stage 2 banks (per-task cascade, paired-diff where a failure exists), full banks as in reproduce.py's headline eval

Seeds: seeds-0, seeds-1000, seeds-2000; success % pooled (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| nobank (N) | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig_100 (orig) | 72.4 (n=420) [75.7 / 67.9 / 73.6] | 65.4 (n=402) [64.2 / 67.9 / 64.2] | 63.3 | 61.4 |
| R_100 (EnvHarness) | 69.5 (n=420) [75.7 / 67.9 / 65.0] | 63.2 (n=402) [68.7 / 61.2 / 59.7] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +10.7 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -2.2 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +7.9, OOD -0.7 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points):
- orig_100 minus nobank: ID +10.7 ± 3.2, OOD +1.5 ± 3.4
- R_100 minus orig_100: ID -2.9 ± 3.1, OOD -2.2 ± 3.4
- R_100 minus nobank: ID +7.9 ± 3.3, OOD -0.7 ± 3.4

Corpus: 840 policy episodes, USD 24.70 (USD 0.0294 per episode); designer USD 0.31; induction USD 0.00 (released-pipeline induction USD 0.22).
Eval: 2466 episodes (E0 822, diagnosis 1644), USD 19.84 (USD 0.0080 per episode).

Projection N=30: corpus USD 120 + confirmations USD 183 + evals USD 93 = USD 396
Projection N=50: corpus USD 201 + confirmations USD 306 + evals USD 93 = USD 599
Backbone rule: corpus episode USD 0.0294 <= 0.10 -> Flash-Lite stays.
