# AEA `llm_v1` — regime-conditioned LLM intervention design (method spec)

Status: IMPLEMENTED in the `aea-llm-vnext` branch (phase 2 of the LLM-first redesign); no
experiment has run on it yet. Selected by `AEAConfig.method_version = "llm_v1"`; the default
`"v0.4"` is the box of `AEA_v0.4.md` unchanged (a config without the field is v0.4).

Method identity, one line: **the LLM chooses what environmental intervention to try;
current-policy interaction decides whether the intervention works.**

Three primitives and nothing else at the paper level:

1. **Measure** the learner's behaviour on the task (regime estimation).
2. **Design**: one LLM, conditioned on the regime and on real trajectory evidence, proposes at
   most two interventions.
3. **Control**: current-policy rollouts accept, reject or calibrate each proposal.

## Pseudocode (paper level, 15 lines)

```text
D  <- rollout current policy on E (K = 16, early stop)
r  <- estimate regime from D                      # zero | band | saturated

if r is band:                     return E         # useful as it is

if r is saturated (HIGH):
    F <- LLM(goal, D, HIGH contract)               # <= 2 dose-parameterised families
    for family in F (designer order):
        if not solvable(family, d = 1):            continue
        if not leverage(family, d = 1):            continue    # 4 -> 8 probe: too_easy
        d* <- task-local bracket on [0, 1]         # accept iff 3..5 of 8
        if d* exists:             return family(d*)

if r is zero (LOW):
    R <- privileged reference from reset, if available (lazy; designer-only)
    S <- LLM(goal, failed D, R, LOW contract)      # <= 2 grounded restart points
    for stage in S (designer order):
        if not solvable(stage):                    continue
        if probe(current policy, stage) in band:   return stage

return unresolved
```

## What the designer receives (implementation detail, `aea.designer`)

Evidence is serialised without any LLM, deterministically, under a fixed size bound
(`EvidenceBounds`: 2 successes + 1 failure on HIGH, the `impl.n_failed_rollouts` seeded failures
on LOW, 12 head + 6 tail steps per trajectory, 320 characters per observation, 240 per reasoning
excerpt, 24 000 characters in total). Each step shows the policy's reasoning excerpt (from
`policy_raw_response`), its action with `blocked` / `no effect` flags, and the observation it saw.

| item | HIGH (`serialize_high`) | LOW (`serialize_low`) |
| --- | --- | --- |
| task goal | from the step-0 observation (`Your task is to:`) | same |
| regime, p_hat, n | yes | yes |
| trajectories | shortest and longest success, first failure | the seeded failed rollouts, labelled `F1..` |
| success lengths | yes | no |
| Rules contract + the two library families as few-shot | yes | no |
| privileged reference | never | when available: the expert's action list, labelled `reference` |

## HIGH contract (`propose_interventions`)

Up to two proposals, each `name`, `axis ∈ {O, T, A}`, `mechanism_summary`, `rules_code` with a
class attribute `DOSE = __DOSE__`; larger DOSE must be harder, DOSE = 0 unchanged, the goal and the
verifier untouched, solvable at DOSE = 1. Validation is the v0.4 `validate_rules_template`
(released `code_loader`, LLM-free smoke at d = 1) plus: library copies rejected, empty mechanism
summary rejected, bad axis rejected, duplicate names rejected. The LLM never outputs a dose and
never sees a rollout result; it is called once per task.

Empirical control is the v0.4 `_try_family` unchanged: solvability guard at d = 1 (O-axis by
construction; otherwise the policy's own success replayed, then the oracle), leverage test at
d = 1 by the 4 -> 8 rule (`too_easy` = no leverage, `in_band` = accepted at d = 1, `too_hard` =
search), task-local bracket on [0, 1] with at most 4 bisections, the 30-rollout cap.

**Library role.** `FooterMask` and `HorizonSqueeze` are few-shot examples in the prompt only; the
main `llm_v1` HIGH path is `llm_only`. There is no hybrid mode in this version: the fixed-library
method remains available as `method_version = v0.4` for the comparison.

**Warm start.** `llm_v1` always starts the bracket at 0.5. A generated family's name is a
per-task identity; trusting a cross-task frontier history keyed by such names would let two
unrelated interventions that happen to share a name seed each other. No name matching, embedding
or clustering is introduced; the leverage and frontier events are still written for audit.

**Known v0.4 detail, unchanged here.** When the leverage test at d = 1 is already `in_band`, the
v0.4 loop accepts before `_record_frontier`, so no frontier is written for that task. Under
`llm_v1` the frontier history is not consumed (see Warm start), so the omission has no effect;
it is left for the post-E5 review rather than fixed here.

## LOW contract (`select_stages`)

Up to two grounded restart points, each `source ∈ {failure, reference}`, `trajectory_id`,
`step`, `mechanism_summary`. A failure proposal must name a supplied failure (`F1..`) and a step in
`1..length`; a reference proposal must name `reference` with a step in `1..len(reference)` and is
only valid when a reference was supplied. Anything else is rejected; nothing is repaired and the
designer is not called again.

Each accepted proposal is compiled by the v0.4 stage machinery: the prefix (the failure's actions
up to the step, or the reference's actions up to the step) goes through `compile_prefix` on the
100-step staged configuration (effective, admissible actions kept; `look` appended), is
deduplicated by the hash of the compiled prefix, becomes `Candidate(in_env_actions=...)` (the
released `Setup` harness), and is guarded by `solvable()` with the oracle only. Candidates are
probed in the designer's order by the 4 -> 8 rule; the first `in_band` one is written as a corpus
entry of kind `stage` (unchanged format; E3-SL consumes it as before). Otherwise the task is
`dropped` (`uncertified`, `too_easy`, `dead`, `budget`).

**The reference is privileged designer information.** It is generated lazily, only on `llm_v1 +
zero`, by `ExpertReference` (the ALFWorld handcoded expert from the task's reset state, through
the same locked in-process session the guards use; never charged). It reaches exactly two places:
the LOW designer prompt and the selected prefix. It never reaches `traces.jsonl`, `corpus.jsonl`
(beyond the selected prefix, which is learner-visible by construction), the policy prompt, or
skill induction. `designer_calls.jsonl` keeps the evidence with the reference block replaced by
its metadata (length, hash); the full evidence is hashed (`evidence_sha256`). If no provider is
configured or the expert fails (error, stuck, timeout, no success), the designer works from the
failures alone; there is no midpoint/end fallback.

**Not implemented (deliberately).** Assistive dose-parameterised Rules on the LOW side (would add a
second, direction-specific calibration mechanism); learner-specific or task-type routing; any
second agent (critic, planner, ranker, refiner); an iterative rewrite loop after rollout feedback.

## Outcomes and failure policy

| situation | outcome |
| --- | --- |
| designer API / provider / parse failure | `infra_error` (re-run on resume; never a silent v0.4 fallback) |
| no designer configured under `llm_v1` | `infra_error` (kind `config`) |
| 0 valid HIGH proposals | `dropped: no_valid_proposal` |
| 0 valid LOW proposals | `dropped: no_valid_proposal` |
| HIGH: every family infeasible / uncertified / no leverage | `dropped: no_leverage` |
| HIGH: bracket exhausted | `dropped: exhausted` |
| LOW: no certified candidate | `dropped: uncertified` |
| LOW: no in-band candidate | `dropped: dead` / `too_easy` |
| cap reached | `dropped: budget` |

## Records

- `designer_calls.jsonl`: one row per designer call (`task_id`, `regime`, `method_version`,
  `evidence_sha256`, redacted `evidence`, `arguments`, `accepted`, `mechanisms`, `rejected`,
  `reference_used`, `reference_steps`).
- `events.jsonl`: v0.4 events plus `designer_evidence`, `reference`, `llm_stage_proposals`; the
  `families` and `stage_candidates` events carry `source: designer`. Every accepted environment
  is reconstructable from `corpus.jsonl` + `events.jsonl` + `traces.jsonl`.
- The designer call is ledgered as `budget = designer` (provider pin, usage and cost as every
  other LLM call) and is not charged to the 30-rollout cap.

## Future ideas (not part of `llm_v1`)

Assistive LOW Rules; a learner-utility distinction downstream of the behavioural regime; a shared
identity for generated families (only if evidence shows a cross-task prior helps).
