# AEA Final Candidate v1 — method freeze

Status: **method frozen; matched E3 preregistered; paid execution not started**.

- Implementation commit: `cf976b4e332ecf8575d1df5b6cc7e88f5db609bf`.
- Selector: `llm_v3_designer_controller`.
- Research branch: `aea-llm-vnext`.
- Historical integrated implementation: `969e339281e71190d1df6aed579b2402513bcd45`.
- Historical integrated results: `247ab479ff9f703db0acbb7beff11b8d73893798`.
- Method: [design specification](../../docs/design/AEA_DESIGNER_CONTROLLER.md).
- Acceptance: [25-part implementation report](IMPLEMENTATION_REPORT.md).
- Prospective comparison: [matched E3 preregistration](PREREG_MATCHED_E3.md).
- Machine-readable freeze: [final_candidate_v1.json](frozen/final_candidate_v1.json).

## Two explicit frozen choices

1. Each captured equivalence class uses its **last nominal setting** as representative.
   This is a deterministic selection rule. Equality is defined only over the frozen
   capture suite; aliases are not claimed globally behaviorally equivalent, and the
   representative may behave differently from another alias on unseen histories.
2. A new DESIGN round requires at least **eight remaining adaptation episodes** by
   default. A promising family may consume these in one probe and leave no budget for
   another level. This is a method budget outcome, not infrastructure failure. Preserve
   both the latest feedback and the actual terminal budget reason in analysis.

Neither choice changes in this release. The 3–5/8 search target, final K16 definitions,
R5 judge, shared LOW/HIGH loop, three-round default and final freeze boundary remain fixed.
No new method implementation or prompt tuning is introduced by this documentation freeze.

## Acceptance and publication boundary

The implementation passed 1,278 unit tests, 12 integration tests with one optional-Ray
skip, two real ALFWorld offline smoke cases, strict mypy, Ruff, formatting and pre-commit.
Those are the implementation's recorded checks, not evidence of new-method efficacy.

Publish implementation, synthetic tests, protocol and metadata/hashes only. References,
GT-derived observations/actions, generated task candidates, complete trajectories, raw
requests/responses and judge prose remain local and gitignored. The publication audit
covers every commit newly sent to the branch, including intermediate blobs; it does not
claim that all inherited repository history is free of sensitive material.

## Execution readiness

The method and prospective protocol are pinned here. A separate matched experiment
launcher must implement and pass the preregistered offline acceptance checks before any
paid dispatch, then bind its own commit/hash in the execution manifest. The old integrated
launcher must not be pointed at new results or used to overwrite its historical freeze.
Paid-start scope is pending the user's response to the current execution-scope question.
