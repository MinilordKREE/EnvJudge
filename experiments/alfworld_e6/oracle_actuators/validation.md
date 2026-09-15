# Oracle actuator offline validation (before the freeze; LLM-free; no current-policy call)

| task | class / family | code sha | validation reasons | ref replay original / d=0 / d=1 (won, steps) | identity at 0 on env | support events on a failure prefix at d = 0.25 / 0.5 / 0.75 / 1 | monotone | expert under W(1) | offline valid |
|---|---|---|---|---|---|---|---|---|---|
| 85 | S / explored_receptacle_pruning | e5534269381e3916 | - | won 15 / won 15 / won 15 (blocked 0) | True | 5 / 8 / 8 / 10 | True | oracle True | True |
| 86 | G / goal_decomposition_annotation | 70992eda167f2199 | - | won 48 / won 48 / won 48 (blocked 0) | True | 3 / 6 / 9 / 12 | True | oracle True | True |
| 92 | P / precondition_gating | 796a166826347706 | - | won 48 / won 48 / won 48 (blocked 0) | True | 0 / 0 / 0 / 1 | True | oracle True | True |
| 97 | P / precondition_gating | dc89dcd9b1f4dc2e | - | won 14 / won 14 / won 14 (blocked 0) | True | 0 / 1 / 1 / 2 | True | oracle True | True |
| 99 | P / precondition_gating | d5a0e8fd494405f0 | - | won 6 / won 6 / won 6 (blocked 0) | True | 0 / 0 / 0 / 1 | True | oracle True | True |
| 107 | P / precondition_gating | 3cd952c0a4cf71c4 | - | won 8 / won 8 / won 8 (blocked 0) | True | 0 / 0 / 0 / 1 | True | oracle True | True |
| 109 | S / explored_receptacle_pruning | c685b2d9c4506195 | - | won 7 / won 7 / won 7 (blocked 0) | True | 0 / 0 / 0 / 4 | True | oracle True | True |
