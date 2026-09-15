# Preregistration: iterative LOW semantic-gate efficacy smoke

Prospective four-task D/I smoke. This document and its input manifest must be committed and
pushed before the first paid designer or policy request. Starting HEAD:
`4d368fea2d6ab06d3656420e6f99c561bb9d50cf`, branch `aea-llm-vnext`.

## Question and frozen implementation

Does candidate-specific evaluator feedback improve the second LOW proposal relative to an
equally budgeted independent second proposal?

- Implementation: **7555cc3bf0594cb132250949fa57e18fecf10982**.
- Variant: **llm_v2_iterative_low_semantic_gate**.
- Production source tree: `ee579f05b9ab51cc4686d98e5c5c1ef95fb03ada`.
- Semantic screen: **alfworld-semantic-screen-v1**, source SHA256
  `ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`.
- Surface runner SHA256: `c637d9519ed3db273262a123c075f830121a6c75932fbd030ae7e2744dcacee0`.
- Admission adapter SHA256: `53c0a9886b3adba1101a9144239bf6dc5a8f68cfaae8907df5151fae90b8b088`.

No production changes: optimizer, two-call cap, REPAIR_CODE / REPLACE_MECHANISM taxonomy,
designer contract/prompts, lexical and semantic gates, solvability, 4-to-8 evaluator,
freeze boundary, assist_bracket, acceptance, budget rules and K16 remain frozen. A genuine
method/code defect stops this smoke; no patch-and-continue. The old task-110 smoke remains
permanently IMPLEMENTATION_FAILURE and its files remain unchanged. Task 110 is only an
offline privilege regression and is excluded from scientific efficacy counts.

## Exact tasks and original evidence

Tasks, in order: **114, 115, 126, 129**. Programmatic audit scans historical adaptation
events, designer/proposal/candidate records and ledgers, alongside frozen LOW pool files.
LOW_POOL_3 has 13 confirmed 0/16 tasks; previously consumed adaptation tasks are
85, 86, 87, 92, 97, 99, 107, 109, 110. The exact unused set is the four tasks above.
Reference preparation without adaptation is not consumption. Any discrepancy stops before
paid requests. No substitution or new pool screening is allowed.

Frozen classification source `experiments/alfworld_e6/frozen/low_pool3_k16.jsonl` SHA256:
`f415aced6c4423356b2f4c62f68e4ec70a13c76feb3a0907fc04685b132473ed`.
Original trace source `runs/e6-pool3-k16/confirm.jsonl` SHA256:
`db0ad3d2601c8ecb3b804bd05dc507fb41b29295abee3cc09e70e2f18fec3456`.

Reuse the first ten stored original episodes per task, then unchanged
`seeded_failures(..., n=3, seed=task_id)`. Each selected trajectory contains all 50 steps.
Use unchanged rich `serialize_low`, p_hat=0, n=10 and its existing content limits.
No original policy calls, K16 rerun, richer failure collection or evidence substitution.
Canonical evidence hash means SHA256 of `json.dumps(trace_records, sort_keys=True)`.

| Task | Selected episode IDs | Canonical evidence SHA256 |
|---|---|---|
|114|1204829a62, fe6d09f519, d45654777d|3fe56eccfa64222cdee9d09ec76266227efc7085d9d92fb18c443a8115675c1f|
|115|344e71ba14, 2ebb3e172b, 37ad99151d|180d57ebe50bcbbb4060bab132a96380140b9e02cc4934fbac12ae0ad602117a|
|126|afede69dc0, 2dcc3e9223, 9a47b9c175|24f2def9b9c92ea034c395dd5b1518353017ec8d3b79a698172fbf3ecb943209|
|129|2c8d0611cc, 2ed7ec6c77, ca26486138|5994595a3e00c068ae70d3cbf583e22eba68748be3ad8d8028ba1dd38cef786f|

The committed `frozen/iterative_low_semantic_smoke/` manifests bind audit sources, selected
episode hashes, exact references, serialized evidence and preflight checks. Before paid work,
validate both disk records and committed manifests. Corrupted evidence stops without repair.

## One exact reference per task

Use the existing local ExpertReference provider and exact rich-reference provenance.
Reuse the already frozen provider outcomes for 114, 115 and 126, without rerunning them.
For 129 obtain one local provider result and freeze it. Successful references require rich
observations/admissibles and the exact verified executed action sequence; the action list,
step list, reference ID and record hash must agree. No successful reference is regenerated
later for audit. The prepared manifest records full canonical hashes and provenance.

114 and 126 have existing verified ten-step references; 115 retains its existing unavailable
`verifier_fail` outcome. Unavailable reference means `reference_unavailable` for both arms,
no designer call and no failure-only fallback. All four tasks remain in the primary
denominator; referenced and paired denominators are reported separately. At least two usable
references are required for an aggregate scientific decision.

Preparation is complete without model API calls. Task129 has a verified 30-step reference.
The exact frozen reference records are:

|Task|Availability / reference ID|Canonical record SHA256|
|---|---|---|
|114|available / 9f1502115cd92a43|15d51ac83eea9ef118e80a9541941f81edc3ccfc87d28e3c2d72b937e3437f39|
|115|unavailable / verifier_fail|729c583918ceb1ac4081152d8748572f316b7168fe262edcdb0201616edee0b1|
|126|available / de1683aefd48799c|fdd5352128563fede883c15d94ff83e5ca382c6e39371a99708f75ff5ecc0a8b|
|129|available / 056434ac2d25319a|b8cedd5bb768903a9ed6bb361aa2b92aa49d2ae23cf2fd0cc5eba4d42a8ce934|

## Identical admission and shared C1

Generate one physical C1/task using common evidence/reference. Its complete structural,
lexical, semantic, solvability and endpoint result is shared by D and I. Reuse exact source,
source hash and immutable candidate record, asserting equality. Physically execute every
necessary C1 stage once, and charge its opportunity equally to both logical budgets.

Both arms use the same frozen ScreenedLowOptimizer and one task-local LowPrivilegeScreen:
static/schema/API -> lexical -> semantic -> solvability -> d=1 learner endpoint. The semantic
screen inspects source and executed same-state/history surfaces, all original failure
prefixes, the actual policy formatter and all 17 reachable doses in {0,1/16,...,1} for the
existing four bisections. Learner authorization is specific to task/episode/step and derives
only from original observations/actions/admissibles plus the public goal. Designer history,
privileged reference and candidate-generated text never become learner-authorized evidence.
Exact source/dose PASS admission is required before policy measurements, including CONTROL.

FAIL rejects through the frozen privilege REPLACE_MECHANISM feedback path. UNCERTAIN stops
that arm before solvability/policy and receives no redesign by default. Shared C1 UNCERTAIN
stops both arms; C2_D UNCERTAIN does not erase I's independently allocated C2 opportunity.
There is no LLM privilege judge. This remains independent bounded semantic screening, not
a guarantee of semantic isolation.

C1 categories: STRUCTURAL_FAIL, PRIVILEGE_FAIL, SEMANTIC_UNCERTAIN, SOLVABILITY_FAIL,
ENDPOINT_TOO_HARD, ENDPOINT_IN_BAND, ENDPOINT_TOO_EASY. These display labels map existing
typed candidate records; infrastructure and budget termination remain separate statuses.

C1 in-band or too-easy ends DESIGN in both arms, freezes the same family and forbids C2.
In-band accepts directly; too-easy runs unchanged CONTROL once and shares its outcome.
This is a paired tie, including unresolved CONTROL. Only ordinary C1 failure before
viability permits branching, subject to the unchanged remaining-budget reserve.

## D2 versus I2 and exact prompt audit

D2 receives exactly the frozen Feedback record: C1 identity/source/hash/mechanism, typed
category, exact relevant gate/evaluator reason, remaining calls/policy budget, and the
existing bounded endpoint/failed-rollout evidence when applicable. Mechanical feedback is
REPAIR_CODE; privilege/solvability/no-leverage feedback is REPLACE_MECHANISM. Do not enrich
feedback or invent reference facts. Preserve each supplied feedback record, C1 hash, semantic
input hash where applicable and exact D2 request/message hashes.

I2 is independently reconstructed by the frozen `iterative_messages` from original Evidence
and reference with feedback=None. Include only previous C1 source for duplicate avoidance,
using the existing neutral sentence. No C1 validation error, semantic verdict/reason,
solvability result, endpoint s/n/verdict, policy rollout or rejection category enters I2.
Its internal optimizer history may contain typed state, but the actual request has no
evaluator fields. Retain privileged exact requests separately from learner artifacts.

Before paid calls, exact prompt-level offline tests inject distinct validator, semantic
verdict/gate reason, solvability, s/n, too_hard/too_easy and rollout sentinels. D2 must contain
the relevant feedback; I2 must match independently constructed neutral messages and omit
every evaluator sentinel. Repeat exact-message equality checks for every actual request.
Isolation failure stops before further calls. Both C2 candidates use identical frozen gates;
duplicates use the frozen rejection behavior, terminal duplicate_candidate, no new policy
evaluation and no C3. D runs before I; provider time drift is a limitation.

## Budgets, CONTROL and physical cap

Per arm/task: at most **two logical proposals** including C1 and **20 fresh logical adaptation
rollouts**, beyond reused original evidence. Shared C1 measurements count once physically
and equally logically; branch measurements charge their own arm. Unused budget stays unused.
The frozen optimizer requires **16 remaining rollouts before a proposal**, including C2:
worst-case endpoint8 plus calibration8. Insufficient reserve is ordinary budget_unresolved,
with no call or measurement and no top-up. This preserves the existing reservation point.

After viable endpoint freeze, in-band search acceptance and too-easy assist_bracket retain
the existing 4-to-8 evaluator, midpoint/bisection policy, maximum four bisections, thresholds
and budget checks. CONTROL never reopens DESIGN or alters code/dose semantics. CONTROL
failure is unresolved. No parameterization rescue or fallback.

**Hard total physical API cap: USD12**, including designer, policy, K16 and failed-request
reservations. Use existing frozen model/provider/pricing settings: Qwen3-8B Alibaba policy,
thinking off, temperature .5, max_tokens2048, max_steps50; DeepSeek V4 Pro designer, thinking
off, temperature .7, max_tokens6144. C1 seed=task, C2 seed=task+1 in both arms.

Reuse the existing capped transport with a shared file lock. Before each actual HTTP attempt,
reserve at frozen uncached peak rates (Qwen input/output .117/.455 USD per million;
DeepSeek 1.32/3.96), using serialized UTF-8 request bytes plus4096 protocol tokens as input
bound and the requested output-token maximum. Returned usage settles at the larger of
upstream cost and peak token cost. Ambiguous failed attempts retain their full reservation;
in-flight reservations count. Cap denial stays stopped across retries. A bound violation
is IMPLEMENTATION_FAILURE. Never increase the cap.

Check cumulative committed spend before each task, designer request and K16. Task planning
uses the historical original episode mean37.754917694/800, projects40 physical adaptation
episodes plus .30 designer USD; K16 projects16 episodes. These checks may stop early;
per-request reservations enforce the hard cap. Report actual priced ledger spend separately
for policy, designer and confirmation, plus conservative failed-request reserves. Shared
physical calls are never double-counted; report each arm's logical opportunity separately.

## Fresh K16 and ordinal outcomes

Only a final search-accepted environment receives fresh K=16 confirmation. Deduplicate by
exact final environment hash **and dose**, physically once per identical D/I result, with
16 logical confirmation episodes attributed to each. K16 is outside adaptation20 and inside
USD12. No K16 evidence enters designer prompts, search or further proposals.
Historical B_L=[.2,.8] and B_T=[.4,.6], inclusive; report both.

Frozen ordering:
`no_reference < invalid/privilege_fail < valid < certified < endpoint_too_hard <
endpoint_viable < search_accepted < K16_B_L < K16_B_T`.
Endpoint too-easy is endpoint_viable. C2 is scored by its own reached stage, never the maximum
over C1/C2; a regression remains visible. Duplicate C2 is invalid. If reserve denies C2,
record no C2 and retain the shared C1 outcome as a paired tie; it cannot count as improvement.

Primary comparison: among ordinary C1-failed tasks with rankable arm outcomes, C2_D vs C2_I.
Secondary comparisons: C2_D vs C1 and C2_I vs C1. C1 viable shared outcomes are reported ties
outside the primary failure-conditioned contrast. Reference-unavailable tasks remain /4
coverage outcomes, not feedback opportunities.

UNCERTAIN is an unranked, separately reported arm-level inconclusive screening outcome.
Exclude affected pairs from ordinal win/loss counts; never map it to ordinary invalid or
infer the missing candidate stage. Continue other authorized arms/tasks. Semantic uncertainty
alone is not one of the user-authorized aggregate INCONCLUSIVE causes. If the observed
rankable outcomes do not meet the positive criteria below, report NO_FEEDBACK_SIGNAL with
explicit screening-censoring coverage and no claim that feedback is ineffective. Even zero
rankable pairs establish only that this smoke delivered no observable feedback signal.
Infrastructure outcomes are also unranked and handled by the interruption rule below.
The frozen optimizer's `certification_inconclusive` and endpoint infrastructure failures
retain their exact reasons as unranked infrastructure outcomes; they are not semantic
UNCERTAIN verdicts or ordinary SOLVABILITY_FAIL. Provider/expert infrastructure failure
therefore stops with aggregate INCONCLUSIVE unless a correctness violation takes priority.

## Exact aggregate decision, in priority order

1. **IMPLEMENTATION_FAILURE**: any leak reaches policy, evaluator information enters I,
   different admission rules, budget violation, corrupted candidate identity, old-method
   regression, incorrect shared accounting, K16 feedback or wrong version. Stop immediately.
2. **INCONCLUSIVE**: fewer than two usable referenced tasks, provider outage, transport
   failure, corrupted frozen evidence, or USD-cap interruption before sufficient paired
   outcomes. Conservatively require all usable-reference tasks and required confirmations
   to reach terminal outcomes; do not treat a missing arm after interruption as a loss.
3. **ITERATIVE_LOW_STRONG_SIGNAL**: correctness passes; D delivers at least one K16 B_L;
   D beats I on at least one ordinary C1-failed paired task; D losses do not exceed wins.
   This rule does not additionally require two D2-over-C1 improvements.
4. **ITERATIVE_LOW_SIGNAL**: correctness passes; D2 strictly improves on C1 on at least
   two ordinary C1-failed tasks; D beats I on at least one paired task; losses <= wins.
5. **NO_FEEDBACK_SIGNAL**: correctness passes and the observed outcomes do not meet those
   paired signal criteria. Ordinary poor candidates, exhausted logical budgets or too few
   C1-failure opportunities do not justify aggregate INCONCLUSIVE.

## Preflight and artifacts

Before any paid request: full units, LLM-free integration including real task110, frozen
semantic benchmark, Ruff, format check, strict mypy and full pre-commit must pass (report
any existing optional-dependency integration skip explicitly). Archived task110 C1 must FAIL.
Independently review driver wiring, shared accounting and exact prompt isolation. Verify
production/old-artifact hashes and the pushed prereg commit before execution. No method edits
afterward; no correction of a discovered method defect within this smoke.

New namespace: `runs/e6-iterative-low-semantic-smoke/`.
Report: `experiments/alfworld_e6/results/e6_iterative_low_semantic_smoke.md`.
Retain per-task references, source hashes/mechanisms, all candidate gates and endpoints,
CONTROL/K16 outcomes, exact D feedback, I isolation proof, semantic FAIL/UNCERTAIN counts,
logical/physical rollouts, priced and conservative costs, freeze/prereg SHAs and one decision.
All learner artifacts exclude privileged designer/reference audit packets.

After reporting, STOP. A positive result supports only a larger matched pilot; this small
selected sample cannot establish generalization, LOW solved, superiority to EnvHarness,
learner improvement or outer-loop efficacy. No C3, raised budget/cap, R arm, HIGH iteration,
outer AEA loop, full E6 or E6-SL is authorized.

## Experiment driver freeze

Driver SHA256: `22112d20634d5e4d9b06439a7c1355d60de6aaa1ab9a32286a76d431e4bdfb6d`.
Eligibility audit script SHA256: `3665ffac8f9ff1ac895262d06ce9582410456b3d88216a8d2cdfdf2ecfa809fc`.
Exact prompt/accounting test SHA256: `a74bc999110ab517bd27c5889de0239dde73e3bc4f2a24ed6d4407ab4d03e132`.
Only these experiment orchestration/audit files and prospective manifests are new.
Production source and the prior smoke/offline-gate records remain byte-identical.

## Recorded preflight

All checks completed before paid calls: 298 unit tests passed; 10 LLM-free integration
tests passed including real task110; one existing optional RL-loader dependency test skipped
(ray absent). All14 semantic benchmark cases matched (3 PASS,9 FAIL,2 UNCERTAIN), including
archived task110 FAIL. Ruff, format (176 files), strict mypy (93 source files) and full
pre-commit passed. The eight new driver tests include five exact prompt-isolation cases.
Three verified references are frozen; task115 remains unavailable. Model API calls so far:0.
