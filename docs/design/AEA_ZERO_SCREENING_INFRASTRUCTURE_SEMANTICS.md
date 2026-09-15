# Fresh ZERO screening: infrastructure and behavioral evidence

## Scope and preserved history

This correction applies only to a new prospective fresh-pool screening driver.
It does not change AEA regime estimation or any LOW method code. The preceding
130–149 scan, its preregistration and its report permanently remain
`INSUFFICIENT_FRESH_LOW`; those IDs are consumed and cannot be resumed.

The research branch starts at `d88d2e1b7be3279f89944f155fc41cf1c18a5c2a`.
Production LOW, the semantic gate and validator remain at the frozen source tree
including `bec74ed8a6ff40e119b2299c92b07b8602ff5fef`. The new experiment uses
separate driver, run directory, frozen-input directory and V2 preregistrations.

## What is observed

The behavioral quantity is the policy's probability of task success in the
original environment. A completed policy episode provides one observation.

| Event | Meaning | Behavioral counter effect |
| --- | --- | --- |
| Valid completed success | Policy reached task success | episodes +1, successes +1 |
| Valid completed failure | Policy completed its episode without task success, including the fixed horizon | episodes +1, successes unchanged |
| Failed provider/network attempt | No usable response from that physical request | Neither counter changes |
| Internal request retry succeeds | The episode can continue using a usable response | No separate observation; count only its eventual valid completion |
| Episode terminates with an infrastructure error | No valid completed outcome exists, even if a partial trajectory exists | Neither counter changes |
| Fresh episode retry completes | A new episode supplies one valid outcome after a missing result | Count that valid outcome once |
| Bounded episode attempts exhausted | Next behavioral observation could not be obtained | task `INFRA_INCONCLUSIVE` |

**Policy episode failure is valid behavioral evidence. Provider/network failure
is a missing observation, not a behavioral failure.** A recovered provider error
must not erase the task's other valid evidence. Physical-attempt counts, episode
execution counts and valid behavioral episode counts are distinct quantities.
The existing substrate's `rollout` ledger rows describe episode executions;
the screening driver owns the explicit valid-outcome counters.

## Qualification and stopping

Initialize `valid_episodes = 0`, `valid_successes = 0`. Every trace is checked for
identity candidate, expected train bridge seed, fresh episode identity and a
valid completion before it enters these counters.

- First valid success: classify `NON_ZERO` and immediately stop the task.
- Exactly 16 valid completed failures: classify `CONFIRMED_ZERO` and freeze all
  16 traces. Recovered provider retries do not invalidate these completions.
- Fewer than 16 failures without a success do not establish ZERO.
- Exhausted episode attempts: classify `INFRA_INCONCLUSIVE`, retain all valid
  and invalid evidence/costs, then advance to the next preregistered fresh ID.
- Stop the pool after four confirmed ZERO tasks or at most 20 inspected IDs.
  Fewer than four after the 20-ID scan means `INSUFFICIENT_FRESH_LOW`.
- The $8 screening committed-cost ceiling stops the entire scan with
  `SCREENING_COST_LIMIT`; it cannot be bypassed by moving to another task.

## Bounded infrastructure recovery

Keep the existing physical provider retry implementation unchanged. For the
policy this permits up to ten attempts per request, the existing exponential
backoff and total retry window. A successful retry inside a still-running
episode creates no extra episode and needs no replacement execution.

For each next valid behavioral episode, permit at most **three fresh episode
executions**, each with a distinct episode identity. Each execution retains the
frozen 50-step horizon and 600-second subprocess timeout. An errored execution
consumes one of these three attempts but contributes no behavioral outcome.
Reset this attempt count only after a valid completion; at most 48 episode
executions can be dispatched per task. The first success still stops immediately.

After three invalid executions for the same next observation, stop that task as
`INFRA_INCONCLUSIVE` and advance once; do not return to it. Missing outcomes are
never imputed, and a partial failed execution is never stitched into a later
valid trajectory. After a later valid completion, report prior physical or
episode failures as recovered infrastructure events, independently of success.

This episode retry policy is confined to screening. Adaptation, certification,
CONTROL and K16 retain their frozen infrastructure behavior.

## Ambiguous billing and worker completion

The shared locked monetary guard retains the full conservative reservation for
every ambiguous failed physical request. Recovering later does not refund it.
All returned calls, reservations and requests in flight count against the same
$8 screening / $20 whole-run ceilings. Costs never reset at the adaptation boundary.

The frozen `SubprocessRunner` uses `subprocess.run`; a returned timeout/error
trace is received only after that worker has exited or has been killed and waited
for. With screening concurrency one, an orphaned in-flight reservation may then
be transferred, in full, to uncertain cost and recorded as `orphan_reconciled`.
This is bookkeeping for an already dispatched request, not another API attempt.
No reservation is released. If worker completion is unknown because dispatch
itself raises, retain in-flight reservations and stop globally as infrastructure
inconclusive; do not start overlapping or implicitly resumed work.

Source, candidate, seed or episode-identity corruption; wrong model/provider or
pricing; and monetary-bound violations remain correctness stops. Such defects
must not be hidden by the infrastructure retry path. A prospective correctness
failure is never patched and continued in the same run.

## Evidence and frozen LOW continuation

Store every episode execution, including invalid ones, with its outcome status,
trace hash, physical-attempt attribution and cost record. Maintain an explicit
mapping from valid episode indices to the executions that produced them.

For a confirmed ZERO task, freeze exactly its 16 valid original traces in order.
Use the unchanged `seeded_failures(all_16, 3, seed=task_id)` and normal LOW
serialization with truthful `p_hat=0, n=16`. Do not select partial errored traces
or collect extra evidence. Obtain one rich verified reference per task and
freeze its status and exact bytes once; missing references stay in denominator4.

Once four tasks qualify, commit/push their exact input manifest and V2 viability
preregistration, then immediately execute the already-frozen single-arm LOW
smoke. Three designer calls, 30 adaptation episodes, gate order, typed feedback,
semantic UNCERTAIN handling, solvability, first-viable freeze, unchanged CONTROL,
3–5/8 acceptance and evaluation-only K16 remain unchanged.
