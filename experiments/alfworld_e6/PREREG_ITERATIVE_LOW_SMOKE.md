# Preregistration: one iterative LOW redesign versus one independent proposal

Status: preregistered before any paid smoke call; implementation committed and pushed.
Implementation SHA: **76e14b3b477e73ffe5f10540a5157dc99b6ab559**.
Variant: `llm_v2_iterative_low`; experimental iterative DESIGN only.

## Question and fixed scope

Does one bounded feedback-driven redesign reach a better intervention gate than one equally
budgeted fresh guess? Four tasks are an engineering/scientific smoke, not a powered performance
experiment. Only D and I run. No R, historical rerun, new screening, parameterization rescue,
third proposal, HIGH iteration, learner update, outer AEA loop, E6 or E6-SL follows this smoke.

## Deterministic task and evidence freeze

Programmatic audit of frozen `low_pool3_k16.jsonl` finds 13 confirmed zeros. Actual historical
adaptation events consume 85, 86, 87, 92, 97, 99, 107, 109, leaving **110, 114, 115, 126, 129**.
The four smallest, in order, are **110, 114, 115, 126**. Task **129 stays untouched**. Audit
sources and file hashes are retained in `runs/e6-iterative-low-smoke/pool_audit.json`.

Each selected task has 16 complete original-environment failed trajectories in
`runs/e6-pool3-k16/confirm.jsonl`, each with observations, actions and policy responses.
No new original K16 or original policy evidence is collected. Use the first ten original
traces in frozen file order, matching the historical all-failure estimator stop at n=10.
Select three with unchanged `seeded_failures(..., n=3, seed=task_id)`, then use unchanged rich
`serialize_low` with p_hat=0,n=10. The 0/16 pool classification is retained for provenance;
additional original traces are not exposed to the designer. Preserve selected episode IDs,
full trace hashes and the ordinary serializer bounds.

Generate exactly one local, zero-API rich expert reference per task via the existing provider.
Freeze observations/admissible actions/executed actions, reference ID and full record hash in
`privileged_reference.json`. Successful references must have nonempty rich steps whose actions
exactly match the verified executed sequence. Missing/mismatched rich data is unavailable;
never regenerate or replace the task. `prepared.json` freezes availability and evidence hashes.
All four tasks remain in the primary denominator. At least **two usable references** are
required for a scientific decision. Before every paid task, verify frozen evidence/reference
hashes. Reference content stays out of the policy prompt and candidate Setup.

## Shared C1 and the only experimental contrast

C1 is generated once from the common frozen evidence. D physically runs C1's existing static
checks, guard and endpoint. I reuses its exact raw proposal, source/hash, guard and endpoint
traces; equality of the entire C1 candidate record is asserted. The initial static validation result is cached as well; no C1 gate or policy evidence is
physically repeated for I.

If C1 is in_band or too_easy, its family is frozen. Run unchanged CONTROL once when needed,
attribute the entire outcome to D and I, and make no C2. This is a paired tie even if CONTROL
fails. If C1 fails before viability, each arm may make exactly one more proposal:

- **D:** unchanged original evidence/reference, C1 source/hash/mechanism, exact typed failure
  and compact relevant rollout; REPAIR_CODE for mechanical failures, REPLACE_MECHANISM for
  privilege/task-preservation, solvability or maximum-dose no-leverage.
- **I:** build a new request directly from frozen original Evidence and the same static
  contract; add only "Produce a different valid assistive Rules family from your previous
  proposal." Include C1 source solely for duplicate avoidance. No failure category, validator
  message, solvability result, endpoint verdict or C1 rollout is supplied. Never redact a D
  prompt to construct I. Persist privileged exact requests plus public request/evidence hashes
  and compare every actual request with the independently constructed expected messages.

I's production candidate history records the optimizer's internal requested operation because
it shares the same state machine; its separate `designer_inputs.jsonl` records the **actual**
neutral `INDEPENDENT_PROPOSAL` request operation and `feedback_supplied=false`. The actual
request record is authoritative for information-flow audit.

Every proposal emits exactly one family. Same task, policy, designer, reference, validation,
solvability, evaluator, controller and acceptance in both arms. Byte-identical proposals are
rejected without new policy evaluation. D runs before I for each task; temporal provider drift
is not independently controlled by this small smoke. Use proposal seed=task_id for C1 and task_id+1 for each arm's C2. Use the historical fixed Qwen3-8B Alibaba
policy (thinking off, temperature .5, max_tokens2048, max_steps50) and DeepSeek V4 Pro designer
(thinking off, temperature .7, tool request max_tokens6144); normal provider routing/pricing
guards remain active.

## Fixed budgets and freeze boundary

Each arm/task: **two logical designer calls maximum**, including shared C1, and **20 fresh
logical adaptation rollouts** beyond reused original evidence. Shared C1 episodes count once
physically and equally against both logical budgets. I's fresh C2 and CONTROL count physically
only for I. Unused budget is never topped up. Before C2 (including its call), require **16
remaining rollouts**: worst-case endpoint8 plus at least one calibration8. If unavailable,
`budget_unresolved` is an ordinary completed outcome. With C1=too_hard at8, only12 remain, so
neither arm gets C2. No opportunity is created by borrowing future confirmation budget.

A structurally valid, certified family with endpoint in_band or too_easy ends DESIGN. Freeze
source, family hash, mechanism and dose semantics. In_band accepts directly; too_easy enters
unchanged `assist_bracket`: 4→8 measurements, 3–5/8 search acceptance, existing midpoint/bisection
policy, at most four bisections and hard remaining budget. CONTROL failure is unresolved and
never reopens DESIGN. No Stage/library fallback.

**Hard total physical API cap: USD12**, including policy, designer, retries and K16. Keep
physical API spending distinct from logical opportunity accounting. An experiment-only
transport wrapper reserves each actual HTTP attempt, before sending, under a shared file lock:
serialized request UTF-8 byte count plus4096 protocol tokens bounds prompt usage; max_tokens
bounds output; use frozen uncached peak prices (.117/.455 per million Qwen input/output;
1.32/3.96 DeepSeek). Thinking stays disabled. Returned usage settles the reservation using
conservative peak token cost or upstream cost, whichever is larger. Ambiguous failed requests
retain their entire reservation as uncertain spend. Unsettled in-flight reservations count
against the cap; no retry bypasses this guard. A bound violation is IMPLEMENTATION_FAILURE. Reservation denial sets a persistent stop flag;
all subsequent physical attempts refuse to send, even if another in-flight reservation settles.
The ledger reports actual priced USD; the cap account separately reports its conservative
upper bound and uncertainty.

Before a task, check cumulative committed plus projected USD using the frozen pool mean
37.754917694/800=.0471936471175 per episode: 40 physical adaptation episodes plus .30 for at
most three physical designer calls. Before K16, project16 episodes at that same rate. These
planning projections may stop before the cap; per-request reservations enforce the cap during
an episode. Stop partial at either cap check; never raise the cap or add a task.

## Independent K16

Confirm only the one final search-accepted environment per arm/task, with16 fresh policy
rollouts and original Rules reset options. Group exact final environment hashes within each
task: equal D/I environments receive one physical K16 and16 logical confirmation rollouts per
arm. Do not confirm invalid, uncertified, too_hard or unresolved candidates. K16 data never
returns to either designer or search. B_L is unchanged [.2,.8]. Incomplete/errored K16 is an
infrastructure interruption, not a search revision opportunity.

## Outcomes and deterministic decision

Fixed gate ordering: **invalid < valid < certified < endpoint too_hard < endpoint viable <
search accepted < K16-confirmed B_L**. The primary comparison on C1-failed tasks uses the stage
of each arm's **C2 itself**, including its downstream CONTROL/K16, so a C2 regression is visible;
it never substitutes the maximum over C1 and C2. If the budget forbids C2 in both arms, use the
shared C1 stage and record C2 unavailable; this is a tie. A duplicate rejected C2 is invalid.
Endpoint too_easy is viable, not a design failure.

Secondary: C1 viability /4; C2 validity, certification, endpoint viability, search accept and
K16 B_L in each arm; mechanical/privilege/solvability/no-leverage feedback and D escape from
that failure; source hashes and lineages; logical/physical designer calls, episodes, tokens and
USD. Report counts on the four-task denominator and referenced/C2-eligible subsets explicitly.
D improves C1 if D2's reached stage (including its CONTROL/K16) is strictly higher than C1.

Correctness/provenance gates include old/HIGH/MID tests, identical shared C1, independent I
input, source identities, original/reference hashes, privilege isolation, freeze, budget and
reconciled accounting. Any failure yields **IMPLEMENTATION_FAILURE**.

A decision requires completion of **every task with a usable frozen reference**, with at
least two usable references. Ordinary invalid proposals, failed guards, no-leverage, exhausted
call caps and20-rollout budget_unresolved cases count as completed outcomes. Too few C1
failures (including all C1 viable) is not infrastructure inconclusiveness.

- **ITERATIVE_LOW_SIGNAL:** all correctness gates pass; on at least two C1-failed tasks D2
  strictly improves on C1; D strictly beats I on at least one paired task; D-worse count does
  not exceed D-better count.
- **ITERATIVE_LOW_STRONG_SIGNAL:** above plus at least one D K16-confirmed B_L delivery.
- **NO_FEEDBACK_SIGNAL:** correctness passes and the complete paired outcomes do not satisfy
  all SIGNAL conditions. This includes mixed/isolated improvements below the frozen threshold,
  ties, ordinary poor performance, and too few opportunities because C1 was already viable.
- **INCONCLUSIVE:** fewer than two usable frozen references, provider/expert infrastructure
  outage, or USD interruption before all usable-reference task outcomes and their required
  confirmations complete. Never use this label for ordinary poor candidate outcomes.

Freeze `src/aea`, designer prompts, optimizer behavior, thresholds and call cap at the recorded
implementation SHA. Only driver/audit bugs may be corrected after that SHA, with explicit
before/after hashes and a dated log; no result-conditioned method changes.

After reporting one decision and the full paired audit, **STOP FOR REVIEW**. Even STRONG_SIGNAL
only motivates a larger preregistered D/I/R pilot; it does not show LOW solved, superiority to
EnvHarness, definitive feedback benefit, generalization, learner improvement or an outer loop.

## Recorded preflight

Implementation freeze: `76e14b3b477e73ffe5f10540a5157dc99b6ab559`, pushed to the existing
`aea-llm-vnext` branch. Full units: 253 passed; LLM-free integration: 9 passed, 1 optional
RL-loader dependency skip (ray/gymnasium absent); Ruff/format, strict mypy (85 files), and
full pre-commit passed. Independent source/causal/cost review passed. No paid call preceded
this preregistration.

The committed `frozen/iterative_low_smoke/prepared.json` and `pool_audit.json` bind the
exact original episode IDs, source-file hashes, selected evidence hashes and reference hashes.
Reference generation is complete and will not be repeated:

| Task | Verified rich reference | Steps | Reference ID |
|---|---|---:|---|
|110|available|5|14c924bb414ffd1e|
|114|available|10|9f1502115cd92a43|
|115|unavailable: verifier_fail|0|none|
|126|available|10|de1683aefd48799c|

Three usable-reference tasks must complete for the scientific decision; task115 remains
in the primary denominator of four. Exact rich content remains in the local privileged
reference files, whose hashes are committed. Task129 is untouched.
