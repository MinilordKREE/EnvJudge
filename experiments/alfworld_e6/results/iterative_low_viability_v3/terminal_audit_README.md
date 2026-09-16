# V3 terminal adaptation provenance audit

Helper: `/tmp/viability_v3_adaptation_audit.py`
SHA-256: `03d6bd351967359af0dd4ceb0ded5f4709248b2c5e9a4d31f2e2041a93e13291`
Tests: `/tmp/test_viability_v3_adaptation_audit.py` — 29 offline tests passed.

After the adaptation stage terminates, from the research worktree:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -B /tmp/viability_v3_adaptation_audit.py --output /tmp/viability_v3_terminal_audit.json
```

All outputs must be under `/tmp`. The helper refuses active screening/adaptation.
It imports the hash-pinned V3 driver only to reuse read-only `ensure_frozen`,
`verify_input_set`, original-evidence/reference parsing, and `phase_limit`.
It does not call `build`, `screen`, `freeze_inputs`, `run_task`, `adapt`, `confirm`,
`cost_check`, `cap_lock`, Rules hooks, an environment, or a model.
The final artifact contains hashes, counts, pass/fail checks, and limitations;
no raw reference, source, prompt, semantic findings, or trajectory text is emitted.

## Checks

- Frozen implementation/runtime/prereg/input bindings and unchanged V2→V3
  execution functions; all64 original episodes and exact16→3 evidence selection
  via the frozen read-only validator; one completed reference operation/task.
- Exact designer requests, source/proposal identity, parent chain, actual typed
  rejection feedback, max3 calls, original n16 evidence, and endpoint reserve16.
- Semantic gzip hashes and exact source/reference/designer evidence binding;
  all17 reachable doses, verdict consistency, same-episode raw-action prefixes,
  and required same-state/final-formatter coverage for admitted candidates.
- PASS at each policy batch's exact source/dose; actual solvability record;
  runtime source reconstruction; all physical policy attempts and logical
  returns bound to a dispatched batch; no source substitution in K16.
- 4→8 behavior accounting, max30 requested adaptation episodes including
  interrupted batches, no episode refunds, first viable family freeze, CONTROL
  family identity, no designer attempt after CONTROL/confirmation begins.
- K16 exactly once after search acceptance, fresh global episode IDs, actual
  success counts/BL/BT, immutable pre-confirmation DESIGN/CONTROL summary,
  and exact designer inputs excluding confirmation results.
- Ledger pricing/model/provider pins, physical-request accounting, preserved
  ambiguous reservations, orphan reconciliation deduplication, immutable top-up
  baseline and separate25USD adaptation limit, historical V2 sunk cost excluded.
- Stable artifact snapshot at completion.

## Interpret the output

`PASS` means the recorded provenance/accounting checks passed. It does not
classify LOW efficacy or prove semantic isolation. `FAIL` lists concrete failed
checks. `REFUSED` means active/inconsistent/incomplete audit inputs prevented a
terminal audit. `NOT_RUN` means terminal screening/reference boundary occurred
before adaptation; root's screening audit and reporting remain authoritative.
An interrupted policy batch keeps the full requested episode charge even if only
some trace records returned. Missing or errored K16 is not a confirmation miss.

Semantic gate records have no timestamps. Gate-before-policy is established by
frozen control flow and exact source/dose admission bindings, not an independent
timestamped gate event. This helper does not rejudge the semantic inputs or
independently authenticate observation text; root's actual surface review is
separate. Rich reference serialization binds exact bytes but does not itself
prove the trusted producer's semantic correctness.

Run the adversarial tests offline with research `.venv/bin/python -B -m pytest`,
research-root PYTHONPATH and `-o cache_dir=/tmp/viability_v3_audit_pytest`. Synthetic
PASS gate fixtures test provenance checks only; they are not security evidence.

## Auditable helper correction after terminal execution

The first audit had 1,865 passing checks and four failures caused solely by an
auditor assumption that direct DeepSeek responses always carry a provider label.
All four such response labels are unavailable (`null`) under the frozen client
schema. The corrected helper accepts this only with exact frozen model/config/
request routing; it does not claim an independent upstream provider label. The
Qwen policy response still requires the explicit Alibaba provider pin.

Original helper: `/tmp/viability_v3_adaptation_audit_initial.py.txt`
Original failure: `/tmp/viability_v3_terminal_audit_initial.json`
Exact evidence and correction: `/tmp/viability_v3_audit_correction.json`
Source diff: `/tmp/viability_v3_auditor_correction.diff`
Final audit: `/tmp/viability_v3_terminal_audit.json` — 1,869 checks passed.
Only /tmp audit code changed; production/run artifacts and decisions did not.
