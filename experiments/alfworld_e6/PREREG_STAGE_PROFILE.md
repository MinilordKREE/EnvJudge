# PREREG_STAGE_PROFILE — Stage-depth response surface along a verified reference (phase 3.3a, part B)

Written and committed before any Stage-profile policy probe. Analysis experiment only: no method
change (`src/aea` unchanged from `48dc028`), no LLM designer, no diagnosis, no adaptive rule, no
acceptance. The object measured is t -> p_pi(E_t): the current policy's success rate when the
environment is reset by silently replaying the first t actions of ONE verified successful expert
reference, the policy then receiving only its ordinary observation.

## Sample (frozen)

LOW_POOL_2 (PREREG_LOW_POOL2, `frozen/low_pool2_k16.jsonl`, sha256 `92dc4bd5436ee183`): the 14
fresh tasks with 0 / 16 and 0 errors = {33, 43, 53, 54, 56, 58, 62, 66, 67, 70, 71, 73, 78, 79}.
Characterisation sample = the six smallest ids: **33, 43, 53, 54, 56, 58**. The other eight stay
untouched for future prospective tests.

## References (frozen before this commit; `runs/e6-profile/privileged_references.jsonl`, archived under `results/stage_profile/`)

One rich expert trajectory per task (`ExpertReference`: ALFWorld handcoded expert from the reset
state, in-process, step / observation / admissible commands / action, no reasoning), verified
successful by the simulator (`Session.won`). Never regenerated.

| task | reference_id | T (expert actions) | anchors t = round(a·T), a in {0, .25, .5, .75, 1} (deduplicated) | t = T terminal? |
| --- | --- | --- | --- | --- |
| 33 | `a6e9d096714e42f1` | 9 | 0, 2, 4, 7, 9 | yes (won after full replay) |
| 43 | `2494c65100d225eb` | 12 | 0, 3, 6, 9, 12 | yes |
| 53 | `2983510d89e0b323` | 22 | 0, 6, 11, 16, 22 | yes |
| 54 | `f1964819c953d2f3` | 15 | 0, 4, 8, 11, 15 | yes |
| 56 | `60886eb9d33e7b1e` | 23 | 0, 6, 12, 17, 23 | yes |
| 58 | `335ef34c5f23a35e` | 8 | 0, 2, 4, 6, 8 | yes |

All 30 anchor prefixes compiled exactly on the staged configuration (every expert action
admissible and effective; `runs/e6-profile/stages.jsonl`). ALFWorld semantics audited: replaying
the complete reference satisfies the goal, the episode is terminal (`won`, `done`) and cannot hand
control back to the policy, so t = T is recorded `terminal_reference_state = True` and excluded
from all response statistics; the 75 % anchor is the strongest probeable assistance point. t = 0
is the original reset (no replay) under the same staged configuration (the 100-step engine cap
never binds because the policy keeps its own 50-step cap): 24 probeable anchors.

## Probe protocol

K = 8 fixed rollouts per probeable anchor (no 4 -> 8 early stop, no acceptance), current policy
(Qwen3-8B, E3 `policy_qwen()`, unchanged), Stage = `Candidate(in_env_actions = reference[:t])`
compiled by the existing `compile_prefix` / `stage_candidate`, staged reset options
(`configs/alfworld_config_100.yaml`), the released Setup harness replays the prefix silently;
the policy never sees the reference, its observations or future actions. Errored episodes are
re-run once; an anchor with fewer than 8 valid episodes is reported with its n. Anchor order:
task ascending, t ascending; 8 episodes in flight. Attribution `phase = profile, budget = eval`.

Budget: 24 anchors × 8 = 192 rollouts (plus re-runs); measured pool-2 cost USD 0.048 per
rollout (USD 0.079 for 50-step failures) -> expected USD 10-15. **USD cap 35** over
`runs/e6-profile*`, checked before every anchor; STOP at the cap, no raise. Reference generation
is in-process (USD 0). Pool-2 K16 (USD 38.13) is reported separately and not counted here.

## Definitions (frozen; `scripts/make_tables_e6_profile.py`)

s(t) = successes of 8 at a probeable anchor. Thresholds (descriptive frontier markers, not AEA
acceptance): dead s <= 1; easy s >= 6; useful 3 <= s <= 5 (the operational target band).

- leverage (Q1): max_t s(t) - s(0) >= 3; also reported: any anchor with t > 0 and s >= 1.
- ordering (Q2): over adjacent probeable anchors in increasing t, increase / same / decrease by
  successes; fraction nondecreasing; a meaningful reversal is an adjacent decrease of >= 2.
- frontier crossing (Q3): dead-to-easy = some anchor s <= 1 followed (larger t) by an anchor
  s >= 6; dead-to-useful likewise with 3..5.
- useful band (Q4): any anchor with 3 <= s <= 5.
- profile category (precedence order): NO_LEVERAGE if not leverage; else
  LEVERAGED_BUT_NONMONOTONIC if >= 1 meaningful reversal; else STEP_LIKE if no useful anchor and
  dead-to-easy; else ORDERED_FRONTIER. ALREADY_USEFUL_AT_ANCHOR is reported as a flag (= useful
  band) alongside the category. A task with fewer than 2 measured anchors or without a measured
  t = 0 is INSUFFICIENT_ANCHORS.

## Decision rule (exactly one; applied mechanically)

Let L = tasks with leverage, F = tasks with a useful anchor or a dead-to-easy crossing, N =
LEVERAGED_BUT_NONMONOTONIC tasks, S = STEP_LIKE tasks, over measured tasks.

1. INCONCLUSIVE: fewer than 4 verified references, fewer than 4 measured tasks, more than a
   third of the defined anchors invalid, or a provider / infrastructure / budget interruption.
   Never for ordinary weak results.
2. STAGE_AXIS_NO_LEVERAGE: L < 3.
3. STAGE_AXIS_SUPPORTS_CONTROL: L >= 4 and F >= 3 and N < L / 2.
4. STAGE_AXIS_EFFECTIVE_BUT_NOT_ORDERED: N >= L / 2 (and not 3).
5. STAGE_AXIS_TOO_STEP_LIKE: otherwise (leverage present, but frontier / resolution evidence
   insufficient: covers a step-like majority and the residual cases; the reason is printed).

No Stage-depth controller, binary search, neighbouring-cut search or method change follows from
this phase; the outcome is the recommended scientific question for a separately pre-registered
phase 3.3b. Raw anchors are reported and plotted as measured; no fit, smoothing or isotonic
regression.
