# Privilege evidence verification: round 3

**Outcome: JUDGE_GATE_NOT_READY.** All 21 scheduled cases completed without interruption.
Implementation/preregistration commit: `941b053a6fb18aa9237645a37bb98ed77ad4cd58`.
The independent offline audit passed all 325 checks, reproducing every request and final
record. No Phase B, saved full admission replay, designer call or learner rollout started.

| Frozen validation criterion | Result |
| --- | --- |
| Core expected verdicts | 11/13 |
| Leak cases returning FAIL | 8/9; delayed ranking returned UNCERTAIN |
| Legitimate cases returning PASS | 3/4; generic prerequisite returned FAIL |
| Identical-input repeat agreement | 3/4 |
| Final records without generated uncertainty | 18/21 |
| Logical calls / physical attempts | 43/43 |

The public-observation and goal-only cases now passed. The task110 repeat returned
UNCERTAIN while its core judgment returned FAIL. The four unlabeled saved inspections
returned PASS, UNCERTAIN, PASS, PASS in their frozen order. These inspections have no
accuracy labels. No labeled leak returned PASS.

## Offline findings

All 20 parsed source anchors and 36 runtime anchors passed exact verification. Two checks
failed the unchanged schema because they supplied 9 and 11 candidate anchors, exceeding
the limit of 8. The delayed-ranking case had valid citations but both checks identified a
narrower claim while copying the original overbroad information unchanged; reconsideration
preserved unsupported clauses. These conditions continued to block admission.

Both generic-prerequisite judgments used reconsideration. Their first checks removed
invented hidden-instance bindings, but the final judgments still classified an ordinary
goal-conditioned prerequisite order as private because it was not stated verbatim in the
public goal. This confuses a reusable procedure with an additional hidden instance choice.

Round 4 will test concise prompt-only corrections: distinguish ordered procedures based
on public goal operands and ordinary tool semantics from hidden instance choices; rewrite
a narrowed claim to remove unsupported clauses; request one or two sufficient candidate
anchors in total. Model, schemas, host checks, evidence inputs, labels, four-call bound and
LOW control logic remain fixed. The same 21-case schedule and five-round maximum apply.

## Cost, preservation and publication

Round 3 conservatively cost USD0.65410532, with no ambiguous reservations or requests in
flight. Cumulative cost is USD3.85197956, including earlier runs and Round 1's retained
USD0.46601632 reservation. Remaining authorization is USD16.14802044. The cumulative
USD20 ceiling and each new round's USD2.50 ceiling remain enforced before dispatch.

Before dispatch, 169 relevant unit tests and commit hooks, including strict mypy, passed.
Independent prompt review verified that only the two prompt literals changed; the main
prompt contains 289 words and the checker 275. Publication/history audit found no
privileged-material matches. All earlier records remain unchanged. Raw references,
inputs and responses stay local and gitignored.

This remains engineering on reused cases, not a fresh generalization test. Public outcomes,
counts and hashes are in `frozen/iterative_low_llm_judge_evidence/round-3/validation_result.json`
and `frozen/iterative_low_llm_judge_evidence/round-3/independent_audit.json`.
