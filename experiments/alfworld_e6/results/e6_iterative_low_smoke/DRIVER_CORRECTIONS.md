# Post-freeze driver/audit correction

Implementation freeze: `76e14b3b477e73ffe5f10540a5157dc99b6ab559`.
Preregistration: `7c472fba573ca518152062028a327db5c456df72`.

## 2026-09-15: correctness audit takes priority over its induced stop errors

The run ended after the documented task110 privilege violation. Setting the already-existing
persistent transport flag stopped further HTTP calls. The interrupted CONTROL batch raised
the ordinary rollout infrastructure error; `report()` initially emitted INCONCLUSIVE because
it did not read the separately recorded semantic correctness audit.

Change: `report()` reads `correctness_audit.json`, includes it in the summary and assigns
IMPLEMENTATION_FAILURE when that audit documents a failed correctness gate. This applies the
existing preregistered priority; it does not change task eligibility, DESIGN, CONTROL,
acceptance, source, prompts, budgets, candidate results or decision thresholds. A focused
offline regression test verifies this reporting case. Only `--stage report` was rerun.

- Driver before SHA256: `383fd906daa4974270efcc90fb390254f506e1918f971e693d2de1e51408a3ba`.
- Driver after SHA256: `86aa45af30cfafefd251b8da5f1fc45399404956eac18f5f94c0027899acd459`.
- Frozen `src/aea` tree remains `c075947920a4ff35d31a9532e06ae355a264a418`.
- Original automatic summary: `automatic_summary_before_audit.json`, retained unchanged.
- Corrected summary: `summary.json`; semantic evidence: `privilege_evidence.json`.
- Post-correction offline driver suite: six tests passed. No paid rerun or continuation.
