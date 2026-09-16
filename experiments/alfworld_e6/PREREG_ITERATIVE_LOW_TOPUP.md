# Preregistration: one-task ZERO top-up and frozen iterative LOW continuation

Status: frozen before the first top-up screening request. Commit and push this
preregistration, driver, tests and bound audit artifacts before paid execution.

## Scope and preserved results

Work only in `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`.
Starting HEAD: `6fbf237f749e48e099bd75ea5a9c79b8d2cdc94e` (clean).
Main HEAD/status and all historical artifacts are preserved in the starting audit.

The previous V2 result remains **INCONCLUSIVE / SCREENING_COST_LIMIT** forever.
Its $7.994786072 committed cost is historical sunk cost, outside both new caps.
The earlier 130–149 result remains `INSUFFICIENT_FRESH_LOW`; previous failed
implementation smokes retain `IMPLEMENTATION_FAILURE`. No old report, run,
preregistration, source driver or evidence selection is edited.

Reuse exactly **154, 158, 159**, each prospectively confirmed at **0/16 valid
completed episodes**. The committed V2 all-16 identities/hashes and exact seeded
three-failure selection are immutable. Verify them before screening and before
input freeze. No original-policy rescreening or evidence reselection for this core.
Task162 remains **0/11 INFRA_INCONCLUSIVE** and cannot be resumed or used for efficacy.

The objective is exactly one additional fresh ZERO, then a single four-task LOW
viability arm. No D/I, comparison, new mechanism, prompt change, semantic gate
change, validator change, CONTROL change, fourth designer call, HIGH iteration,
outer AEA, E3 or E3-SL is authorized.

## Frozen implementation and provenance

- Method: `llm_v2_iterative_low_semantic_gate`.
- Production/validator-fidelity SHA: `bec74ed8a6ff40e119b2299c92b07b8602ff5fef`.
- Semantic screen: `alfworld-semantic-screen-v1`.
- Semantic source SHA256: `ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`.
- Historical viability base commit: `d151b150a65f7455084345e4b165b9b62234bd4a`.
- Historical viability base SHA256: `21e3a91c2a598385e2ed8c27fdeab0584015874d3c5411260a00f6bc042f839c`.
- Frozen V2 driver commit: `b6cd05418f619ad23318e55916aaae2a96d07875`.
- Frozen V2 driver SHA256: `c230bcfaea60b3c1b346018a5a7380c96d67c25e4f8fbe75702aef517d6129f4`.
- Prior committed evidence/report commit: `6fbf237f749e48e099bd75ea5a9c79b8d2cdc94e`.
- New driver: `scripts/e6_iterative_low_viability_v3.py`, SHA256 `980528539037365cb321c9a7678918dbb9302ecacd265cc10be2617e5d124e33`.
- New namespace: `runs/e6-iterative-low-viability-v3/`.
- Frozen audit directory: `frozen/iterative_low_viability_v3/`.
- Used-task audit SHA256: `1d8e571d57a5c67d2b82e4d200022908fb1d76c5423fc817ee4fcfc30de181df`.
- Prior-core audit/manifest SHA256: `c25cab9b7cab7777310b7b8f4947ef3a423f0a51d6ce7701f3e58549c684c42a`.
- Runtime manifest SHA256: `490a40c0d9eb2bba5257ae9101af9eaea7ed67019e8d1c9b193e25eceb2de2e4`.
- Cost-basis SHA256: `1b7b8969021090d2b7b0e0a02abca8e599945107499f8fef702f5ac205eefcac`.

Production `src/aea/`, designer prompts, candidate admission, semantic grammar,
solvability, feedback, lineage, endpoint evaluation, first-viable freeze,
CONTROL and K16 behavior remain byte-identical. Changes are experiment-level
pool assembly, provenance, separate monetary accounting, tests and reporting.
Every paid stage verifies exact implementation/input/runtime hashes and pushed
preregistration ancestry. No implicit stage replay or crash resume is permitted.

## Audited top-up order and limits

- Same nonnegative integer ALFWorld **train bridge-seed task ID** universe.
- Smallest unused ID from programmatic audit: `163`.
- Exact ascending newly inspected IDs: `163, 164, 165, 166, 167, 168, 169, 170, 171, 172`.
- Maximum newly inspected IDs: **10**.
- Goal: **exactly one additional CONFIRMED_ZERO**, named Z4.
- Additional screening committed-cost cap: **USD4**.

No task-semantic selection, substitution or automatic scan extension. Immediately
stop screening after the first new confirmed ZERO; do not dispatch the next ID.
The final sample is exactly **[154,158,159,Z4]**, retaining all four in its primary
denominator, including later reference-unavailable tasks.

## Unchanged V2 screening semantics

Each task starts with zero valid episodes and zero valid successes. A complete
nonerrored identity-environment trace contributes exactly one behavioral outcome.
First valid success immediately produces **NON_ZERO** and ends that task.
Exactly sixteen valid completed failures produce **CONFIRMED_ZERO**.

Provider retries do not add behavioral observations. If the request recovers and
the episode completes validly, preserve its behavioral outcome. An execution
without a valid complete outcome contributes zero valid episodes and zero
successes; retain its partial/error artifact and conservative request costs.

For each next valid episode permit at most **three fresh episode executions**;
at most48 per task. Reset this episode-execution counter only after a valid
outcome. Exhaustion produces task-level **INFRA_INCONCLUSIVE**, then advance to
the next audited fresh ID. Do not revisit a task or combine partial trajectories.
Identity, seed, provider/pricing, contract, lineage or accounting errors are
correctness defects, not retryable missing outcomes.

The frozen runner returns an errored trace only after worker exit or kill/wait.
Only then may an orphan in-flight reservation move in full to uncertain cost,
with the same attempt identity and no refund or extra API attempt. Unknown
worker completion preserves in-flight cost and globally stops; no overlapping
retry or implicit restart.

### Terminal top-up outcomes

- One new ZERO: stop screening, freeze Z4 evidence, then immediately assemble
  the four-task input set and continue after the viability preregistration is pushed.
- Ten inspected IDs without Z4, $4 cap denial, or global infrastructure stop:
  **TOPUP_INCONCLUSIVE**, with the detailed reason recorded; stop this continuation.
- Any genuine correctness defect: **IMPLEMENTATION_FAILURE**, immediate global
  stop, no patch-and-continue.

The global cap stop prevents all subsequent requests. Never use task162, add IDs,
change the provider/model, increase the cap, or reinterpret an invalid outcome.

## Frozen policy, provider, environment and retries

Unchanged `scripts/e3.py`, corpus and environment configuration: OpenRouter
`qwen/qwen3-8b`, Alibaba pinned, no fallback, thinking off, temperature0.5,
max output2048; `think_action`, history200, horizon50, train reset seed=task ID,
`repetition_threshold=0`, concurrency1, subprocess timeout600seconds.

Within-request policy retries remain at most10 physical attempts, initial2seconds,
exponential backoff capped90seconds plus at most1second jitter, total900seconds.
Retry408/409/425/429/5xx and transport timeout/connection failures; no internal
retry for400/401/403. Fresh-episode retry never converts infrastructure errors
into behavioral failures. Each physical attempt reserves money before dispatch.

Designer, when reached, remains direct DeepSeek v4 Pro, thinking off,
temperature0.7, effective max6144 output tokens and unchanged request retry policy.
No model/provider/pricing migration occurs during this continuation.

## Evidence, references and immediate adaptation

Preserve all original executions and physical attempts. For Z4 freeze the ordered
sixteen valid traces and use the unchanged `seeded_failures(all16,3,seed=Z4)`.
The input all16 order is chronological; preserve the function's returned sample
order. Core tasks retain their previously committed exact selections, including
order. Record identities, hashes, seeds and truthful `p_hat=0,n=16`.

Obtain one exact verified rich benchmark-expert reference per task using the
existing provider. Freeze successful or unavailable records once. An already
successful reference is not regenerated for auditing. Unavailable references
remain in denominator4, with no task replacement or failure-only fallback.

Freeze one input manifest for the four tasks, binding all/selected original
traces, their two screening provenances, references, policy/environment settings,
method/validator SHA, semantic gate SHA/version and exact driver/runtime inputs.
Commit and push `PREREG_ITERATIVE_LOW_VIABILITY_V3.md` with that manifest before
the first designer call, then execute immediately without another permission round.

Execution remains C1→typed feedback→C2→typed feedback→C3 when nonviable and
budget allows. Max3 designer calls/task, max30 fresh adaptation episodes/task;
K16 separate and evaluation-only. Preserve candidate gate order, semantic
UNCERTAIN behavior, solvability, 4→8 endpoint evaluation, first-viable freeze,
unchanged `assist_bracket`, 3–5/8 acceptance, K16, B_L4–12/16 and B_T7–9/16.
Safe candidate rejections remain normal DESIGN outcomes. Too_easy completes
DESIGN and enters CONTROL; no CONTROL→DESIGN return or parameterization rescue.

## Separate monetary limits and measured planning basis

- Top-up committed-cost cap: **USD4**.
- Separate adaptation plus confirmation committed-cost cap: **USD25**.
- Absolute ceiling for this new continuation: **USD29**; old V2 spend is excluded.
- Successful top-up completion freezes its exact committed-cost baseline.
  Adaptation spending is cumulative continuation committed cost minus that
  immutable baseline. Unused top-up allowance cannot enlarge the $25 phase cap.
- The shared physical ledger is never reset or refunded; all top-up and adaptation
  returned costs, failed reservations and in-flight reservations remain visible.
- References use the existing local expert and require no model API calls.
- No cap increase after paid execution begins.

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

Reservation arithmetic is unchanged: full wire UTF-8 bytes plus4096 and requested
max output at conservative uncached rates. Qwen input/output$0.117/$0.455 and
DeepSeek$1.32/$3.96 per million tokens. Returned cost is the maximum of upstream
cost and frozen token-rate cost; ambiguous attempts retain their full reservation.
A bound violation is a correctness failure. The next reservation that meets or
exceeds its phase cap is refused before transport dispatch and makes the stop sticky.

## Prospective reporting and final stop

The V3 viability preregistration will bind the exact four-task sample and the
user-specified decision rules. In particular, an unperformed K16 is not a failed
confirmation: multiple endpoint-viable but CONTROL-unresolved tasks alone do not
satisfy the partial-signal clause about failed confirmations. This is prospective
reporting clarification; candidate admission, optimization and CONTROL execution
are unchanged. Correctness failure takes precedence; valid observed K16 deliveries
and any infrastructure/cost incompleteness are reported explicitly.

Report verification of the prior core, new IDs and top-up result/cost, Z4 evidence,
references and exact-input preregistration, all actual C1/C2/C3 and typed feedback,
gates, endpoints, CONTROL, search accepts, K16/B_L/B_T, and phase-specific physical
spending. LOW_VIABLE recommends freezing LOW and full-AEA integration. Otherwise
identify the single direct functionality blocker. No follow-on experiment is run.
