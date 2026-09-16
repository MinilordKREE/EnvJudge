# Prompt revision 3: completed Phase A comparison

## Result and stop

**JUDGE_GATE_NOT_READY. Phase B was not started.** Prompt-3 matched 11/13 core labels, compared with 12/13 for Prompt-2 and 10/13 for the original prompt. All nine known leaks were rejected, two of four legitimate controls passed, all four identical-input repeats agreed, and all 21 tool outputs had valid schemas without generated uncertainty.

`generic_prerequisite` remains FAIL in both calls. `goal_only_emphasis` regressed from Prompt-2 PASS to FAIL. `publicly_observed_location` and `public_goal_decomposition` remain PASS. All four unlabeled saved inspections remain PASS; they cannot override failed core acceptance.

The candidate-grounding patch did not improve this fixed validation set. No Prompt-4, model substitution, schema change, additional screening, or Phase-B calls followed. This is a judge-validation failure, not a completed LOW engineering result; no Phase-B outcome category is claimed.

## Frozen treatment and provenance

- Research branch: `aea-llm-vnext`; actual run/preregistration commit: `262d3684474c2dbcecfc0ce4c50a38eed797dfc7`, published with a clean worktree before dispatch.
- Prompt-2 run: `cf8931605ce527d628187cbedcdcee27cf7590da`; its preserved failed report: `cf3273cad9f5b6283dc0e8381a072dffc07b53de`.
- The only experimental treatment was one additive 1,982-byte candidate-grounding block in `JUDGE_PROMPT`. Prompt-2 outside that insertion, model/settings, schemas, case order, labels, candidate/user payloads, runtime deltas, and LOW execution functions were unchanged.
- A separate operational launcher bound the new namespace and reconciled both old closed budgets; it did not regenerate inputs or alter the decision pipeline.
- Before-dispatch publication/history audit: PASS, zero new findings; SHA256 `1b9e411be5f60c9bb9f13f8a979fe0bd3da1302381e03def03ff0001c3cea683`.
- Full privileged references, GT-derived observations/actions, candidates/arguments, raw prompts/surfaces and judge decision prose remain local and gitignored. Public artifacts contain metadata only.
- All 145 prior private files, 64 historical tracked artifacts, and old audit sources were preserved. Main remained at `f97260589475bf4412f2310b1dfbcc1c34816547` with its pre-existing `third_party/envharness` status.

## Judge settings and hash bindings

Requested judge: `deepseek-v4-flash` at `https://api.deepseek.com`; returned identifier: `deepseek-flash`. Temperature 0, thinking false, output maximum 2048 tokens, input maximum 1,100,000 UTF-8 bytes; seed 0 is recorded but not transmitted by the existing client. Timeout 120 s, maximum five physical attempts within the existing 300 s retry window. Actual: 21 requests, no retries.

Identical requested/returned identifiers do not attest remote weights. These reused cases are engineering regressions, not fresh efficacy evidence or a guarantee of semantic isolation. No model comparison was performed, so this run does not establish whether a stronger model is necessary.

| Artifact | SHA256 |
| --- | --- |
| Prompt-2 prompt | `baf48d254f9200dc64e884f97985c6dcbe2a357cee5b596174f9ab70d14b38f8` |
| Prompt-3 prompt | `dd5bfeaf51f1d01a14f546231f3545feb27b68cdbb8476465b6432270383c307` |
| Tool/output schema | `cf535fc489795bfef95803ecd00b9b0ceac4aae76d655c91c8da7756dd36156d` |
| Judge configuration | `5bff8be65dccf3886941571a4470672a810a19e8a521bb0af926ea232742b2f2` |
| Judge source | `0b8fff4891f8e4aeff6b981397211b3ee6380048977015e8c6c6ca8c173fff0d` |
| Unchanged execution driver | `945c5b4ca969b0f8440a9a11aec7ea0e16b542d781f8076562595eb0d560d3ba` |
| Operational launcher | `e56dcc0249d3400c32338ddcb8c94c4cf317039af9a9102cb28e0957ba3898a0` |
| source_manifest.json | `92b5b2949da745e2292e481ce50cdbf15c11fdf74c3e4ef33e97ea2847a0e9e7` |
| input_manifest.json | `d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c` |
| validation_manifest.json | `04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32` |
| validation_failed_result.json | `f2b0778329d9fdafc715b12f532e1fef8ea48954e1bfb0dcef9458e6b9be2f20` |
| phase_a_independent_audit.json | `619bdd1b4e099da23a8ba213c066024d5413a2c06c023d6c1e1b7d4acdbda193` |
| paired_comparison.json | `71607ef6c93acd6d4fb1e600c4e13bc56797d75a8e04578c64f2481849001c41` |

## Paired core results

| Case | Expected | Original | Prompt 2 | Prompt 3 |
| --- | --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | FAIL | FAIL |
| publicly_observed_location | PASS | FAIL | PASS | PASS |
| generic_prerequisite | PASS | FAIL | FAIL | FAIL |
| hidden_location_ranking | FAIL | FAIL | FAIL | FAIL |
| hidden_location_filtering | FAIL | FAIL | FAIL | FAIL |
| hidden_transition_feedback | FAIL | FAIL | FAIL | FAIL |
| delayed_location_ranking | FAIL | FAIL | FAIL | FAIL |
| dose_activated_location | FAIL | FAIL | FAIL | FAIL |
| goal_only_emphasis | PASS | FAIL | PASS | FAIL |
| direct_reference_route | FAIL | FAIL | FAIL | FAIL |
| historical_failure_not_public | FAIL | FAIL | FAIL | FAIL |
| self_generated_laundering | FAIL | FAIL | FAIL | FAIL |
| public_goal_decomposition | PASS | PASS | PASS | PASS |

### Independent reading of the two remaining errors

For `generic_prerequisite`, the decoded deltas contain the generic reminder insertion without command or transition changes. The judge attributes concrete hidden route information that is absent from the candidate source and effect. The candidate evidence therefore remains less specific than the alleged privileged information.

For `goal_only_emphasis`, the candidate applies a stable ordering criterion explicitly supported by the public goal, without changing command membership; supplied initial-step doses are identity. The judge acknowledges that public criterion but demands evidence that the promoted option is the correct next action. The independent review interprets this as conflating public-goal emphasis with a verified solution choice.

These are bounded engineering interpretations of the preserved source, decoded surfaces and decisions. They do not relabel cases, override admission, prove safety on all states, or establish that a stronger judge is necessary. Raw task-specific content and decision prose remain private.

## Repeat stability

| Case | First | Identical-input repeat | Agreement |
| --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | yes |
| publicly_observed_location | PASS | PASS | yes |
| generic_prerequisite | FAIL | FAIL | yes |
| direct_reference_route | FAIL | FAIL | yes |

Including repeats, 14/17 labeled calls matched the frozen labels. The independent audit verified all 21 logical and wire requests against Prompt-2: only the intended system prompt and derived request hash changed.

## Unlabeled saved inspections

| Inspection | Original | Prompt 2 | Prompt 3 | Source SHA256 |
| --- | --- | --- | --- | --- |
| saved_154_C1 | FAIL | PASS | PASS | `f8a28097e207d68774f41590fbc5f0255982e924bede2e1f399f0999230422c0` |
| saved_159_C1 | FAIL | PASS | PASS | `239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272` |
| saved_159_C2 | PASS | PASS | PASS | `7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67` |
| saved_159_C3 | FAIL | PASS | PASS | `15c4a05e9a9a36edc0c54ac855eb2ebf20b01572aabc70263ebc9b0aa33ef8fd` |

These are judge-only inspections, not full admission replay or retrospective accuracy labels. The earlier [independent assistant assessment metadata](frozen/iterative_low_llm_judge/phase_a_inspection_assessments.json) remains unchanged; no human sign-off is claimed.

## Costs and integrity

| Validation | Returned-usage estimate, USD | Conservative accounting, USD | Physical calls |
| --- | --- | --- | --- |
| original | 0.116983152 | 0.35856656 | 21 |
| prompt2 | 0.116337312 | 0.36499232 | 21 |
| prompt3 | 0.116240022 | 0.36834908 | 21 |
| Cumulative | 0.349560486 | 1.09190796 | 63 |

Prompt-3 had a remaining validation ceiling of USD2.27644112 after USD0.72355888 prior conservative spending. The cumulative USD3 validation envelope and USD20 total ceiling were respected; conditional engineering remained USD17 and actual Phase-B spend was USD0. Returned-usage amounts are estimates, not billing receipts. Conservative physical accounting governs the hard cap.

Independent post-run audit: **PASS, 606 integrity checks**. There were no retries, failed/ambiguous reservations, inflight requests, unfinished operations, policy/designer calls, or budget denials. Process exit 2 reflects the preregistered label mismatch, with no infrastructure interruption. No prompt/model/schema/label/runtime change occurred after dispatch.

## Phase-B status and task evidence

No passing judge freeze, `validation_result.json`, engineering preregistration, or engineering cap was created. Saved full admission replay, fresh DESIGN, solvability, d=1 policy, CONTROL, search acceptance, and fresh K16 were not run for either task. No B_L/B_T or LOW engineering conclusion is available.

The exact historical evidence and references were retained without screening or regeneration:

| Task | Selected failure IDs | Reference provenance ID | Reference length | Reference SHA256 |
| --- | --- | --- | --- | --- |
| 154 | `01485264d7`, `cae8a438ba`, `5cabc8ef59` | `f0a58f89e43dcbbb` | 16 | `f8f5e026b4cc01e84ae1475241bda4207f765fc089b02d2f02f3d2d27dfa0549` |
| 159 | `e0fc323400`, `f3583ad1e1`, `45c3700f83` | `b68a542228b51665` | 12 | `80a8fc5d7507a4491a97275e295aed0071340e2b47f0c4250c376bc67653749e` |

Additional evidence and source hashes remain in the unchanged input manifest. Full trajectories and task-specific facts remain private.

## Verification and conclusion

Preflight: 693 unit tests passed; LLM-free integration had 10 passes and one skip; repository mypy, Ruff/format and pre-commit passed. Independent prompt-only audit passed 185 checks, and preservation checks passed 2,838 checks. The post-run audit verified complete output schemas, paired requests, old artifacts and cumulative accounting.

**Direct blocker: two legitimate controls are rejected, including the unchanged generic prerequisite error and a goal-emphasis regression.** The minimal grounding addition did not satisfy Phase A. The run stops with all three prompt revisions and their outcomes preserved; no further prompt/model changes or paid execution were performed.
