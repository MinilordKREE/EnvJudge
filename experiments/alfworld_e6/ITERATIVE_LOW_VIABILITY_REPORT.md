# Iterative LOW viability: fresh-pool screening result

**Decision: INSUFFICIENT_FRESH_LOW**

The preregistered twenty-ID scan (130–149) ended with 0 confirmed ZERO tasks; four were required. No scan extension.

Inspected 20 task IDs; 0 qualified ZERO tasks. The four-task primary sample did not form. Iterative LOW viability was not evaluated; no four-task efficacy denominator applies.

## Screening outcomes

The driver labels seven tasks `rejected_first_success` and thirteen `rejected_provider_error`. These are exclusive stop labels: **13 tasks succeeded**, including six with recovered errors. Seven tasks had no observed success before a recovered error stopped their screening; none reached 16 clean failures. All 30 physical failures recovered: 29 HTTP 429 responses and one connection failure.

| Task | Successes / completed episodes | Outcome | Terminal episode errors | Provider retries | Ambiguous failed requests | Physical requests | Ledger USD | Failed reservations USD |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 130 | 0/1 | rejected_provider_error | 0 | 2 | 2 | 52 | $0.096375 | $0.015060 |
| 131 | 1/1 | rejected_first_success | 0 | 0 | 0 | 18 | $0.006963 | $0.000000 |
| 132 | 1/1 | rejected_first_success | 0 | 0 | 0 | 8 | $0.001786 | $0.000000 |
| 133 | 0/1 | rejected_provider_error | 0 | 2 | 2 | 52 | $0.133135 | $0.019300 |
| 134 | 1/2 | rejected_first_success | 0 | 0 | 0 | 79 | $0.070301 | $0.000000 |
| 135 | 1/1 | rejected_first_success | 0 | 0 | 0 | 35 | $0.035837 | $0.000000 |
| 136 | 0/1 | rejected_provider_error | 0 | 1 | 1 | 51 | $0.046898 | $0.003154 |
| 137 | 1/1 | rejected_provider_error | 0 | 2 | 2 | 29 | $0.017814 | $0.004956 |
| 138 | 1/1 | rejected_first_success | 0 | 0 | 0 | 4 | $0.000585 | $0.000000 |
| 139 | 1/1 | rejected_first_success | 0 | 0 | 0 | 12 | $0.004402 | $0.000000 |
| 140 | 1/2 | rejected_provider_error | 0 | 10 | 10 | 84 | $0.118074 | $0.033503 |
| 141 | 1/1 | rejected_provider_error | 0 | 2 | 2 | 7 | $0.001002 | $0.003480 |
| 142 | 0/1 | rejected_provider_error | 0 | 3 | 3 | 53 | $0.098960 | $0.011420 |
| 143 | 1/1 | rejected_first_success | 0 | 0 | 0 | 19 | $0.014163 | $0.000000 |
| 144 | 1/3 | rejected_provider_error | 0 | 1 | 1 | 119 | $0.138901 | $0.003962 |
| 145 | 0/3 | rejected_provider_error | 0 | 1 | 1 | 151 | $0.413413 | $0.013539 |
| 146 | 0/1 | rejected_provider_error | 0 | 2 | 2 | 52 | $0.059731 | $0.009067 |
| 147 | 1/1 | rejected_provider_error | 0 | 1 | 1 | 22 | $0.009575 | $0.003696 |
| 148 | 0/1 | rejected_provider_error | 0 | 2 | 2 | 52 | $0.089001 | $0.010065 |
| 149 | 1/1 | rejected_provider_error | 0 | 1 | 1 | 35 | $0.029409 | $0.003801 |

The frozen strict rule excludes a task after any recovered provider retry or ambiguous failed request. Recovered episodes remain in the descriptive s/n column; they do not qualify the task. Failed reservations and retry events describe related accounting records and are not added together as distinct failures.

## Calls and cost

- Completed screening episodes: 26; all have no terminal episode error. Thirteen had recovered provider errors and 13 were strictly error-free; episode operations: 26.
- Physical request attempts: 934 (904 returned, 30 ambiguous failures, 0 in flight).
- Actual returned-call ledger cost: **$1.386324485**.
- Conservative returned cost: $1.386324485; retained failed-request reservations: $0.135002361; in-flight reservations: $0.000000000.
- Committed cost for the hard guard: **$1.521326846**. Screening cap $8; whole-run cap $20.

## Adaptation stages

| Stage | Result |
| --- | --- |
| Privileged references | Not run (N/A) |
| C1 / C2 / C3 | Not run (N/A) |
| Structural / identity / lexical / semantic candidate gates | Not run (N/A) |
| Solvability / endpoint measurement | Not run (N/A) |
| CONTROL / search acceptance | Not run (N/A) |
| K16 / B_L / B_T | Not run (N/A) |

All stages in this table are N/A for every inspected task. Reference-provider calls, designer calls, adaptation rollouts and K16 rollouts are all **0**. No four-task input manifest or adaptation preregistration was created because qualification failed. The candidate failure funnel is **not assessed**; these are not zero failures among evaluated candidates.

## Freeze and validation

- Pool preregistration commit: `d151b150a65f7455084345e4b165b9b62234bd4a`.
- Validator-fidelity implementation: `bec74ed8a6ff40e119b2299c92b07b8602ff5fef`.
- Driver SHA256: `21e3a91c2a598385e2ed8c27fdeab0584015874d3c5411260a00f6bc042f839c`.
- Preregistration SHA256: `d89acbcf7ddf6b692dd8368296627d87bd6b05740a563cdcb15c6cb38c31b7fb`.
- Preflight: 344 unit tests passed; strict mypy passed for 96 source files; pre-commit passed.
- Final read-only audit: **PASS**, 21,198 checks, zero failures, zero pending operations and no in-flight requests. All 26 trace identities/hashes, original candidates, task seeds, ordering, physical attempts, provider/pricing and cap balances reconcile.
- Preservation audit: all 2,480 baseline tracked files and all 105 historical run files/path sets unchanged; main HEAD/status unchanged. Production source and all frozen configuration/runtime hashes match the preregistration.
- This screening audit makes no claim about semantic admission performance: no candidate reached that phase.
- Raw traces and complete ledgers remain in `runs/e6-iterative-low-viability/`. [Artifact hashes](results/iterative_low_viability/artifact_manifest.json), [compact result](results/iterative_low_viability/screening_result.json), [screening audit](results/iterative_low_viability/screening_audit.json) and [preservation audit](results/iterative_low_viability/preservation_audit.json) are committed with this report.

The 20 inspected train IDs, 130–149, are now scientifically consumed. The historical unused-ID audit remains the immutable pre-run record; this report and the run artifacts record the new consumption.

## Interpretation and next action

The prospective screening pool did not form. This provides no estimate of iterative LOW efficacy and does not reclassify any historical IMPLEMENTATION_FAILURE.

Stop. A larger or differently qualified pool requires separate review and preregistration before any new screening. No LOW method change is recommended from screening alone.
