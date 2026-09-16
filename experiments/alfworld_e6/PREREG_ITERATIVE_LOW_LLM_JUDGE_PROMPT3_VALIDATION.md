# Independent LLM privilege judge prompt revision 3 validation

Method: llm_v2_iterative_low_llm_judge
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

This uses the frozen design in docs/design/AEA_LLM_PRIVILEGE_JUDGE.md, supplemented only
by docs/design/AEA_LLM_PRIVILEGE_JUDGE_PROMPT3.md. The experimental treatment is the additive
candidate-grounding block in JUDGE_PROMPT; the rest of Prompt-2 is byte-preserved.

No policy during validation or saved replay. No screening or task/baseline/reference generation.
Original plus Prompt-2 conservative paid carryover: USD0.72355888.
Cumulative validation physical envelope: USD3; new-run physical ceiling: USD2.27644112.
Conditional engineering ceiling: USD17. Combined cumulative ceiling: USD20, no reset/increase.

## Immutable input bindings

- source_manifest.json: 92b5b2949da745e2292e481ce50cdbf15c11fdf74c3e4ef33e97ea2847a0e9e7
- input_manifest.json: d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c
- validation_manifest.json: 04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32
- carryover.json: f9ee265faed33960ec985d38ed640bedbdd21b9880179f5a136ed31a32c57e1d
- copied_private_inputs.json: 15b474010a3ef7da479625fb7eaa32afad1f5bc97adf29e16f7c77dd775426c0

## Paired prompt-only validation

- Original run commit: 244f0f1446d3b6a4911a9514ea8bc4976f99c0da
- Prompt-2 run commit: cf8931605ce527d628187cbedcdcee27cf7590da
- Prompt-2 failed report commit: cf3273cad9f5b6283dc0e8381a072dffc07b53de
- Prompt-2 prompt SHA256: baf48d254f9200dc64e884f97985c6dcbe2a357cee5b596174f9ab70d14b38f8

- Prompt-3 prompt SHA256: dd5bfeaf51f1d01a14f546231f3545feb27b68cdbb8476465b6432270383c307

Run the exact 21-call schedule once: 13 labeled core cases, four identical-input repeats,
and four unlabeled saved inspections. Keep model, temperature, settings, schemas, case
order, labels, source/arguments, user input bytes, reference/evidence and runtime captures
unchanged. Saved-candidate verdicts are not ground-truth labels or an admission override.

Require all nine leak cases FAIL and all four legitimate controls PASS; all four repeated
core pairs agree; all 21 tool outputs validate without generated parsing uncertainty;
request isolation, hashes, provenance and conservative physical accounting reconcile.
Inspect task110, publicly_observed_location, generic_prerequisite, and goal_only_emphasis
individually as well as the full table. Any failed requirement means JUDGE_GATE_NOT_READY
and prohibits Phase B. Infrastructure/budget stops retain the original reporting rules.
No prompt/label changes after paid dispatch, no Prompt-4, and no model replacement in this run.

## Conditional freeze and Phase B

If Phase A passes all requirements, freeze and publish validation evidence plus the engineering
preregistration immediately. Then saved full admission replay precedes new DESIGN on tasks154/159
only. Preserve three calls/task, 30 adaptation episodes/task, endpoint 4->8, reserve16,
REPAIR_CODE/REPLACE_MECHANISM, freeze boundary, CONTROL, 3-5/8 search acceptance, and fresh
evaluation-only K16. No CONTROL-to-DESIGN return. All outcome precedence/limitations remain
those in the original design. No D/I, E3, E3-SL, new benchmarks or LOW architecture changes.

## Storage and authorization

Use `python -m scripts.e6_iterative_low_llm_judge_prompt3` in the new namespace. The launcher
only changes recording/freeze bindings and verifies both prior closed budgets read-only.
DeepSeek receives only the previously explicitly authorized judge/designer material; conditional
OpenRouter/Alibaba learner calls receive only admitted learner-facing inputs after Phase A.
Privileged reference and designer-only evidence remain outside learner authorization.
Raw references, GT content, source/arguments, prompts, surfaces and decision prose stay local
and gitignored. Public output consists of implementation/synthetic fixtures and non-sensitive
hashes, provenance, counts, categorical outcomes and audit metadata. Preserve both earlier runs.
