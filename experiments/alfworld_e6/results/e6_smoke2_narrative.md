## Narrative (hand-written after the run; every number above comes from the tables script)

### Decision

**NO-GO**, by the pre-registered functionality criteria: all eleven correctness gates pass
(including gate 8 evaluated against the exact recorded references, `expert_recomputed = false`,
provenance intact on all three LOW tasks, no leak), HIGH functionality PASS, LOW functionality
FAIL (3 of 3 LOW tasks reached `zero` and received valid, certified grounded cuts, but 0 of 3
produced a single successful current-policy rollout). Smoke 1's decision stands as recorded
(NO-GO by gate 8, HIGH PASS, LOW PASS); it is not reinterpreted here.

### HIGH mechanism

Did trajectory-conditioned LLM generation produce executable, nontrivial and empirically
effective actuators? Yes on all three counts this time. 5 of 5 proposals were valid (0 rejected);
3 of 3 branch-reaching tasks showed measurable leverage (the first family on each task took the
policy from 10 of 10 to 0 of 4 or to 4 of 8 at d = 1); 2 of 3 tasks delivered an accepted
environment, both confirmed learnable at K = 16 (task 15 `fridge_distractor_objects` at d = 1.0:
11 of 16, p16 0.69; task 22 `object_label_scramble` at d = 0.5: 10 of 16, p16 0.63; both inside
B_L = [0.2, 0.8], neither inside the narrower target B_T = [0.4, 0.6]). Task 13
`object_identity_swap` had leverage but its response was again a step function (`DOSE >= 0.5`
gate in the code: 0 of 4 above, 4 of 4 below) and the bracket exhausted at [0.4375, 0.5] under
the cap.

Descriptive delivery: HIGH accepted / branch-reaching = 2 / 3; leveraged-but-not-accepted = 1.

What changed versus smoke 1 is visible in the generated code, not in the method: with the static
environment surface in the contract, 2 of 5 families now edit `data["admissible_commands"]`
alongside the text (tasks 13 and 22), the A-axis families use `filter_action` on
`action.kwargs["text"]` and return `Blocked(reason=...)` instances (task 22 `command_verb_gate`,
task 15 `fridge_open_requires_cooling_check`), and no family filtered on `action.name`. Every
guard ran by policy replay (5 of 5), none by construction.

### LOW mechanism

Did failure plus privileged reference produce grounded restart interventions that changed learner
behaviour? Grounded: yes, 6 of 6 proposals pointed at real supplied steps, 5 of 6 were certified
by the expert from the restarted state (task 11's step-8 cut was `uncertified`: the expert could
not finish from a state where the wrong object had already been cooled and placed). Changed
behaviour: no. Every certified cut scored 0 of 4 (`dead`). The reference was available and
present in the evidence on all three tasks (16, 23 and 29 expert actions) and was never chosen as
a cut source: all six cuts were failure cuts, three of them very early (after 1, 3 or 6 actions)
and one at the very end of a failure (after 49). The designer's summaries diagnose the failures
plausibly (wrong object picked; drawers abandoned; cleaning step skipped) but its chosen restart
states were not ones from which this policy succeeds.

Descriptive delivery: LOW accepted / branch-reaching = 0 / 3; unlocked-but-too-easy = 0; dead = 3.
Over both smokes the LOW side has produced one unlocking task (smoke 1, task 9) out of six
branch-reaching tasks and no accepted stage.

### Automation

Yes. Every `families` and `stage_candidates` event has `source = designer`, no library family was
executed, no midpoint or end heuristic ran, one designer call per task (6 ledger rows, 6 records),
at most two proposals, no rollout-feedback rewrite, regime estimated prospectively on all six tasks
(all matched the frozen K16 regime), the six tasks pre-registered in order, `src/aea` unchanged
from `f63c47b`.

### Complexity

No new paper-level primitive: Measure -> Design -> Control. Phase 3.1 changed audit provenance,
a static API description in the designer contract, and an evidence label; 0 method branches.

### Interpretation (as pre-registered)

LLM intervention generation can affect policy behaviour and, on the HIGH side, now lands
environments in the learnable band (2 of 3, both confirmed); the HIGH bottleneck that remains is
step-like dose responses that the bracket cannot calibrate (1 of 3). On the LOW side the
mechanism is grounded and safe but the LLM-chosen restart states have not changed the policy's
behaviour in this sample (0 of 3), and the LLM did not use the reference as a cut source: LOW
controllability / target landing is the bottleneck. No method patch is derived from this here.

### Remaining limitations (recorded, not fixed)

- Generated HIGH dose functions can be step-like (`DOSE >= 0.5` gates), so the bracket exhausts
  on a discontinuity (tasks 12 in smoke 1, 13 in smoke 2).
- LOW cuts can overshoot to too-easy (smoke 1, task 9) or stay dead (smoke 2, all three); the
  designer prefers failure cuts to reference cuts (11 of 12 cuts over both smokes).
- The reference is expert actions only (no observations or reasoning).
- Confirmed HIGH environments landed in B_L but not in B_T on both accepted tasks.
- Spend guard: the driver counts every `runs/e6-*` ledger, so smoke 1's closed USD 4.32 was
  included under smoke 2's cap (conservative; logged).
- Not changed in this phase by design: the v0.2 baseline cleanup after E5; learner-specific
  routing; task-type routing; assistive LOW Rules.

### Spend

Smoke 2: USD 7.38 (search 6.11 over the policy calls, designer 0.03 over 6 calls, confirmations
1.24). Cumulative `runs/e6-*` including smoke 1: USD 11.70 of the 30 cap.
