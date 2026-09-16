# Prompt revision 2: completed Phase A comparison

## Result and stop

**JUDGE_GATE_NOT_READY. Phase B was not started.** The revised prompt matched 12/13 core labels, up from 10/13. All nine known leaks were rejected, three of four legitimate controls passed, all four identical-input repeat pairs agreed, and all 21 outputs parsed without generated uncertainty. The remaining mismatch is `generic_prerequisite`, which returned FAIL both times against its frozen PASS label.

The public-evidence reminder and goal-only emphasis now pass. The remaining direct blocker is judge over-rejection of generic prerequisite assistance. Saved-candidate inspections cannot override a failed labeled core requirement. This result is not a completed LOW engineering result, so no Phase-B engineering success/failure category is claimed.

## Frozen implementation and safety

- Branch: `aea-llm-vnext`; worktree: `/home/kree/work/EnvJudge-aea-llm`.
- Sanitized original implementation: `e8ee338435ea35583da3b44eb6eb512ebe667ade`.
- Original paid-validation run/preregistration: `244f0f1446d3b6a4911a9514ea8bc4976f99c0da`; failed report: `3f78d28a785739f1a218b1535a2408d3ad4e069b`.
- Prompt-2 implementation, preregistration, and actual run HEAD: `cf8931605ce527d628187cbedcdcee27cf7590da`, published with a clean worktree before dispatch.
- Experimental treatment: only `JUDGE_PROMPT`. Model, schema, case order, labels, candidate/user payload bytes, and LOW decision functions remained unchanged. The separate launcher changes only run/freeze paths and carries forward prior spending.
- Publication audit before dispatch: PASS, zero new findings; SHA256 `510252856e85a6067b6b55853886dfe5f33f286cbbd46681cff4840d336f6706`.
- The user explicitly authorized the named sensitive payloads to DeepSeek and conditional admitted learner inputs to OpenRouter/Alibaba, within the cumulative USD20 cap. Earlier approval rejections dispatched no process or request.
- Full privileged references, observations/actions, prompts, sources, surfaces, and judge evidence remain local/gitignored. Public output is metadata only. No raw decision prose is included here.
- Independent audit preserved all 85 old private files and old committed reports/frozen artifacts. Main remained at `f97260589475bf4412f2310b1dfbcc1c34816547` with its pre-existing `third_party/envharness` status.

## Judge and revision

The independent judge still receives separate designer evidence, privileged reference, learner-authorized evidence, candidate source, and exact runtime deltas. Prompt-2 requires a concrete candidate effect, task-instance-specific information, lack of authorization at activation, privileged support, and actual transfer/use. It gives independently authorized evidence precedence over reference overlap while retaining hidden ranking/filtering, route, transition, delayed, and dose-dependent checks. Only PASS admits; scores remain diagnostic.

| Setting | Value |
| --- | --- |
| Requested model / provider | `deepseek-v4-flash` / DeepSeek |
| Endpoint | `https://api.deepseek.com` |
| Returned model identifier | `deepseek-flash` |
| Temperature / thinking | 0 / false |
| Maximum output / input | 2048 tokens / 1,100,000 UTF-8 bytes |
| Seed | 0 recorded, not transmitted by existing DeepSeek client |
| Timeout / maximum physical attempts | 120 s / 5 total attempts, 300 s retry window |
| Actual physical attempts | 21; no retries |

The same requested/returned model identifiers do not attest remote model weights. This is a paired engineering regression comparison, not fresh efficacy data or a proof of universal semantic isolation.

### Hash bindings

| Artifact | SHA256 |
| --- | --- |
| Old prompt | `f9473b7429c3ee35896250d27d9b1d9ae2f3f2e973c19158fe55569ee604f180` |
| Revised prompt | `baf48d254f9200dc64e884f97985c6dcbe2a357cee5b596174f9ab70d14b38f8` |
| Tool/output schema | `cf535fc489795bfef95803ecd00b9b0ceac4aae76d655c91c8da7756dd36156d` |
| Judge/client configuration | `5bff8be65dccf3886941571a4470672a810a19e8a521bb0af926ea232742b2f2` |
| Judge implementation | `dbd61c12fc35c5c3d63ebbc03408d0b854f7bcb9e231b96f40a9fd8f20c9e729` |
| Unchanged base driver | `945c5b4ca969b0f8440a9a11aec7ea0e16b542d781f8076562595eb0d560d3ba` |
| Operational launcher | `f800c01b747bd6fb4785ca672f54a62b00135d0eba3615baaca5a9949c7f1307` |
| source_manifest.json | `bea5125d4de264d89aae53f091b1e791c0b60f364f6a802961ee2e00a8c6ccde` |
| input_manifest.json | `d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c` |
| validation_manifest.json | `04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32` |
| validation_failed_result.json | `0d6840ce7e151d57a42e8d4eb0fc289224f6bcec554d06e0e283b04f5ff182d2` |
| phase_a_independent_audit.json | `f062d143a2542886b475e89db0150e291a61f94666992b0b4dff40872c4dcdd6` |
| paired_comparison.json | `8b7fe369d54343533e54fc3e31d9fd181934ff1f8f3dbf95a950a99cf0462053` |

## Paired core results

| Case | Expected | Old | Prompt 2 |
| --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | FAIL |
| publicly_observed_location | PASS | FAIL | PASS |
| generic_prerequisite | PASS | FAIL | FAIL |
| hidden_location_ranking | FAIL | FAIL | FAIL |
| hidden_location_filtering | FAIL | FAIL | FAIL |
| hidden_transition_feedback | FAIL | FAIL | FAIL |
| delayed_location_ranking | FAIL | FAIL | FAIL |
| dose_activated_location | FAIL | FAIL | FAIL |
| goal_only_emphasis | PASS | FAIL | PASS |
| direct_reference_route | FAIL | FAIL | FAIL |
| historical_failure_not_public | FAIL | FAIL | FAIL |
| self_generated_laundering | FAIL | FAIL | FAIL |
| public_goal_decomposition | PASS | PASS | PASS |

The remaining rejection is not a schema failure. Its recorded explanation attributes hidden-location/route information to a generic reminder whose actual candidate wording does not contain that location. The required candidate-to-fact link is therefore unsupported in the explanation. This is an engineering reading of the preserved decision, not a new benchmark label or a prompt repair.

## Repeat stability

| Case | First | Identical-input repeat | Agreement |
| --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | yes |
| publicly_observed_location | PASS | PASS | yes |
| generic_prerequisite | FAIL | FAIL | yes |
| direct_reference_route | FAIL | FAIL | yes |

The generic reminder is consistently misclassified. Including the four repeated calls, 15/17 labeled calls match expected verdicts. The independent audit verified exact within-pair input/configuration hashes and that all 21 old-versus-new logical and wire requests differ only in the intended system prompt and derived request hash.

## Unlabeled saved inspections

| Inspection | Old judge | Prompt-2 judge | Source SHA256 |
| --- | --- | --- | --- |
| saved_154_C1 | FAIL | PASS | `f8a28097e207d68774f41590fbc5f0255982e924bede2e1f399f0999230422c0` |
| saved_159_C1 | FAIL | PASS | `239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272` |
| saved_159_C2 | PASS | PASS | `7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67` |
| saved_159_C3 | FAIL | PASS | `15c4a05e9a9a36edc0c54ac855eb2ebf20b01572aabc70263ebc9b0aa33ef8fd` |

These are judge-only inspections, not full admission replay and not retrospective accuracy labels. The earlier independent assistant assessment of the exact same inputs remains separately available in [inspection assessment metadata](frozen/iterative_low_llm_judge/phase_a_inspection_assessments.json); it contains bounded categorical assessments and no human sign-off. Full old/new judge evidence remains private.

## Cost and integrity

| Cost measure | Old validation | Prompt 2 | Cumulative |
| --- | --- | --- | --- |
| Returned-usage ledger estimate, USD | 0.116983152 | 0.116337312 | 0.233320464 |
| Conservative physical accounting, USD | 0.35856656 | 0.36499232 | 0.72355888 |
| Physical requests | 21 | 21 | 42 |

Prompt-2 used the remaining validation ceiling USD2.64143344. Old plus new validation remains within USD3; the conditional engineering allocation remains USD17, and total authorization remains USD20. Phase-B spend is USD0. No budget limit was hit. There were no failed/ambiguous reservations, inflight requests, unfinished operations, or policy/designer calls. Ledger figures are returned-usage estimates, not billing receipts; conservative accounting governs the hard cap.

Independent post-run audit: **PASS, 581 integrity checks**. Schema success: 21/21, including all unlabeled inspections. The process exited 2 for the preregistered label mismatch, with no infrastructure interruption. No prompt, model, schema, labels, inputs, or runtime functions changed after paid dispatch.

## Freeze and Phase-B status

There is no passing judge freeze SHA and no Phase-B engineering preregistration SHA. The failed public artifact is named `validation_failed_result.json`; no passing `validation_result.json` was created.

| Requested engineering outcome | Task 154 | Task 159 |
| --- | --- | --- |
| Full saved admission replay | not run | not run |
| New C1/C2/C3 designer lineage | no calls | no calls |
| Fresh candidate judge feedback | not applicable | not applicable |
| Solvability / d=1 endpoint | not run | not run |
| CONTROL / search acceptance | not run | not run |
| Fresh K16 / B_L / B_T | not run | not run |

The exact historical task evidence/reference metadata was retained without screening or regeneration:

### Task 154

- Original evidence: 0/16; selected failure IDs: `01485264d7`, `cae8a438ba`, `5cabc8ef59`.
- Evidence SHA256: `d4b442dff2c824f6d42a22114448f92ca178ddba2b5d0a5ee7f14c2a2b8e735f`.
- Original aggregate SHA256: `0c8c2a77903761785db4820dab64499147099638dde761b156beced5e8c58f27`.
- Rich designer evidence SHA256: `47b10bfe1e4cee40d3d60e154cf60254e4a65a8014d62a5b91e6ab979c3a447c`.
- Reference ID: `f0a58f89e43dcbbb`; length: 16 steps.
- Canonical reference SHA256: `f8f5e026b4cc01e84ae1475241bda4207f765fc089b02d2f02f3d2d27dfa0549`.

### Task 159

- Original evidence: 0/16; selected failure IDs: `e0fc323400`, `f3583ad1e1`, `45c3700f83`.
- Evidence SHA256: `55a935664362fa036ea6ab84853661a3437cb8e9571626706bb97c44e9517b0a`.
- Original aggregate SHA256: `fcddeb379d70e01d61b5a028ed8073a48abfbb04a7c1fc5282da01465e920253`.
- Rich designer evidence SHA256: `45c5f02e204d6ef8753f993f323e928b86aef1a5a39bd2bbb020dcd50503cf8b`.
- Reference ID: `b68a542228b51665`; length: 12 steps.
- Canonical reference SHA256: `80a8fc5d7507a4491a97275e295aed0071340e2b47f0c4250c376bc67653749e`.

## Verification and final boundary

Preflight: 640 unit tests passed; after a test-only import maintenance change, all 33 affected launcher tests, default repository mypy, and pre-commit passed. The independent prompt-only audit passed 176 checks and preservation checks passed 2,838 checks. The post-run audit additionally verified old artifact preservation, exact paired requests, and cumulative accounting.

**Direct blocker: the judge still rejects legitimate generic prerequisite assistance.** Two earlier false positives are resolved on this fixed set, but this prompt revision does not meet Phase-A acceptance. This does not determine whether a stronger judge model is necessary or whether LOW can produce a useful environment.

Stop honored: no further prompt tuning, model changes, screening, D/I, full AEA, E3, or E3-SL; no Phase-B calls. Source, prompt, and all old/new result records are preserved for review.
