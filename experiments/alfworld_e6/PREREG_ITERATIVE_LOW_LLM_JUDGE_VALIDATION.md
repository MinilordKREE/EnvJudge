# Independent LLM privilege judge validation

Method: llm_v2_iterative_low_llm_judge
Base driver SHA256: 980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33

This stage uses the exact frozen design in docs/design/AEA_LLM_PRIVILEGE_JUDGE.md.
No policy during validation or saved replay. No task/baseline/reference generation.
Hard physical cap: USD 3. No increase or reset.

## Immutable input bindings

- source_manifest.json: 518f992089a6c4fc9ef72748ea25f5dc0700be06952a05d6e3b6c3857c10ecf1
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

## Publication boundary

Full input and reference bytes remain in the gitignored private store. Public manifests
contain only identifiers, counts, hashes, labels, and configuration. This publication-only
checkpoint starts no paid validation; the sanitized commit and audit must be reported first.
