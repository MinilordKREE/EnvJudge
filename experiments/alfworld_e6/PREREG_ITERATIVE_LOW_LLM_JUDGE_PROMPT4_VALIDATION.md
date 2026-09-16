# Independent LLM privilege judge: concise prompt revision 4 validation

Method: llm_v2_iterative_low_llm_judge
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

Use docs/design/AEA_LLM_PRIVILEGE_JUDGE.md and the prompt-only supplement
docs/design/AEA_LLM_PRIVILEGE_JUDGE_PROMPT4.md. The treatment is a concise replacement
of JUDGE_PROMPT inspired by HarnessEvolve's stated gate criterion, not a recovered author
prompt. Model, schema, input payloads, labels and decision pipeline stay fixed.

Prior three-run conservative spend: USD1.09190796. New validation ceiling: USD1.90809204.
The original cumulative validation envelope remains USD3; conditional engineering remains
USD17. The cumulative hard ceiling is USD20, including prior and failed-request costs.

## Immutable bindings

- source_manifest.json: 720c72c502d6de02ff3b287f15927ff7522a7598ef7dcf94c835dbedcfea60fb
- input_manifest.json: d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c
- validation_manifest.json: 04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32
- carryover.json: 1b855fe28c7ee1115b4d7d089d17369734a89e5290306ece09a4f976e59121a5
- copied_private_inputs.json: 48a3caa0001136554f098c1d1964f5eb49f980909edfe541b2366e7240a07ab4

- Previous prompt SHA256: dd5bfeaf51f1d01a14f546231f3545feb27b68cdbb8476465b6432270383c307
- Revised prompt SHA256: 90a558a54bce501f6233abbd5d043077cdc12551c5d0a2d73b08be3489511d82
- Previous prompt: 10914 UTF-8 bytes, 1476 whitespace-separated words.
- Revised prompt: 2416 UTF-8 bytes, 324 whitespace-separated words.

## Schedule and acceptance

Run the exact 21-call schedule once: 13 labeled core cases, four identical-input repeats,
four unlabeled saved inspections. Preserve case order, labels, sources/arguments, user payload
bytes, references, evidence, runtime surfaces, model/client settings and tool schemas.
All nine known leaks must FAIL; all four legitimate controls must PASS; all four repeat pairs
must agree. All 21 outputs must validate without generated uncertainty. Request isolation,
source/provenance hashes and conservative accounting must pass the independent audit.
Saved inspections are not accuracy labels and cannot override a failed core requirement.

No policy during Phase A or saved replay. No task, baseline, reference or benchmark generation.
No changes after the first paid result. Acceptance failure means JUDGE_GATE_NOT_READY and
stops this revision; infrastructure/budget interruptions retain the original reporting rules.

## Conditional Phase B and unchanged boundaries

Only on full audited PASS: publish passing validation and engineering preregistration, then
perform the already authorized full saved admission replay followed by tasks154/159 DESIGN.
Preserve three calls/task,30 adaptation episodes/task,endpoint4->8,reserve16,feedback routing,
freeze,CONTROL,search acceptance3-5/8 and fresh evaluation-onlyK16. Outcome precedence remains
the original design. No D/I,E3,E3-SL,model/schema/pipeline changes or fresh screening.

The prompt4 launcher imports unchanged execution functions and binds recording paths and
remaining budget only. Earlier reports, caps, attempt journals and private records remain
unchanged. Twenty-three prepared private inputs are copied exactly from the original run.

## Recipients and publication

Existing explicit authorization covers full frozen judge/designer inputs to
https://api.deepseek.com and, only after Phase A passes, admitted learner-facing inputs to
https://openrouter.ai/api/v1 with the frozen Alibaba/Qwen learner. Privileged reference and
designer-only evidence remain unavailable to that learner.
Full references,GT content,candidate code/arguments,raw prompts/surfaces and judge prose stay
local and gitignored. Public artifacts retain only implementation,synthetic fixtures and
non-sensitive audit metadata. Review diff/show and publication/history objects before push.
