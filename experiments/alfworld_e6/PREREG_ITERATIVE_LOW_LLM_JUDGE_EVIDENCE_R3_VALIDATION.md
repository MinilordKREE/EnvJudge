# Privilege witness verification: round 3 validation

Method: llm_v2_iterative_low_llm_judge
Implementation: candidate-witness-v1
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

Use docs/design/AEA_LLM_PRIVILEGE_JUDGE_EVIDENCE.md and the unchanged LOW engineering
procedure in docs/design/AEA_LLM_PRIVILEGE_JUDGE.md. This is a new candidate-admission
implementation, not a retrospective correction to earlier results.

## Frozen treatment

Prompt-only revision after completed Round 2: verify every hypothesis clause and actual activation; check public goals, generic prerequisites/tool semantics and original episode prefixes before rejecting authorization; copy conditional source evidence verbatim. Preserve both schemas, host validation, runtime display, model settings, four-call protocol and LOW control logic. Main/checker prompts remain concise, without task-specific examples.

At most four logical judge calls per candidate: full judgment, reference-blind witness
check, one full reconsideration when justified, and one check of any new rejection.
Only a full-judgment PASS admits. Invalid or unresolved witness checks do not create PASS.
The exact existing PrivilegeDecision schema and DeepSeek configuration remain unchanged.
The new internal evidence schema is frozen by the source and schema hashes below.
All underlying input files, case order and labels remain byte-identical to the original.

## Bindings

- source_manifest.json: 2de6470eb2d655835e37670acdeccaccf9af01394943b0686c8f0a3e9780ab10
- input_manifest.json: d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c
- validation_manifest.json: 04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32
- carryover.json: 4c3cd20621fc426a7496c892e4467de66c7c7c97d34eb15e22ec126546f6cff3
- copied_private_inputs.json: a769f580690b7834710cc8e35a80da0ee9bce532bcb80b35069cabe91cfc15dd
- judge_prompt_sha256: 24232618a0f26047c4f7cd5f52eebc804c9ca7777375dfc2796fc16061607362
- judge_schema_sha256: cf535fc489795bfef95803ecd00b9b0ceac4aae76d655c91c8da7756dd36156d
- witness_prompt_sha256: 23b02024e94c1009a006af8cbcad923778c46707fe8dc2197dac85ec162d6f70
- witness_schema_sha256: 51ec241be852db768db551b6154cc64fb22579875ea17c3b05a9da505d2b0d2a
- Main judge prompt: 289 words, 2315 UTF-8 bytes.
- Witness prompt: 275 words, 2248 UTF-8 bytes.

## Fixed validation and stopping

Run exactly 21 case evaluations: 13 labeled core cases, four identical-input repeats and
four unlabeled saved inspections. Maximum 84 logical calls, with existing client retries
subject to the physical reserve-before-dispatch guard. Require 9/9 leak FAIL, 4/4 legitimate
PASS, four repeat agreements, all 21 valid final schemas without generated uncertainty and
complete valid witness/request/accounting audits. Saved inspections do not define labels.

Freeze before any paid request. Preserve all outcomes. This is round 3 of at
most five newly authorized rounds. Continue only after a complete, audited failed round;
record the next targeted evidence-verification/prompt treatment in a new preregistration.
Stop on success, round 5, budget exhaustion or operational interruption. Do not silently
restart partial runs. No new task screening, benchmark collection, D/I, E3 or E3-SL.

## Cumulative budget

The original four runs consumed USD 1.44588620 in conservative accounting. All earlier
and new round receipts are hash-bound in carryover.json. This round's validation ceiling
is USD 2.5; the cumulative experiment ceiling is USD 20 including
retained failed-request reservations. The new campaign replaces the old 3/17 allocation
with per-round maximum 2.50 and conditional engineering min(17, remaining total). Monetary
allocation changes do not increase any task, episode or designer-call budget.

## Conditional engineering and recipients

Only after full audited Phase A success: publish the passing freeze and engineering
preregistration, then run saved full admission replay and tasks 154/159 with the same gate.
Keep three designer calls/task, thirty adaptation episodes/task, endpoint 4-to-8,
freeze/CONTROL, acceptance 3-to-5/8 and fresh evaluation-only K16 unchanged.

Privileged judge/designer inputs may go only to https://api.deepseek.com under the user's
explicit authorization. Only admitted learner inputs may go to https://openrouter.ai/api/v1
with the frozen Qwen configuration after Phase A passes. References, GT-derived content,
raw prompts/surfaces and decision/witness prose remain local/gitignored. Public records
contain hashes, counts, fixed labels and other allowlisted metadata. Audit diff/show and
publication/history objects before push; retain all previous outcomes unchanged.

## Preserved round 1 operational failure

Round 1 remains IMPLEMENTATION_FAILURE after 19/21 cases. This round uses the explicit narrow continuation amendment in the design document: exact archived failure hashes, published failure audit and passing source-bound serialization regressions. It starts a new full 21-case schedule and retains every prior charge. This does not permit restarting round 1 or admitting its candidates.

- experiments/alfworld_e6/frozen/iterative_low_llm_judge_evidence/round-2-continuation.json: 05e4f6855e1cfa4216023b762c4df3db902210e13722d8ecd082f64ab62cdd96
- experiments/alfworld_e6/frozen/iterative_low_llm_judge_evidence/round-2-repair-tests.json: 607a963f48fd9324ca79c6418b4e9ddf78d75930d593f1839684d8b2dd0c8e77
