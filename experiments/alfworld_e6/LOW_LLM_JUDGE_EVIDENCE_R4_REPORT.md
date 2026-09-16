# Privilege evidence verification: round 4

**Outcome: JUDGE_GATE_NOT_READY.** All 21 scheduled cases completed without interruption.
Implementation/preregistration commit: `8b4806c00b239724fe799d619c00d953b52c7b0f`.
The independent offline audit passed all 328 checks, reproducing every request and final
record. No Phase B, saved full admission replay, designer call or learner rollout started.

| Frozen validation criterion | Result |
| --- | --- |
| Core expected verdicts | 11/13 |
| Leak cases returning FAIL | 8/9; transition feedback returned UNCERTAIN |
| Legitimate cases returning PASS | 3/4; generic prerequisite returned FAIL |
| Identical-input repeat agreement | 3/4 |
| Final records without generated uncertainty | 19/21 |
| Logical calls / physical attempts | 44/44 |

Delayed ranking now returned FAIL. The task110 repeat returned UNCERTAIN while its core
judgment returned FAIL. All four unlabeled saved inspections returned PASS; these have no
accuracy labels and do not establish gate readiness. No labeled leak returned PASS.

## Offline findings and final authorized revision

The generic case contains procedural guidance beyond the literal goal, but no additional
hidden instance choice. Neither judge nor checker supplied such a choice. They treated
find/acquire/transport ordering as private despite the input contract authorizing generic
prerequisite and tool semantics. This is a semantic authorization error, not a missing
quotation or a contradictory fixture.

The transition-feedback check used an off-by-one source end line. The task110 repeat
correctly narrowed the alleged information, but full reconsideration reintroduced the
discarded reference-route clauses; its second checker narrowed again. Both conditions
continued to return UNCERTAIN. No host check was bypassed or relaxed.

Round 5 will be the final authorized attempt. Its prompt-only treatment will clarify that
contract-authorized reusable procedures may add steps beyond verbatim goal text, preserve
the supported narrowed proposition during reconsideration, and simplify exact source
line-span citations. The same model, schemas, host checks, inputs, labels, four-call bound
and LOW workflow remain fixed. Failure in round 5 stops validation without Phase B.

## Cost, preservation and publication

Round 4 conservatively cost USD0.44754644, with no ambiguous reservations or requests in
flight. Cumulative cost is USD4.29952600, including earlier runs and Round 1's retained
USD0.46601632 reservation. Remaining authorization is USD15.70047400. The cumulative
USD20 ceiling and each new round's USD2.50 ceiling remain enforced before dispatch.

Before dispatch, 169 relevant unit tests and commit hooks, including strict mypy, passed.
Independent bytewise/AST review confirmed only two prompt literals changed. Prompts contain
308 and 310 words. Publication/history audit found zero privileged-material matches.
All earlier artifacts remain unchanged. Raw references, inputs and responses stay local
and gitignored. This is engineering on reused cases, not a fresh generalization test.

Public counts, verdicts and hashes are in
`frozen/iterative_low_llm_judge_evidence/round-4/validation_result.json` and
`frozen/iterative_low_llm_judge_evidence/round-4/independent_audit.json`.
