# Matched contemporaneous E3: legacy integrated vs Designer–Controller AEA

Protocol: `e3-matched-designer-controller-v1`.
Prepared before any new baseline, designer, judge or learner API request for this study.
Method implementation: `cf976b4e332ecf8575d1df5b6cc7e88f5db609bf`.
Execution status: **NOT_STARTED**. This preregistration does not start an experiment.

## 1. Question and treatment

On the same 30 task instances, with identical newly measured baseline evidence and matched
external execution protocol, does the frozen Designer–Controller implementation produce
more independently K16-learnable environments than the frozen integrated mechanism?

| Arm | Frozen selector | DESIGN / CONTROL |
|---|---|---|
| A: matched legacy | `llm_v2_integrated` | Existing integrated proposals, endpoint family freeze and raw-dose bracket |
| B: new AEA | `llm_v3_designer_controller` | Shared bounded DESIGN ↔ effective-level CONTROL, then final family freeze |

Both selectors execute from the pinned implementation checkout. Legacy core modules and
configuration defaults retain their historical behavior; the historical baseline is
`969e339281e71190d1df6aed579b2402513bcd45`, not a reconstructed method from result summaries.
Do not modify either method to equalize its internal decisions.

The treatment is the **complete frozen design/control implementation bundle**. Its declared
differences include prompts and output contracts, LOW round admission (A:16, B:8 remaining
episodes), HIGH design bounds (A:one call/up to two families, B:up to three rounds), effective
level characterization, feedback, identity/admission coverage, exact final certification
and the family-freeze boundary. Designer model and R5 model/prompt/schema are common, but
request counts, request-level output limits and gate coverage follow each frozen method.
This contrast cannot isolate the effect of deduplication or REFINE_CONTROL alone.

No O/R/G reruns, new tasks, screening, E3-SL, learner training, target-band change or judge
optimization are included. Historical 9/30, 5/30 and other results are descriptive context,
not the contemporaneous comparator and not inputs to selection or routing.

## 2. Cohort, common measurement and evidence

- Task IDs and simulator seeds: exactly `0..29`, seed equals task ID. Bind the original
  ALFWorld game mapping, runtime files and package versions to the freeze manifest.
- Collect **one fresh original-environment baseline per task**, before either arm adapts
  that task. Both arms receive exactly the same ordered evidence and estimator result.
- Estimator unchanged: Beta(1,1), batches 4 then 2, confidence .9, at most 16 valid episodes,
  LOW <.2 / MID [.2,.8] / HIGH >.8, maximum posterior-mass routing. Preserve its existing
  single retry for an errored measurement episode; physical costs remain recorded.
- A separately tested experiment adapter replays this immutable measurement evidence into
  both native Controllers, reproducing their baseline budgets and trace receipts. It must
  not recompute from historical K16, independently remeasure an arm, invent paid calls,
  fabricate new physical episode identities, or alter the estimator's stopping rule.
- Shared baseline IDs may occur in both arm receipts **only by this declared sharing rule**.
  All adaptation and confirmation IDs must be globally unique and disjoint from baseline.
- For each fresh LOW task, locally obtain/verify one rich reference under the frozen
  provider, bind its provenance/hash, and supply the same immutable reference to both arms.
  The same raw baseline pool is available to both; within-pool evidence selection follows
  each method's frozen code. Reference material remains Designer/Judge-only.
- MID remains original, with no Designer, Controller calibration, reference or judge.
- The fresh common LOW/MID/HIGH task counts determine subgroup denominators. The previous
  run's ten LOW tasks must not be imposed on this run or used for selective recruitment.

## 3. Common models and budgets

Model, endpoint, retry and pricing configurations are copied exactly into the freeze.

| Component | Configuration |
|---|---|
| Learner | OpenRouter `qwen/qwen3-8b`, Alibaba pin, thinking off, T=.5, output 2048, original horizon 50 |
| Designer | DeepSeek `deepseek-v4-pro`, thinking off, T=.7; arm-native request limits |
| LOW judge | Frozen R5 `WitnessCheckingPrivilegeJudge`, DeepSeek `deepseek-v4-flash`, T=0, output 2048 |
| Measurement | ≤16 valid episodes, shared between arms |
| Adaptation | ≤30 valid policy episodes **per arm per task** |
| Search acceptance | Existing 4→8 rule; 3–5/8 |
| Confirmation | Fresh 16 episodes for each accepted or kept final environment |
| K16 metrics | B_L=4–12/16; B_T=7–9/16 |

No fallback learner provider/model. Record requested and returned model/provider identities;
a routing mismatch or unreconciled accounting is a stop condition, not a new task result.
R5 Phase A remains NOT_READY; this study does not relabel its validation status or tune it.

No additional monetary ceiling is set by this preregistration. Applying the previously
authorized E3 no-dollar-ceiling execution policy to this new two-arm run awaits explicit
confirmation of this run's paid-start scope. Until then no paid dispatch is permitted.
Regardless of USD authorization, method rounds, candidates, episodes and retries stay bounded.

## 4. Frozen B control policy

B uses the last nominal member of each captured class as its deterministic representative.
Captured equivalence is not global behavioral equivalence. Do not switch representatives
based on outcomes or probe known aliases separately within a provisional family.

Keep the default three DESIGN rounds, at most five distinct positive levels per round,
seventeen-point scalar grid, strongest/weakest/ordinal-gap search and typed feedback mapping.
A redesigned family is characterized and admitted afresh. Keep the ≥8 episode admission
threshold: later budget exhaustion is an ordinary method outcome. No budget is added to
finish a promising refinement, and K16 cannot fund or reopen search.

## 5. Matched contemporary scheduling

Freeze a task permutation independent of historical scores, using `Random(20260917)`.
Freeze an independently shuffled balanced list of fifteen A-first and fifteen B-first
submission orders using `Random(20260918)`. Save the explicit schedule in the manifest.

Use fifteen waves of two task pairs:

1. Collect and seal both shared baselines for the wave, with four episode workers per task.
2. Submit A and B for each task, in its recorded submission order. Both arms run within
   the same wave, each in its own task/arm directory with four episode workers.
3. At most four adaptation arm jobs and sixteen learner episodes are concurrent. Do not
   refill a completed job's slot with a later wave. Arm-specific work/call counts may differ.
4. After all four searches are terminal, seal eligible final environments. Run separate
   fresh K16 for each eligible arm/task with the same concurrency limits, then close the wave.
5. Start the next wave only after outcomes, evidence and accounting for this wave close.

The first baseline requests provide routing verification; no extra outcome-bearing probe
or unregistered screening task is added. Record UTC start/end and per-stage timestamps;
contemporaneous means interleaved windows, not an assertion that remote weights never change.

## 6. Final evaluation and interruption

Use independent four-by-four K16 batches for each accepted/kept environment, including MID.
Even when both MID arms return the same original environment, their K16 episodes are fresh
and separate. Do not reuse search episodes or K16 observations between arms.

Snapshots of the exact final candidate, source/actions, required admission/certificates and
method-state digest must verify before evaluation. The digest must remain fixed afterward.
No DESIGN/CONTROL callback, selection of a better confirmation, or implicit confirmation
restart is allowed. Use exclusive started receipts and compare dispatch against an immutable
candidate copy in both arms. Native method gates remain arm-specific as declared above.

- A method drop or budget/round exhaustion yields no final environment and no K16.
- Terminal infrastructure/correctness/accounting failure stops new dispatch, preserves
  in-flight evidence and closes an **incomplete study**. Do not convert it to a method drop.
- Do not substitute tasks, silently restart a partial arm, or replace failed K16 episodes.
  Any repair/restart requires a prospectively documented execution amendment before new calls;
  method tuning requires a new method/protocol version. Preserve all original attempts.
- Run-native bounded client retries and measurement-error handling remain frozen. Charges
  for failed/retried requests remain in physical accounting even if a logical episode refunds.

## 7. Primary and secondary analysis

For task i and arm a, define Y_BL=1 only when the method returns an accepted or kept final
environment and its fresh complete K16 is in B_L. A completed method drop gives Y_BL=0.
An interrupted/invalid search or incomplete K16 is **missing**, never silently 0.

**Primary:** retain the integrated E3 productivity estimand, now compared with paired
contemporaneous data: `R[a] = 1000 * sum_i Y_BL[a,i] / sum_i (M[i] + A[a,i])`, and
`Delta_R = R[B] - R[A]`. M is valid shared measurement episodes; A is all valid adaptation
episodes, including rejected families and partial probes. Use the ratio of totals, not the
average of per-task ratios. Keep dropped-task costs in the denominator. K16, Designer/Judge
calls and offline replay are reported separately and do not enter this episode denominator.

A completed all-30-pair study is required for the confirmatory primary result. If incomplete,
report completion/missingness and descriptive bounds; do not rename complete-case estimates
the primary result. Do not change the denominator to only returned environments.

Prespecified secondary results:

- K16-learnable output coverage out of 30, paired difference `sum_i(Y_BL[B,i]-Y_BL[A,i])/30`,
  absolute counts and the paired win/tie/loss table. Report this alongside the primary.
- Newly measured LOW: final transformed outputs/N_LOW and K16 B_L transformed outputs/N_LOW;
  the same for HIGH. MID: kept outputs and independent K16 band preservation.
- Overall transformed-only B_L coverage out of 30; final output coverage; K16 B_T coverage.
- Search acceptance, final freeze, and confirmation precision among eligible outputs,
  each with its own explicit denominator and missing-K16 count.
- Transformed-only productivity using the same all-task search denominator; LOW/HIGH
  productivity using all search costs within their fresh shared subgroup.
- Baseline, adaptation, confirmation episodes, logical calls and physical USD.
- Per-task outcome pairs and all prespecified fresh LOW/MID/HIGH subgroup results, including
  zeros and failures. No additional historical-outcome subgroup is a primary or secondary
  estimand in this protocol.

Use a paired task bootstrap: 10,000 resamples, seed 20260917, percentile 95% intervals;
resample the same task indices in both arms and recompute rates/productivity denominators.
For conditional LOW/HIGH summaries resample their common fresh subgroup; if n=0 report N/A.
Treat these small-cohort intervals and secondary analyses as descriptive uncertainty; no
post-hoc favorable subset, target-band change or historical-arm causal significance claim.

## 8. Method-specific funnel and refinement evidence

Report task-level coverage and proposal/family-level counts separately. The stages are:

`DESIGN requests -> parsed proposals -> structural/identity-valid -> characterized levels`
`-> required privilege PASS -> strongest solvable -> policy response -> Controller in-band`
`-> exact required final certification / final freeze -> fresh K16 complete -> K16 B_L`.

A stage that does not exist in A is N/A, not zero. Mechanical PASS may be inferred from
validated progression; do not fabricate an explicit receipt that the implementation lacks.
Include malformed proposals in the request/proposal denominator even without a family ID.

Define demonstrated directional leverage from the actual first/strongest probe: LOW
in_band or too_easy; HIGH in_band or too_hard. Gate-valid/solvable alone does not establish
policy leverage. Report provisional solvable families and empirically leveraged families
separately. A Controller ACCEPTED decision is not final freeze: final solvability can fail.

For B, report nominal settings, effective classes including OFF, positive classes,
actual distinct-level probes, partial probes and captured recurrence diagnostics. Optional
read-only application of the frozen characterizer to saved A families may quantify redundant
raw-dose probes; label it post-search offline diagnosis, report coverage failures as N/A,
and never use it to admit, reject or rescore A environments.

Count all typed feedback, including NO_LEVERAGE, OVERPOWERED_BINARY,
INSUFFICIENT_ATTENUATION, INSUFFICIENT_RESOLUTION, CONTROL_EXHAUSTED, ACCEPTED and gate failures.
Separate characterization diagnostics such as NON_MONOTONE_CONTROL_SURFACE from Controller
return reasons. Report **last feedback** separately from **terminal stop** (round cap,
admission stop (A LOW: remaining<16; B LOW/HIGH: remaining<8), partial/unaffordable control
  batch, no levels, final freeze,
infrastructure). Do not infer a budget stop solely from session_exhausted.reason.

For each REFINE_CONTROL chain report parent/child identity hashes, shared mechanism lineage,
feedback trigger, control-class counts before/after, remaining/used episodes, acceptance,
final freeze and K16. Count direct and later-descendant acceptance separately; preserve failed
refinements. Mechanism-summary retention establishes declared lineage, not semantic proof.
A useful→refinement→accepted→K16 B_L chain is mechanism-consistent evidence, not an isolated
causal estimate of refinement.

## 9. Accounting, privacy and publication

Keep shared measurement, A adaptation/design/judge, B adaptation/design/judge, both K16,
local expert/replay work, logical requests and physical API attempts in separate ledgers.
Each arm's deployment-equivalent search denominator includes the **full** common baseline;
actual study physical costs/episodes count that baseline once. If displaying allocated
per-arm USD, allocate shared costs 50/50 and label that view; also report full-baseline
standalone estimates. Never duplicate a paid ledger row to imitate matched spending.

The valid-policy-episode ceiling is 30*(16+2*30+2*16)=3,240 for the physical study. This is
not a bound on token-level API requests, failed attempts, expert work or USD. Unused arm
budget is not transferred. In-flight/unpriced charges are reported separately, not zero.

Recipients remain DeepSeek for authorized Designer/Judge data and OpenRouter/Alibaba for
admitted learner-facing inputs. Shared measurement does not authorize privileged evidence
to the learner. Complete references, candidate source, trajectories, surfaces, raw prompts
and judge prose stay under a new gitignored private run namespace. Public artifacts use
allowlisted enums, numbers and hashes only. No overwrite of historical runs or results.

## 10. Required execution-harness acceptance before paid start

This commit freezes the method and preregistration, not an unimplemented launcher.
Implement the harness separately, without edits to either frozen method, and bind its
commit plus this protocol's SHA256 before paid execution. Offline tests must prove:

1. Shared measurement is collected once, replayed identically, and accounted without
   duplicated physical calls; both native Controller/K16 evidence validators pass.
2. Same task mapping/models/provider pins/caps; exact per-arm attribution and isolated roots.
3. Fixed balanced wave scheduling and concurrency; no next-wave dispatch after terminal error.
4. Independent immutable fresh K16, disjoint IDs, exclusive start/no restart and no feedback.
5. Correct method-budget vs infrastructure classifications, all-30 denominators, missingness,
   Controller-accepted vs final-freeze distinction and complete refinement lineage.
6. Fail-closed source/runtime/protocol checks; private raw journals and safe public projection.

Do not invoke the historical e3_integrated run/build/freeze functions with their old global
paths or rewrite their manifests. Reuse audited primitives through the new experiment layer.
No paid model call is part of preparing or validating this preregistration.
