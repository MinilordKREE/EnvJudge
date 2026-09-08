# E0 reproduction (e0-20260907)

Seeds (released eval rounds): seeds-0, seeds-1000, seeds-2000; splits ID n=140, OOD n=134 per seed; success % pooled over seeds (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| N | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig | 68.6 (n=420) [74.3 / 60.7 / 70.7] | 69.2 (n=402) [70.1 / 72.4 / 64.9] | 63.3 | 61.4 |
| EnvHarness | 68.6 (n=420) [72.9 / 64.3 / 68.6] | 63.2 (n=402) [66.4 / 64.9 / 58.2] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +6.9 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -6.0 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +6.9, OOD -0.7 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points; per-seed sign in the table above):
- orig minus N: ID +6.9 ± 3.3, OOD +5.2 ± 3.3
- EnvRigger minus orig: ID +0.0 ± 3.2, OOD -6.0 ± 3.3
- EnvRigger minus N: ID +6.9 ± 3.3, OOD -0.7 ± 3.4

Corpus: 180 policy episodes, USD 4.30 (USD 0.0239 per episode); designer USD 0.06; induction USD 0.04.
Eval: 2466 episodes, USD 29.13 (USD 0.0118 per episode).

Projection N=30: corpus USD 84 + confirmations USD 149 + evals USD 136 = USD 369
Projection N=50: corpus USD 140 + confirmations USD 248 + evals USD 136 = USD 524
Backbone rule: corpus episode USD 0.0239 <= 0.10 -> Flash-Lite stays.
