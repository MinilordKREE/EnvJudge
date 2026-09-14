# AEA LOW assistive Rules — design audit (phase 3.4, written before implementation)

## Evidence chain (frozen results, not re-interpreted)

| phase | result | what it showed about LOW |
| --- | --- | --- |
| 3 / 3.1 smokes (`results/e6_smoke.md`, `e6_smoke2.md`) | one-shot LLM Stage selection: 6 branch-reaching LOW tasks, 1 unlock, 0 accepted | direct selection rarely delivers a LOW environment |
| 3.2 refalign (`results/e6_low_refalign.md`) | rich reference + explicit diagnosis: unlocks 2 / 2 vs 1 / 2, accepted 0 vs 1, NO_EVIDENCE | diagnosis improved semantic localisation, not accepted delivery |
| 3.3a profile (`results/stage_profile.md`) | reference-prefix depth: leverage 5 / 6, no reversal, dead-to-easy within one anchor gap on 4 / 5 | the reference axis has leverage and approximate ordering |
| 3.3b stage control (`results/e6_low_stage_control.md`) | feedback control: t_max too easy 6 / 6, brackets consistent, resolution_limited 3 / 6 with gaps [6, 7], [2, 3], [10, 11], budget 2 / 6, accepted 1 (K16-confirmed in B_T) | the controller locates the frontier; the discrete Stage family often has no operating point between a dead depth t and a trivial depth t + 1 |

Therefore the next hypothesis concerns **actuator resolution**, not diagnosis or search. Nothing
here claims that assistive Rules work; that is what the pre-registered comparison tests.

## Hypothesis (to be pre-registered)

LOW failure is partly caused by the coarse granularity of reference-prefix Stage interventions.
An LLM conditioned on failed policy behaviour and a verified successful reference can generate a
parameterised assistive Rules family W(d), d in [0, 1], whose intervention strength varies more
finely than Stage depth, allowing the same empirical controller to locate useful operating points
more often. Compared prospectively: arm A = `llm_v1_stage_control` (E_t, frozen), arm B =
`llm_v1_assistive_rules` (W(d)); the manipulated variable is the intervention family only.

## Paper-level method (unchanged: three primitives)

MEASURE (regime estimate) -> DESIGN INTERVENTION AXIS (LOW: the LLM proposes an assistive
parameterised Rules family from failures + reference; HIGH: unchanged) -> CONTROL OPERATING
POINT (the existing 4 -> 8 measurement calibrates the dose). "The LLM chooses what kind of help;
feedback chooses how much help." No cascade (Stage then Rules), no meta-selector, no router.

## Variant

`method_version = "llm_v1_assistive_rules"`: shares the `_llm` code path (HIGH and MID identical
to `llm_v1`, asserted by tests); only the LOW branch differs. `llm_v1`, `llm_v1_refalign`,
`llm_v1_stage_control`, `v0.4` untouched.

## DESIGN: what the LOW designer sees and returns

Evidence (existing serialiser, rich mode): task goal, regime and estimate, the seeded failed
rollouts step by step, the exact verified rich reference (observations, admissible commands,
actions), the static environment surface of phase 3.1 (`ENVIRONMENT_SURFACE`), and abstract
prompt examples only (highlight relevant affordances, reduce distractor salience, increase
observation support, make a needed interaction easier to discover). No hand-written library, no
fixed fallback operator.

One call, tool `diagnose_and_propose_assistance`: diagnoses (as `llm_v1_refalign`:
failure_id, failure_step, reference_step, error_cause, fix_hint) then at most 2 families, each
`name`, `axis` in {O, T, A}, `mechanism_summary`, `why` (how it addresses the diagnosed
bottleneck), `rules_code` (`class _Rules(Rules)` with `DOSE = __DOSE__`), `direction =
easier_with_d`.

Dose contract: W(0) = E (no assistance; the hooks are identities at DOSE = 0), larger DOSE =
more assistance of the SAME mechanism, DOSE = 1 = the strongest version of that mechanism; an
ordered parameterised family (no continuity requirement); no switching between unrelated
mechanisms across the dose range.

## Validation (LLM-free, structural; the LLM cannot certify its own Rule)

1. Released loader + LLM-free smoke at d = 1 (`validate_rules_template`, unchanged).
2. Dose-0 identity: instantiate at `DOSE = 0.0` on the smoke inner env; `filter_action` must
   return an equal Action, `modify_transition` an equal EnvResponse, `filter_observation` an
   equal Observation (`identity_at_zero`).
3. Privilege boundary, structural: reject code that contains any reference action string
   verbatim, or two or more reference actions in sequence, or that assigns / sets `won`,
   `success`, `terminated`, `reward` to reach the goal without policy action, or that calls
   `step(` on the inner environment (a disguised Stage), or that names an object / receptacle
   token that appears in the reference observations but neither in the task goal nor in any of
   the policy's own failed observations (a privileged constant). Simple substring checks; no
   AST policy engine, no LLM judge.
4. Solvability at d = 1: the existing `solvable()` guard (policy witness when available, then
   the oracle) on `Candidate(rules_code = W(1))`.
5. Rejected families cost no policy rollout; the reason is recorded.

## CONTROL: direction-aware use of the existing dose machinery

For each valid family in proposal order: probe d = 1 first (maximum assistance; the LOW
philosophy). too_hard at d = 1 -> the family has no leverage, move to the next family.
in_band -> accept. too_easy -> refine inward on [0, 1] with the HIGH bracket's rule mirrored
(lo = largest measured too_hard dose, starting at 0 = the estimate's reset; hi = smallest
measured too_easy dose; probe (lo + hi) / 2; at most `impl.max_bisections` bisections; the same
4 -> 8 measurement). A leveraged family that runs out of budget ends the task (`budget`); no
second family gets fresh budget. Direction ordering is not trusted: a measured too_easy dose
below a measured too_hard dose is `dose_order_violation` and stops the family (no repair, no
rewrite). No cross-task warm start (start at d = 1, refinement from the local bracket only).

Unavoidable difference from the HIGH bracket: the verdict-to-bound mapping is inverted
(HIGH: too_easy raises lo; LOW: too_hard raises lo), so the LOW bracket is a mirrored copy of
the same abstraction (`aea.rules_control.assist_bracket`) rather than a call into
`aea.bracket.bracket` with swapped verdicts, to keep both directions readable and the diagnostic
history untransformed.

## Outcomes

accepted (corpus kind `knob`, regime `zero`, family, axis, d, p_hat; E3-SL consumes it unchanged)
/ no_valid_proposal / uncertified / no_leverage (every valid family too_hard at d = 1) /
exhausted / dose_order_violation / budget / reference_unavailable (no fallback to Stage).

## Budget

Unchanged: 30 charged policy rollouts per task including the estimate; validation, the guard and
the reference are in-process and uncharged; one designer call per task (`budget = designer`).

## Records

`designer_calls.jsonl` (redacted evidence, diagnoses, families with mechanism and why,
rejections with reasons), events `llm_assist_proposals`, `dose_control` per family (history of
(d, s, n, verdict), lo, hi, status), `solvable`, `no_leverage`, `probe`; privileged reference
record as before; K16 confirmation evaluation-only.

## Not implemented

LLM repair, refinement rounds, Stage + Rules cascade, task-type router, Stage / Rules
meta-selector, cross-task family memory, prompt optimisation, embeddings, learner routing,
skill learning.
