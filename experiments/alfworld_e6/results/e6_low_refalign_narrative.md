## Narrative (hand-written after the run; every number above comes from the tables script)

### Conclusion

**NO_EVIDENCE_REFERENCE_ALIGNMENT_HELPS**, by the pre-registered rule: all correctness gates
pass, arm B accepted 0 of 2 fresh LOW tasks against arm A's 1 of 2, and the paired ordinal
outcome is one win each (task 20: B better, task 27: A better), so neither the SUPPORTED nor the
HELPS-BUT-CONTROL-LIMITING condition holds. With n = 2 (the entire remaining frozen LOW pool),
this is a small sample; the pre-registration accepted that and the rule is applied as written.

### Audit-tool correction, recorded for transparency

The chain's first tables run reported INCONCLUSIVE with two gates false: `reference_leakage`
(both arms) and `method_unmodified`. Both were defects of the audit tooling, not of the run,
and both are verifiable from the archived files:

- The leakage auditor (inherited from the smoke driver) compared every Setup prefix by string
  against `reference[min(cuts):]`. That flagged the compiler's own trailing `look`, a failure
  prefix that happens to share an action with the reference's future (`go to fridge 1`), and the
  second of two reference cuts against the first cut. The pre-registration defines the gate by
  provenance ("post-cut actions that the policy emitted itself are counted by provenance, never
  flagged"; a prefix is checked against its own cut). Every arm B prefix is exactly the recorded
  reference up to its own cut plus `look`; every arm A prefix is the policy's own failure
  actions. The corrected auditor (`e6_refalign.leakage_audit`, provenance through the run's own
  candidate ids) is unit-tested on these exact false positives and finds no leak.
- The tree check reused the smoke driver's marker, which diffs `src/aea` against smoke 2's method
  commit (`f63c47b`); this experiment's method commit is `48dc028`, and `src/aea` was and is
  unchanged from it (`git diff --quiet 48dc028 -- src/aea`). The manifests therefore carry a
  spurious `+DIRTY` marker; the corrected gate diffs against `48dc028`.

No paid call was made after the correction; the tables were regenerated from the same run
files. The pre-correction report is kept in the session scratch directory and described in the
LOG.

### What the two arms did with the same evidence

Task 20 (put a clean soapbar in cabinet; reference 8 steps). Arm A chose two failure cuts (after
46 and 11 policy actions), both dead. Arm B diagnosed the first consequential divergence at
failure step 1 versus reference step 3 (the policy wanders among receptacles and never goes to
the toilet where the soapbar is; missing capability: locate and take the target object) and cut
the reference at 3 (holding the soapbar: 0 of 4) and at 5 (holding a clean soapbar: 4 of 4,
too easy). Paired: B better (unlock vs dead).

Task 27 (put a cool potato in microwave; reference 8 steps). Arm A chose the failure cut after
one action (`go to fridge 1`) and the reference cut after `look`; the failure cut was probed
first and landed in band (4 of 8), K16 confirmation 14 of 16 (p16 0.88, outside B_L and B_T).
Arm B gave the same diagnosis as on task 20 in structure (failure step 1 vs reference step 3:
never acquires the potato from the sinkbasin) and cut the reference at 3 and 2; both restarts
unlocked the policy at 4 of 4 and overshot. Paired: A better (accepted vs unlock).

### Diagnosis usage (arm B)

5 of 5 diagnoses named a valid failure step and a valid reference step (0 rejected); 4 of 4
proposals were linked to a diagnosis; the selected cuts sat at or after the diagnosed reference
step on task 20 and at or before it on task 27. The diagnoses read as accurate credit assignment
(both tasks: the policy never acquires the target object; the reference does so at step 3).

### Interpretation

Reference-guided credit assignment did what the hypothesis predicted at the level of proposal
quality: arm B's cuts were reference-grounded, diagnosis-linked and unlocked the policy on both
tasks (2 of 2 versus 1 of 2 for arm A), whereas arm A's failure cuts were dead on task 20. It
did not translate into accepted environments: every arm B restart that unlocked the policy
overshot the target band (4 of 4), because a reference cut at the diagnosed state hands the policy
a state from which the remaining subtask is trivial for it. Arm A's one acceptance came from a
near-reset failure cut whose K16 confirmation lies outside the learnable band, i.e. the accepted
environment was itself borderline. Under the pre-registered rule the result is no evidence that
reference alignment helps; descriptively, the bottleneck moved from selection to controllability
(target landing) on the LOW side, consistent with smokes 1 and 2. No method change is derived
from this here.

### What HarnessEvolve mechanism was actually tested

Reference-guided failure localization and structured error signalling (first consequential
divergence, error cause, fix hint) from a verified rich observation/action reference, used by the
same single designer call to choose a task-local environment Stage. Not tested: the same-policy
GT-conditioned reference producer, LLM-judge verification of references, cross-task error
clustering, harness (prompt / skill / tool) updates, and batch-level performance gates.

### Remaining limitations

- n = 2 fresh LOW tasks (the frozen pool is exhausted); a larger prospective LOW pool would need
  a new frozen K16 measurement, pre-registered separately.
- LOW restarts that unlock the policy overshoot the 3..5-of-8 band on every reference cut seen
  so far (smoke 1 task 9, this experiment tasks 20 and 27); no neighbouring-cut search was added.
- The reference is the benchmark expert (different agent from the learner) with observations and
  actions but no reasoning; same-policy GT-conditioned references remain untested.
- The audit tooling needed two corrections after runs (smoke 1: recomputed expert; here: string
  overlap and baseline commit); the corrected provenance auditor is now unit-tested.

### Spend

USD 5.31 in total over `runs/e6-refalign-*` (shared estimation 1.89, arm A 1.40 of which
designer 0.02, arm B 0.31 of which designer 0.02, confirmation 1.63, offline diagnostic 0.08) of
the 15 cap.
