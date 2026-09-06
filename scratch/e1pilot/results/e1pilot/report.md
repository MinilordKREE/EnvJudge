# E1-pilot report — generated 2026-09-06 03:55 UTC

PREREG3 sha `f8080d4`; qwen_map.yaml sha256 `101bfad5ec3285d75054f0bbd06cfcfbd01176150485906d7646c5b88d805501`; policy model `openai/qwen3-8b` at `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (enable_thinking=false); pricing dashscope-qwen3-8b-2026-09-06 (Qwen) / deepseek-pricing-2026-09-03 (DeepSeek); spend by phase (USD): {'p1_probe': 0.0}; total USD 0.00 of the 30 cap.

## P0 — ΔSR by operator type (E-obs H arm, saturated tasks)

| set | operator | n | tasks | mean SR_c | share SR ≤ 0.6 | share in band | share accepted |
|---|---|---|---|---|---|---|---|
| S_H | A:block(literal) | 20 | 10 | 0.930 [0.883, 0.987] | 0.050 [0.000, 0.120] | 0.000 [0.000, 0.000] | 0.100 [0.000, 0.263] |
| S_H | T:nothing_happens | 14 | 10 | 0.914 [0.850, 1.000] | 0.071 [0.000, 0.214] | 0.071 [0.000, 0.214] | 0.214 [0.000, 0.333] |
| S_H | O:admissible | 7 | 6 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | S0:setup_actions | 7 | 4 | 0.971 [0.880, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.143 [0.000, 0.600] |
| S_H | T:text_edit | 3 | 3 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | O:text | 3 | 3 | 0.867 [0.600, 1.000] | 0.333 [0.000, 1.000] | 0.333 [0.000, 1.000] | 0.333 [0.000, 1.000] |
| S_H | T:nothing_happens+random | 2 | 2 | 0.900 [0.800, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.500 [0.000, 1.000] |
| S_H | A:block(regex) | 2 | 1 | 0.900 [0.900, 0.900] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | S0:setup_actions+O:admissible | 1 | 1 | 0.400 [0.400, 0.400] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| S_H | none | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | A:block(literal)+O:text | 1 | 1 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | T:nothing_happens+random+O:text | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | A:block(literal)+T:text_edit | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H | A:block(literal)+O:admissible | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | A:block(literal) | 22 | 12 | 0.918 [0.864, 0.978] | 0.091 [0.000, 0.211] | 0.045 [0.000, 0.174] | 0.136 [0.000, 0.333] |
| S_H_prime | T:nothing_happens | 18 | 12 | 0.900 [0.842, 0.971] | 0.111 [0.000, 0.235] | 0.111 [0.000, 0.235] | 0.222 [0.071, 0.333] |
| S_H_prime | O:admissible | 10 | 8 | 0.940 [0.836, 1.000] | 0.100 [0.000, 0.273] | 0.100 [0.000, 0.273] | 0.000 [0.000, 0.000] |
| S_H_prime | S0:setup_actions | 9 | 5 | 0.822 [0.514, 1.000] | 0.222 [0.000, 0.667] | 0.111 [0.000, 0.333] | 0.222 [0.000, 0.571] |
| S_H_prime | T:text_edit | 4 | 4 | 0.950 [0.850, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | O:text | 4 | 4 | 0.900 [0.700, 1.000] | 0.250 [0.000, 0.750] | 0.250 [0.000, 0.750] | 0.250 [0.000, 0.750] |
| S_H_prime | T:nothing_happens+random | 2 | 2 | 0.900 [0.800, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.500 [0.000, 1.000] |
| S_H_prime | A:block(literal)+T:text_edit | 2 | 2 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | A:block(regex) | 2 | 1 | 0.900 [0.900, 0.900] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | S0:setup_actions+O:admissible | 1 | 1 | 0.400 [0.400, 0.400] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| S_H_prime | none | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | A:block(literal)+O:text | 1 | 1 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | T:nothing_happens+random+O:text | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| S_H_prime | A:block(literal)+O:admissible | 1 | 1 | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |

## P1 — Qwen3-8B regime map

P1 not run (DashScope model access pending).

## P2 — structural hardening dose pilot

P2 not run.


## P3 — downstream skill sanity

Not run (gated; owner approval after P2).

## Measurement notes

- Parse failure = no <action> tag or a command outside the admissible list shown to the policy; computed per step from traces.
- Certificates: R_pol replays the shortest successful baseline trajectory of the same policy; R_exp is the stochastic handcoded expert (≤ 3 attempts) from the staged state; uncertified doses are skipped and counted.
- F_S0 placement verb fixed to `move <obj> to <recep>` before any dose was run (LOG).

## Caveats

- Qwen3-8B via the DashScope API (international endpoint), not local weights; single benchmark; N = 30; operator library of two families; no EnvRigger comparison under Qwen yet.
