# Prospective iterative LOW pilot with frozen Round 5 judge

Protocol: iterative-low-r5-judge-pilot-v1
Method: llm_v2_iterative_low_llm_judge
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

Design: docs/design/AEA_LLM_PRIVILEGE_JUDGE_PILOT.md

R5 remains JUDGE_GATE_NOT_READY. This is a new prospective startup rule.
All nine labeled leaks were blocked; the known generic false rejection remains.
Candidate-level admission still requires PASS; FAIL and UNCERTAIN never reach policy.
No further judge tuning or validation rounds.
Tasks 154/159 and four saved candidates only.
Full saved admission replay precedes unchanged LOW DESIGN/CONTROL/fresh K16.
Three designer calls and 30 adaptation episodes per task; endpoint 4 -> 8;
acceptance 3..5/8; CONTROL freeze and evaluation-only K16 stay unchanged.
Hard cumulative cap USD 20; prior conservative spend USD 4.93304108;
remaining pilot cap USD 15.06695892. No resets/restarts or concurrent stages.
Paid execution requires renewed local authorization bound to this exact preregistration.

## Immutable bindings

- source_manifest.json: b664a41d1181d80b043b25e1b584c4da387b5b2b80d1049fd472a493cf4a20da
- input_manifest.json: d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c
- validation_manifest.json: 04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32
- startup_basis.json: b371f05395b3007c20434b7acb0fb2c9b5e1b766beb9984c06660271073b698e
- engineering_budget.json: 3e0d2363e311b0a693e9c742bcaccd97a480be328280d37162346a2bd72e315d
- copied_private_inputs.json: 1c3b142a65facf66df44e2d46c29feb3b0ff74a72fab335cc0aeb8ff569f9017

## Prospective scope and interpretation

This protocol was prepared before renewed API authorization and before any paid pilot call.
It changes only the experiment startup condition; the old Phase A remains failed and the old
launcher remains closed. Candidate FAIL and UNCERTAIN retain existing bounded
REPLACE_MECHANISM feedback and never reach solvability or policy. No manual verdict override.

Use exactly the archived failures/references for tasks 154/159. No new screening, baselines,
reference collection, D/I, E3 or E3-SL. No saved-replay verdicts or K16 outcomes enter new
DESIGN feedback. Keep endpoint reserve 16, first viable-family freeze, no CONTROL-to-DESIGN
return, and K16 only after search acceptance. Judge/model/schema/LOW code stay frozen.

Report actual C1-to-C2/C3 revisions separately from first-proposal success. A first-proposal
success demonstrates pipeline functionality, not an iterative-feedback benefit. Rejections
can leave LOW usefulness unmeasured; they do not supply labels for admission accuracy.

## External processing and budget

Renewed consent must explicitly remove the old Phase-A-pass prerequisite for this pilot.
All other data/recipient constraints remain: privileged judge/designer inputs go only to
https://api.deepseek.com; only admitted learner-facing inputs go to
https://openrouter.ai/api/v1 with the frozen Qwen configuration. Full references, raw prompts,
candidate arguments/surfaces and free-text judge/designer records remain local/gitignored.

All prior charges and ambiguous reservations remain committed. The USD15.06695892 pilot
cap includes saved replay, every judge/verifier/designer/learner request, K16 and retries.
The cumulative USD20 limit is enforced before each physical attempt, including child policy
processes. Correctness, provenance, transport or accounting failure stops without patch-and-resume.

## Offline preflight

Independent review and 202 focused tests passed (33 new pilot tests plus 169 existing
judge/admission/controller regressions). Strict typing of the new launcher and Ruff passed.
The existing R5 audit was replayed offline and is byte-identical to its published 349-check
PASS result; judge_ready remains false. No new paid call has been executed.

- preflight_review.json SHA256: 353d7ddfffe625e634465d5b356ec8c9cde8476d25cf0a93e342a5b54e0c3cab
