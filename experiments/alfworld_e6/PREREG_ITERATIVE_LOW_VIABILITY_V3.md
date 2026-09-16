# Preregistration: iterative LOW lightweight viability V3

Status: frozen before the first adaptation designer request; commit and push this preregistration and its exact input manifest before execution.
This is one experimental arm, not a D/I or other method comparison.

## Frozen implementation and input set

- Method: `llm_v2_iterative_low_semantic_gate`.
- Production/validator-fidelity SHA: `bec74ed8a6ff40e119b2299c92b07b8602ff5fef`.
- Base frozen driver commit: `d151b150a65f7455084345e4b165b9b62234bd4a`.
- Base frozen driver SHA-256: `21e3a91c2a598385e2ed8c27fdeab0584015874d3c5411260a00f6bc042f839c`.
- Prior V2 screening implementation commit: `b6cd05418f619ad23318e55916aaae2a96d07875`.
- Prior frozen V2 driver SHA256: `c230bcfaea60b3c1b346018a5a7380c96d67c25e4f8fbe75702aef517d6129f4`.
- Prior core evidence/report commit: `6fbf237f749e48e099bd75ea5a9c79b8d2cdc94e`.
- Exact V3 driver SHA-256: `980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33`.
- Semantic screen: `alfworld-semantic-screen-v1`, SHA-256
  `ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`.
- Used-task audit SHA-256:
  `1d8e571d57a5c67d2b82e4d200022908fb1d76c5423fc817ee4fcfc30de181df`.
- Runtime-source manifest SHA-256:
  `490a40c0d9eb2bba5257ae9101af9eaea7ed67019e8d1c9b193e25eceb2de2e4`.
- Four-task input manifest: `frozen/iterative_low_viability_v3/input_manifest.json`.
- Input manifest SHA-256: `ad6019cff5b1ee1712e892404cefd5eb2813f032341e322de782f277d8ada46d`.
- Top-up preregistration commit: `4d8419e584d695591e55d1bbf85981b37cfa3764`.
- Prior-core audit/manifest SHA256: `c25cab9b7cab7777310b7b8f4947ef3a423f0a51d6ce7701f3e58549c684c42a`.
- Cost-basis SHA256: `1b7b8969021090d2b7b0e0a02abca8e599945107499f8fef702f5ac205eefcac`.
- Exact four tasks: `[154, 158, 159, 165]`.

| Task | Original outcome | Reference | Steps |
|---|---|---|---|
| 154 | 0/16 | REFERENCE_AVAILABLE | 16 |
| 158 | 0/16 | REFERENCE_UNAVAILABLE | 0 |
| 159 | 0/16 | REFERENCE_AVAILABLE | 12 |
| 165 | 0/16 | REFERENCE_UNAVAILABLE | 0 |

Exact all-16 episode IDs and per-trace hashes are in the immutable manifest.
The following bindings retain each task’s exact selected evidence and reference:

### Task 154

- Original all-16 aggregate SHA256: `0c8c2a77903761785db4820dab64499147099638dde761b156beced5e8c58f27`.
- Selected three episode IDs (ordered): `01485264d7, cae8a438ba, 5cabc8ef59`.
- Selected evidence SHA256: `d4b442dff2c824f6d42a22114448f92ca178ddba2b5d0a5ee7f14c2a2b8e735f`.
- Serialized designer evidence SHA256: `47b10bfe1e4cee40d3d60e154cf60254e4a65a8014d62a5b91e6ab979c3a447c`.
- Reference ID: `f0a58f89e43dcbbb`.
- Reference SHA256: `f8f5e026b4cc01e84ae1475241bda4207f765fc089b02d2f02f3d2d27dfa0549`.
- Evidence n: `16`; selection seed: `154`.

### Task 158

- Original all-16 aggregate SHA256: `20c0b77d08fb88efbe47ba5e96c7450f6c709355ac8ccf6a9cbdd6fe5813907d`.
- Selected three episode IDs (ordered): `7f461cecb1, 7729b3343a, 50434a07d4`.
- Selected evidence SHA256: `46b84d32279a0843d6a64bd73ae49d005f776f8f913fc9f76ab5c5254deb7445`.
- Serialized designer evidence SHA256: `9da71055b0462da64b5e08ba383e9214e4f730dea41740db5e51cdd58dd46712`.
- Reference ID: `None`.
- Reference SHA256: `729c583918ceb1ac4081152d8748572f316b7168fe262edcdb0201616edee0b1`.
- Evidence n: `16`; selection seed: `158`.

### Task 159

- Original all-16 aggregate SHA256: `fcddeb379d70e01d61b5a028ed8073a48abfbb04a7c1fc5282da01465e920253`.
- Selected three episode IDs (ordered): `e0fc323400, f3583ad1e1, 45c3700f83`.
- Selected evidence SHA256: `55a935664362fa036ea6ab84853661a3437cb8e9571626706bb97c44e9517b0a`.
- Serialized designer evidence SHA256: `45c5f02e204d6ef8753f993f323e928b86aef1a5a39bd2bbb020dcd50503cf8b`.
- Reference ID: `b68a542228b51665`.
- Reference SHA256: `80a8fc5d7507a4491a97275e295aed0071340e2b47f0c4250c376bc67653749e`.
- Evidence n: `16`; selection seed: `159`.

### Task 165

- Original all-16 aggregate SHA256: `321cf4f4bbd856c92dd9204201d78bdc180aec7dad8bfbebcb5a1937c670d610`.
- Selected three episode IDs (ordered): `2e6df0cdfa, feda2bac18, 53e5f3a572`.
- Selected evidence SHA256: `321baa81a6b995ca98964173789d47b7abd14d6d96827e410bfe656aadb35a2b`.
- Serialized designer evidence SHA256: `c69684e5d72032b30fa6cd0cb756c394596b6fdf848d4199531292ee64f7db4b`.
- Reference ID: `None`.
- Reference SHA256: `729c583918ceb1ac4081152d8748572f316b7168fe262edcdb0201616edee0b1`.
- Evidence n: `16`; selection seed: `165`.


All four remain in the primary denominator. Each has exactly 16 fresh valid
original-environment failures under the corrected frozen V2 pool protocol. Recovered provider retries
do not invalidate completed behavioral outcomes; errored executions never enter
the 16 valid original episodes or the selected failure evidence. Tasks154,158,159 retain their exact committed V2 all16 and selected3 identities, hashes and order; they were not rescreened or reselected. Only Z4 uses new top-up traces and unchanged
`seeded_failures(all_16, 3, seed=task_id)`. The normal
serializer uses `p_hat=0, n=16`; its code and prompts remain unchanged.

Each reference was obtained once with the existing provider and frozen. An
unavailable reference produces `reference_unavailable`, without substitution,
failure-only fallback or regeneration. Execute every referenced task. No task
replacement is allowed after input freeze.

Policy/environment settings and hashes are those in the pool preregistration
and input manifest: Qwen3-8B/Alibaba, thinking off, temperature0.5, max output2048,
think_action, history200, original train seed=task ID, horizon50. Designer is
direct DeepSeek v4 Pro, thinking off, temperature0.7, effective request max6144.

## The only experimental budget changes

- Maximum **3 designer calls per task**: C1, then at most two actual
  feedback-conditioned redesigns. No independent proposals or C4.
- Maximum **30 fresh adaptation policy rollouts per task**, after ZERO screening;
  endpoint and CONTROL share this budget. No extensions. K16 is evaluation-only.
- Production optimizer source remains byte-identical. The dedicated sequential
  driver scopes `MAX_OPTIMIZER_CALLS` from asserted default2 to3 around a single
  optimizer run, then restores2 even on failure. History, duplicate detection,
  candidate lineage, feedback and remaining-call records use that same instance.
- Preserve endpoint/calibration reserve16. It may legitimately prevent C3 after
  earlier endpoint measurements; three calls is a maximum, not a promise.

## Frozen candidate and feedback pipeline

Every candidate follows schema/API/structural → d=0 identity → lexical privilege
→ semantic privilege → solvability → d=1 current-policy endpoint. All exact
source/dose admission bindings and reconstruction checks remain active.

- Mechanical defects may request `REPAIR_CODE`; a repair consumes the next call.
- Lexical/semantic FAIL never reaches policy; existing `REPLACE_MECHANISM`
  feedback handles it as an ordinary rejection.
- Semantic UNCERTAIN remains task-terminal with no redesign or policy probe.
  Report it separately from FAIL and no leverage. It is an ordinary completed
  method outcome, not an infrastructure interruption.
- Candidate solvability defects use existing feedback. Infrastructure/expert
  failure is not fed to the designer and stops as inconclusive infrastructure.
- Endpoint evaluation remains 4→8: 0/4 too_hard; 4/4 too_easy; otherwise complete8
  and use the unchanged verdict. Too_hard requests `REPLACE_MECHANISM` with the
  exact frozen optimizer feedback if budget remains.
- Too_easy and in_band both complete DESIGN. Freeze source bytes/hash, mechanism
  and dose semantics. No unused designer call may be spent afterward.
- For too_easy, unchanged `assist_bracket` owns strength: initial [0,1], first
  interior dose0.5, at most4 bisections, unchanged scheduling/evaluator/acceptance.
  No CONTROL→DESIGN return. Calibration failure or adaptation-budget exhaustion
  is an ordinary unresolved task.
- Search accepts exactly **3–5 successes out of8**. Record source hash, dose,
  s/n and generation index.

## Confirmation and cost

Every search-accepted environment receives exactly **16 fresh K16 episodes** on
the frozen source/dose. B_L=[0.2,0.8] means **4–12/16**; B_T=[0.4,0.6] means
**7–9/16**. K16 never feeds DESIGN, CONTROL or the semantic screen.

The old V2 $7.994786072 committed cost remains historical sunk cost in its
unchanged ledger. This continuation has separate hard limits: **$4 top-up** and
**$25 adaptation plus confirmation**, with an absolute **$29 continuation ceiling**.
The top-up committed baseline is `USD 1.364482886`; its returned and
failed-reservation amounts are permanently retained. Adaptation committed spending
is cumulative continuation cost minus this immutable successful-top-up baseline.
Unused top-up allowance does not enlarge the $25 adaptation allowance. No ledger
reset or reservation refund occurs, and no cap increases after execution starts.
All designer, adaptation policy, K16, ambiguous/orphan and in-flight costs are
included. References used the existing local expert and no model API calls.

`The prior 48 confirmed-ZERO episodes averaged $0.094971100 returned cost and
$0.034430593 retained failed-request cost per episode. The 70 valid V2 episodes
overall averaged $0.087739830 returned and $0.026112153 retained per episode.
Planning 120 adaptation episodes at the core means, 64 confirmations at the
all-valid means, and 12 designer calls at the recent $0.01711512 peak returned
cost gives $23.020111429 including measured request-failure exposure. Applying
the core means to all184 policy episodes plus12 designer calls gives
$24.015292829. The $25 cap rounds above that measured maximum-count scenario.
These are planning scenarios, not a statistical upper bound or completion
guarantee; all actual failed reservations still count against the hard cap.`

Retry, provider, pricing, accounting and per-request reservation arithmetic are
unchanged. This planning cap is not a guarantee that every task reaches K16.

## Primary result and mutually exclusive decision rule

Primary result: number of fresh ZERO tasks yielding K16-confirmed B_L, **out of4**.
No significance test, B_T requirement or comparison arm is introduced.

Apply this precedence:

1. Any method-invalidating correctness defect → **IMPLEMENTATION_FAILURE**,
   immediate stop; no patch-and-continue. Includes contract/gate mismatch, actual
   privileged admission reaching a learner-facing surface, wrong implementation,
   lineage/accounting corruption, reconstruction error or K16 feedback leakage.
2. Without correctness failure, at least2 K16 B_L deliveries → **LOW_VIABLE**.
   This threshold remains met if a later infrastructure/cap interruption prevents
   completing another task. Do not voluntarily stop early after the second win.
3. With fewer than2 confirmed deliveries, infrastructure interruption or a hard
   cap before required referenced tasks complete → **INCONCLUSIVE**; preserve any
   observed positive signal descriptively.
4. Otherwise exactly1 K16 B_L, or at least2 search-accepted tasks with completed
   K16 confirmations that miss B_L → **LOW_PARTIAL_SIGNAL**. Report actual
   successes/n and B_L/B_T for every completed confirmation. An unperformed K16
   is not a confirmation miss; endpoint-viable but CONTROL-unresolved tasks alone
   do not satisfy this clause. This prospective reporting predicate follows the
   user's failed-confirmation requirement and supersedes the old V2 report-only
   `viable >= 2` shortcut. It does not affect DESIGN, gates, freeze or CONTROL.
5. Otherwise zero B_L with at least3 referenced/evaluable tasks completed without
   correctness/infrastructure failure → **LOW_NOT_WORKING**.
6. Too few usable references to apply the preceding rules → **INCONCLUSIVE**.

Ordinary candidate weakness, privilege rejection, terminal semantic uncertainty,
no leverage and CONTROL failure never trigger a method edit or infrastructure
classification. Missing references remain in denominator4.

## Reporting and stop

Report each task's reference status; C1/C2/C3 mechanism, structural/identity/
privilege/solvability/endpoint outcomes and exact typed feedback; first viable
generation; CONTROL measurements; acceptance/dose; K16/B_L/B_T; calls, rollout
counts and USD. Mark unused proposals after viability as “not needed”.

Aggregate the specified failure funnel without launching another analysis phase.
LOW_VIABLE recommends freezing LOW and integrating full AEA. PARTIAL recommends
exactly one minimal implementation improvement; NOT_WORKING recommends the most
direct functionality change. This run implements neither recommendation.

The previous130–149 screening run remains `INSUFFICIENT_FRESH_LOW` and is not
reinterpreted. The prior V2 run remains INCONCLUSIVE / SCREENING_COST_LIMIT. Its three verified ZERO tasks are reused exactly; task162 is excluded and never resumed. This preregistered four-task continuation alone supplies LOW efficacy evidence.

Stop after the complete report. No D/I ablation, external method comparison,
iterative HIGH, outer AEA loop, E3 or E3-SL follows automatically.

## Successful top-up phase binding

- Top-up baseline SHA256: `60b6e4bf87641204df4d48cf664c85855005ed833e53f2bbeb46b1402d250233`.
- Returned cost: $1.319209502; retained failed-request reservations: $0.045273384; in-flight: $0.
- Physical top-up attempts: 858.
- Top-up screening SHA256: `25224e2d841730804cdbb4769eb9151d022c759b95fe35b1ac37ac97d7fbebaa`.
- Combined screening SHA256: `e05cfbbd858bb2f23e9ad0a7aecadcc52dbdbb8e04560e8c844928351be64511`.
