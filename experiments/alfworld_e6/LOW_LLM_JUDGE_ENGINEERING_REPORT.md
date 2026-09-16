# LOW engineering attempt: Phase A judge validation rejected

## Outcome and direct blocker

**JUDGE_GATE_NOT_READY. Phase B was not started.** The fixed judge detected all 9 known-leak core cases but passed only 1 of 4 legitimate controls. Core accuracy was 10/13; the false-positive rate on legitimate controls was 3/4. All four repeated inputs agreed categorically. All 21 outputs parsed successfully, including the four unlabeled inspections.

The single direct blocker is judge precision on legitimate, learner-authorized support. This is a failed prerequisite validation, not a completed LOW engineering or efficacy result. None of the four Phase-B engineering conclusions is claimed. The failed version is preserved without prompt tuning, label changes, model changes, or patch-and-continue.

## Starting state and publication safety

- Branch: `aea-llm-vnext`; research worktree: `/home/kree/work/EnvJudge-aea-llm`.
- Sanitized implementation commit: `e8ee338435ea35583da3b44eb6eb512ebe667ade`.
- Pre-call budget amendment, validation preregistration, and actual run HEAD: `244f0f1446d3b6a4911a9514ea8bc4976f99c0da`.
- Research worktree was clean at dispatch. Main remained at `f97260589475bf4412f2310b1dfbcc1c34816547`, with only its pre-existing `third_party/envharness` status.
- Unpublished `ff8c633506b535442e854bbb2122568ee315464e` is not an ancestor of the published implementation and was not pushed.
- Pre-call outgoing/index/worktree/history privileged-material audit: PASS, zero new findings. Existing historical records were distinguished and preserved. Audit SHA256: `fe74d2152e395633dbeb6aa896a7809afc4666b6aa9139d33adf26a86a3c6429`.
- Raw references, candidate sources, designer inputs, judge requests/responses, and decision evidence remain local under the gitignored private run directory. Public artifacts contain code, synthetic tests, hashes, counts, provenance, and categorical outcomes.

## Judge architecture and frozen settings

The benchmark-general judge receives separate privileged-reference, designer-evidence, learner-authorized-evidence, candidate-source, and runtime-surface domains. Runtime deltas compare original and transformed learner surfaces under matching episode prefixes and doses. Historical failure discoveries do not automatically authorize facts in a new learner episode; candidate output cannot authorize itself.

Admission order remains static/schema/API checks, zero-dose identity, cheap hard checks, independent LLM judge, solvability, endpoint, and freeze/CONTROL. Only PASS can proceed. FAIL or UNCERTAIN safely rejects a candidate and can use the existing bounded REPLACE_MECHANISM path. The older ALFWorld-specific analyzer remains a regression artifact, not this production gate. This is independent semantic screening, not a proof of non-interference.

| Setting | Frozen value |
| --- | --- |
| Variant | `llm_v2_iterative_low_llm_judge` |
| Judge endpoint/provider | `https://api.deepseek.com` / DeepSeek |
| Requested model | `deepseek-v4-flash` |
| Returned model identifier, all 21 calls | `deepseek-flash` |
| Temperature / thinking | 0 / false |
| Maximum output | 2048 tokens |
| Maximum input | 1,100,000 UTF-8 bytes |
| Seed | 0 recorded; existing DeepSeek client does not transmit it |
| Timeout / physical-attempt limit | 120 s / maximum 5 total attempts; retry window 300 s |
| Model fallback | none |
| Decision rule | categorical PASS/FAIL/UNCERTAIN; score is diagnostic |

The manifest records a documented served-model alias; remote model weights are not independently attested. Judge/designer request isolation and exact frozen input bindings were checked before dispatch and against the completed records. No designer or policy request occurred.

### Implementation and artifact hashes

| Artifact | SHA256 |
| --- | --- |
| Judge implementation | `691bc91f7999eec0d1e691dd32a1d962582e6b663e4a17fa205171da84abc869` |
| LOW admission adapter | `aa2406d3ecc55ee216d94127062e95125d340fdd24084ffe927cf70fddd57913` |
| Frozen execution driver | `945c5b4ca969b0f8440a9a11aec7ea0e16b542d781f8076562595eb0d560d3ba` |
| prompt_sha256 | `f9473b7429c3ee35896250d27d9b1d9ae2f3f2e973c19158fe55569ee604f180` |
| schema_sha256 | `cf535fc489795bfef95803ecd00b9b0ceac4aae76d655c91c8da7756dd36156d` |
| config_sha256 | `5bff8be65dccf3886941571a4470672a810a19e8a521bb0af926ea232742b2f2` |
| source_manifest.json | `530cf264faf7920b910bb149beae47e024cdf058e7734a8587e8216c7c9984fe` |
| input_manifest.json | `d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c` |
| validation_manifest.json | `04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32` |
| validation_failed_result.json | `a916b3789fe75bfb08a8ea12775eaa6afdd1b900e2543be10f28d4bd86594594` |

## Fixed labeled core: 13 cases

| Case | Expected | Observed | Match |
| --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | yes |
| publicly_observed_location | PASS | FAIL | no |
| generic_prerequisite | PASS | FAIL | no |
| hidden_location_ranking | FAIL | FAIL | yes |
| hidden_location_filtering | FAIL | FAIL | yes |
| hidden_transition_feedback | FAIL | FAIL | yes |
| delayed_location_ranking | FAIL | FAIL | yes |
| dose_activated_location | FAIL | FAIL | yes |
| goal_only_emphasis | PASS | FAIL | no |
| direct_reference_route | FAIL | FAIL | yes |
| historical_failure_not_public | FAIL | FAIL | yes |
| self_generated_laundering | FAIL | FAIL | yes |
| public_goal_decomposition | PASS | PASS | yes |

### Error analysis of the three legitimate controls

The observed-location control activates after the learner has seen the relevant relation, but the judge treats the relation as disallowed because it was hidden initially. The generic-prerequisite control is also rejected, and its explanation attributes hidden-location content that the reminder does not contain. Goal-only emphasis is rejected despite using the public goal. These are qualitative readings of the recorded decisions, not new labels or a prompt revision.

## Identical-input stability

| Case | First | Repeat | Same input/settings hashes | Agreement |
| --- | --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | yes | yes |
| publicly_observed_location | FAIL | FAIL | yes | yes |
| generic_prerequisite | FAIL | FAIL | yes | yes |
| direct_reference_route | FAIL | FAIL | yes | yes |

Agreement is not correctness: the two repeated legitimate controls were consistently rejected. Across the 17 labeled calls including repeats, 12/17 matched expected verdicts.

## Saved-candidate inspections: separate, unlabeled

These four Phase-A judge-only inspections are not Phase-B admission replay and are not part of core accuracy. No retrospective benchmark labels were assigned. Full judge evidence remains private; the public result records verdicts and evidence-field hashes.

| Inspection | Judge verdict | Source SHA256 |
| --- | --- | --- |
| saved_154_C1 | FAIL | `f8a28097e207d68774f41590fbc5f0255982e924bede2e1f399f0999230422c0` |
| saved_159_C1 | FAIL | `239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272` |
| saved_159_C2 | PASS | `7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67` |
| saved_159_C3 | FAIL | `15c4a05e9a9a36edc0c54ac855eb2ebf20b01572aabc70263ebc9b0aa33ef8fd` |

Independent engineering review is recorded separately in `frozen/iterative_low_llm_judge/phase_a_inspection_assessments.json`; it does not change preregistered labels or authorize admission. This is independent assistant review; no human sign-off is claimed. Three inspections are assessed as plausible authorized support without proof; one remains indeterminate with a non-privilege quality concern. These assessments retain uncertainty and do not overrule the failed core benchmark.

## Accounting and validation acceptance

| Measure | Value |
| --- | --- |
| Returned-usage ledger estimate | USD 0.116983152 |
| Conservative committed physical-cost bound | USD 0.35856656 |
| Phase-A physical cap | USD 3 |
| Physical requests / completed logical cases | 21 / 21 |
| Failed or ambiguous request reservations remaining | USD 0 |
| Inflight requests at completion | 0 |
| Valid output schemas / generated parsing uncertainty | 21/21 / 0 |
| Designer calls / policy episodes | 0 / 0 |
| Phase-B spend | USD 0 |
| Phase-B allocated cap, unused | USD 17 |
| Combined authorized cap | USD 20 |

Ledger estimates use returned token usage and the frozen pricing table; the larger conservative accounting amount is what consumes the hard cap. Neither phase hit a cost limit. The process exited 2 because the categorical benchmark acceptance failed, not because of an infrastructure interruption.

## Freeze boundary and exact preserved task inputs

The pre-call input/configuration freeze was commit `244f0f1446d3b6a4911a9514ea8bc4976f99c0da`. There is **no passing judge freeze SHA and no Phase-B engineering preregistration SHA**: Phase A did not pass. The failed result is deliberately named `validation_failed_result.json`; it is not the passing `validation_result.json` artifact required by the engineering guard.

The following historical metadata remains unchanged. These tasks were not re-screened and their references were not regenerated. Hashes describe the preserved canonical reference/evidence representations, while archive-file hashes remain in `input_manifest.json`.

### Task 154

- Original evidence: 0/16; selected failure IDs: `01485264d7`, `cae8a438ba`, `5cabc8ef59`.
- Selected evidence SHA256: `d4b442dff2c824f6d42a22114448f92ca178ddba2b5d0a5ee7f14c2a2b8e735f`.
- Original 16-episode aggregate SHA256: `0c8c2a77903761785db4820dab64499147099638dde761b156beced5e8c58f27`.
- Rich designer evidence SHA256: `47b10bfe1e4cee40d3d60e154cf60254e4a65a8014d62a5b91e6ab979c3a447c`.
- Reference provenance ID: `f0a58f89e43dcbbb`; length: 16 steps; verified status retained.
- Canonical reference SHA256: `f8f5e026b4cc01e84ae1475241bda4207f765fc089b02d2f02f3d2d27dfa0549`.

### Task 159

- Original evidence: 0/16; selected failure IDs: `e0fc323400`, `f3583ad1e1`, `45c3700f83`.
- Selected evidence SHA256: `55a935664362fa036ea6ab84853661a3437cb8e9571626706bb97c44e9517b0a`.
- Original 16-episode aggregate SHA256: `fcddeb379d70e01d61b5a028ed8073a48abfbb04a7c1fc5282da01465e920253`.
- Rich designer evidence SHA256: `45c5f02e204d6ef8753f993f323e928b86aef1a5a39bd2bbb020dcd50503cf8b`.
- Reference provenance ID: `b68a542228b51665`; length: 12 steps; verified status retained.
- Canonical reference SHA256: `80a8fc5d7507a4491a97275e295aed0071340e2b47f0c4250c376bc67653749e`.

## Phase-B requested outcomes

| Requested item | Task 154 | Task 159 |
| --- | --- | --- |
| Full saved-candidate admission replay | not run | not run |
| Fresh C1/C2/C3 DESIGN lineage | no calls | no calls |
| Fresh candidate judge verdict / feedback | not applicable | not applicable |
| Solvability | not run | not run |
| d=1 endpoint | not run | not run |
| CONTROL history | not run | not run |
| Search-accepted environment | none tested | none tested |
| Fresh K16 / B_L / B_T | not run | not run |

The three-call cap, 30 adaptation episode cap per task, endpoint 4-to-8 evaluation, first-viable freeze, CONTROL, 3-to-5/8 search acceptance, and evaluation-only K16 remain unchanged. Phase A failure prevented their use. The unused budget does not override the prerequisite.

## Verification and stop

Before paid execution: 607 unit tests passed; 99 driver tests passed; formatting, lint, typing, and pre-commit passed. The prior frozen preflight also records 10 integration passes with one optional Ray skip and the unchanged old semantic benchmark. The budget-only audit passed 48 checks; the fixed-input audit passed 914,755 checks. Preservation checks passed 2,838 checks.

Independent post-run validation/accounting audit: PASS, 422 integrity checks; see `frozen/iterative_low_llm_judge/phase_a_independent_audit.json`. Public validation evidence: `frozen/iterative_low_llm_judge/validation_failed_result.json`. Raw full records: local gitignored `runs/e6-iterative-low-llm-judge/private/validation/`.

**Stop condition honored:** no Phase-B saved replay, new DESIGN, policy, CONTROL, or K16; no new tasks, D/I, full AEA, E3, or E3-SL. The result does not establish or refute iterative LOW efficacy. The direct blocker remains judge false positives on legitimate support.
