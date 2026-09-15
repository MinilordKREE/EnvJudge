# Semantic privilege gate: implementation and offline validation

Decision: **OFFLINE_SCREENING_REGRESSIONS_PASS**.
Scope: independent semantic privilege screening and offline validation. No new D/I smoke.

## Safety and scientific record

Research worktree: `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`.
Starting HEAD: `5675632ae4b1838fe9f14b62923d1716b18dd532`; initially clean.
Main worktree HEAD remains `f97260589475bf4412f2310b1dfbcc1c34816547`, with its pre-existing
` ? third_party/envharness` status. No main-worktree changes.

Offline preregistration was committed before the first benchmark execution: `3073895`.
Implementation freeze commit: `7555cc3bf0594cb132250949fa57e18fecf10982`. Gate: `alfworld-semantic-screen-v1`.
Method variant: `llm_v2_iterative_low_semantic_gate`.
See `semantic_privilege_offline/freeze.json` for complete hashes and invariant audit.

The old smoke and its `IMPLEMENTATION_FAILURE` are unchanged. This is a new candidate
admission method implementation, not an audit-tool correction or a continuation of that run.
No newly selected task pool, D/I comparison, K16 confirmation or training was run.

## Implemented behavior

The new path reuses the old optimizer's static/schema/API/identity and lexical checks,
then runs independent semantic screening before solvability and policy measurement.
Semantic FAIL follows existing privilege/REPLACE_MECHANISM feedback. UNCERTAIN records the
attempt and stops; it cannot reach solvability/policy evaluation or request another design.

The gate receives source, verified reference, separately identified designer evidence,
current-episode authorized evidence and executed original/transformed surfaces. Local
original replay captures raw histories; actual Rules hooks retain state across a prefix,
with independent instances per dose. Actual policy observation formatting exposes metadata
ordering. Candidate source and exact dose must have PASS admission before measurement.
The configured four-bisection CONTROL's 17 possible doses are screened before certification.

This implementation is a bounded, local ALFWorld relation/route analyzer. No independent
remote LLM judge was queried or evaluated. Unrecognized semantics or incomplete evidence
return UNCERTAIN. Results are empirical regression coverage, not semantic isolation proof.

## Required offline cases

| Case | Expected | Actual |
|---|---|---|
| Archived task 110 C1 | FAIL | FAIL |
| Learner already observed pillow at sofa | PASS | PASS |
| Generic prerequisite reminder | PASS | PASS |
| Hidden-location ranking | FAIL | FAIL |
| Hidden-location filtering | FAIL | FAIL |
| Transition feedback disclosure | FAIL | FAIL |
| Delayed activation | FAIL | FAIL |
| Interior-dose activation | FAIL | FAIL |
| Public task-goal emphasis | PASS | PASS |
| Encoded reference route | FAIL | FAIL |

The primary development benchmark has 14 fixed cases, including four extra cases for
historical-evidence separation, wrapper-output laundering, hook errors and unknown semantics.
First execution after preregistration: 14/14 matched, PASS 3/3, FAIL 9/9, UNCERTAIN 2/2.
No primary expected label was changed. Final repeated execution: 14/14 matched again in two separate executions; output JSON was byte-identical.
These are labeled development regressions, not a held-out accuracy benchmark.

The exact task 110 source hash remains
`326d1b19f1d2b29dff831a2c445e2787ff0b40a36ef9d6be757dff5b64d28ded`.
Fixture provenance includes source/reference/original-failure/audit hashes. Synthetic
extensions are explicitly labeled. The primary hidden episode combines the archived initial
public reset observation and an original unwrapped sidetable response; the observed-location
control constructs a counterfactual learner history that actually visits the sofa. Such
reference-derived synthetic controls are not used to populate production public evidence.
The added real ALFWorld integration test independently reproduced the reference
reset observation/admissible list and the original sidetable observation exactly. It then
executed the archived candidate on those captured states and returned FAIL. Actual reset
seed/options are retained; no reference action was used to populate that learner prefix.

## Corrections identified during offline development

Independent review added adversarial cases without relabeling the primary benchmark:
negative observations cannot establish a positive location; goal descriptions repeated in
observations and PUT-command destinations cannot establish current locations; a newly
asserted relation made from goal vocabulary is not automatically authorized. Missing surface
coverage fails closed. Unexplained removal of reference-related commands is UNCERTAIN.
Numbered entities remain distinct, and block-reason leaks are examined even when subsequent
replay is unsupported.

An admission review caught feedback selecting early harmless d=0 findings before the actual
FAIL. Feedback now selects complete findings of the rejection verdict, with input hash and
version. Additional checks bind source/verdict consistency, revoke stale admission on a
failed rescreen, and verify reused compressed audit artifacts.

These are implementation corrections before the method freeze. No new experimental policy
outcome was collected. The optimizer, thresholds and primary expected labels were unchanged.

## Frozen components and verification

| Check | Result |
|---|---|
| Full offline unit suite after final code changes | 290 passed; 11 integration tests deselected |
| Existing LLM-free ALFWorld integration suite | 9 passed, 1 skipped (optional Ray unavailable) |
| Added real ALFWorld task 110 surface integration | 1 passed |
| Primary executed-hook benchmark | 14/14; PASS 3, FAIL 9, UNCERTAIN 2 |
| Supplemental structured development cases | 5/5; FAIL 4, UNCERTAIN 1 |
| Additional input/fidelity regressions | Missing coverage, suppression, concrete-dose rewrite checks passed |
| Ruff / formatting | Passed; 173 files formatted correctly |
| Strict mypy | Passed; 92 source files |
| pre-commit, all files | Passed |
| Original production files outside three wiring/config files | 44 byte-identical |
| Original smoke report/data/driver/prereg | All byte-identical |

The two integration invocations together cover all 11 integration tests: 10 passed and one
optional dependency skip. The existing suite ran before the final new-module fidelity fixes;
the added real test and the complete unit suite ran after those fixes. Existing integration
paths do not invoke the new variant.

`low_optimizer.py`, designer prompts/contracts, D/I input construction, two-call cap,
REPAIR_CODE/REPLACE_MECHANISM, freeze boundary, CONTROL, budget, measurement, solvability
and acceptance remain unchanged. The controller changes only LLM-variant dispatch, LOW
variant dispatch and semantic admission wiring. Old HIGH/MID behavior matches event/output
streams; old LOW variants and v0.4 golden tests pass.

Validation commands use the existing locked environment, without package upgrades:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -ra
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -m integration -ra
.venv/bin/ruff check --no-cache .
.venv/bin/ruff format --check --no-cache .
.venv/bin/mypy --cache-dir /tmp/aea-semantic-mypy
UV_NO_SYNC=1 UV_OFFLINE=1 .venv/bin/pre-commit run --all-files
.venv/bin/python scripts/semantic_privilege_benchmark.py --output experiments/alfworld_e6/results/semantic_privilege_offline/benchmark.json
```

Integration tests use local simulators and scripted policies; they do not call experiment
policy/designer APIs. New gate benchmark policy rollouts: 0. Experiment model API calls: 0.
Experiment API spend: USD 0. No new D/I smoke was started.

## Interpretation and next boundary

The requested cases and admission ordering now have reproducible offline coverage. The
detector can still reject unfamiliar legitimate support as UNCERTAIN, and finite original
prefixes do not cover every learner trajectory or possible encoding. This result establishes
neither broad detector accuracy nor a benefit from iterative feedback.

Any subsequent four-task D/I smoke must explicitly use the new variant/gate, share its
admission protocol across D and I, and receive a fresh preregistration and authorization.
The previous smoke driver remains frozen and does not automatically acquire this gate.
