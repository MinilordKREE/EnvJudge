# Iterative LOW pilot with the frozen R5 judge

Date: 2026-09-17 UTC. Protocol: `iterative-low-r5-judge-pilot-v1`.
Execution and preregistration commit: `b6d9e693999dd9d77461a5f4270ad152185e2a54`.

## Outcome

The frozen engineering decision is **LOW_IMPLEMENTATION_WORKS**. On task 159, a
measured failure led to a revised candidate that reached search acceptance and
passed the preregistered broad confirmation band. Task 154 exhausted its three
DESIGN calls without a successful episode.

| Task | C1 endpoint | C2 endpoint | C3 endpoint | DESIGN calls | Adaptation episodes | Fresh K16 |
| --- | --- | --- | --- | --- | --- | --- |
| 154 | 0/4, too hard | 0/4, too hard | 0/4, too hard | 3 | 12 | Not triggered |
| 159 | 0/4, too hard | 3/8, accepted at d=1 | Not dispatched after freeze | 2 | 12 | 5/16 |

Task 159 C2 first measured 1/4, then 2/4 in the additional batch. Its 3/8 endpoint
met the frozen search criterion of 3..5/8. C2 was the first viable family and was
frozen at dose 1. No CONTROL search occurred. Fresh K16 achieved 5/16 (31.25%):
inside B_L=4..12/16, outside B_T=7..9/16. K16 supplied no redesign or acceptance
feedback. No task 159 C3, extra confirmation, or post-confirmation adjustment ran.

## What the run establishes

Three measured-feedback transitions occurred: task 154 C1->C2 and C2->C3, and
task 159 C1->C2. Each used the actual previous endpoint and a recorded failed
parent episode with `no_leverage` / `REPLACE_MECHANISM`; each produced a distinct
template. The task 159 sequence was 0/4 -> 3/8 -> fresh 5/16. This supports engineering
viability for the realized iterative path on these reused tasks.

The small, adaptively selected samples do not establish a causal advantage of
feedback. Task 154 showed no improvement. The broad K16 criterion passed on one
task; the narrow target band did not. This pilot did not exercise CONTROL or
produce a fresh scientific efficacy estimate. No D/I, E3, E3-SL, new task
screening, or further judge tuning was performed.

## Judge and frozen boundaries

All four saved candidates and all five fresh proposals passed full admission.
The fresh proposals also passed structural/lexical checks and oracle solvability.
Each semantic record covered the frozen 17-dose grid. No candidate admission
rejection occurred in this pilot; judge rejection did not cause task 154's outcome.
These nine inspections are unlabeled and do not measure judge accuracy.

R5 remains **JUDGE_GATE_NOT_READY**. The user explicitly authorized removing the
Phase-A-pass startup prerequisite for this prospective pilot. Candidate-level
PASS admission, the R5 judge/model/prompts/schema, LOW logic, freeze boundary,
acceptance rules and recipients stayed unchanged. FAIL/UNCERTAIN were not
manually overridden. Earlier experiment results were not relabeled.

## Accounting

| Budget component | Conservative USD |
| --- | ---: |
| All prior committed costs/reservations | 4.933041080 |
| Pilot returned calls at guarded rates | 3.745386032 |
| Pilot retained ambiguous reservation | 0.005765929 |
| Pilot total | 3.751151961 |
| Cumulative total | **8.684193041** |
| Cumulative hard cap | 20.000000000 |

There were 1849 physical attempts: 1848 returns and one APIConnectionError whose
full reservation remains charged to the guard. The frozen client retried; no
stage was restarted. No inflight reservations or terminal interruption remain.
The pilot's returned logical ledger cost is USD 3.367354798; it is distinct from
the conservative budget commitment above. The R5 validation cost shown in the
machine report is already included in prior spending and must not be added again.

All five DESIGN calls, nine judge calls and 1834 returned learner calls are
accounted for. There were 24 adaptation episodes and 16 fresh confirmation episodes.
Paid execution stopped after the prescribed K16.

## Verification and artifacts

Independent offline execution audit: **3980/3980 checks PASS**. It replays stored
judge responses, reconstructs stored runtime evidence, checks actual feedback
lineage, all 40 fresh candidate-bound traces, K16 source/dose identity and isolation
from adaptation, public report projection, and physical/logical accounting.
The 85 frozen source hashes, 533 prior private files and 693 prior tracked files are
unchanged. The pre-execution 202 focused tests remain the checks for the unchanged
implementation.

The audit does not re-execute environments or establish semantic truth for new
candidates. Physical journals lack request-body hashes, so cross-ledger matching
uses the logged attribution, model, token usage and timing. Raw designer responses
were not separately logged; proposal arguments bind to saved optimizer records.

- [Frozen preregistration](PREREG_ITERATIVE_LOW_LLM_JUDGE_PILOT.md)
- [Machine report](results/iterative_low_llm_judge_pilot/report.json)
- [Task and candidate metadata](results/iterative_low_llm_judge_pilot/task_metadata.json)
- [Execution audit metadata](results/iterative_low_llm_judge_pilot/execution_audit.json)

Full execution-audit SHA256:
`c7cf4ac2ad9e51d4f9ec03db555479ad7f5225a567d58858329e0c72df454ac4`.
Auditor-source SHA256:
`04f7390e15ba803ff83faa93fbdc9d62f11523aa53bc52663f0be09885093364`.

Full references, observations/actions, candidate code, raw requests/responses,
runtime captures and free-text designer/judge feedback remain local and gitignored.
Publication contains only this research summary and allowlisted metadata. The
outgoing publication is screened separately from inherited history. The previous
history audit retained 3136 fingerprint findings; no clean-history claim or history
rewrite is made. Fresh pilot fingerprints apply to new outgoing content, while the
exact earlier audit supplies inherited-history coverage.
