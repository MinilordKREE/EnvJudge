# Independent LLM privilege judge prompt revision 2 validation

Method: llm_v2_iterative_low_llm_judge
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

This stage uses the exact frozen design in docs/design/AEA_LLM_PRIVILEGE_JUDGE.md.
No policy during validation or saved replay. No task/baseline/reference generation.
Cumulative Phase-A physical envelope: USD 3, including prior committed USD0.35856656.
New-run physical ceiling: USD2.64143344. Engineering ceiling: USD17.
Combined old + new validation + engineering ceiling: USD20. No increase or reset.

## Immutable input bindings

- source_manifest.json: bea5125d4de264d89aae53f091b1e791c0b60f364f6a802961ee2e00a8c6ccde
- input_manifest.json: d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c
- validation_manifest.json: 04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32

## Acceptance and order

Labeled regressions must match; identical core repeats must agree.
Saved candidates are unlabeled inspections; verdicts are not ground-truth labels.
Any validation acceptance failure means JUDGE_GATE_NOT_READY and no LOW policy.
Engineering requires pushed passing validation and frozen implementation first,
then saved admission replay, then new DESIGN on 154/159 only with 3 calls/task,
30 adaptation episodes/task, reserve16 unchanged and fresh evaluation-only K16.
Reporting precedence and limitations are exactly those in the frozen design document.

## Prompt-only comparison and operational bindings

The experimental treatment changes only JUDGE_PROMPT. Model, schemas, settings, case order,
labels, candidate/user input bytes, and LOW decision functions remain unchanged. The full
revision design is docs/design/AEA_LLM_PRIVILEGE_JUDGE_PROMPT2.md; it supplements the preserved
original design. Use `python -m scripts.e6_iterative_low_llm_judge_prompt2` for this namespace.

- Prior failed validation run commit: 244f0f1446d3b6a4911a9514ea8bc4976f99c0da
- Prior result/report commit: 3f78d28a785739f1a218b1535a2408d3ad4e069b
- Prior prompt SHA256: f9473b7429c3ee35896250d27d9b1d9ae2f3f2e973c19158fe55569ee604f180
- Revised prompt SHA256: baf48d254f9200dc64e884f97985c6dcbe2a357cee5b596174f9ab70d14b38f8
- carryover.json: 5652a8dd367991b06a081ff9a8ef6d733da633d51dac6689caa76af988472aa3
- copied_private_inputs.json: 13341a9e360588953f1b83fd3b0fa0537c0608a093d245a22e3215c7912d672a

All 21 tool outputs, including the four unlabeled inspections, must validate without
generated parsing uncertainty. A complete leak miss, legitimate-control rejection,
repeat disagreement, schema failure, or request-isolation failure prohibits Phase B.
The fixed21 schedule runs once without post-result prompt or label changes. The previously
authorized API payload/destination boundary and remaining USD20 combined cap apply.
Raw inputs and outputs remain local and gitignored. No new screening or reference capture.
