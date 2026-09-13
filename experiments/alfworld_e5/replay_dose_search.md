# Offline replay of the saturated-side search rules on the E3 bracket evidence

Brackets replayed: 13 (E3 v0.2 run + E3b v0.3 run), in run order per family. The oracle treats each task's observed gap (lo_t, hi_t) as its band; a rule 'reaches' when a probe lands inside it within that task's remaining budget; 'censored' means the rule's search interval excluded the observed region because of OTHER tasks' observations.

| family | tasks | rule | reachable | censored | reached band | probes | rollouts |
|---|---|---|---|---|---|---|---|
| footer_mask | 8 | v0.2 | 8 | 0 | 2 | 21 | 92 |
| footer_mask | 8 | v0.3 | 7 | 1 | 6 | 13 | 76 |
| footer_mask | 8 | v0.4 | 8 | 0 | 5 | 14 | 76 |
| observation_noise | 3 | v0.2 | 3 | 0 | 1 | 6 | 28 |
| observation_noise | 3 | v0.3 | 2 | 1 | 0 | 8 | 32 |
| observation_noise | 3 | v0.4 | 3 | 0 | 1 | 6 | 28 |
| observation_noise_insertion | 1 | v0.2 | 1 | 0 | 1 | 3 | 16 |
| observation_noise_insertion | 1 | v0.3 | 1 | 0 | 1 | 3 | 16 |
| observation_noise_insertion | 1 | v0.4 | 1 | 0 | 1 | 3 | 16 |
| command_swap | 1 | v0.2 | 1 | 0 | 1 | 1 | 8 |
| command_swap | 1 | v0.3 | 1 | 0 | 1 | 1 | 8 |
| command_swap | 1 | v0.4 | 1 | 0 | 1 | 1 | 8 |

## Per task (families with >= 3 tasks)

| family | task | observed (lo_t, hi_t) | budget left | v0.2 start / reached / probes | v0.3 interval / reached / censored | v0.4 start / reached / probes |
|---|---|---|---|---|---|---|
| footer_mask | 3 | (0.875, 1.0) | 12 | 0.5 / False / 3 | [0.875, 1] / False / False | 0.5 / False / 3 |
| footer_mask | 7 | (0.75, 1.0) | 8 | 0.5 / False / 2 | [0.875, 1] / True / False | 0.5 / False / 2 |
| footer_mask | 12 | (0.875, 1.0) | 12 | 0.5 / False / 3 | [0.875, 1] / True / False | 0.5 / False / 3 |
| footer_mask | 13 | (0.75, 1.0) | 16 | 0.5 / True / 3 | [0.875, 1] / True / False | 0.9375 / True / 1 |
| footer_mask | 15 | (0.25, 0.5) | 16 | 0.5 / True / 3 | [0.875, 0.8828] / False / True | 0.9375 / True / 2 |
| footer_mask | 22 | (0.75, 1.0) | 8 | 0.5 / False / 2 | [0.875, 0.8828] / True / False | 0.9375 / True / 1 |
| footer_mask | 25 | (0.5, 1.0) | 8 | 0.5 / False / 2 | [0.875, 0.8828] / True / False | 0.9375 / True / 1 |
| footer_mask | 29 | (0.875, 1.0) | 12 | 0.5 / False / 3 | [0.875, 0.8828] / True / False | 0.9375 / True / 1 |
| observation_noise | 28 | (0.125, 0.25) | 16 | 0.5 / False / 4 | [0.125, 0.25] / False / False | 0.5 / False / 4 |
| observation_noise | 21 | (0.0, 1.0) | 2 | 0.5 / False / 0 | [0.125, 0.25] / False / False | 0.5 / False / 0 |
| observation_noise | 1 | (0.5, 1.0) | 16 | 0.5 / True / 2 | [0.2422, 0.25] / False / True | 0.5 / True / 2 |

## E3b (v0.3 run) brackets, replayed but not counted

| family | tasks | rule | reachable | censored | reached band | probes | rollouts |
|---|---|---|---|---|---|---|---|
| footer_mask | 10 | v0.2 | 10 | 0 | 7 | 9 | 64 |
| footer_mask | 10 | v0.3 | 10 | 0 | 0 | 20 | 80 |
| footer_mask | 10 | v0.4 | 10 | 0 | 7 | 9 | 64 |
| footer_shuffle | 1 | v0.2 | 1 | 0 | 0 | 2 | 8 |
| footer_shuffle | 1 | v0.3 | 1 | 0 | 0 | 2 | 8 |
| footer_shuffle | 1 | v0.4 | 1 | 0 | 0 | 2 | 8 |
| goal_obfuscation | 1 | v0.2 | 1 | 0 | 0 | 4 | 16 |
| goal_obfuscation | 1 | v0.3 | 1 | 0 | 0 | 4 | 16 |
| goal_obfuscation | 1 | v0.4 | 1 | 0 | 0 | 4 | 16 |
| command_typo | 1 | v0.2 | 1 | 0 | 0 | 4 | 16 |
| command_typo | 1 | v0.3 | 1 | 0 | 0 | 4 | 16 |
| command_typo | 1 | v0.4 | 1 | 0 | 0 | 4 | 16 |
| command_alias_swap | 1 | v0.2 | 1 | 0 | 0 | 4 | 16 |
| command_alias_swap | 1 | v0.3 | 1 | 0 | 0 | 4 | 16 |
| command_alias_swap | 1 | v0.4 | 1 | 0 | 0 | 4 | 16 |
| observation_noise_typos | 1 | v0.2 | 1 | 0 | 0 | 2 | 8 |
| observation_noise_typos | 1 | v0.3 | 1 | 0 | 0 | 2 | 8 |
| observation_noise_typos | 1 | v0.4 | 1 | 0 | 0 | 2 | 8 |
