# AEA LOW Stage control — design audit (phase 3.3b, written before implementation)

Motivation (frozen, phase 3.3a, `results/stage_profile.md`): on fresh confirmed-zero tasks the
silently replayed prefix of a verified successful expert reference is an empirically ordered
assistance axis (leverage 5 / 6, no meaningful reversal at coarse anchors, dead-to-easy crossing
5 / 6, useful band hit directly 1 / 6, transition confined to a 3-6-action anchor gap on 4 / 5
leveraged tasks). Phase 3.3b tests whether current-policy feedback can choose the operating
point on that axis: the LOW analogue of HIGH dose control. Nothing else changes.

Method reading: HIGH = the LLM proposes a challenge family w(d) and the controller chooses d*;
LOW (this variant) = the verified reference defines an assistance family E(t) and the controller
chooses t*. The shared principle: the intervention family defines an axis; current-policy
interaction chooses its operating point. No LLM chooses the cut on this path; HIGH remains
LLM-generated and the reference is generated as already defined (lazy, LOW only, privileged).

Variant: `method_version = "llm_v1_stage_control"`; identical to `llm_v1` on band and saturated
(the shared `_llm` code path); differs from `llm_v1` / `llm_v1_refalign` only in the LOW branch.

## Definitions

| item | definition |
| --- | --- |
| reference | the exact rich expert trajectory of `llm_v1_refalign` (`ExpertReference`, verified `won`, recorded to `privileged_references.jsonl`), actions a_1 .. a_T |
| Stage family | E_t = `Candidate(in_env_actions = compile_prefix(a_1..a_t))` on the staged configuration (100-step engine cap, released Setup harness, prefix replayed silently); t is the actuator (integer prefix depth) |
| dose | d = t / t_max, reported only; the environment implementation uses t |
| t_max | the largest t in 1..T whose prefix (1) compiles to exactly a_1..a_t (every action admissible and effective), (2) leaves the staged session NOT won and NOT done (policy hand-off possible); found by trying t = T, T-1, ... in one in-process pass (never charged); the full reference is terminal on every ALFWorld task seen so far, so t_max < T is the normal case |
| maximum-assistance state | E_{t_max}; the first probe (the LOW analogue of d = 1 first) |
| measurement | the existing `evaluate` (4 -> 8 rule): 0 / 4 too_hard, 4 / 4 too_easy, else top up to 8 and 3..5 / 8 in_band, 0..2 too_hard, 6..8 too_easy; every rollout charged to the task's one budget through `_rollouts(phase = "probe")` |
| bracket state | integers lo (largest measured too_hard depth; starts at 0, the estimate's zero-regime reset, never re-probed) and hi (smallest measured too_easy depth; undefined until E_{t_max} is measured); `history` = every (t, successes, n, verdict) |
| update | too_hard at t -> lo = t; too_easy at t -> hi = t; in_band -> accept; next probe mid = floor((lo + hi) / 2) while hi - lo > 1 and budget remains; a depth is never probed twice |
| terminal reference | t = T (or any t) whose replay leaves the task won / done is never a Stage; if no t in 1..T is valid and non-terminal the task ends `no_stage_family` |
| acceptance | unchanged: the first in_band probe writes a corpus entry of kind `stage` (t, state hash, profile, stage budget 100, candidate id, p_hat); K = 16 confirmation is evaluation-only and never fed back |

## Outcomes (task-level, all `dropped:<reason>` except accepted)

| outcome | when |
| --- | --- |
| accepted | some probed t is in_band |
| no_stage_leverage | E_{t_max} is too_hard: maximum assistance does not make the task accessible; no further mechanism |
| resolution_limited | hi - lo == 1 with lo too_hard and hi too_easy: no unmeasured integer depth remains; no fractional Stage, no partial action, no interpolation |
| nonmonotonic_profile | the measured history contains t1 < t2 with verdict(t1) = too_easy and verdict(t2) = too_hard (a discrete ordering contradiction); refinement stops; nothing is repaired, fitted or ignored |
| budget | the cap is reached during a probe (unused budget stays unused; never raised) |
| invalid_stage | a chosen depth does not compile exactly or fails the existing oracle guard at that depth; refinement stops (no neighbouring depth is substituted) |
| reference_unavailable | the expert produced no verified reference (lazy request failed); no fallback to another LOW mechanism on this variant |
| no_stage_family | every non-terminal depth is invalid |

A note on `nonmonotonic_profile`: a bracket that only shrinks between a measured too_hard lo and
a measured too_easy hi cannot produce the contradiction (every new probe lies strictly inside
the bracket and moves one bound toward it). The check is kept as a stated invariant over the
full history and would fire only if the probe order ever left the bracket; under the update rule
above it is structurally unreachable, so the phase-3.3b ordering evidence comes from the t_max
verdict distribution, the acceptance / resolution outcomes and the K16 confirmations, not from
this counter. This is written into the pre-registration so the `AXIS_ORDERING_BREAKS` state is
interpreted correctly.

## Budget accounting

One task budget, cap 30 charged policy rollouts (unchanged). The regime estimate charges its
actual rollouts (10 on a decided zero task; in the paired driver the estimate is replayed from
the shared evidence and still charged); Stage control receives the remainder (20 on a 10-rollout
estimate): at most one t_max probe (4 or 8) plus refinement probes of 4 or 8 each, i.e. at most
five 4-rollout probes or two 8-rollout probes plus one 4-rollout probe. The `BudgetExhausted`
raised by `_rollouts` ends the task as `budget` (the same as HIGH). Reference generation, t_max
determination, prefix compilation and the oracle guard are in-process sessions and are never
charged.

## Ordering claim (what the spec may say)

Stage control uses reference progress as an *empirically ordered* assistance axis (phase 3.3a
evidence at coarse resolution). It does not assume, prove or require that success probability
is monotone in reference depth; contradictions are recorded as outcomes.

## Privilege boundary (unchanged)

The reference reaches only the privileged record and the compiled prefix; the policy sees its
ordinary observation after the Setup replay; `traces.jsonl` and `corpus.jsonl` carry the
prefix only; nothing past the selected depth is learner-visible; no designer call is made on
this path, so no designer record is written for the cut choice (the `reference` event and the
privileged record are written as for `llm_v1_refalign`).

## Records

Event `stage_control`: `T`, `t_max`, `t_max_verdict`, `history` [(t, s, n, verdict)],
`lo`, `hi`, `status`, `unique_cuts`, `accepted_t`, `accepted_d = t / t_max`. Event
`stage_candidates` per probed depth (certified / rejected, source `control`), `probe` events as
today. Corpus entry unchanged (`kind = stage`).

## Complexity

No new paper-level primitive: MEASURE (estimate) -> DEFINE INTERVENTION AXIS (the verified
reference's prefix family) -> CONTROL (the existing 4 -> 8 measurement drives an integer
bracket, the LOW mirror of the HIGH bracket). New code: one module with the pure integer bracket
(`aea.stage_control`), one controller branch (`_stage_control`), one config literal. No new
LLM call, no new threshold, no new budget.

## Tests to write before any paid call

latest valid non-terminal t_max (full terminal reference excluded); first probe = t_max;
too_easy updates hi; too_hard updates lo; mixed first batch tops up to 8; 3..5 / 8 accepts;
6..8 / 8 updates the easy side; 0..2 / 8 updates the hard side; no duplicate depth; one-action gap
-> resolution_limited; injected ordering contradiction -> nonmonotonic_profile; t_max too_hard ->
no_stage_leverage; budget <= 30 with the estimate charged; HIGH / MID identical to llm_v1;
llm_v1_refalign records unchanged; v0.4 golden unchanged; no reference content past the selected
depth in learner artifacts.
