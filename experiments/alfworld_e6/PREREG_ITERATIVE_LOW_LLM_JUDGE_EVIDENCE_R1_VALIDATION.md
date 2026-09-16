# Privilege witness verification: round 1 validation

Method: llm_v2_iterative_low_llm_judge
Implementation: candidate-witness-v1
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

Use docs/design/AEA_LLM_PRIVILEGE_JUDGE_EVIDENCE.md and the unchanged LOW engineering
procedure in docs/design/AEA_LLM_PRIVILEGE_JUDGE.md. This is a new candidate-admission
implementation, not a retrospective correction to earlier results.

## Frozen treatment

Add independent candidate-side witness verification with exact source/runtime/public anchors and unresolved-result blocking. Shorten the main judge prompt to candidate-grounded provenance adjudication; freeze the concise reference-blind checker prompt. Preserve all existing case bytes, labels, model settings and LOW control logic.

At most four logical judge calls per candidate: full judgment, reference-blind witness
check, one full reconsideration when justified, and one check of any new rejection.
Only a full-judgment PASS admits. Invalid or unresolved witness checks do not create PASS.
The exact existing PrivilegeDecision schema and DeepSeek configuration remain unchanged.
The new internal evidence schema is frozen by the source and schema hashes below.
All underlying input files, case order and labels remain byte-identical to the original.

## Bindings

- source_manifest.json: 0bfb24ad972eb0b06bbbeb08e3a3ac0b99455a88166a205c227bff0bf37f60ee
- input_manifest.json: d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c
- validation_manifest.json: 04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32
- carryover.json: 965de895d9f34c869dbdae2f5dbd22b24c2aa782e23726a142f052f4f2d7e918
- copied_private_inputs.json: 33e904fe89c93df3197ac97ac09ecf1b080e524984b72c9238504a2edeb60a40
- judge_prompt_sha256: 20a791b1225102fd8da1dd0e7e2e09432b8eb3f8812be3dcbec65ec18b126024
- judge_schema_sha256: cf535fc489795bfef95803ecd00b9b0ceac4aae76d655c91c8da7756dd36156d
- witness_prompt_sha256: 39991dfce59fa2ec7cb5f972346f41235dcc1d2cf1f65f2c03308ac244555d1e
- witness_schema_sha256: 51ec241be852db768db551b6154cc64fb22579875ea17c3b05a9da505d2b0d2a
- Main judge prompt: 283 words, 2162 UTF-8 bytes.
- Witness prompt: 309 words, 2395 UTF-8 bytes.

## Fixed validation and stopping

Run exactly 21 case evaluations: 13 labeled core cases, four identical-input repeats and
four unlabeled saved inspections. Maximum 84 logical calls, with existing client retries
subject to the physical reserve-before-dispatch guard. Require 9/9 leak FAIL, 4/4 legitimate
PASS, four repeat agreements, all 21 valid final schemas without generated uncertainty and
complete valid witness/request/accounting audits. Saved inspections do not define labels.

Freeze before any paid request. Preserve all outcomes. This is round 1 of at
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
