# Preregistration: corrected fresh ZERO pool for iterative LOW viability

Status: frozen before the first V2 screening request. Commit and push this
preregistration, corrected driver, tests, infrastructure semantics and used-task
audit before paid execution.

## Purpose and immutable method

Form four fresh `CONFIRMED_ZERO` tasks using **16 valid completed episodes with
zero successes**, then immediately run the frozen single-arm iterative LOW
viability smoke after committing/pushing its exact-input preregistration.

Research worktree: `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`.
Starting HEAD: `d88d2e1b7be3279f89944f155fc41cf1c18a5c2a`.
Method: `llm_v2_iterative_low_semantic_gate`; frozen production/validator SHA:
`bec74ed8a6ff40e119b2299c92b07b8602ff5fef`.

The preceding 130–149 screening report remains `INSUFFICIENT_FRESH_LOW`.
Its task IDs are consumed; none is resumed. All historical reports, drivers,
preregistrations and run namespaces remain byte-identical. Main remains untouched.

Only new experiment-level screening/accounting, tests and records are added.
`src/aea/`, the optimizer, designer prompts/evidence, validator, lexical and
semantic screens, solvability, lineage, freeze boundary, CONTROL, acceptance
and K16 remain unchanged. No comparison arm, method redesign or gate relaxation.

## Programmatic freshness and order

- Same universe: nonnegative integer ALFWorld **train bridge-seed task IDs**.
- Used-task audit: `frozen/iterative_low_viability_v2/used_task_audit.json`.
- Audit SHA-256: `0a1e90a825018b4a07a276fb9a170f8e37e8215cccde9603a0b05c36be03f835`.
- Smallest never-used ID: `150`.
- Exact ascending unused IDs: `150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169`.
- Maximum inspected IDs: **20**. No task-semantic selection or scan extension.
- The audit includes both worktrees and the consumed V1 screening traces;
  designer RNG, fake unit IDs and held-out-split seeds remain separate domains.

## Frozen policy, environment and physical retries

Unchanged `scripts/e3.py`, `configs/corpus_aea.yaml` and frozen pricing:
OpenRouter `qwen/qwen3-8b`, Alibaba pinned, fallback disabled, thinking disabled,
temperature0.5, max output2048, `think_action`, history200, horizon50.
Original ALFWorld train environment, reset seed=task ID, `repetition_threshold=0`.
Each episode execution dispatches the identity candidate, concurrency1,
subprocess timeout600seconds and a fresh episode identity.

Existing provider retry infrastructure remains unchanged: at most10 physical
attempts per policy request, initial2second delay, exponential backoff capped at
90seconds plus up to1second jitter, total900second window. Retryable outcomes
include408/409/425/429,5xx,timeouts/connections;400/401/403 are not retried within
a request. Every physical attempt reserves cost before dispatch.

Semantic screen remains `alfworld-semantic-screen-v1`, source SHA-256
`ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`.
It does not participate in original-environment ZERO classification.

## Corrected behavioral counters and bounded episode retries

For each task start `valid_episodes=0`, `valid_successes=0`.

1. A completed nonerrored identity-environment trace contributes exactly one
   valid episode. Add one success only if it reports task success.
2. Recovered physical provider retries are recorded but do not invalidate that
   completed episode or other task evidence. They are not behavioral outcomes.
3. An episode terminating with provider/network/environment infrastructure error
   contributes **zero** valid episodes and **zero** successes. Save its complete
   error record and any partial trajectory; do not impute a behavioral failure.
4. For each next valid behavioral episode, allow at most **3 fresh episode
   executions** with unique identities. On a valid completion reset this counter;
   never combine a partial errored execution with another trajectory. This also
   bounds total executions per task by **48**.
5. If3 executions fail to produce that next valid observation, classify the task
   **INFRA_INCONCLUSIVE** and advance to the next fresh ID. Do not revisit it.
6. A later valid result after physical or episode failures is reported as
   **RECOVERED_PROVIDER_ERROR**, separately from its behavioral success/failure.
7. First valid success immediately classifies **NON_ZERO** and stops that task.
8. Exactly16 valid completed failures classify **CONFIRMED_ZERO**. Fewer than16
   never qualify. Preserve the ordered mapping from valid indices to executions.

A returned errored trace comes from the frozen subprocess runner after its
worker has exited or been killed/waited. Only then may an orphaned in-flight
reservation be moved in full to uncertain cost and logged as `orphan_reconciled`.
No reservation is refunded and this reconciliation is not a new API attempt.
Unknown dispatch/worker completion instead keeps the reservation and globally
stops infrastructure-inconclusive, without replay or overlapping dispatch.

Identity, seed, model/provider/pricing, lineage, contract or accounting violations
are correctness failures, not retryable missing outcomes. Stop with
`IMPLEMENTATION_FAILURE`; never patch and continue this prospective run.

## Screening stop rules

- Four confirmed ZERO tasks: stop screening, freeze their16 valid traces and
  references, then proceed after the exact-input V2 preregistration is pushed.
- Twenty inspected IDs with fewer than4 ZERO tasks: stop as
  **INSUFFICIENT_FRESH_LOW**, with final LOW viability **INCONCLUSIVE**.
- Screening committed-cost guard denies a request: stop globally as
  **SCREENING_COST_LIMIT**, with final LOW viability **INCONCLUSIVE**.
  Mark the active task infrastructure-inconclusive, never ZERO/NON_ZERO.
- Task-level retry exhaustion alone advances to the next preregistered ID.
- Unknown worker completion or another global infrastructure interruption:
  **INCONCLUSIVE**; preserve all reservations and completed evidence.
- Correctness defect: **IMPLEMENTATION_FAILURE**, immediate global stop.

No policy request may follow the global monetary stop. No cap increase, new
provider, model change, manual retry, scan extension or old-task continuation.

## Evidence and immediate LOW continuation

Preserve every execution, including invalid ones, and all physical attempts.
Freeze all16 valid original failures for each confirmed ZERO. Select exactly3
using unchanged `seeded_failures(all_16, 3, seed=task_id)`, in chronological order.
Freeze all/selected episode IDs and hashes, selection seed and truthful evidence
`p_hat=0,n=16`; collect no additional evidence.

Once exactly4 qualify, obtain one rich verified benchmark-expert reference per
task through the existing provider. Freeze availability/ID/hash/bytes once;
reference-unavailable tasks remain in denominator4, without substitution or
failure-only fallback. Create the immutable input manifest and commit/push
`PREREG_ITERATIVE_LOW_VIABILITY_V2.md` before the first designer request.

Then run the frozen method immediately: max3 designer calls/task, max30 fresh
adaptation episodes/task, normal typed feedback, every candidate gate in order,
first-viable freeze, unchanged `assist_bracket`/4→8 evaluator/3–5of8 search
acceptance. K16 is16 fresh evaluation-only episodes; B_L4–12/16 and B_T7–9/16.
No extra code-design review or permission round is required by this protocol.

## Measured costs and immutable guard

Cost basis: `frozen/iterative_low_viability_v2/cost_basis.json`, SHA-256
`f8233e1d9c437c70d7829728cdf08238067dd3708db30f1ef1e749220e547076`.
Historical confirmed-ZERO episodes averaged$0.087147189;64 such episodes cost
about$5.5774 before rejected IDs, extra executions or failed-request reservations.
The prior strict scan cost$1.386324485 for26 completed episodes, but truncation
makes it unsuitable for predicting corrected ZERO yield. The maximum adaptation
120episodes at the ZERO mean is$10.4577;64 confirmations at the overall mean
are$3.0204;12 designer calls at the recent conservative maximum are$0.2054.
These planning figures cannot guarantee completion within the hard ceilings.

- **V2 screening committed-cost cap: USD8.**
- **Whole V2 operation committed-cost cap: USD20.**
- Includes original screening, all retries, paid references if any, designer,
  adaptation, K16, failed-request reservations and in-flight reservations.
- Same shared locked ledger for parent and policy workers; never reset spend
  between phases. The old completed run's ledger remains unchanged and separate.
- Frozen conservative reservation arithmetic: full wire UTF-8 bytes plus4096,
  output request limit, peak uncached prices. Qwen input/output$0.117/$0.455 and
  DeepSeek$1.32/$3.96 per million tokens. Charge at least the maximum of returned
  upstream cost and frozen token-rate cost; retain full ambiguous reservations.
- Persistent stop on monetary denial; bound violation is correctness failure.

## Executable and runtime freeze

- Driver: `scripts/e6_iterative_low_viability_v2.py`.
- Driver SHA-256: `c230bcfaea60b3c1b346018a5a7380c96d67c25e4f8fbe75702aef517d6129f4`.
- Frozen prior driver commit: `d151b150a65f7455084345e4b165b9b62234bd4a`.
- Frozen prior driver SHA-256:
  `21e3a91c2a598385e2ed8c27fdeab0584015874d3c5411260a00f6bc042f839c`.
- New namespace: `runs/e6-iterative-low-viability-v2/`.
- Runtime manifest: `frozen/iterative_low_viability_v2/runtime_hashes.json`, SHA-256
  `490a40c0d9eb2bba5257ae9101af9eaea7ed67019e8d1c9b193e25eceb2de2e4`.
- Screening-semantics audit: `docs/design/AEA_ZERO_SCREENING_INFRASTRUCTURE_SEMANTICS.md`.
- Each paid stage checks the clean branch, frozen production/config/runtime
  bytes, exact driver/audit hashes, and its preregistration's pushed ancestry.

Report all inspected IDs, valid and invalid execution counts, recovered errors,
infrastructure-inconclusive tasks, costs and exact stopping reason. If the pool
forms, complete the requested per-task LOW/CONTROL/K16 report and action-oriented
recommendation. Stop afterward: no D/I, comparisons, outer AEA, E3 or E3-SL.
