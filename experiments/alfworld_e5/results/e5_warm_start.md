# E5 — soft warm start of the saturated-side dose search: v0.2 (A2) vs v0.4 (A4)

PREREG12 @ 9b29b26. Same code (tag aea-v0.4), same policy, families (library only, proposer off), guard, verdict, acceptance, cap 30, task order 3, 12, 13, 15, 22, 23, 24, 29; the only difference is the first interior probe of a bracket: 0.5 (A2) vs the median of >= 3 previous task frontiers (A4). Tables from scripts/make_tables_e5.py.

## Per task

| task | arm | estimate (regime, p_hat, n) | outcome:reason | rollouts | families w/o leverage | first interior probe | doses (d: s/n verdict) | accepted d | final local [lo, hi] | warm start | recovered |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | A2 | saturated, 0.938, 16 | dropped:budget | 28 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy | - | [0.75, 1.0] | - | - |
| 3 | A4 | saturated, 0.875, 16 | dropped:budget | 28 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy | - | [0.75, 1.0] | n/a (no history) | - |
| 12 | A2 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy/0.875:4/4 too_easy/0.9375:0/4 too_hard | - | [0.875, 0.9375] | - | - |
| 12 | A4 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy/0.875:4/4 too_easy/0.9375:0/4 too_hard | - | [0.875, 0.9375] | n/a (no history) | - |
| 13 | A2 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:6/8 too_easy/0.75:4/4 too_easy | - | [0.75, 1.0] | - | - |
| 13 | A4 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:7/8 too_easy/0.875:0/4 too_hard | - | [0.75, 0.875] | n/a (no history) | - |
| 15 | A2 | saturated, 1.000, 10 | accepted | 22 | - | 0.5000 | 1.0:0/4 too_hard/0.5:3/8 in_band | 0.5000 | [0.0, 1.0] | - | - |
| 15 | A4 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.8750 | 1.0:0/4 too_hard/0.875:0/4 too_hard/0.4375:4/4 too_easy/0.65625:4/4 too_easy/0.765625:4/4 too_easy | - | [0.765625, 0.875] | harmful | no |
| 22 | A2 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy/0.875:0/4 too_hard/0.8125:4/4 too_easy | - | [0.8125, 0.875] | - | - |
| 22 | A4 | saturated, 1.000, 10 | accepted | 22 | - | 0.8477 | 1.0:0/4 too_hard/0.847656:5/8 in_band | 0.8477 | [0.0, 1.0] | helpful | - |
| 23 | A2 | saturated, 1.000, 10 | accepted | 26 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:5/8 in_band | 0.7500 | [0.5, 1.0] | - | - |
| 23 | A4 | saturated, 1.000, 10 | accepted | 22 | - | 0.8477 | 1.0:0/4 too_hard/0.847656:4/8 in_band | 0.8477 | [0.0, 1.0] | helpful | - |
| 24 | A2 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy/0.875:6/8 too_easy | - | [0.875, 1.0] | - | - |
| 24 | A4 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.8477 | 1.0:0/4 too_hard/0.847656:4/4 too_easy/0.923828:4/4 too_easy/0.961914:4/4 too_easy/0.980957:0/4 too_hard | - | [0.961914, 0.980957] | harmful | no |
| 29 | A2 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.5000 | 1.0:0/4 too_hard/0.5:4/4 too_easy/0.75:4/4 too_easy/0.875:4/4 too_easy/0.9375:4/4 too_easy | - | [0.9375, 1.0] | - | - |
| 29 | A4 | saturated, 1.000, 10 | dropped:budget | 30 | - | 0.8477 | 1.0:0/4 too_hard/0.847656:4/4 too_easy/0.923828:4/4 too_easy/0.961914:0/4 too_hard/0.942871:4/4 too_easy | - | [0.942871, 0.961914] | neutral | - |

## Aggregates

| arm | saturated tasks tested | accepted in band | charged rollouts (all / saturated) | rollouts per task | rollouts per accepted task | confirmed learnable (K16) | precision |
|---|---|---|---|---|---|---|---|
| A2 | 8 | 2 (15, 23) | 226 / 226 | 28.2 | 113.0 | 1 | 50% |
| A4 | 8 | 2 (22, 23) | 222 / 222 | 27.8 | 111.0 | 2 | 100% |

## Decision (PREREG12 rule, applied as written)

- A. rollouts per accepted task: A2 113.0 vs A4 111.0 → >= 20% reduction no.
- B. confirmed accepted environments: A2 1 vs A4 2 → >= 1 more yes.
- warm starts: {'n/a (no history)': 3, 'harmful': 2, 'helpful': 2, 'neutral': 1}; harmful 2 (15, 24), of which not recovered 2 (15, 24); no irreversible collapse NO; precision not worse yes.

**REVERT TO v0.2; cross-task prior not worth the complexity.**

## Spend and incidents

| run | budgets | total |
|---|---|---|
| e5-A2 | search 3.11 | 3.11 |
| e5-A4 | search 3.13 | 3.13 |
| e5-confirm | eval 1.83 | 1.83 |

E5 total USD 8.07 (cap 70); ledgered retries 1714; errored rollouts A2 0, A4 0.
