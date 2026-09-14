## Narrative (hand-written after the run; every number above comes from the tables script)

### Decision

**STAGE_CONTROL_NOT_SUPPORTED**, by the pre-registered rule: all gates pass; 8 of 8 tasks
prospectively `zero`; `nonmonotonic_profile` 0; arm B accepted 1 of 8, arm A accepted 1 of 8,
so neither "B >= 3 and B > A" (rule 3) nor "B strictly more paired wins or strictly higher
conversion" (rule 4: paired A 1 / tie 6 / B 1, conversion 0.17 vs 0.17) holds. The
K16-confirmation asymmetry (arm B's acceptance 8 of 16, inside both bands; arm A's 15 of 16,
outside both) is reported but was pre-registered as a separate report, not as a tie-breaker.

### Two audit-tool adaptations, recorded for transparency

The chain's first tables run reported INCONCLUSIVE with two arm-B gates false, both because
the inherited checks were written for designer arms: `B_no_fallback` required every
`stage_candidates` event to carry source `designer`, while the design audit and this
pre-registration specify source `control` for arm B; and the provenance check compared the
recorded reference hash with the hash in the redacted designer evidence, which does not exist
for arm B because it makes no designer call by design. Arm B's recorded hashes equal the
recomputed hash of the recorded actions, the `reference` event and the shared reference on all
six referenced tasks (verified before the fix). The two checks were corrected to the
pre-registered definitions, the tables regenerated from the same run files (no paid call), and
the pre-correction report archived as `results/e6_low_stage_control/tables_before_gate_fix.md`.

### What the controller did (arm B, six referenced tasks)

- t_max (the deepest non-terminal prefix; the full reference was terminal on all six) was too
  easy on 6 of 6: maximum assistance always makes the task trivially accessible, so the inward
  control problem is well posed and the original "start from d = 1" intuition holds on the LOW
  side.
- Three tasks (62, 66, 70) closed the bracket to a one-action gap with the lower depth dead
  (0 of 4) and the upper depth trivial (4 of 4): [6, 7], [2, 3], [10, 11]. There is no integer
  Stage between them; `resolution_limited` is the honest outcome, and it appeared in 3 of 6.
- Two tasks (71, 79) hit the 30-rollout cap with the bracket still open ([7, 9] and [9, 11]):
  each spent one mixed 8-rollout probe (7 of 8, too easy) and could not afford the last step.
- One task (78, reference 30 actions) landed: 29 easy, 14 and 21 dead, 25 in band (3 of 8),
  accepted at the cap, K16 8 of 16 (p16 0.50, inside B_T).
- Leverage was universal (6 of 6 referenced tasks had a probe with >= 1 success; the two
  reference-less tasks were dead in both arms), and every bracket was consistent (0
  contradictions, as the update rule guarantees).

### What arm A did

On the same references the refalign designer chose two cuts per task; on five tasks both cuts
were trivially easy (4 of 4, `too_easy`), and on task 79 its second cut landed 5 of 8 and was
accepted, but K16 put it at 15 of 16, outside the learnable band. On the two tasks without a
reference its failure cuts were all uncertified by the oracle.

### Interpretation, by property

- Leverage: confirmed again (6 of 6 with a reference).
- Ordering: consistent at every probed depth on every task (no contradiction in 26 probes).
- Resolution: the binding constraint. On 3 of 6 tasks the policy's response switches from 0 of
  4 to 4 of 4 between two consecutive expert actions; the discrete Stage family has no
  operating point in the 3..5-of-8 band there. On 2 more the bracket needed more than the
  20 probe rollouts left after the estimate. Only the longest reference (30 actions) offered a
  depth that landed, and it did so inside the narrow target.
- Controllability: the loop itself worked as designed (maximum assistance first, monotone
  bracket, no wasted or repeated probes) but converted leverage into an accepted Stage on
  1 of 6, the same count as the LLM-selected baseline.

### What the experiment establishes

Given a verified reference, reference-prefix depth is an ordered, well-posed control axis whose
maximum is always accessible and whose bracket can be run within the cap; the LOW landing
problem is not one of selection or ordering but of granularity: on half of the tasks the
useful operating point does not exist at integer depth, and on the rest it costs more probes
than the budget leaves. Arm B's one acceptance is the first LOW Stage of the whole programme
to confirm inside the narrow target band.

### What it does not establish

That any Stage-depth controller can beat the LLM baseline on accepted count (n = 8, 1 vs 1);
that the one-action gaps hide no useful state under a different Stage construction (only
integer prefixes of the expert path were probed); anything about a larger probe budget; anything
about downstream learners.

### Not done (by the pre-registration)

No fractional or partial-action Stage, no extra environment rule, no neighbouring-depth search
beyond the bracket, no extra budget, no change to the decision thresholds, no full E6, no E6-SL.
The next scientific question is about the granularity of the assistance family itself (a
different LOW actuator, or a Stage family with finer state resolution), to be pre-registered
separately.

### Spend

See the spend line above (all `runs/e6-sc-*` ledgers): shared estimation, arm A, arm B,
confirmations; designer USD 0.047 (arm A only).
