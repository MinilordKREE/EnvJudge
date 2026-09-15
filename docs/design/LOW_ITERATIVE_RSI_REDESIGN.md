# Iterative LOW redesign: research decision

**Decision, 2026-09-15:** test a bounded, failure-conditioned DESIGN optimizer for a fixed
policy, followed by frozen-family CONTROL. The first experiment must distinguish feedback's
value from extra proposal search. Keep a bounded artifact optimizer as the fallback. Do not
start with population evolution or learner training.

This is a design recommendation, **not evidence that iterative LOW works**. Phase 3.5a weakens
the claim that code reliability alone explains LOW failure: its hand-verified families were
valid on7/7 tasks, had controller-defined endpoint leverage on3/7, and delivered1/7
K16-confirmed learnable environments. The preregistered decision remained
`ASSISTIVE_RULES_ACTUATOR_NOT_SUPPORTED`.

## 1. Current codebase / method reconstruction

### Safety record

Initial commands: `git rev-parse HEAD`, `git branch --show-current`, `git status --short`,
`git worktree list`.

| Worktree | HEAD | Branch | Initial status |
|---|---|---|---|
| `/home/kree/work/EnvJudge` | `f97260589475bf4412f2310b1dfbcc1c34816547` | `main` | ` ? third_party/envharness`, pre-existing |
| `/home/kree/work/EnvJudge-aea-llm` | `01654104c1fbf4e169280ca45bf1e5c91d0c8148` | `aea-llm-vnext` | clean |

No checkout/reset/merge/rebase/clean/stash/pull, production edits, test execution, experiment
rollouts, paid optimizer calls, fresh pools, E6 or E6-SL runs were performed. Documents were
prepared in `/tmp` before copying only these two Markdown files to the research worktree.
The main worktree was not modified. No applicable `AGENTS.md` was found in the inspected
ancestor/research paths. No commit is created by this task.

### Paper abstraction and HIGH

**MEASURE → DESIGN INTERVENTION → CONTROL.** The intervention is an environment change;
the learner and benchmark goal/verifier remain fixed during adaptation. MEASURE estimates a
behavioral regime. MID keeps the task. HIGH searches challenge families; LOW searches support.

`estimate()` uses Beta-posterior regime masses, stopping at confidence.9 or K16; ZERO is a
classification, not a definition requiring literally zero successes. All-failure evidence in
these experiments stopped at 0/10. `evaluate()` uses4 rollouts: 0 means too_hard, 4 too_easy,
otherwise top up to 8; 3–5/8 means in_band. Search acceptance is therefore distinct from both
the intended target interval B_T=[.4,.6] and evaluation's learnable interval B_L=[.2,.8].
[Estimate](../../src/aea/estimate.py#L108), [measurement](../../src/aea/evaluate.py#L52),
[configuration](../../src/aea/config.py#L54).

HIGH's `_harden_llm` supplies actual successes/failure and durations to one LLM call, proposing
≤ 2 harder-with-dose Rules families. `parse_high` checks template/API, axes, names, mechanism
summary and library-copy restrictions. `_try_family` tests d=1 solvability using a successful
policy witness then oracle; **generated O-axis code cannot skip the guard**. d=1 too_easy
means no challenge leverage; in_band accepts; too_hard opens a local bracket, starting.5,
≤ 4 bisections. The shared cap is 30 policy rollouts including estimation. Acceptance writes
the environment; independent K16 belongs to experiment scripts.
[HIGH flow](../../src/aea/controller.py#L745), [family trial](../../src/aea/controller.py#L456).

HIGH is also one-shot. Its strongest relevant pilot, Phase 3.1, accepted2/3 HIGH tasks and
confirmed both in B_L (11/16 and 10/16), neither in B_T. Earlier Phase 3 had0/3 HIGH accepts.
Thus relative HIGH success is promising small-pilot evidence. Our explanation is an inference:
HIGH can perturb an action/observation the learner already demonstrably uses; LOW must make
missing behavior usable without completing the task for the learner. No ablation establishes
that asymmetry as the sole cause.

### Historical method sequence

| Version / stage | What changed and hypothesis | Prospective finding / remaining failure |
|---|---|---|
| v0.2 CHS / discrete Stage | Deterministic midpoint/end cuts of 3 seeded failures, ≤ 6 compiled/deduplicated prefixes; oracle guard and policy probes | Could shorten failed episodes, but a failed trace need not contain useful progress. No semantic design feedback. |
| v0.4 | LOW unchanged. HIGH replaced v0.3 population hard bounds with a soft median warm start after ≥3 frontiers; local bracket preserved | Historical bad cross-task bounds motivated local control. This was not iterative LOW design. |
| llm_v1 | One regime-conditioned LLM; ≤ 2 failure/reference Stage cuts; lazy action-only reference | Phases3/3.1: one unlock among 6 LOW tasks; 0 accepts. Good intervention localization remained uncertain. |
| llm_v1_refalign | Rich reference plus explicit consequential divergence/cause/fix, same one-call Stage selection | Phase 3.2: more unlocks, 0 accepts in refalign arm; diagnosis did not create a useful operating point. |
| Phase 3.3a | Measured reference-depth axis rather than choosing two points | Leverage/ordering supported exploration; most observed transitions were abrupt. |
| llm_v1_stage_control | Removed LOW LLM; exact nonterminal reference defines E_t; integer depth feedback control | Phase 3.3b: 1 confirmed control-arm task; adjacent-depth resolution and budget failures dominated. |
| llm_v1_assistive_rules | One diagnosis/call emits ≤2 assistive W(d), continuous numeric dose but no continuity guarantee | Phase 3.4: invalid/privileged proposals, ineffective mechanisms, noisy acceptance and abrupt dose response. |
| Experiment-only assist_provider | Frozen human family replaces generator; same guard/control/accounting | Phase 3.5a: validity fixed, leverage still scarce; not an automated result or exhaustive upper bound. |

History inspected includes `9b29b26`, `0a77e0f`, `47a0091`, `f63c47b`, `48dc028`,
`423011c`, `d67da43`, `09bc8b0`, `f91bacd`, `23e87aa`, and `0165410`.
[Specs](../spec/README.md), [LLM audit](AEA_LLM_FIRST_AUDIT.md),
[Stage design](AEA_LOW_STAGE_CONTROL.md), [Rules design](AEA_LOW_ASSISTIVE_RULES.md).
Historical specs contain superseded status and O-axis guard wording; live code takes precedence.

### Exact latest LOW call chain

| Step | Source and behavior |
|---|---|
| ZERO dispatch | `Controller._run_task → _estimate → _stage → _stage_assist` in [controller.py](../../src/aea/controller.py#L348) |
| Failed evidence | `seeded_failures`, [stage.py: 78](../../src/aea/stage.py#L78): ≤ 3 original estimate failures with steps, seeded sample |
| Lazy reference | `_lazy_reference`, [controller.py: 806](../../src/aea/controller.py#L806); `ExpertReference`, [designer.py: 123](../../src/aea/designer.py#L123), injected by `reference_provider` in substrate; missing reference ends assistive LOW |
| Serialization | `serialize_low`, `reference_text`, `trajectory_text`, [designer.py: 299](../../src/aea/designer.py#L299): rich reference then clipped failed observations/actions/reasoning; 24k bound. Admissibles are recorded in Reference but not separately rendered by rich-reference formatter |
| Diagnosis + families | `design_low_assist`, [designer.py: 1168](../../src/aea/designer.py#L1168), `ASSIST_CONTRACT`, `DESIGN_ASSIST_TOOL`: one call, ≤ 2 families, direction easier_with_d; LLM does not choose numeric dose |
| Parse and smoke | `parse_assist`, [designer.py: 1109](../../src/aea/designer.py#L1109); `validate_rules_template`, [families.py: 158](../../src/aea/families.py#L158); `identity_at_zero`, [designer.py: 1029](../../src/aea/designer.py#L1029) |
| Privilege | `privilege_check`, [designer.py: 1055](../../src/aea/designer.py#L1055): lexical checks on task-specific reference actions, hidden constants, simulator stepping and success shortcuts |
| Solvability | `_stage_assist` calls `solvable`, [witness.py: 35](../../src/aea/witness.py#L35), at d=1, no by-construction exemption; benchmark expert, uncharged against policy cap |
| Leverage | [controller.py: 1088](../../src/aea/controller.py#L1088): 4→8 endpoint evaluation. Operational leverage means **verdict is not too_hard**, not any observed success |
| Control | `assist_bracket`, [rules_control.py: 46](../../src/aea/rules_control.py#L46): d=1 first; too_easy opens[0, 1]; midpoint; hard raises lo/easy lowers hi; ≤ 4 bisections |
| Accept and records | `_accept_assist`, [controller.py: 1151](../../src/aea/controller.py#L1151); `_record_designer`; `entry_from_candidate`, `TraceWriter` in [io.py](../../src/aea/io.py): knob corpus, full code/dose, probe traces, designer rejections, privileged reference separately |
| Confirmation | `accepted_envs`, `stage_confirm`, [e6_refalign.py: 551](../../scripts/e6_refalign.py#L551), used by e6_assist/e6_oracle: every accepted Stage or Rules environment, 16 fresh episodes, correct reset configuration, never fed back |

**Limitations of existing gates:** smoke identity is not identity over all states; lexical
privilege checking is not complete information-flow verification; failure to certify can mean
expert failure rather than unsolvability. Invalid diagnoses can be dropped without rejecting
families. Neither declared dose direction nor the inward bracket proves global monotonicity.

Oracle injection is `Controller(assist_provider=...)`, called at `_stage_assist:972`;
`scripts/oracle_actuators.provider` validates frozen files, `e6_oracle.apply` injects it and
disables the designer. Corpus source is explicitly oracle. Human construction saw10 original
failures versus the automated designer's3, plus privileged reference information. This tests
seven chosen mechanisms with a fixed controller, not the maximum achievable by all legal Rules.
The oracle arm also changed mechanism choices and human evidence exposure, on reused tasks.
It is not a randomized code-repair ablation and cannot tell us how the exact rejected
Phase3.4 programs would perform after purely mechanical repairs. Its post-freeze measurements
remain useful evidence about the chosen legal actuators.

## 2. Evidence from Phases3–3.5a

Denominators are prospective LOW branch-reaching tasks; referenced subsets are stated
separately. Pools changed across phases, so rows must not be pooled as a longitudinal effect.
K16 below means B_L confirmation unless B_T is stated. Profiling N/A is not zero delivery.

| Phase | LOW intervention | Generation mechanism | Feedback loop | Accepted/search | K16 confirmed | Formal decision | Scientific conclusion |
|---|---|---|---|---|---|---|---|
|3|Discrete Stage|One LLM call; ≤ 2 failure/reference cuts|Fixed-cut guard/probe|0/3|None accepted|NO-GO; functionality PASS; provenance audit failed|1 unlock overshot; 2 dead. Expert recomputation differed; no observed leakage.|
|3.1|Discrete Stage|Same method; API/provenance corrections|Same fixed-cut probes|0/3|0|NO-GO; LOW FAIL|0 unlocks; valid grounded selection still ineffective. HIGH2/3 accepts confirmed.|
|3.2|A direct Stage; B refalign Stage|B rich reference+explicit cause/fix in one call|No design feedback|A 1/2; B 0/2|A 0 (14/16); B 0|NO_EVIDENCE_REFERENCE_ALIGNMENT_HELPS|B unlock2/2 versusA1/2 but overshoots; diagnosis alone did not improve delivery.|
|3.3a|Reference-depth profile|Fixed5 anchors/task; no LLM|24 nonterminal anchors×K8=192, no search|N/A|N/A|STAGE_AXIS_SUPPORTS_CONTROL|Leverage5/6; useful anchor1/6; 4 STEP_LIKE; sparse ordering supports trying control, not controllability.|
|3.3b|A refalign; B depth control|B deterministic verified reference axis|Maximum depth→integer bracket|A 1/8; B 1/8; each1/6 referenced|A 0; B 1/8, also B_T (78: 8/16)|STAGE_CONTROL_NOT_SUPPORTED|Maximum assistance easy6/6; 3 resolution gaps, 2 budgets; no search-accept gain.|
|3.4|A Stage control; B assistive Rules|B one diagnosis/call, ≤ 2 W(d)|Static/guard/endpoint→dose; no repair|A 1/8; B 1/8; each1/7 referenced|A 0 (3/16); B 0 (13/16)|RULE_GENERATION_FAILURE|B upstream failure 5/7; validity, mechanism leverage and calibration all fail.|
|3.5a|Oracle assistive Rules|1 frozen human family/task, provider only|Same endpoint/control; no revisions|O 1/7|O 1/7 (99: 6/16); 0 B_T|ASSISTIVE_RULES_ACTUATOR_NOT_SUPPORTED|7/7 valid, 3/7 endpoint leverage; 2 of 3 leveraged families unresolved, 1 confirmed.|

### Preregistration and result trail

| Phase | Preregistration | Final report | Underlying evidence checked |
|---|---|---|---|
|3|[PREREG_SMOKE](../../experiments/alfworld_e6/PREREG_SMOKE.md)|[smoke](../../experiments/alfworld_e6/results/e6_smoke.md)|[data](../../experiments/alfworld_e6/results/e6_smoke_data.json), events/gates/empty confirm list|
|3.1|[PREREG_SMOKE2](../../experiments/alfworld_e6/PREREG_SMOKE2.md)|[smoke2](../../experiments/alfworld_e6/results/e6_smoke2.md)|[K16](../../experiments/alfworld_e6/results/e6_smoke2/confirm_summary.json), final data|
|3.2|[PREREG_LOW_REFALIGN](../../experiments/alfworld_e6/PREREG_LOW_REFALIGN.md)|[refalign](../../experiments/alfworld_e6/results/e6_low_refalign.md)|[data](../../experiments/alfworld_e6/results/e6_low_refalign_data.json), [K16](../../experiments/alfworld_e6/results/e6_low_refalign/confirm/confirm_summary.json)|
|3.3a|[PREREG_STAGE_PROFILE](../../experiments/alfworld_e6/PREREG_STAGE_PROFILE.md)|[profile](../../experiments/alfworld_e6/results/stage_profile.md)|[profile records](../../experiments/alfworld_e6/results/stage_profile/profile.jsonl), stages.jsonl|
|3.3b|[PREREG_LOW_STAGE_CONTROL](../../experiments/alfworld_e6/PREREG_LOW_STAGE_CONTROL.md)|[stage control](../../experiments/alfworld_e6/results/e6_low_stage_control.md)|[data](../../experiments/alfworld_e6/results/e6_low_stage_control_data.json), [K16](../../experiments/alfworld_e6/results/e6_low_stage_control/confirm/confirm_summary.json)|
|3.4|[PREREG_LOW_ASSISTIVE_RULES](../../experiments/alfworld_e6/PREREG_LOW_ASSISTIVE_RULES.md)|[assistive Rules](../../experiments/alfworld_e6/results/e6_low_assistive_rules.md)|[B events](../../experiments/alfworld_e6/results/e6_low_assistive_rules/B/events.jsonl), [data](../../experiments/alfworld_e6/results/e6_low_assistive_rules_data.json), [K16](../../experiments/alfworld_e6/results/e6_low_assistive_rules/confirm/confirm_summary.json)|
|3.5a|[PREREG_LOW_ORACLE_ACTUATOR](../../experiments/alfworld_e6/PREREG_LOW_ORACLE_ACTUATOR.md)|[oracle ceiling](../../experiments/alfworld_e6/results/e6_low_oracle_actuator.md)|[data](../../experiments/alfworld_e6/results/e6_low_oracle_actuator_data.json), [K16](../../experiments/alfworld_e6/results/e6_low_oracle_actuator/confirm/confirm_summary.json), frozen registry/validation|

The initial CHS/v0.2 and v0.4 LOW paths are historical controls, not the manipulated variants
in these phase comparisons. Their unchanged LOW behavior is established from code/spec/git
history; there is no separate Phase 3–3.5a prereg conclusion for a v0.4 LOW redesign.

### Artifact corrections and inference limits

Use final reports/JSON/events/confirm summaries; `pre_correction` files document corrections,
not alternate outcomes. Phase 3.4's seven valid families are **structural survivors**: only 5
were actually guarded, all 5 passed; only 2/5 endpoint-tested families cleared the controller's
leverage gate. Its descriptive any-success count is 3/7 tasks because97 had1/8, which the
controller classified too_hard. Keep both definitions labeled. The final narrative's claim
that all 7 passed the guard overstates what was executed.

Phase 3.5a's task 99 confirmation is 6/16 after fixing an O 2/alias join in the table builder;
the formal decision does not change. Phase 3.4's accepted Rules task 92 was confirmed after
correcting the Stage-only confirmation collector and using the default Rules reset.

Observed adjacent0/4 versus 4/4 responses do not prove the true probabilities jump or that
no in-band point exists. Zero reported order violations under inward bracketing is weak
evidence: the controller does not systematically sample pairs capable of revealing global
reversals. Oracle event thinning also gives monotone **counts on a fixed event stream**, not
nested support sets: with `floor(k*d)>floor((k-1)*d)`, event k=2 is included at.5 but excluded
at.75. Different doses change later policy trajectories as well. This limits the dose
interpretation; no code is changed here.

## 3. Why the one-shot assumption may be too strong

The first call must simultaneously diagnose the bottleneck, choose useful support, write
API-correct code, avoid privileged constants, preserve task/identity at 0, obey assistance
direction, produce strong endpoint leverage and supply a family with a discoverable useful
intermediate response. It need not predict d*, but it must invent a family containing d*.

These burdens are conjunctive. Static failures get no repair; no-leverage failures get no
new diagnosis from their executions; calibration failure gets no revised parameterization.
Other artifact optimizers can distribute these decisions across feedback rounds. That makes
one-shot LOW unusually demanding as an engineering contract, **not scientifically disproved**.
The oracle result says iterative validity repair alone is unlikely to suffice.

## 4. Field-method audit

The companion [field audit](LOW_ITERATIVE_FIELD_AUDIT.md) contains primary-source loop records
for all 18 required starting papers plus mechanism-relevant search additions. It separates
implemented behavior, proposed outer loops and unreported details. Key caution: evocative
paper names do not establish a demonstrated recursive learning cycle.

## 5. Mechanism matrix

See the [two-panel matrix](LOW_ITERATIVE_FIELD_AUDIT.md#5-methodmechanism-matrix): optimization
object, representation, feedback, verifier, performance, candidate/best memory, repair,
gating/rollback, population, budget and outer loop. AEA has substantial audit storage but no
designer feedback state. Our transfer priorities are typed feedback, candidate identity,
an incumbent and a hard budget; a population and learned optimizer are optional later ideas.

## 6. What relevant systems do after failed proposals

The field audit distinguishes quality-gate repair, performance rejection retaining a parent,
strictly improving artifact edits, neutral moves with a separate best checkpoint, and
population stepping stones. These are different algorithms. The review supports testing
failure-specific update rules; it does not support an undifferentiated “refine” call for
every failure. See the individual primary-linked cards for actual thresholds and budgets.

## 7. What AEA currently does differently

| Question | Verified current behavior |
|---|---|
| Where does designer have feedback? | Original estimate trajectories plus verified reference, once |
| Does designer see rejected code/guard/policy/dose results? | No; these are written for audit only |
| What persists within control? | Fixed family, per-dose candidates, measured bracket/history, remaining task budget |
| Can invalid code be repaired? | No; only another family already in the initial response can be tried |
| Can no-leverage support be rewritten? | No |
| Can leveraged but uncalibratable support be redesigned? | No; first leveraged family ends the task on bracket failure, even with an unused second proposal |
| Do rejected candidates inform later tasks/resume? | No semantic memory. Completed drops are skipped; infrastructure rerun is not feedback repair |
| Is accepted state rolled back? | No optimizer incumbent; acceptance writes corpus and stops |
| Does K16 guide search? | No, and it should remain independent |

The explicit no-repair contract is in [controller.py: 959](../../src/aea/controller.py#L959);
the first leveraged family's terminating behavior is at
[controller.py: 1131](../../src/aea/controller.py#L1131), covered by the read-only inspection of
[test_assistive_rules.py](../../tests/unit/test_assistive_rules.py).

## 8. Candidate iterative architectures

### Common contract for all candidates

Keep task/goal/verifier, policy checkpoint and sampling, observation privileges and Rules API
fixed. All code versions get new identities and validation. Optimizer never edits accounting,
acceptance bands or evaluators. Hard invariants precede behavioral selection. Record all
attempts, costs, parent hashes and rejection causes. Stop on acceptance, infrastructure
inconclusiveness, exhausted call/candidate/rollout caps, or explicit abandonment. Independent
K16 is never optimization feedback. Numeric caps below are **proposed**, not field defaults.

### A. Typed revision of complete environment families

**Idea:** an EnvRigger-like serial loop can change mechanism and dose family after each result.
State: current source, original evidence, recent trajectories, failures, one best feasible
snapshot. LLM sees code/diff, typed evaluator result and budget; may rewrite the whole Rules
family, but not the common contract. Syntax errors allow one local code revision; privilege
or no leverage permits mechanism replacement; poor scaling allows full redesign. Every version
is structurally/semantically guarded then measured; rollback retains the best validated state.

```text
propose → validate → measure endpoint/interior → typed feedback → revise or replace
                                               ↘ in_band: freeze and return
```

Bound: ≤ 4 LLM calls/versions, ≤ 3 mechanisms; cap 60 for efficacy, cap 30 as a matched feasibility condition.
Advantages: directly exposes all observed failures to the designer. Risk: changes support and
scaling together, so progress/credit assignment can drift. Budget may be consumed by validation
of repeated rewrites. Reuses validators/evaluate/corpus; new serial optimizer and feedback
serializer. Estimated500–800 production lines plus tests/driver work. Paper complexity: one
iterative DESIGN process, but weaker separation from EnvRigger. Distinction from current AEA:
post-proposal evidence changes source. Distinction from EnvHarness: explicit Rules/dose contract
and simulator gates. Minimal test: versus feedback-free proposals with identical caps.

### B. Bounded artifact optimizer

**Idea:** treat executable Rules as the artifact; optimize localized patches to a valid seed.
State: incumbent, immutable versions, bounded rejected-patch buffer, measured stage reached,
best feasible candidate. LLM sees failures/successes, incumbent source and exact gate outcomes;
may edit one declared hook or dose mapping per attempt. Task/verifier remain fixed. Allow
one initial validity repair; no mechanism replacement after seed selection. All patches
are revalidated. Hard-gate regressions roll back; operational gate progress commits. Ties
stay in the rejection buffer; do not maximize raw success rate.

```text
valid seed → propose bounded patch → validate/evaluate → commit gate progress or retain seed
```

Bound: seed+≤ 3 patches, same30/60 rollout caps. Inspiration: SkillOpt's artifact discipline;
we do not assume code-locality equals behavior-locality or copy its scalar objective. The
no-progress0/4 plateau can trap this optimizer even when another mechanism would work. New
patch-contract/application code adds risk; existing loader/guard/control reused. Estimated
700–1,000 production lines plus tests. Paper complexity: edit operator and incumbent ordering.
Versus EnvHarness: constrained local edits; versus current AEA: persistent evaluated artifact.
Minimal test: same seed/calls/budget as full-family revision, compare valid-to-leverage and
confirmed delivery. This is the **runner-up**, especially if mechanisms often work but need
localized realization or parameter changes.

### C. Small portfolio search

**Idea:** explore different support mechanisms before refining one. State: ≤ 3 mechanism
lineages, parent code, structural outcomes, endpoint evidence and a champion. LLM sees
parent-specific failures and other mechanism summaries; may replace or mutate a selected
parent. Compile filters are cheap; invalid children rejected, functional nonwinning parents
retained for diversity. Candidate selection uses hard gates then operational viability,
not oracle selection on future confirmations. Parent snapshots give rollback.

```text
3 mechanisms → static filters → limited endpoint probes → select one → ≤1 mutation → CONTROL
```

Bound: ≤ 4 calls/versions; ≤ 3 live parents; same cap 30/60. At30, three endpoint probes can
consume almost all available adaptation work. Population diversity does not solve calibration.
Inspired by program-evolution archives, not a claim that HELIX proved iterative population
repair. New allocation/selection/lineage machinery, existing Rules/evaluation reused;
estimated900–1,400 production lines plus tests. Paper complexity highest among fixed-policy
options. Versus EnvHarness/current AEA: explicit competing lineages. Main hypothesis:
mechanism diversity beats serial diagnosis. Minimal test: portfolio versus independent
sequential search and D under matched caps; defer until cheaper methods establish signal.

### D. Staged DESIGN, then frozen CONTROL — recommended

**Idea:** first search for support with operational endpoint leverage; freeze its semantics;
let the empirical controller choose assistance amount. State: original evidence, bounded
attempt log, current candidate, one highest-gate incumbent, current code/dose hashes, budget.
LLM sees only the evidence needed for its typed operation: code repair, mechanism replacement,
or parameterization repair. It may replace a no-leverage mechanism; it may not silently change
a frozen family during control. On an observed calibration failure, allow **one explicit
unfreeze/reparameterize/revalidate cycle** only when reserved budget permits.

```text
DESIGN: propose → structure → solvability → endpoint → revise/replace if needed
CONTROL: freeze viable family → dose search → accept
         failed calibration → at most one parameterization redesign, if budgeted
```

Bound: ≤ 4 LLM calls total including repairs; ≤ 3 distinct mechanisms; ≤ 1 parameterization
redesign; cap 60 primary. A separate matched cap 30 condition tests historical-budget
feasibility. No automatic grant of extra budget after failure. Reuse all core evidence,
Rules, guard, measurement and bracket machinery. New `LowEnvironmentOptimizer`, typed
feedback/state records and a small controller adapter; estimated 450–750 production lines
plus 300–600 test/driver lines. These are planning estimates, not measured implementation size.

Inspiration: external artifact optimization plus environment-refinement feedback, adapted to
AEA's semantics/control distinction. Versus EnvHarness: LLM does not choose numeric operating
points or accept itself; versus current AEA: DESIGN receives consequences. Main hypothesis:
typed evidence makes later proposals more useful than equal-budget fresh guesses. Main risk:
endpoint leverage stays scarce, or freezing succeeds but dose calibration still fails.
Minimal test: D versus feedback-free sequential proposals; details in §19.

### E. Two-timescale learner–environment co-evolution

**Idea:** use D as a fixed-policy inner optimizer, then train the learner on its accepted
environments and remeasure with the changed learner. State additionally includes policy
checkpoints, environment versions, training corpus and held-out base-task evaluations.
The inner LLM sees current-policy failures and permitted references, not held-out answers.
Outer training changes policy weights or persistent skills; inner invariants remain fixed.
Reject/roll back outer learner updates on independent regression checks; retire or reoptimize
environments that became trivial.

```text
π_k → bounded ImproveEnv → E*_k → verified experience → Learn → π_(k+1) → remeasure
```

Conceptually aligned with adaptive curricula and demonstrated co-evolution mechanisms where
present; do not treat every RSI paper as having completed this cycle. For a future pilot,
cap 2 outer updates with a separately preregistered training budget; no training now. Adds a
real outer-loop primitive: roughly1,000+ orchestration/evaluation lines beyond D, dominated
by training integration and provenance. Main risk: assisted success teaches shortcuts or
fails to transfer. Minimal future test: 2 rounds versus fixed environments under matched
training data/tokens and held-out base tasks. Distinct from current AEA by policy updates;
not uniquely distinct from EnvHarness at this broad abstraction. **Not the next experiment.**

## 9. Ranking

Qualitative judgments, not probabilities estimated from experiments. H/M/L mean favorable,
intermediate or unfavorable on the named criterion; budget favors low overhead.

| Rank | Architecture | Fit to failures | Chance of useful LOW | Scientific clarity | Reuse | Simplicity | Distinction | Budget | RSI extension | Falsifiability |
|---|---|---|---|---|---|---|---|---|---|---|
|1|D staged design/control|H|M–H|H|H|H|H|H|H|H|
|2|B bounded artifact|M–H|M|H|H|M|H|M|H|H|
|3|A full revision|H|M–H|M|H|H|L|M|H|H|
|4|C portfolio|M–H|M|M|M|L|M|L|H|M|
|Deferred|E co-evolution|Does not isolate current bottleneck|Unknown|L now|M|L|L broadly|L|H|L now|

D ranks first because it can replace a mistaken mechanism without asking the LLM to control
dose, and its success is directly falsifiable against simple search. B ranks second because
it preserves useful behavior, but its seed dependence is poorly matched to the many no-leverage
tasks. A remains an essential broad-refinement comparator, even though it is not the runner-up
implementation choice. If D's design freeze blocks recovery and A wins reliably, abandon the
freeze preference rather than preserving three primitives for appearance.

## 10. Recommended architecture: objectives and information

### Staged objective, not a complicated reward

1. **Hard admissibility:** valid schema/API, task preservation, identity at 0, permitted
   information/action surface. No performance benefit compensates for a violation.
2. **Certification:** expert/witness can solve the candidate; inconclusive infrastructure is
   separate from a tested candidate failure.
3. **Operational endpoint viability:** current4→8 verdict at 1 is in_band or too_easy.
   Record raw s/n separately.0/4 is not a proof of zero probability; 1/8 is weak behavioral
   signal but does not meet the current gate.
4. **Useful operating point:** freeze family and seek search acceptance. A stronger endpoint
   is not automatically a better calibrated family.

Maintain a lexicographic **gate-stage** incumbent, not a scalar mixing correctness, success
and simplicity. One incumbent suffices because gates are nested; ties retain the earlier
version. Archive all immutable records for audit, but do not create three active populations
named best-valid/best-leverage/best-calibration. A rejected child may inform the next proposal
without replacing the incumbent. In-band ends search; no optimization of its numerical score.

### Minimum feedback packet

`task/policy/config IDs; candidate and parent hashes; requested operation; error class;
exact exception or guard status; (d, s, n, verdict); representative blocked/no-effect/failure
trajectory; one success if available; current source/diff; incumbent gate stage; recent
rejection summaries; remaining call/rollout budget.`

Retain the verified reference on the designer side for semantic comparison. Original action
string mismatch is not automatically a causal error because ALFWorld allows different valid
orders. Diagnosis remains a hypothesis checked by actual learner behavior.

Compile-only feedback suffices for purely mechanical problems; scores alone do not explain
an ignored reminder. One compact trajectory plus counts is the minimum behavioral packet.
Use exact trace IDs/full audit retention so clipping is visible. Do not expose all historical
raw traces by default. Calibration sees the entire measured dose history. Confirmation seeds,
results and held-out task answers never enter a packet.

### Repair versus replace

| Failure | Action | Preserve / abandon |
|---|---|---|
| JSON envelope/name/placeholder formatting with unambiguous meaning | Deterministic normalization; log changed bytes, revalidate | Preserve semantics; counts as a version |
| Undefined `DOSE`, wrong constructor or API | One bounded LLM code repair; compiler output alone does not justify guessing semantics | Preserve intended mechanism; consumes a call |
| Privileged constant / reference action / task shortcut | Reject artifact; ask semantic replacement under same privilege contract | Never “repair” by hiding or obfuscating the forbidden constant |
| Guard indicates broken task under valid runtime | Revise support or replace; new full gates | Preserve original task, not harmful mechanism |
| Expert timeout/unavailability/infra error | Mark inconclusive; bounded infrastructure handling, separate ledger | Do not call it no-leverage or train designer on false unsolvability |
| d=1 too_hard | Return count and trajectory; replace support mechanism unless a concrete localized implementation defect is visible | Keep audit record; no dose search below1 by default |
| d=1 too_easy | Freeze mechanism, run controller | Preserve support; avoid reflexively maximizing more success |
| Narrow hard/easy bracket or order problem | One explicit parameterization redesign if affordable; otherwise unresolved | Preserve highest-gate incumbent; invalidate old measurements for changed code |
| New patch regresses to earlier gate | Roll back incumbent; retain rejected feedback | A new alternative can still be proposed within cap |
| In-band search result | Freeze final code+dose; final-dose guard, write corpus | Stop designer; independent confirmation later |
| No budget / calls / useful proposal | Return typed unresolved outcome | No automatic cap extension |

Proposed final-dose guard is an additional uncharged simulator check on the actually selected
environment. Apply it to all future comparison arms; retain the historical baseline separately.
It is a bounded check, not proof of solvability over the whole dose continuum.

## 11. Concrete state machine

`b` is remaining policy rollouts, `c` remaining optimizer calls. Typical ZERO begins with
b=50 under proposed total cap 60, or b=20 under historical cap 30. Every code-changing output
consumes a version; calls ≤4, mechanisms ≤3,
parameterization redesign ≤1. Guard runs have separate wall-time/attempt caps.

| State / transition | Input → output | Feedback destination | Cost | Stop condition |
|---|---|---|---|---|
|S0 MEASURE/EVIDENCE → S1|Estimate/failures/reference → fixed evidence packet|Designer|Actual estimate n charged; reference logged separately|Not ZERO dispatches normal method; no usable evidence/reference unresolved|
|S1 PROPOSE → S2|Evidence+incumbent+typed history → one candidate/version|Audit|1 optimizer call, 0 policy|c=0, mechanism/version cap, duplicate-only output → unresolved|
|S2 STRUCTURE → S3 or S1|Code → validation/identity/privilege report|Mechanical repair or semantic replacement|0 policy; deterministic work bounded|Repeated same failed hash rejected; no repair calls remain → unresolved|
|S3 CERTIFY → S4 or S1|Valid family at 1 → certified/inconclusive/failed|Designer only on actual candidate defect|Oracle ≤3 attempts × 50 steps; separate cost|Infrastructure failure unresolved/inconclusive; no feasible redesign budget|
|S4 ENDPOINT → S5/S6/S1|Certified W(1) →4→8 measurement|Controller or designer|4 or 8 policy|Before entry require b ≥16: worst 8 endpoint plus 8 calibration reserve; otherwise budget stop|
|S5 VIABLE SNAPSHOT → S6|Endpoint too_easy → immutable family+bracket seed|Controller|0 additional policy|No implicit claim of confirmed viability; evidence stage only|
|S6 CONTROL → S7/S8|Frozen family/history →in_band or unresolved bracket|Controller; typed failure available for S8|4 or 8 per dose, ≤ 4 bisections, remaining shared cap|Budget stops whole attempt; no branch silently resets cap|
|S7 FINALIZE → DONE|In-band candidate → final-dose guard, frozen corpus record|Audit/evaluation|0 new policy; simulator guard|Guard fails/inconclusive → unresolved|
|S8 REPARAMETERIZE → S2|Calibration failure+incumbent → revised dose family|Designer|1 call; new endpoint/control costs required|Allowed once only if c>0 and b ≥16; otherwise unresolved|
|DONE → K16 report|Frozen accepted candidate →fresh 16 episodes|Evaluator only|16 evaluation episodes outside search cap|Report B_L/B_T and uncertainty; never returns to S1|

Endpoint in_band goes directly from S4 to S7. Endpoint too_hard goes to S1 if remaining budget
permits another endpoint trial. Static repair may consume calls without policy work. The
16-rollout reservation is conservative and identical for the matched sequential comparator;
it intentionally permits fewer candidates under cap 30: at most two endpoint-tested mechanisms,
and only one when the first too-hard endpoint costs 8. Three is a representation cap, not a
promise of three affordable trials. The 8-rollout reserve guarantees only one full calibration
measurement. At cap 60 more semantic iterations and occasional parameterization rescue become
feasible. A cap-limited failure cannot establish that a family lacks an operating point.
The parameterization rescue is a single final proposal: if its structural, solvability,
endpoint or calibration gate fails, restore the incumbent snapshot for the audit and end
unresolved. It does not open another mechanism-replacement loop.

## 12. Pseudocode

High-level design only; this is not an implementation patch.

```python
def iterative_low(evidence, policy, caps):
    state = OptimizerState(evidence, caps, incumbent=None)
    pending = "propose_mechanism"
    while state.can_call() and state.can_evaluate_with_reserve(16):
        candidate = designer(state.feedback(pending))  # one artifact, charged call
        duplicate = state.seen_identical(candidate)
        state.record_version(candidate)
        if duplicate:
            if state.in_final_rescue:
                return rollback_and_unresolved("duplicate", state)
            state.record_rejection("duplicate")
            pending = "replace"
            continue
        structural = validate_all(candidate)
        if not structural.ok:
            if state.in_final_rescue:
                return rollback_and_unresolved(structural, state)
            pending = classify_repair_or_replace(structural)
            state.remember(structural)
            continue
        guard = certify(candidate.at(1))
        if guard.inconclusive:
            return unresolved("certification_inconclusive", state)
        if not guard.ok:
            if state.in_final_rescue:
                return rollback_and_unresolved(guard, state)
            state.remember(guard)
            pending = "revise_mechanism"
            continue
        endpoint = measure_4_then_8(candidate.at(1), state.policy_budget)
        state.remember(candidate, endpoint)
        state.advance_incumbent_if_gate_improves(candidate, endpoint)
        if endpoint.verdict == "too_hard":
            if state.in_final_rescue:
                return rollback_and_unresolved(endpoint, state)
            pending = "replace_mechanism"
            continue
        frozen = freeze(candidate)
        result = (
            endpoint
            if endpoint.in_band
            else assist_control(frozen, endpoint, state.policy_budget, max_bisections=4)
        )
        state.remember(result)
        if result.in_band:
            final = frozen.at(result.dose)
            if certify(final).ok:
                return accepted(final, state)  # K16 happens elsewhere
            return unresolved("final_dose_uncertified", state)
        if state.may_reparameterize_once(reserve=16):
            state.mark_reparameterization_used()
            state.in_final_rescue = True
            pending = "preserve_support_revise_parameterization"
            continue  # all gates rerun; new hash
        return unresolved(result.reason, state)
    return unresolved("bounded_search_exhausted", state)
```

The final-dose-guard failure branch deliberately ends in this first design rather than
adding another poorly specified recovery loop. Duplicate detection compares against prior versions before recording the new attempt;
trial state is recorded before advancing the incumbent.

Runner-up B:

```python
incumbent = obtain_valid_seed_under_same_caps()
for attempt in bounded_patch_attempts(3):
    patch = optimizer(incumbent, recent_rejections, typed_rollout_evidence)
    child = apply_one_declared_hook_or_mapping_edit(incumbent, patch)
    result = gated_evaluate_and_calibrate(child, shared_budget)
    if result.accepted:
        return freeze(child, result.dose)
    if result.gate_stage > incumbent.gate_stage:
        incumbent = snapshot(child, result)
    else:
        remember_rejection(patch, result)  # no hidden replacement of incumbent
return unresolved(incumbent)
```

## 13. Codebase attachment plan

| Reuse | Attachment / change needed later |
|---|---|
| LOW evidence / reference | `serialize_low`, `Reference`, `ExpertReference`; add candidate-result packet serializer preserving reference redaction |
| Rules representation / checks | `AssistFamily`, `parse_assist`, `validate_rules_template`, `identity_at_zero`, `privilege_check`; return structured diagnostics without changing privilege policy |
| Certification | `solvable`; expose timeout/infrastructure vs candidate failure clearly; optionally selected-dose check common to arms |
| Episodes / budget | `evaluate`, `Controller._rollouts`, `AeaSubstrate.rollouts`, `runner.episode_spec/dispatch`; one task ledger, no extra pool |
| Dose control | `assist_bracket`; keep frozen semantics and actual history; new code version invalidates bracket/cache |
| Accepted artifacts | `_accept_assist`, corpus/traces/events/accounting; add parent/candidate hashes and operation/rejection fields |
| Confirmation | Shared experiment collector supporting Stage and Rules; keep default Rules reset and source labels |
| Oracle provenance | Existing provider remains ceiling-only; never use task-specific human families as hidden automated fallback |

The new module should be `src/aea/low_optimizer.py` with a compact `LowEnvironmentOptimizer`
and state/result records. Controller dispatches once to this object and retains common
rollout/acceptance services. Keep typed feedback serialization in the designer boundary.
Do not scatter special cases through `_stage_assist`. No new file/module is implemented now.

Required future tests would cover budget reservation, call/version caps, repair classification,
no-leverage replacement, frozen-family control, stale-cache invalidation, rollback and
confirmation isolation. These are meaningful state-machine checks, not tests of prose.

## 14. Expected complexity

D turns DESIGN into a stateful optimizer; it does not require a new paper primitive.
MEASURE and CONTROL already process feedback. The real addition is routing candidate failures
back to DESIGN while preserving a frozen control phase. One parameterization escape makes
the abstraction less rigid without an unbounded nested loop. Report it explicitly.

B adds bounded-edit semantics; C adds population selection; E adds learner training and
cross-round validation. Those are real additional primitives. Start with D because its
extra machinery corresponds directly to observed failure types. If its reserve or state
machine becomes more complex than full revision without buying reliability, prefer A.

## 15. Matched-budget evaluation requirements

Match **opportunities and actual spend**, not only maximum episode count:

- Same frozen policy/settings, prospective ZERO evidence, reference instance, task order,
  allowed Rules surface, diagnosis visibility, guard and final selector across arms.
- Primary cap 60 includes actual regime-estimation episodes; typical 0/10 leaves 50. A separately
  matched cap 30 condition leaves 20 and tests resource feasibility, not the full efficacy of
  repeated behavioral revision. Replayed
  common evidence is charged to every arm for opportunity accounting, with shared actual
  API cost reported once. No free policy probes are hidden as validation.
-≤ 4 optimizer calls including repair; ≤ 4 code versions; ≤ 3 mechanism proposals. Deterministic
  normalization is logged without an extra call. Report optimizer input/output tokens,
  retries, dollar cost, policy steps/tokens, oracle attempts/time and wall-clock time.
- Same8-rollout calibration reserve and 16-rollout endpoint-entry rule for the causal
  sequential comparison. Native frozen AEA keeps its historical behavior and is separately
  labeled; it is not the fully matched causal comparator.
- Cache only exact candidate+dose+policy+task+environment-config identities. Reuse past
  observations as history, not new independent trials. A changed version receives new
  policy evidence even if the prose mechanism sounds unchanged. Deduplicate byte-identical
  candidates; report skips. Cached historical evidence cannot count twice toward sample n.
- Separate search randomness from withheld confirmation episode indices/seeds. Use the same
  confirmation schedule across arms when feasible; report stochastic backend limitations.
- At most one frozen final candidate/task/arm reaches K16. Count all prospective ZERO tasks
  in the primary denominator; reference-missing tasks remain failures of delivery, reported
  separately. Also show the conditional referenced denominator. No favorable task replacement.

K16 membership is a noisy descriptive reproducibility check, not a confidence guarantee that
the true success probability lies in B_L. Report counts and binomial uncertainty. Fresh
episodes on the same task do not establish generalization; unseen tasks and later base-task
learning evaluation answer different questions. Do not optimize for easy1.0 success or
use an oracle union over candidates as delivered LOW performance.

## 16. Relationship to EnvHarness

AEA already uses the wrapper substrate. Program refinement is shared intellectual territory.
The testable distinction is **LLM chooses support semantics; empirical controller chooses
the operating point inside a frozen family**, with explicit task budget and independent
acceptance. That is narrower than claiming a new general environment-evolution paradigm.
The [EnvHarness loop record](LOW_ITERATIVE_FIELD_AUDIT.md#eh--envharness--envrigger-pe)
documents native settings and what a matched adaptation changes.

A Rules-only unrestricted-revision baseline tests whether that separation helps. If it
outperforms D under equal resources and evidence, the family-freeze restriction has failed
its empirical justification. Do not dismiss it merely because it resembles EnvHarness.

## 17. Relationship to HarnessEvolve

Earlier AEA borrowed reference-based diagnosis. The next design can borrow candidate-state
discipline and gate feedback without copying a four-agent harness optimizer. Environment
success is judged by the existing simulator; reference-only information remains designer-side.
Batch regression protection becomes more relevant when families transfer across tasks.
See the [primary-linked record](LOW_ITERATIVE_FIELD_AUDIT.md#he--harnessevolve-pe).

One correction to the historical local audit: the current primary paper rejects leakage
scores above the threshold; it does not require the leakage score to exceed it to pass.
Also, its experimental zero improvement margin admits performance ties. Those distinctions
matter when borrowing a gate rather than a verbal summary.

## 18. Relationship to RSI / co-evolution

For now call the method **iterative policy-conditioned environment optimization**. A frozen
external designer improving Rules is not an agent improving its own improvement process.
Rules do not rewrite themselves; the optimizer rewrites them using external evidence.

A later system can reasonably be called **agent–environment co-evolution** if both persist
and causally affect subsequent rounds:

\[
E^*_{k}=\operatorname{ImproveEnv}(E_k,\pi_k; B_{env}),\qquad
\pi_{k+1}=\operatorname{Learn}(\pi_k, E^*_k; B_{learn}).
\]

Then remeasure π_(k+1), regenerate/adapt support, and retain policy/environment provenance.
Training the policy while repeatedly regenerating unrelated environments without using
current capability feedback is not the same claim. Environment adaptation and a slow optimizer
meta-skill update are also different meanings of “two timescales.”

Stronger **recursive self-improvement** needs evidence that improved components strengthen
subsequent improvement itself—for example an improved designer/optimizer, or the same updated
agent performing later design—not just repeated fixed-designer loops. The field audit compares
HELIX's proposed closure, MetaSkill's optimizer-side persistence, SEAL's implemented learning
interface, and GenEnv/Agent-World's curriculum feedback. These should not be conflated.

Prevent self-confirming degradation with a frozen base verifier, independent confirmation,
held-out original-task evaluations, immutable snapshots, explicit policy-version remeasurement,
and rollback of regressing learner updates. AEA has not demonstrated this outer loop; no RSI
performance claim or implementation follows from this document.

## 19. Minimal next experiment

**First prospective question:** does typed post-proposal feedback improve confirmed delivery
over the same amount of independent search? Do not retest only the seven now-familiar oracle
tasks as if they were unseen.

Before any runs, preregister a deterministic unused-ID eligibility audit, fixed task order,
screening limit, policies/designer versions, evidence freezing, caps and analysis. Target 20
prospective ZERO tasks, screening at most 100 unused tasks; if fewer are obtained, report the
shortfall and smaller paired sample. Screening uses up to 16 episodes/task and is separately
reported; accepted ZERO estimates count toward each arm's 60 budget. Do not exclude reference
failures from the primary delivery denominator. Freeze the implementation before outcomes.

The recommended primary condition is total cap 60 for every D/I/R task. This deliberate
increase over historical 30 buys room for the mechanism revision being tested. Run a separate
matched 30 condition only if its resource question is important and funded in advance; a
truncated 60 trajectory is not a faithful counterfactual 30 run when budget affects proposals.

### Core comparison and essential controls

| Arm | Purpose | Design feedback |
|---|---|---|
|D|Recommended typed DESIGN→CONTROL|Exact rejection and current candidate behavior, bounded memory|
|I|Matched independent sequential family search|Original evidence only on each call; same evaluator, reserve, calls and candidate limits|
|R|Rules-only EnvHarness-inspired full revision|May rewrite family or propose a dose after feedback; common evaluator and budget|
|H, historical reference|Frozen one-shot automated LOW|Original one-call ≤2 contract; report budget difference explicitly|

The smallest causal pilot is D versus I. Include R for any claim about the value of separated
DESIGN/CONTROL; H anchors history but cannot isolate feedback. Prefer all three D/I/R in the
same preregistered run if affordable; run H only as a clearly labeled resource-unmatched
reference. A mechanical-repair-only arm is a follow-up if validity dominates; adding it now
would broaden a small pilot without resolving mechanism search.

Specify R before implementation: its first family is tested at 1. After each result its next
LLM call chooses either a new dose of that same family or a rewritten family; every rewrite
restarts full validation and d=1 testing. Each dose-choice call also counts toward the four-call
cap. It has no automatic bisection. Measurements and final acceptance use the common4→8
evaluator; a new family requires the same 16-rollout reserve, and a dose-only probe requires 8
remaining. This tests whether empirical CONTROL is a more useful allocation than LLM-directed
scaling. It is an explicitly constrained EnvHarness-inspired comparator, not a reproduction
of native EnvRigger. D versus I remains the clean comparison isolating proposal feedback.

For 20 ZERO tasks and D/I/R, adaptation ceiling is 20 × 3 × 50=3,000 fresh policy episodes when
estimation cost is 10; confirmation ceiling 20 × 3 × 16=960. Optimizer ceiling 20 × 3 × 4=240 calls.
Actual estimation varies and remaining adaptation adjusts accordingly. Screening can consume
up to 1,600 episodes; share it across arms. These are ceilings, not expected spend; dollar
estimates require measured policy lengths and current provider prices, which this task does
not query. The optional 30-cap condition adds at most 1,200 adaptation and 960 confirmation
episodes under the same n=10 assumption. Neither budget is granted selectively to failing
D tasks after inspecting results.

### Outcomes and decision rules to freeze

Primary: per-task **K16-confirmed B_L delivery** of the single search-selected environment;
compare paired D−I and D−R, exact discordance counts and uncertainty. Secondary: valid
candidate rate, certified rate, operational endpoint viability, any-success rate separately,
search accept, target-band confirmation, repeated candidate errors, calibration failures,
cost per confirmed delivery and cumulative yield by rollout/call budget.

Proposed pilot continuation rule: D yields at least 4/20 confirmed deliveries and at least 3
more than I, with no invariant/provenance violations. This is a practical go/no-go threshold,
**not a powered superiority test**. Report paired intervals even if the rule passes. If
sample size falls short, this threshold is not rescaled after outcomes; classify the planned
decision inconclusive and report all results. Any broad distinction from R needs a later
powered comparison based on observed paired discordance.

Interpretations fixed in advance:

- Validity rises but endpoint viability does not: code repair helps reliability, not the
  behavioral bottleneck. Do not claim LOW solved.
- Endpoint viability rises but delivery does not: parameterization/control remains limiting;
  consider B and a matched larger-budget calibration study.
- D and I tie at equal cost: extra search, not feedback, may explain any improvement over H.
- R consistently beats D: the freeze/separation constraint is probably too restrictive.
- Search gains vanish at K16: adaptive selection/noise remains limiting; do not feed those
  confirmations back and rerun selection.
- All arms remain near zero: legal assistance mechanisms or the learner's ability to exploit
  them may be limiting. More RSI machinery is not the default next step.

An optional later fixed-budget curriculum study measures learning on original held-out tasks.
The immediate study measures adaptation delivery, not learner improvement.

## 20. Open questions and read inventory

Open: how much low-but-nonzero endpoint response should justify further design investment;
whether an intermediate dose can work when1 does not; how often real dose reversals occur
under a non-bracket diagnostic; whether support changes behavior without erasing the learning
problem; how strong structural privilege guarantees should become; whether diagnosis quality
or learner inability to use correct support dominates; and whether code-local patches remain
behaviorally local. These require separate evidence, not additions to the first state machine.

Read inventory (including delegated read-only audits):

- `src/aea/`: controller, designer, estimate/evaluate, budget/config, stage/stage_control,
  rules_control/bracket/families, witness/session/substrate/runner, corpus/io/logging and
  relevant LLM attribution boundaries.
- `docs/spec/AEA_v0.2.md`, `AEA_v0.4.md`, historical v0.3/v2 and `AEA_llm_v1.md`;
  all seven relevant LLM/LOW design and audit documents in `docs/design/`.
- All seven phase preregistrations/final reports/narratives; `LOG.md`; final data JSON,
  candidate/designer/events/accounting records and K16 confirmation summaries;
  oracle registry, frozen families, validation records and ceiling design.
- `scripts/e6_smoke.py`, `e6_refalign.py`, `e6_profile.py`, `e6_stage_control.py`,
  `e6_assist.py`, `e6_oracle.py`, `oracle_actuators.py`, their offline/table builders,
  shared pool/confirmation code and relevant `e3.py` evaluation helper.
- Read tests for method-version compatibility, llm_v1/refalign, assistive Rules, Stage
  control, oracle provider, budget and confirmation collection. No tests were executed.
- Local EnvHarness `agents/harness_agent.py` and orchestration source inspected as a
  filesystem snapshot, **not assumed identical to the published release**; submodule status
  showed the uninitialized marker for recorded `fab7d57`. Its refine method explicitly
  accepts old code plus rollout feedback and permits editing or replacing it. Paper-level
  settings come from the primary paper, not this possibly divergent snapshot.

Deliverables: this decision document and [LOW_ITERATIVE_FIELD_AUDIT.md](LOW_ITERATIVE_FIELD_AUDIT.md).
Stop at this recommendation. No new method version, prompts, repair loop or training code
is authorized by the conclusions themselves.
