# E1-pilot report — generated 2026-09-06 18:48 UTC

PREREG3 sha `f8080d4`; qwen_map.yaml sha256 `d584098f2d7dfcd5f1152f18c93f595e380916bccabb454fff1100af6f3b5265`; policy model `openai/qwen3-8b` at `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (enable_thinking=false); pricing dashscope-qwen3-8b-2026-09-06 (Qwen) / deepseek-pricing-2026-09-03 (DeepSeek); spend by phase (USD): {'p1_probe': 0.001, 'p1_map': 21.457, 'p2_dose': 5.197, 'p3_induce': 0.13, 'p3_induce_embed': 0.0, 'p3_skills': 5.714, 'p3_skills_embed': 0.0}; total USD 32.50 of the 30 cap.

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

| consumer | zero | edge-low | band | edge-high | saturated |
|---|---|---|---|---|---|
| Qwen3-8B p16 | 0.267 [0.133, 0.433] | 0.067 [0.000, 0.167] | 0.200 [0.067, 0.367] | 0.100 [0.000, 0.233] | 0.367 [0.200, 0.533] |
| Pro p16 | 0.033 [0.000, 0.100] | 0.133 [0.033, 0.267] | 0.200 [0.067, 0.333] | 0.267 [0.133, 0.433] | 0.367 [0.200, 0.533] |
| Flash p8 | 0.000 [0.000, 0.000] | 0.033 [0.000, 0.100] | 0.200 [0.067, 0.367] | 0.167 [0.033, 0.300] | 0.600 [0.433, 0.767] |

Mean p16 (Qwen) = 0.573; parse-failure rate = 0.129 of 15645 policy steps (0 without an <action> tag, 2021 inadmissible); episodes 480, errors 0, mean steps 32.594.

**K1 outcome: both-sides** — zero + edge-low = 0.333, saturated + edge-high = 0.467.

## P2 — structural hardening dose pilot

Targets: 11 tasks; regime qwen; rollouts 144; dose outcomes {'NOEFFECT': 22, 'UNCERTIFIED': 9, 'ZERO': 11, 'INFEASIBLE': 12, 'IN-BAND': 1}; certificate sources {'R_pol': 31, 'uncertified': 9, 'R_exp': 3}.

| task | type | hit | hit dose | rollouts to hit | total rollouts | F_S0 max-dose class | F_O max-dose class | infeasible | uncertified |
|---|---|---|---|---|---|---|---|---|---|
| 1 | pick_clean_then_place_in_recep | False |  |  | 20 | NOEFFECT | ZERO | 0 | 1 |
| 2 | pick_two_obj_and_place | False |  |  | 8 | none-feasible | ZERO | 2 | 1 |
| 7 | pick_and_place_simple | False |  |  | 12 | NOEFFECT | ZERO | 2 | 0 |
| 12 | pick_two_obj_and_place | False |  |  | 8 | none-feasible | ZERO | 3 | 0 |
| 13 | pick_clean_then_place_in_recep | False |  |  | 16 | NOEFFECT | ZERO | 1 | 0 |
| 15 | pick_cool_then_place_in_recep | False |  |  | 12 | NOEFFECT | ZERO | 0 | 2 |
| 21 | pick_and_place_simple | True | F_O:0.5 | 20 | 24 | NOEFFECT | ZERO | 0 | 0 |
| 22 | pick_two_obj_and_place | False |  |  | 8 | none-feasible | ZERO | 0 | 3 |
| 24 | pick_cool_then_place_in_recep | False |  |  | 12 | NOEFFECT | ZERO | 0 | 2 |
| 25 | look_at_obj_in_light | False |  |  | 8 | none-feasible | ZERO | 3 | 0 |
| 29 | pick_clean_then_place_in_recep | False |  |  | 16 | NOEFFECT | ZERO | 1 | 0 |

Share of target tasks reaching IN-BAND with ≤ 16 rollouts = 0.000 [0.000, 0.000] (n=11, tasks=11); median rollouts-to-hit = 20.
Share still NOEFFECT (or infeasible) at the maximum feasible dose of BOTH families = 0.000 [0.000, 0.000] (n=11, tasks=11).

**K2 outcome: dead for this policy (< 0.30)**; **K2′: no expressivity ceiling (< 0.40)**.

Dose–response rows (all doses with rollouts) are in p2_curves.csv.

## P3 — downstream skill sanity (P3a: nobank / orig; P3b: orig_m / ours)

| condition | split | tasks | episodes | success | CI |
|---|---|---|---|---|---|
| nobank | eval_in_distribution | 30 | 90 | 0.444 | [0.300, 0.589] |
| nobank | eval_out_of_distribution | 30 | 90 | 0.322 | [0.178, 0.478] |
| orig | eval_in_distribution | 30 | 90 | 0.422 | [0.256, 0.589] |
| orig | eval_out_of_distribution | 30 | 90 | 0.433 | [0.267, 0.600] |
| orig_m | eval_in_distribution | 30 | 90 | 0.589 | [0.422, 0.756] |
| orig_m | eval_out_of_distribution | 30 | 90 | 0.467 | [0.311, 0.622] |
| ours | eval_in_distribution | 30 | 90 | 0.344 | [0.189, 0.511] |
| ours | eval_out_of_distribution | 30 | 90 | 0.289 | [0.144, 0.444] |
| ours - orig_m (paired per task) | eval_in_distribution | 30 |  | -0.244 | [-0.411, -0.078] |
| ours - orig (paired per task) | eval_in_distribution | 30 |  | -0.078 | [-0.278, 0.122] |
| ours - nobank (paired per task) | eval_in_distribution | 30 |  | -0.100 | [-0.222, 0.011] |
| ours - orig_m (paired per task) | eval_out_of_distribution | 30 |  | -0.178 | [-0.378, 0.022] |
| ours - orig (paired per task) | eval_out_of_distribution | 30 |  | -0.144 | [-0.400, 0.111] |
| ours - nobank (paired per task) | eval_out_of_distribution | 30 |  | -0.033 | [-0.200, 0.144] |

Held-out = first 30 tasks of each released split (start seed 0), the SAME tasks × 3 replicates (owner deviation from the released 0/1000/2000 rounds). Banks: orig = P3a bank from all 30 train tasks; orig_m = matched-original (8 P1 trajectories on each of the 9 in-band tasks); ours = 8 Qwen rollouts on each in-band controlled env (P2b hit dose). Item counts: orig 67, orig_m 23, ours 9 (trajectory counts matched; the released induction emits fewer items from paired success/failure trajectories).

**K3 outcome: SL line at risk (< −0.02); the RL Study becomes the primary downstream evidence** — ours − orig_m (paired per task): in-distribution -0.244 [-0.411, -0.078]; out-of-distribution -0.178 [-0.378, 0.022]; threshold −0.02 on the in-distribution split.

## Measurement notes

- Parse failure = no <action> tag or a command outside the admissible list shown to the policy; computed per step from traces.
- Certificates: R_pol replays the shortest successful baseline trajectory of the same policy; R_exp is the stochastic handcoded expert (≤ 3 attempts) from the staged state; uncertified doses are skipped and counted.
- F_S0 placement verb fixed to `move <obj> to <recep>` before any dose was run (LOG).

## Caveats

- Qwen3-8B via the DashScope API (international endpoint), not local weights; single benchmark; N = 30; operator library of two families; no EnvRigger comparison under Qwen yet.
