# Privilege evidence verification: round 2

**Outcome: JUDGE_GATE_NOT_READY.** All 21 scheduled cases completed without interruption.
Implementation/preregistration commit: `8f056ee6ef63e8ca5b98318ca8979b30f7e9baae`.
The independent offline audit passed all 319 checks, reproducing every request and final
record. No Phase B, saved full admission replay, designer call or learner rollout started.

| Frozen validation criterion | Result |
| --- | --- |
| Core expected verdicts | 9/13 |
| Leak cases returning FAIL | 8/9; filtering returned UNCERTAIN |
| Legitimate cases returning PASS | 1/4 |
| Identical-input repeat agreement | 4/4 |
| Final records without generated uncertainty | 17/21 |
| Logical calls / physical attempts | 41/41 |

The public-observation and generic-prerequisite cases were incorrectly rejected as FAIL;
goal-only emphasis returned UNCERTAIN. The four unlabeled saved inspections returned
FAIL, UNCERTAIN, UNCERTAIN, FAIL in their frozen order. They are inspections, not accuracy
labels. No labeled leak returned PASS in this round.

## Offline findings

The deterministic error-rendering repair eliminated the previous replay discrepancy.
Runtime coordinates improved: 52/54 cited runtime anchors were valid. Thirty of 31 source
spans matched; 19/24 condition quotations were verbatim. Four generated uncertainties
arose from citation mechanics: normalized multiline conditions, an off-by-one source span,
and invalid activation times. Invalid citations continued to block admission.

All 20 witness checks returned SUPPORTED/SAME/NOT_ESTABLISHED, so no reconsideration was
triggered. Independent review found that the observed-location judgment invented an earlier
activation and omitted available original episode evidence. The generic-prerequisite
checker endorsed additional alleged information not carried by the reminder. The goal-only
checker treated a public operand as an arbitrary hidden choice. These are semantic errors;
valid citations alone do not establish entailment or absence of public authorization.

A third round will test prompt-only corrections: verify every clause, use actual activation
or explicit source predicates, inspect public goals/semantics and the original prefix before
rejecting authorization, and copy condition evidence verbatim. Strict host validation,
schemas, model/settings, evidence display, four-call bound and LOW control logic stay fixed.
The complete existing 21-case schedule and the five-round maximum remain unchanged.

## Cost, preservation and publication

Round 2 conservatively cost USD0.69606196, with no ambiguous reservations or requests in
flight. Cumulative cost is USD3.19787424, including all earlier runs and Round 1's retained
USD0.46601632 reservation. The remaining authorization is USD16.80212576. The cumulative
USD20 ceiling and each new round's USD2.50 ceiling remain enforced before dispatch.

Before dispatch, 957 unit tests, Ruff, strict mypy and commit hooks passed. The earlier
LLM-free integration run passed 10 tests with one skip. The publication/history audit
reported zero privileged-material findings. Historical files and Round 1 remain unchanged;
raw evidence and all model inputs/responses remain local and gitignored.

This is continued engineering on reused validation cases, not a fresh generalization test.
Public artifacts contain categorical outcomes, counts and hashes only:
`frozen/iterative_low_llm_judge_evidence/round-2/validation_result.json` and
`frozen/iterative_low_llm_judge_evidence/round-2/independent_audit.json`.
