# Iterative LOW viability V3 continuation

**Final decision: INCONCLUSIVE**

**The top-up succeeded, but no LOW candidate reached policy evaluation.** Z4 is task165 at 0/16; the exact sample is [154,158,159,165]. Only154/159 had verified references. Their four candidates were rejected before solvability: one semantic UNCERTAIN, two semantic FAIL, and one lexical rejection. There were zero endpoint, CONTROL and K16 episodes. Consequently, 0/4 means zero delivered confirmations; it is not an empirical K16 failure rate.

The formal INCONCLUSIVE reason is the frozen rule for too few usable references (two, below the three-task negative-result threshold). The direct functionality blocker is admission precision, described below. The run had no infrastructure interruption or observed method-invalidating execution defect.

The primary denominator remains the four frozen ZERO tasks, including unavailable references. Actual completed K16 outcomes determine confirmation evidence; endpoint success alone does not imply a failed confirmation.

## Prior core and prospective freeze

- Prior core154/158/159: LOCAL_HASH_BINDINGS_VERIFIED; 96 original artifact hashes verified against the preserved manifest.
- Core manifest SHA: `c25cab9b7cab7777310b7b8f4947ef3a423f0a51d6ce7701f3e58549c684c42a`.
- Top-up preregistration: `4d8419e584d695591e55d1bbf85981b37cfa3764`; viability preregistration: `80005ab90fae93525af669a82a09910cc562590a`.
- Final audit: **PASS**.

## Top-up

Start ID 163; newly inspected IDs [163, 164, 165]; status `qualified`.
Z4: 165; final four-task set: [154, 158, 159, 165].

| Task | Valid s/n | Outcome | Invalid returned / unreturned | Recovered physical / episode failures | Ledger USD |
| --- | ---: | --- | ---: | ---: | ---: |
| 163 | 1/1 | NON_ZERO | 0 / 0 | 0 / 0 | 0.022755564 |
| 164 | 1/1 | NON_ZERO | 0 / 0 | 0 / 0 | 0.012277577 |
| 165 | 0/16 | CONFIRMED_ZERO | 0 / 0 | 9 / 0 | 1.284176361 |

Tasks150–162 remain consumed;162 was never resumed. Prior screening reports remain unchanged.

## Cost

Historical V2 committed cost **$7.994786072** is excluded from this continuation.

| Phase | Ledger USD | Conservative returned USD | Retained failed USD | Physical requests |
| --- | ---: | ---: | ---: | ---: |
| topup | 1.319209502 | 1.319209502 | 0.045273384 | 858 |
| designer | 0.032073140 | 0.074214360 | 0.000000000 | 4 |
| adaptation_policy | 0.000000000 | 0.000000000 | 0.000000000 | 0 |
| confirmation | 0.000000000 | 0.000000000 | 0.000000000 | 0 |
| other | 0.000000000 | 0.000000000 | 0.000000000 | 0 |

Top-up committed **$1.364482886/$4**; adaptation+confirmation committed **$0.074214360/$25**. Total continuation committed **$1.438697246**; unresolved in-flight reservations $0.000000000.
The immutable top-up baseline is retained. Unused top-up headroom cannot enlarge adaptation. Orphan reconciliation is counted once; ledger and conservative costs are alternative accounting views.

## References and method execution

Reference attempts for158/165 returned `verifier_fail`. Each provider invocation occurred once. Candidate mechanism descriptions below are the designer’s proposals, not verified efficacy claims.

- Task154: REFERENCE_AVAILABLE; reference ID `f0a58f89e43dcbbb`; exact-record SHA `f8f5e026b4cc01e84ae1475241bda4207f765fc089b02d2f02f3d2d27dfa0549`.
- Task158: REFERENCE_UNAVAILABLE; reference ID `None`; exact-record SHA `729c583918ceb1ac4081152d8748572f316b7168fe262edcdb0201616edee0b1`.
- Task159: REFERENCE_AVAILABLE; reference ID `b68a542228b51665`; exact-record SHA `80a8fc5d7507a4491a97275e295aed0071340e2b47f0c4250c376bc67653749e`.
- Task165: REFERENCE_UNAVAILABLE; reference ID `None`; exact-record SHA `729c583918ceb1ac4081152d8748572f316b7168fe262edcdb0201616edee0b1`.
Primary: **0/4 K16-confirmed B_L**; B_T 0/4; search accepted 0/4. Historical bands: B_L4–12/16, B_T7–9/16.

### Task154

Task status completed; DESIGN inconclusive; evidence SHA `d4b442dff2c824f6d42a22114448f92ca178ddba2b5d0a5ee7f14c2a2b8e735f`.
- C1: PRODUCED; 154:C1:f8a28097e207d68774f41590fbc5f0255982e924bede2e1f399f0999230422c0.
- C2: NOT_RUN; semantic UNCERTAIN stopped DESIGN.
- C3: NOT_RUN; semantic UNCERTAIN stopped DESIGN.
- C1: Add an observation-side reminder of the task's required sub-goal sequence (take bread -> cool it with fridge -> place on countertop) and, with increasing DOSE, surface the cooling/placing affordance commands more prominently so the policy is steered toward the missing 'cool bread with fridge' step after it picks up the bread.; parent None; PROPOSE; source `f8a28097e207d68774f41590fbc5f0255982e924bede2e1f399f0999230422c0`.
  Gates `{"d0_identity": "PASS", "lexical": "PASS", "semantic": "UNCERTAIN", "solvability": "NOT_RUN", "structural": "PASS"}`; endpoint `None`.
- Frozen family: `null`.
- CONTROL: `{"status": "NOT_RUN"}`.
- Search accepted False, s/n None/None, dose None.
- K16: NOT_RUN; not a failed confirmation.
- Designer calls 1/3; adaptation policy episodes 0/30.

### Task158

Task status reference_unavailable; DESIGN reference_unavailable; evidence SHA `46b84d32279a0843d6a64bd73ae49d005f776f8f913fc9f76ab5c5254deb7445`.
- C1: NOT_RUN; reference unavailable.
- C2: NOT_RUN; reference unavailable.
- C3: NOT_RUN; reference unavailable.
- Frozen family: `null`.
- CONTROL: `{"status": "NOT_RUN"}`.
- Search accepted False, s/n None/None, dose None.
- K16: NOT_RUN; not a failed confirmation.
- Designer calls 0/3; adaptation policy episodes 0/30.

### Task159

Task status completed; DESIGN unresolved; evidence SHA `55a935664362fa036ea6ab84853661a3437cb8e9571626706bb97c44e9517b0a`.
- C1: PRODUCED; 159:C1:239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272.
- C2: PRODUCED; 159:C2:7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67.
- C3: PRODUCED; 159:C3:15c4a05e9a9a36edc0c54ac855eb2ebf20b01572aabc70263ebc9b0aa33ef8fd.
- C1: Observation-side support that surfaces the correct task sub-steps and the correct receptacles: it highlights the microwave as the heating device and the fridge as the cooling device, and reorders/reinforces the admissible commands toward the heat-then-cool sequence. Larger DOSE gives progressively stronger, more explicit reminders (from subtle highlighting of 'heat ... with microwave 1' and 'cool ... with fridge 1' commands up to a leading step-by-step hint line), without ever telling the policy which specific object instance to pick or replaying reference actions.; parent None; PROPOSE; source `239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272`.
  Gates `{"d0_identity": "PASS", "lexical": "PASS", "semantic": "FAIL", "solvability": "NOT_RUN", "structural": "PASS"}`; endpoint `None`.
- C2: After each world step, if the policy's action was ineffective (no world change) AND the action text names a heating/cooling verb or a stove/microwave/fridge receptacle that is not the correct appliance for the in-hand object, append a short corrective feedback line to the observation explaining what went wrong and naming the correct appliance/verb (e.g. 'That did nothing: to heat an object you must put it in the microwave and use the microwave, not a stoveburner.'). DOSE controls how many distinct error categories get feedback and how explicit the corrective text becomes, from a single generic 'That action had no effect.' at low dose up to category-specific redirects naming microwave/fridge at high dose. DOSE=0 returns the observation unchanged.; parent 159:C1:239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272; REPLACE_MECHANISM; source `7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67`.
  Gates `{"d0_identity": "PASS", "lexical": "FAIL", "semantic": "NOT_RUN", "solvability": "NOT_RUN", "structural": "PASS"}`; endpoint `None`.
- C3: When the policy is holding a potato (or any heatable object) and is at or near the microwave, reorder/re-surface the admissible command list so the correct 'heat <obj> with microwave 1' action is moved to the front and highlighted; DOSE scales how aggressively relevant appliance-verb commands are promoted (from a single reorder at low dose to also injecting a short goal-reminder line naming the microwave at high dose). DOSE=0 returns the observation and admissible list unchanged.; parent 159:C2:7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67; REPLACE_MECHANISM; source `15c4a05e9a9a36edc0c54ac855eb2ebf20b01572aabc70263ebc9b0aa33ef8fd`.
  Gates `{"d0_identity": "PASS", "lexical": "PASS", "semantic": "FAIL", "solvability": "NOT_RUN", "structural": "PASS"}`; endpoint `None`.
- Feedback to C2: REPLACE_MECHANISM/privilege; exact private packet SHA `d626d6d1d4224227dc10191c3c2d6761295f2f0e322cbef89b4e958e8fc65d46`.
- Feedback to C3: REPLACE_MECHANISM/privilege; exact private packet SHA `f34d32d01bd4173497e715b6e5c77c8b2149294eafb378dc31a9be9dcbe90296`.
- Frozen family: `null`.
- CONTROL: `{"status": "NOT_RUN"}`.
- Search accepted False, s/n None/None, dose None.
- K16: NOT_RUN; not a failed confirmation.
- Designer calls 3/3; adaptation policy episodes 0/30.

### Task165

Task status reference_unavailable; DESIGN reference_unavailable; evidence SHA `321baa81a6b995ca98964173789d47b7abd14d6d96827e410bfe656aadb35a2b`.
- C1: NOT_RUN; reference unavailable.
- C2: NOT_RUN; reference unavailable.
- C3: NOT_RUN; reference unavailable.
- Frozen family: `null`.
- CONTROL: `{"status": "NOT_RUN"}`.
- Search accepted False, s/n None/None, dose None.
- K16: NOT_RUN; not a failed confirmation.
- Designer calls 0/3; adaptation policy episodes 0/30.

## Independent saved-surface review

The recorded gate decisions remain unchanged. This review examines the saved artifacts; it does not rerun the gate or retrospectively admit a candidate.

- **154/C1:** the generic cooling reminder falls outside the bounded wording recognized by the gate. It produced5,472 UNSUPPORTED findings and no FAIL witness; the exact raw episode prefixes were verified.
- **159/C1 and C3:** the logged relation extractor treats the pronoun `it` as a location and matches ordinary hint wording. For C1, a second location witness comes from unchanged baseline prose; no corresponding location command is promoted. These witnesses do not independently substantiate the claimed disclosure. Candidate usefulness is also unmeasured.
- **159/C2:** the literal guard rejects `reward=raw_response.reward`. Static inspection shows pass-through construction, not evidence of an altered reward. Its recorded lexical FAIL remains unchanged.

These conservative admission/precision problems prevented every referenced task from reaching policy. They do not establish a gate bypass or leak reaching policy; no policy was run. The single proposed future scope is semantic grounding precision for public prerequisites and true learner-facing deltas, with existing leak regression coverage retained. This continuation implements no change.

## Validation and audit record

The implementation preflight passed403 tests (34 new V3 cases), lint/format and type checks. Production sources and runtime inputs remain at the preregistered hashes. Final checks passed19,299 screening checks,1,869 terminal provenance checks,597 preservation checks and6,173 independent phase/report checks. All28 operation records completed; all862 physical attempts settled, with no in-flight reservations.

The initial offline terminal auditor made four false failures by requiring an explicit provider label in direct DeepSeek responses. The frozen client legitimately records an absent upstream label as null. Only that audit helper was corrected; the initial source/result, correction diff and29 passing regression tests are preserved. Exact frozen direct routing, model and request hashes passed; an independent upstream designer-provider label remains unavailable. No experiment artifact or execution method was patched.

Audit PASS establishes the checked provenance/accounting, not guaranteed semantic isolation. Gate ordering is supported by frozen control flow and source/dose bindings; the gate records lack independent timestamps. Detailed evidence and all21 requested report fields are in [the result](results/iterative_low_viability_v3/result.json) and [phase audit](results/iterative_low_viability_v3/physical_phase_audit.json).

## Decision and next action

Stop this continuation. The single next functionality scope is semantic privilege-screen precision for public prerequisites and actual learner-facing deltas, evaluated offline against these saved cases and the frozen leak benchmarks before any further paid experiment. No fix or further experiment is implemented here.

Single direct blocker: Admission precision prevents the referenced tasks from reaching policy evaluation: generic prerequisite/current-command support is rejected as unsupported or as unsubstantiated hidden-location relations.

Raw traces, source, prompts, references and detailed feedback/gate bodies remain local. Compact artifact manifests bind their bytes. K16 is evaluation-only; unperformed confirmations are not misses.
