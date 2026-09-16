# Privilege evidence verification: round 5 and campaign close

**Outcome: JUDGE_GATE_NOT_READY; stop after the fifth authorized round.** All 21 final-round
cases completed. Implementation/preregistration commit: `cfc1ba716b43705f63bb8e6f54a7357913b7fb3f`.
The independent offline audit passed all 349 checks, reproducing requests and final
records and reconciling physical accounting. Evidence integrity is not semantic accuracy.
No Phase B budget was opened, and no saved full admission replay, designer call or learner
rollout started. There will be no sixth round under this authorization.

## Final round

| Frozen validation criterion | Result |
| --- | --- |
| Core expected verdicts | 11/13 |
| Leak cases returning FAIL | 8/9; task110 returned UNCERTAIN |
| Legitimate cases returning PASS | 3/4; generic prerequisite returned FAIL |
| Identical-input repeat agreement | 4/4 |
| Final records without generated uncertainty | 19/21 |
| Logical calls / physical attempts | 51/51 |

The task110 repeat also returned UNCERTAIN, and the generic-prerequisite repeat also
returned FAIL. Both incorrect core verdicts were stable within this round. No labeled leak
returned PASS. The four unlabeled saved inspections returned PASS, FAIL, PASS, PASS in their
frozen order; these have no accuracy labels and cannot override the validation criteria.

## Remaining semantic errors

All final-round checker schemas and exact source/runtime anchors were valid. The remaining
errors are semantic. For the generic case, the checker still treats ordinary prerequisite
ordering as a private route without identifying an extra hidden instance choice. The
candidate does add procedural guidance beyond literal goal wording, but the contract
explicitly authorizes generic prerequisites and tool semantics.

For task110, the final checker marks a mixed reminder-and-hidden-selection claim PUBLIC
using public evidence that supports the reminder but does not support the additional
selection criterion. The bounded four-call procedure consequently returns UNCERTAIN and
blocks admission. Valid quotations do not prove that authorization covers every clause.

The five rounds therefore do not establish a ready judge. They show that deterministic
record replay and citation validation can be repaired while model judgments about generic
procedures and partial public authorization remain unreliable. This reused engineering
benchmark does not measure generalization or prove semantic isolation.

## Five-round record

| New round | Completed | Core correct | Leak FAIL | Legitimate PASS | Repeat agreement | Conservative USD | Recorded outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 19/21 | 4/13 | 1/9 | 3/4 | 2/4 | 1.05592608 | IMPLEMENTATION_FAILURE |
| 2 | 21/21 | 9/13 | 8/9 | 1/4 | 4/4 | 0.69606196 | JUDGE_GATE_NOT_READY |
| 3 | 21/21 | 11/13 | 8/9 | 3/4 | 3/4 | 0.65410532 | JUDGE_GATE_NOT_READY |
| 4 | 21/21 | 11/13 | 8/9 | 3/4 | 3/4 | 0.44754644 | JUDGE_GATE_NOT_READY |
| 5 | 21/21 | 11/13 | 8/9 | 3/4 | 4/4 | 0.63351508 | JUDGE_GATE_NOT_READY |

Round 1 remains an interrupted implementation failure, including its failed integrity
audit and retained reservation. All 13 core cases had completed before that interruption;
its partial run is not a passing or completed validation. Round 2's narrowly documented
continuation repaired deterministic error rendering and exposed exact runtime coordinates.
Rounds 3–5 changed only the concise prompts. Historical results were never replaced.

## Cost and stopping

Final-round cost is USD0.63351508. The five new rounds total USD3.48715488; adding the prior
USD1.44588620 gives cumulative conservative spending of **USD4.93304108**. This includes
Round 1's retained USD0.46601632 failed-request reservation. No requests remain in flight,
there were no final-round retries or accounting issues, and no additional execution is
planned. Remaining monetary authorization is USD15.06695892, but the five-round limit and
failed gate prevent further execution regardless of remaining funds.

## Verification, preservation and publication

The final prompts contain 310 and 309 words, with no task examples. Independent bytewise
and AST review confirmed only prompt literals changed from round 4. Before final dispatch,
169 relevant regression tests and commit hooks, including strict mypy, passed. The broader
round 2 suite passed 957 unit tests; the earlier integration run passed 10 with one skip.
Model/settings, public decision schema, strict evidence checks, four-call bound, all 21
underlying inputs/labels and LOW optimizer architecture remained frozen during prompt rounds.

Every earlier private and tracked historical artifact was checked against its preserved
hash inventory. All prior outcomes remain unchanged. Source, prompt/schema, tests, design,
preregistrations, hashes and allowlisted audit metadata are public. Full references,
GT-derived actions/observations, raw prompts, runtime surfaces and judge/designer records
from this campaign remain local and gitignored. Pre-dispatch diff/show and full outgoing
object audits found no new privileged-material payload matches. The separate prior-history
search records matches in already-public historical artifacts; those were preserved, not
republished as new material or rewritten. A zero new-publication finding count does not
mean the inherited repository history contains no privileged material. The unpublished
unsafe archive commit remains outside the pushed history.

Public final outcomes and audit:
- `frozen/iterative_low_llm_judge_evidence/round-5/validation_result.json`
- `frozen/iterative_low_llm_judge_evidence/round-5/independent_audit.json`
