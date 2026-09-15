# Preregistration: fresh iterative LOW viability pool

Status: frozen before fresh screening. This preregistration, the driver and the
used-task audit must be committed and pushed before the first screening call.

## Purpose and immutable boundary

Obtain exactly four fresh confirmed-ZERO tasks for a single-arm viability test
of `llm_v2_iterative_low_semantic_gate`. No comparison arms are used. Previous
iterative LOW smokes remain `IMPLEMENTATION_FAILURE`, with no efficacy claim.

Research worktree: `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`.
Starting and validator-fidelity commit:
`bec74ed8a6ff40e119b2299c92b07b8602ff5fef`.
Main and all historical artifacts remain unchanged.

Production `src/aea` remains byte-identical to that commit. The new experiment
driver supplies only the explicitly requested budgets and orchestration. Before
adaptation, a separate preregistration will freeze the exact four tasks, their
evidence and reference hashes, the same driver, and the decision rule.

## Audited task order

- Same task universe: nonnegative integer ALFWorld **train bridge-seed task IDs**,
  using the current corpus reset protocol.
- Used-task audit: `frozen/iterative_low_viability/used_task_audit.json`.
- Audit SHA-256: `cc40cca0dec23c1fa2220cfdc102cd1de33d0753c74030194641bf7e02df9d4b`.
- Smallest never-used task ID: `130`.
- Exact 20 never-used IDs in ascending order: `130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149`.
- This order derives programmatically from recorded historical use, including
  real environment replay/integration use. Designer/request RNG seeds, fake unit
  task IDs and explicitly held-out split seeds do not define train task use.
- Inspect at most these 20 IDs and stop immediately when four qualify. No
  extension, replacement from outside the list, task-semantic selection, or new
  50/100-task pool is permitted.

## Frozen policy and original environment

The policy and configuration are read from unchanged `scripts/e3.py` and
`configs/corpus_aea.yaml`: OpenRouter `qwen/qwen3-8b`, Alibaba pinned, fallback
disabled, thinking disabled, temperature 0.5, maximum output 2048 tokens;
`think_action`, history 200 and a 50-step episode horizon. The environment is
the original ALFWorld train bridge with `repetition_threshold=0`, seeded by the
task ID. Every screening episode uses an identity candidate and a fresh actual
episode identity; no old trace or result is reused.

Policy/configuration hashes are included in the frozen run record. The semantic
screen remains `alfworld-semantic-screen-v1`, source SHA-256
`ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`.
No designer or privileged reference participates in ZERO qualification.

## Sequential qualification and errors

Run one original-environment episode at a time. After each completed episode:

1. If any success occurs, stop this task immediately and advance to the next ID.
2. If a recovered provider error/retry disqualifies the task under the frozen
   rule below, retain all evidence and costs and advance without replacing the
   episode. A terminal provider/environment episode error, provider outage or
   execution interruption instead stops the run as infrastructure inconclusive.
3. Otherwise continue until exactly 16 valid completed episodes. The task
   qualifies only at 0/16 with zero qualifying errors. Freeze it once.

Retry interpretation: **strict physical-error exclusion**. Any recorded
ambiguous failed physical request, `infra_retry` or `infra_failure` event makes
that task ineligible, even if the automatic retry recovers. The policy retry
loop itself remains unchanged. This explicit stricter interpretation of zero
provider errors was chosen before any new screening result; historical pools
permitted recovered retries, so their ZERO rates are not an eligibility forecast
for this stricter pool.

The current policy's request retry loop is unchanged: up to 10 attempts,
2-second initial delay, exponential backoff capped at 90 seconds plus up to
1-second jitter, and a 900-second total window. Retryable outcomes include
408/409/425/429, 5xx, timeouts and connection failures; 400/401/403 are not retried.
Every physical attempt is recorded and charged against the hard guard. Failed
or interrupted episodes are never replaced to produce an apparently clean 0/16.

## Evidence retention and references

Preserve all 16 original traces for every qualified task. Derive the normal
three failed trajectories with the unchanged
`seeded_failures(all_16, 3, seed=task_id)` on their recorded chronological order.
Use the unchanged normal serializer with truthful `p_hat=0, n=16`; freeze task
ID, all/selected episode IDs, trace hashes and evidence hashes. No extra policy
episodes may enrich the evidence.

After four tasks qualify, obtain one rich benchmark-expert reference per task
using the existing provider. Freeze its exact status, ID, bytes and hash once;
never regenerate it for audit. Reference-unavailable tasks remain in the four
task denominator, without replacement or failure-only fallback.

## Measured cost plan and hard ceilings

Historical source: `runs/e6-pool3-k16/ledger.jsonl` and its frozen 0/16
classification, audited before this run. That pool spent $37.754917694 for 800
episodes (mean $0.047193647). Its 208 confirmed-ZERO episodes averaged
$0.087147189 each; the most expensive ZERO task averaged $0.133792925.

| Planning component | Estimate |
| --- | ---: |
| Minimum 64 ZERO-screen episodes at historical ZERO mean | $5.5774 |
| Maximum 120 adaptation episodes at historical ZERO mean | $10.4577 |
| Maximum 64 confirmation episodes at overall mean | $3.0204 |
| Maximum 12 designer calls at latest maximum conservative returned cost | $0.2054 |

These are planning estimates, not guaranteed completion costs. Rejected task
screening and failed-request reservations add cost. The theoretical maximum
504 policy episodes already exceeds $20 at the overall historical mean.

- **Screening hard cap: USD 8**, cumulative from the first physical request.
- **Whole-run hard cap: USD 20**, including screening, design, adaptation,
  confirmation, ambiguous failed requests and requests in flight.
- Use one shared locked cap ledger; never reset spend at a phase boundary.
- Preserve historical conservative reservation arithmetic: full wire UTF-8 byte
  bound plus protocol allowance, request output limit, and frozen peak uncached
  rates. Before every physical transport attempt, reserve against the active
  phase ceiling in both parent and policy subprocesses. Retain the full
  reservation for ambiguous failures; reconcile returned usage conservatively.
- A denial creates a persistent stop. No cap increase after results begin.
  A reservation-bound/provenance/accounting defect is `IMPLEMENTATION_FAILURE`.

## Stopping and subsequent phase

- Four qualified tasks: freeze the input set; proceed only after the exact-input
  viability preregistration has been committed and pushed.
- Twenty inspected IDs with fewer than four ZERO tasks:
  **`INSUFFICIENT_FRESH_LOW`**, then stop without extending the scan.
- Hard cost cap, provider outage or infrastructure interruption before enough
  tasks complete: **`INCONCLUSIVE`**, with the exact stop reason and all costs.
- Method-invalidating correctness defect: **`IMPLEMENTATION_FAILURE`**, stop;
  no patch-and-continue in the same prospective run.

No adaptation designer call is permitted under this pool preregistration alone.

## Critical runtime and cost provenance

- Runtime-source manifest: `frozen/iterative_low_viability/runtime_hashes.json`,
  SHA-256 `ee52b40374ea0b28bc39cb7df262c13babb27a947981d96aa62b0b6e8ca00d29`.
  Actual bridge, Rules wrapper, code loader, policy formatter, core types and
  runner bytes are checked against this manifest before execution.
- Measured cost basis: `frozen/iterative_low_viability/cost_basis.json`, SHA-256
  `a67e8f907a201099cde55266b578331a32dc6603b0c388799b30719a2b56817e`.
- The full historical file inventory remains local; its hash and reproducible
  scanner scripts are bound by the committed used-task audit.

## Executable freeze

- Driver: `scripts/e6_iterative_low_viability.py`.
- Exact driver SHA-256: `21e3a91c2a598385e2ed8c27fdeab0584015874d3c5411260a00f6bc042f839c`.
- New run namespace: `runs/e6-iterative-low-viability/`.
- Both paid phases require their preregistration and exact driver/audit/input
  hashes to be present in a commit already pushed to `origin/aea-llm-vnext`.
- Interrupted in-flight operations cannot be replayed implicitly. All physical
  attempts, completed traces, classifications and stop conditions are retained.
