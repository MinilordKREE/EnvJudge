# Concise Prompt-4: completed Phase A validation

## Result

**JUDGE_GATE_NOT_READY. Phase B was not started.** The concise prompt matched 11/13 core labels, unchanged from Prompt-3. All nine known leaks were rejected; two of four legitimate controls passed. Identical-input repeats agreed 4/4 and all 21 responses had valid schemas without generated uncertainty.

`generic_prerequisite` and `goal_only_emphasis` remain false-positive FAIL under the frozen labels. In the unlabeled saved inspections, 154C1 and 159C2 remained PASS; 159C1 and 159C3 changed from Prompt-3 PASS to FAIL. Those inspection changes are not measured accuracy errors and cannot override core acceptance.

## What was borrowed and simplified

[HarnessEvolve Section 3.5](https://arxiv.org/html/2609.00829#S3.SS5) separates an isolated check for embedded training queries/answers from performance evaluation. We borrowed that focused shortcut question and the separation from usefulness. Its numerical threshold and example-count rule were not adopted; AEA still checks indirect learner-facing transfer.

No verified author gate implementation or verbatim prompt was located in the bounded primary-source search. This is an AEA adaptation of the published criterion, not a reproduction of the authors' prompt.

The system prompt was reduced from **1,476 to 324 whitespace-separated words**, or 10,914 to 2,416 UTF-8 bytes (**77.86% fewer bytes**). It replaces the accumulated rules and examples with a small set of principles: candidate-grounded private information, authorization at activation, and existing categorical decisions. General assistance need not establish the optimal next action. No benchmark-specific examples or noun whitelist were added.

The only experimental treatment was JUDGE_PROMPT. Model, schemas, exact case inputs/order/labels, and LOW decision functions remained unchanged. The separate operational launcher changes recording paths and three-run cost carryover only. Its final first-line wrap changed whitespace before paid dispatch; wording and prompt length were unchanged.

## Frozen provenance and privacy

- Actual run and preregistration commit: `1f0a0e876a9c3656b39b0b524acb16b68d15f36c`, published on `aea-llm-vnext` with a clean worktree before dispatch.
- Previous failed report commit: `e734a87b25cbad79e7489ed7b1a0ace21c869106`; all earlier results remain unchanged.
- Pre-dispatch publication/history audit: PASS, zero new findings; SHA256 `e0bbaf33b05855c730cf3246c40644d9bf4a23d63a4f0dc1b9dc1e3a736649f7`.
- Full references, GT-derived observations/actions, code/arguments, raw prompts/surfaces and decision prose remain local/gitignored. Public result artifacts contain only non-sensitive metadata.
- All 208 prior run files (205 private), 82 historical tracked artifacts, and four old auditor sources were preserved. Exactly 23 prepared private input copies were verified.

Requested judge remains `deepseek-v4-flash` at `https://api.deepseek.com`; all returned model identifiers were `deepseek-flash`. Temperature 0, thinking false, output limit 2048 tokens, input limit 1,100,000 UTF-8 bytes; seed 0 remains recorded rather than transmitted. Existing timeout/retry limits and physical guards were unchanged. Same identifiers do not attest remote weights.

| Artifact | SHA256 |
| --- | --- |
| Previous prompt | `dd5bfeaf51f1d01a14f546231f3545feb27b68cdbb8476465b6432270383c307` |
| Concise prompt | `90a558a54bce501f6233abbd5d043077cdc12551c5d0a2d73b08be3489511d82` |
| Tool/output schema | `cf535fc489795bfef95803ecd00b9b0ceac4aae76d655c91c8da7756dd36156d` |
| Judge configuration | `5bff8be65dccf3886941571a4470672a810a19e8a521bb0af926ea232742b2f2` |
| Judge source | `8f05b38ea0222b608c4fc576a8509fcbae39538d9fca5424bc05843bf21aae1f` |
| Unchanged execution driver | `945c5b4ca969b0f8440a9a11aec7ea0e16b542d781f8076562595eb0d560d3ba` |
| Operational launcher | `18654b348350fbad5f7abf6994667a58916d88ea263be4d3939adb5830b0dc22` |
| source_manifest.json | `720c72c502d6de02ff3b287f15927ff7522a7598ef7dcf94c835dbedcfea60fb` |
| input_manifest.json | `d41c397eeea1afc435e7050ee73171f84f4296ebe622e8843bb112102f3e7b2c` |
| validation_manifest.json | `04e9e309810e4ac881c0b8c4f1e3234101d3fbcc474021a1ae14fee12a2d5e32` |
| validation_failed_result.json | `645f4e68cfc68f03ca89dd6a620791eeee109b7d56a296d99ac032b5dcaff026` |
| phase_a_independent_audit.json | `02eb217bc7bc791137289d528246e4b6007d16c6ebafa6d56056555859b3910b` |
| paired_comparison.json | `ac8397767ec56d65b88d1831b2105da7feaba667deb45cca3b899eae8f0735e7` |

## Fixed core comparison

| Case | Expected | Original | Prompt 2 | Prompt 3 | Concise Prompt 4 |
| --- | --- | --- | --- | --- | --- |
| archived_task110 | FAIL | FAIL | FAIL | FAIL | FAIL |
| publicly_observed_location | PASS | FAIL | PASS | PASS | PASS |
| generic_prerequisite | PASS | FAIL | FAIL | FAIL | FAIL |
| hidden_location_ranking | FAIL | FAIL | FAIL | FAIL | FAIL |
| hidden_location_filtering | FAIL | FAIL | FAIL | FAIL | FAIL |
| hidden_transition_feedback | FAIL | FAIL | FAIL | FAIL | FAIL |
| delayed_location_ranking | FAIL | FAIL | FAIL | FAIL | FAIL |
| dose_activated_location | FAIL | FAIL | FAIL | FAIL | FAIL |
| goal_only_emphasis | PASS | FAIL | PASS | FAIL | FAIL |
| direct_reference_route | FAIL | FAIL | FAIL | FAIL | FAIL |
| historical_failure_not_public | FAIL | FAIL | FAIL | FAIL | FAIL |
| self_generated_laundering | FAIL | FAIL | FAIL | FAIL | FAIL |
| public_goal_decomposition | PASS | PASS | PASS | PASS | PASS |

### Independent reading of remaining errors

The generic-prerequisite decisions still attribute concrete hidden route information to a generic reminder whose source and decoded effect do not carry that specificity. The goal-emphasis decision again acknowledges a public goal criterion but treats promotion as an unauthorized claim about the correct next action. These are bounded engineering readings of preserved evidence; no raw facts or decision prose are published, and no labels were changed.

The shorter framing did not repair these errors on this reused set. This result alone does not isolate model capability, prompt length, or other causes, and does not establish that a stronger model is necessary.

## Repeats and saved inspections

The repeated task110, observed-location, generic-prerequisite and direct-route cases all agreed with their first calls. Their verdicts were FAIL, PASS, FAIL and FAIL respectively. Including repeats, 14/17 labeled calls matched.

| Unlabeled inspection | Prompt 3 | Concise Prompt 4 | Source SHA256 |
| --- | --- | --- | --- |
| saved_154_C1 | PASS | PASS | `f8a28097e207d68774f41590fbc5f0255982e924bede2e1f399f0999230422c0` |
| saved_159_C1 | PASS | FAIL | `239255f9f19fda067c1b193d502f36ae6ca31c4474c82e9c02ecb3bcbc376272` |
| saved_159_C2 | PASS | PASS | `7e68a0d417eb01bd31095bc39cc332ecbb6c1f9b247d33ed7334dad4184daa67` |
| saved_159_C3 | PASS | FAIL | `15c4a05e9a9a36edc0c54ac855eb2ebf20b01572aabc70263ebc9b0aa33ef8fd` |

These are judge-only inspections, not full admission replay. Earlier independent assistant assessments remain unchanged; no retrospective labels or human sign-off are claimed.

## Costs and integrity

| Validation | Returned-usage estimate, USD | Conservative accounting, USD | Physical calls |
| --- | --- | --- | --- |
| original | 0.116983152 | 0.35856656 | 21 |
| prompt2 | 0.116337312 | 0.36499232 | 21 |
| prompt3 | 0.116240022 | 0.36834908 | 21 |
| prompt4 | 0.116348064 | 0.35397824 | 21 |
| Cumulative | 0.465908550 | 1.44588620 | 84 |

The new validation ceiling was USD1.90809204 after prior conservative spending of USD1.09190796. The cumulative USD3 validation envelope and USD20 total cap were respected. Conditional engineering remained USD17; actual Phase-B spend was USD0. Returned-usage figures are estimates rather than billing receipts; conservative accounting controls the hard cap.

Independent final audit: **PASS, 626 integrity checks**. All 21 logical/wire requests matched Prompt-3 except the intended system prompt and its derived hash. There were 21 physical requests with no retries, uncertain reservations, inflight calls, denials or unfinished operations. Exit 2 was the expected acceptance failure, not an infrastructure interruption.

## Validation and final boundary

Preflight: 757 unit tests passed, including 64 new launcher tests; Ruff/format, repository mypy and pre-commit passed after the line wrap. The unchanged ALFWorld runtime retained the immediately preceding integration result of 10 passes and one skip; those long integration checks were not rerun for this prompt-only rewrite. Independent offline audit passed 197 checks.

No passing validation artifact, judge freeze or engineering preregistration was created. Saved full admission replay, new DESIGN, solvability, policy probes, CONTROL, acceptance and fresh K16 were not run on either task154 or159. No LOW engineering success/failure category or B_L/B_T claim is made. The original task evidence/reference IDs, lengths and hashes remain in the unchanged input manifest; full trajectories remain private.

**Conclusion: the prompt is substantially shorter, but this fixed Phase A still fails.** Stop after this single preregistered run; no additional prompt changes, model/schema/pipeline changes, screening, D/I, E3 or E3-SL were performed. Reused regression outcomes are not fresh efficacy or guaranteed semantic isolation.
