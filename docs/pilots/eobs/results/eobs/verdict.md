# E-obs verdict — generated 2026-09-06 00:05 UTC

PREREG sha `b6cb9a5`; config sha256 `b20f0a9ab53bf26f74a13f9e290e29e49dfeb3afec6a17d065bd23ffb554b255`; PREREG_H sha `75a1fb3`; H config sha256 `6fb506cda314dbbe09ea12ea26e228710cf16052cd2dc2efd12b3b9109c63598`; N = 30; spend USD 19.69 (peak-bound 39.38) over 38259 calls; candidates released/H = 18/106; certificates = 124; recoverability trajectories = 126.

## Predictions, released arm (10,000-resample task-level bootstrap 95% CIs; 'CI-decisive' = CI excludes the threshold)

### O1 witness coverage: W_base >= 0.95: contradicted (CI not decisive)

W_base (expert from reset, cap 150 steps) = 0.867 [0.733, 0.967] (n=30, tasks=30); W_base within the policy cap of 50 steps = 0.867 [0.733, 0.967] (n=30, tasks=30). Expert-failure reasons on non-witnessed tasks (expert calibration from reset): {'verifier_fail': 4}; tasks: ['2', '4', '5', '22']. Branch: free-witness availability; size of the no-witness bucket.

### O2 bimodality: share of tasks with p16 in [0.2, 0.8] <= 0.35: supported (CI-decisive)

share = 0.200 [0.067, 0.333] (n=30, tasks=30); p16 histogram = {0.0: 1, 0.06: 1, 0.12: 1, 0.19: 2, 0.38: 1, 0.44: 1, 0.5: 1, 0.69: 1, 0.75: 2, 0.81: 2, 0.88: 3, 0.94: 3, 1.0: 11}. Branch: whether saturated/zero regimes dominate under DeepSeek.

### O3 0/5 unreliability: among p5 = 0 tasks, share with p16 > 0 >= 0.20: supported (CI not decisive)

share = 0.667 [0.000, 1.000] (n=3, tasks=3) (p5 = 0 tasks: ['18', '19', '21']). Branch: sequential estimation vs fixed K=5.

### O4 transformation-induced zero success: (a) SR_c=0 share >= 0.15; (b) certified among them >= 0.30; (c) treated as unsolvable among certified >= 0.30: contradicted

(a) 0.056 [0.000, 0.136] (n=18, tasks=7) -> contradicted (CI-decisive)
(b) 1.000 [1.000, 1.000] (n=1, tasks=1) -> supported (CI-decisive)
(c) 1.000 [1.000, 1.000] (n=1, tasks=1) -> supported (CI-decisive)
All three sub-items contradicted: False. Uninformative by construction on the released arm (scaffold-only prompt, see PREREG_H).
Branch (§4): whether a certification layer changes any decision.

### O5 old-witness false alarm: certified A/T candidates with R_old = 0 >= 0.30; certified O-only with R_old = 1 >= 0.90: inconclusive

A/T: 0.200 [0.000, 1.000] (n=5, tasks=3) -> contradicted (CI not decisive)
O-only: nan [nan, nan] (n=0, tasks=0) -> inconclusive Uninformative by construction on the released arm (scaffold-only prompt, see PREREG_H).
Branch: per-axis certificates vs single replay.

### O7 saturated waste: among p5 = 1 tasks, share with no ACCEPT >= 0.25: supported (CI-decisive)

share = 1.000 [1.000, 1.000] (n=14, tasks=14). On the released arm the ALFWorld designer block instructs SKIP at baseline_sr >= 0.8 (skip_passthrough_candidates: true), so 'no ACCEPT' holds by construction: UNINFORMATIVE. Branch: harden branch (freeze/reallocate vs keep hardening).

### O8 descriptive: descriptive

validation rollouts on SR_c=0 candidates: 5/90 = 0.056; rollouts per ACCEPT = 18.000 (5 accepts over 18 validated candidates); R_hint attempts 3 over 3 candidates, 3 certified by hint (1.000 attempts per hint-certified candidate).

### O6 recoverability: L >= 2 share >= 0.50; non-monotone share >= 0.20: L>=2 supported (CI-decisive); non-monotone supported (CI-decisive)

CONSERVATIVE (expert failure counts C=0): L>=2 0.944 [0.869, 1.000] (n=126, tasks=19) -> supported (CI-decisive); non-monotone 0.667 [0.451, 0.853] (n=126, tasks=19) -> supported (CI-decisive).
EXCLUDED (expert-failure prefixes dropped): L>=2 0.944 [0.867, 1.000] (n=126, tasks=19) -> supported (CI-decisive); non-monotone 0.667 [0.451, 0.857] (n=126, tasks=19) -> supported (CI-decisive).
L/T histogram (bins of 0.1, conservative): {'0.0': 31, '0.1': 6, '0.2': 3, '0.3': 5, '0.4': 2, '0.5': 8, '0.6': 13, '0.7': 6, '0.8': 32, '0.9': 19}; trajectories = 126; prefixes evaluated = 6426; expert failures by class = {'expert_stuck': 1}; recover_mode = ['handcoded_closed_loop'].
Branch: material for a certified self-prefix Stage; bisection admissible only if non-monotone < 0.20.

## Predictions, hardening arm (PREREG_H: App. G configuration)

### O4H transformation-induced zero success: (a) SR_c=0 share >= 0.15; (b) certified among them >= 0.30; (c) treated as unsolvable among certified >= 0.30: contradicted

(a) 0.094 [0.019, 0.188] (n=106, tasks=29) -> contradicted (CI not decisive)
(b) 0.800 [0.500, 1.000] (n=10, tasks=5) -> supported (CI-decisive)
(c) 1.000 [1.000, 1.000] (n=8, tasks=4) -> supported (CI-decisive)
All three sub-items contradicted: False.
Branch (§4): whether a certification layer changes any decision.

### O5H old-witness false alarm: certified A/T candidates with R_old = 0 >= 0.30; certified O-only with R_old = 1 >= 0.90: supported

A/T: 0.318 [0.169, 0.474] (n=66, tasks=26) -> supported (CI not decisive)
O-only: 0.963 [0.875, 1.000] (n=27, tasks=17) -> supported (CI not decisive)
Branch: per-axis certificates vs single replay.

### O7H saturated waste: among p5 = 1 tasks, share with no ACCEPT >= 0.25: supported (CI not decisive)

share = 0.471 [0.235, 0.706] (n=17, tasks=17). Branch: harden branch (freeze/reallocate vs keep hardening).

### O8H descriptive: descriptive

validation rollouts on SR_c=0 candidates: 50/530 = 0.094; rollouts per ACCEPT = 27.895 (19 accepts over 106 validated candidates); R_hint attempts 45 over 35 candidates, 31 certified by hint (1.452 attempts per hint-certified candidate).

## S1 outcome: **proceed to method design with the branches selected above**

Rule (PREREG §4, evaluated on the released arm): stop iff O4(a)∧(b)∧(c) are ALL contradicted AND O6 (L>=2 share) is contradicted; otherwise proceed to method design with the branches above. No GO/NO-GO on the method.

## Descriptive tables

### Task type × regime (p16)

| type | zero | edge | band | saturated | n/a |
|---|---|---|---|---|---|
| look_at_obj_in_light | 0 | 0 | 1 | 2 | 0 |
| pick_and_place_simple | 0 | 1 | 0 | 1 | 0 |
| pick_clean_then_place_in_recep | 0 | 2 | 2 | 4 | 0 |
| pick_cool_then_place_in_recep | 0 | 2 | 2 | 3 | 0 |
| pick_heat_then_place_in_recep | 1 | 2 | 0 | 0 | 0 |
| pick_two_obj_and_place | 0 | 5 | 1 | 1 | 0 |

### Axis × certificate outcomes (released arm)

| axis | n | SR_c=0 | certified | unresolved | R_old=1 | R_exp=1 |
|---|---|---|---|---|---|---|
| S0 | 13 | 1 | 13 | 0 | 12 | 12 |
| T | 5 | 0 | 5 | 0 | 4 | 4 |

### Decision × certified (released arm)

{('reject', 'certified'): 10, ('accept', 'certified'): 5, ('refine', 'certified'): 3}

### reverse_or_loosen matches for audit (released arm; 1 candidates)

- task 21 cand 7dac1475 [reject]: [unsolvable] …sing a recoverable failure-recovery skill; the task remains unsolvable for the Policy in 4/5 runs. The in_env_actions Setup trajec…

### Designer-call alignment (released arm): {('propose', 'content'): 18, ('decide', 'sequence'): 18}

### Axis × certificate outcomes (H arm)

| axis | n | SR_c=0 | certified | unresolved | R_old=1 | R_exp=1 |
|---|---|---|---|---|---|---|
| A | 30 | 2 | 30 | 0 | 19 | 22 |
| A+O | 3 | 2 | 1 | 2 | 1 | 1 |
| A+T | 2 | 0 | 2 | 0 | 1 | 1 |
| O | 27 | 4 | 27 | 0 | 26 | 23 |
| S0 | 9 | 0 | 9 | 0 | 8 | 8 |
| S0+O | 1 | 0 | 1 | 0 | 0 | 0 |
| T | 32 | 2 | 32 | 0 | 23 | 21 |
| T+O | 1 | 0 | 1 | 0 | 1 | 1 |
| none | 1 | 0 | 1 | 0 | 0 | 0 |

### Decision × certified (H arm)

{('refine', 'certified'): 10, ('accept', 'certified'): 19, ('reject', 'certified'): 75, ('reject', 'not'): 2}

### reverse_or_loosen matches for audit (H arm; 35 candidates)

- task 1 cand 78db26fa [accept]: [unsolvable] …vering. This is a mild A-axis failure-recovery miss, not an unsolvable mutation (4/5 succeed). …
- task 2 cand 3279820c [accept]: [impossible] …creates a genuine failure-recovery challenge rather than an impossible task. The S0 pre-placement + O-axis command trimming combo …
- task 3 cand b9c16c09 [reject]: [unsolvable] … the egg) is too strong and effectively makes the task near-unsolvable for this Policy, not a subtle difficulty increase. I'm reje… || [unsolvable] …n of the egg from countertop to fridge made the task nearly unsolvable: SR fell 0.80 -> 0.20, with 4/5 rollouts grinding to the 48…
- task 3 cand ff78d1aa [accept]: [unsolvable] … genuine statedependency/failure-recovery challenge, not an unsolvable mutation. No subprocess timeouts, no blocked steps, and the…
- task 5 cand e3e70a4a [accept]: [unsolvable] … winning — a genuine difficulty signal rather than a broken/unsolvable mutation. The failure is not an impossible task (the other … || [impossible] …er than a broken/unsolvable mutation. The failure is not an impossible task (the other 4 rollouts win with 10-38 steps), so this i… || [impossible] …g a genuine but solvable difficulty increase rather than an impossible mutation. …
- task 7 cand f97fab98 [reject]: [unsolvable] …The mutation made the task unsolvable: success_rate dropped from 0.65 (accepted) / 1.00 (baseline… || [impossible] …. So the completion move is blocked forever, making success impossible. This is exactly the unsolvable-mutation failure mode: SR=0… || [unsolvable] …ked forever, making success impossible. This is exactly the unsolvable-mutation failure mode: SR=0 across K rollouts with failure_…
- task 7 cand 323eae53 [reject]: [unsolvable] …cy sometimes relies on. The prior candidate f97fab98 was an unsolvable mutation (SR=0), so I avoid sweeping bans. Instead I block …
- task 7 cand 38db4481 [reject]: [unsolvable] …emoves a step the Policy relies on, without making the task unsolvable (as the prior f97fab98 did). Blocking 'examine statue' had …
- task 10 cand 3485b59d [accept]: [impossible] …lear, measurable improvement that pulls the task out of the impossible/trivial floor toward the target difficulty band, while keep… || [unsolvable] …mutation exercises failure-recovery without making the task unsolvable. The perturbation type (O-axis goal reminder) is validated …
- task 15 cand b56a1efc [reject]: [unsolvable] …) so it must recover and re-orient, without making the task unsolvable.…
- task 15 cand 65718c65 [accept]: [unsolvable] …ilure-recovery is exercised rather than the task being made unsolvable. This is a mild, targeted A-axis perturbation with measurab… || [unsolvable] …mild and mostly from search re-orientation, not from a hard unsolvable restriction. …
- task 16 cand 68f432b8 [refine]: [unsolvable] … stronger block should land in band without making the task unsolvable (the take eventually succeeds after the block count is exha…
- task 16 cand 884a6d7a [accept]: [unsolvable] … than recover — a genuine failure-recovery exercise, not an unsolvable A-axis block. The success_rate of 0.60 is squarely in band,…
- task 20 cand c2836a3d [accept]: [unsolvable] … one failure (seed=20, steps=50) is a timeout/grind, not an unsolvable-state signal: 4/5 rollouts still won, so the task remains r… || [unsolvable] …his is exactly the intended failure-recovery stress, not an unsolvable mutation — 4/5 rollouts still succeeded, confirming the tas…
- task 21 cand a1a4348a [reject]: [unsolvable] … the pen/pencil confusion, but it made the task effectively unsolvable — all 5 rollouts hit the 50-step repetition-truncation limi… || [unsolvable] …ep repetition-truncation limit with no success. This is an "unsolvable_mutation" failure: the perturbation did not nudge the Polic…
- task 21 cand c86690ea [reject]: [unsolvable] …cil. The recent traces show two prior candidates: a1a4348a (unsolvable_mutation) and c86690ea (overshoot_loop, SR 0.80). The diagn…
- task 21 cand 73fb26b9 [accept]: [unsolvable] …ion. This is a failure-recovery gap (T axis) rather than an unsolvable mutation — 2 rollouts do recover and succeed. …
- task 26 cand 6b3a5c50 [accept]: [unsolvable] …l without shifting presentation. No subprocess timeouts, no unsolvable-mutation signal. Accepting as the iteration result.  …
- task 11 cand 276e9a92 [reject]: [unsolvable] …kept looping. This is an A-axis mutation that made the task unsolvable-in-practice, not a difficulty increase. The failure_analysi…
- task 11 cand cec39046 [reject]: [unsolvable] …equired ~48 steps of wandering. Prior mutations were marked unsolvable/ineffective. I'll make a mild, solvable perturbation: force…
- task 11 cand 141e42f6 [reject]: [unsolvable] …eaking it, and the Policy never reaches the cup. This is an unsolvable-in-practice mutation — the Policy's only observed recovery …
- task 12 cand 1580e59d [reject]: [unsolvable] …ailed, so this is a zero-difficulty mutation rather than an unsolvable one. Baseline SR is 1.00 with a 17-19 step solution that pi…
- task 13 cand a3fbceb2 [refine]: [loosen] …ess-timeout-like behavior). I'll keep the A-axis filter but loosen it: instead of a hard block, block only the FIRST occurrenc… || [unsolvable] …moved the mug's location from reach, making the task nearly unsolvable. I'll replace it with a much narrower, recoverable perturba…
- task 13 cand 54e69c46 [reject]: [unsolvable] …tercepts the Policy's real behavior without making the task unsolvable. filter_action never triggered: blocked_steps=0 in all 5 ro…
- task 14 cand bbc7fc77 [refine]: [LOOSEN] …he working structure that established the correct axis) but LOOSEN it — e.g. allow 'look' more often (block only every Nth 'lo… || [loosen] …navigation, and cutting it off forced aimless looping. I'll loosen it: instead of blocking 'look' outright, only block 'look' …
- task 14 cand 9e74665f [accept]: [loosening] …ut mutation). The prior 'look' hard-block overshot to 0.20; loosening to block 'look' only while repeating brought SR to 0.60, la… || [impossibility] …related (blocked_steps up to 6), not subprocess timeouts or impossibility. …
- task 19 cand 6086f226 [reject]: [unsolvable] …ed to close the microwave and could not recover. This is an unsolvable/impossible mutation in practice: the Policy's only path to … || [impossible] … the microwave and could not recover. This is an unsolvable/impossible mutation in practice: the Policy's only path to heating the…
- task 19 cand 922a2394 [reject]: [unsolvable] … for selecting actions and it could not recover. This is an unsolvable-in-practice mutation, not a difficulty increase — the polic… || [unsolvable] …ine SR is 0.20 (weak Policy). Prior candidates were flagged unsolvable_mutation, so I avoid blocking actions entirely. Instead I e…
- task 19 cand 6f310b48 [accept]: [unsolvable] … a weak 0.20 toward the target band without making the task unsolvable. The mutation exercises failure-recovery (Policy must synth… || [unsolvable] …entation textually identical. Prior candidates were flagged unsolvable_mutation; this one avoids blocking actions entirely and sho…
- task 23 cand c0f523ce [refine]: [unsolvable] …estrict the recovery search space. No subprocess timeouts / unsolvable signals; the task remains solvable (3 wins). Pruning 'go to… || [unsolvable] …olicy must recover faster. However to avoid making the task unsolvable, I keep all non-navigation commands intact. This preserves …
- task 23 cand 76ee5ca5 [accept]: [unsolvable] …er than recover — a genuine failure-recovery signal, not an unsolvable mutation (3/5 rollouts still recovered and won in 17-34 ste… || [impossibility] … and recovered. This is a failure-recovery exercise, not an impossibility — the task remains solvable and the mutation is narrow. …
- task 24 cand fbbe7793 [reject]: [unsolvable] …t, without shifting surface presentation or making the task unsolvable.…
- task 27 cand 454ea8b5 [reject]: [unsolvable] …uts hit the 50-step ceiling (no subprocess timeouts, so not unsolvable — just the Policy still loops). The hint prepended only on …
- task 28 cand bcde9de5 [reject]: [unsolvable] …l natural-language ALFWorld text). To avoid making the task unsolvable, I'll only strip commands when a solid alternative remains,…
- task 29 cand 601fe47c [reject]: [unsolvable] …'ll block 'open microwave 1' — but that would make the task unsolvable since the egg must go in the microwave. Instead, I'll block…

### Designer-call alignment (H arm): {('propose', 'content'): 106, ('decide', 'sequence'): 106}

### L/T histogram

{'0.0': 31, '0.1': 6, '0.2': 3, '0.3': 5, '0.4': 2, '0.5': 8, '0.6': 13, '0.7': 6, '0.8': 32, '0.9': 19}

### Cost per phase (USD, applicable tariff)

{'phase0': 0.0, 'phase0_smoke': 0.36, 'phase1': 4.93, 'phase2': 3.61, 'phase2b': 10.11, 'phase3_hint': 0.68}

## Measurement notes

- Paired vs independent: p16 = EnvRigger's own 5 baseline rollouts + 11 extra rollouts through the same code path (system prompt and first observation byte-identical, checked on tasks 0 and 1); candidate certificates are LLM-free replays on the same seeds; the two designer arms are independent runs on the same seeds.
- Expert = ALFWorld handcoded expert, closed-loop and stateful (recover_mode handcoded_closed_loop); its own failure rate from reset is the O1 calibration; O6 is reported with expert failures counted as C=0 (conservative) and excluded.
- Bug fixes after rollouts and archived pre-fix files are listed in LOG.md and named here when applicable: witness_base_v1_prestuckclass.jsonl (witness classification before expert_stuck/expert_timeout were separated; W_base values unchanged).

## Caveats

- Single benchmark (ALFWorld train split), N per the Phase-0 projection, DeepSeek V4 Pro non-thinking at temperature 0.5 (config) instead of the paper's Gemini backbones, handcoded expert as witness (fails on some pick_two tasks), R_hint capped at 60 candidates × 3 attempts shared across arms.
- Released-arm O4/O5/O7 are uninformative by construction (scaffold-only ALFWorld prompt: SKIP at SR >= 0.8, A/O blocking forbidden, acceptance = SR gain >= 0.2); contribution-2 branches are read from the H arm (PREREG_H).
- litellm 1.99.0 moves a leading <think> block into reasoning_content; policy_raw_response therefore lacks think text (substrate behaviour of the released stack).
