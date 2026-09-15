# AEA LOW oracle actuator ceiling — design (phase 3.5a, written before implementation)

Phase 3.4 concluded **RULE_GENERATION_FAILURE** (frozen): on the 7 referenced tasks the one-shot
LLM family generator produced no loadable, non-privileged family on 3 tasks, a family without
d = 1 leverage on 2, and reached dose control on 2. That result does not say whether assistive
Rules are intrinsically unsuitable for LOW. Phase 3.5a decomposes the causal chain

```
evidence -> ONE-SHOT LLM GENERATION -> validation -> dose control -> K16
```

by replacing only the generator with a **hand-verified, non-privileged assistive family** per
task and keeping everything downstream identical:

```
evidence -> HAND-VERIFIED FAMILY (frozen before any policy call) -> same validation -> same dose controller -> same acceptance -> same K16
```

Question: *generation bottleneck* vs *actuator / control bottleneck*.

## Status of the result

This is an **oracle / ceiling experiment**. The families are privileged experimental assistance
(human, task-specific). Their outcome is reported only as an *oracle actuator ceiling*, a
*mechanistic feasibility* number and a *bottleneck localisation*. It is never reported as AEA,
llm_v1 or LOW performance and is never compared as a method result against EnvHarness, G, R,
AEA v0.2 or any automated method. Nothing here enters a production cascade.

## What is frozen and reused (no new evidence)

| item | source (phase 3.4, immutable) |
| --- | --- |
| tasks | 85, 86, 92, 97, 99, 107, 109 (the phase-3.4 tasks with a verified reference; 87 excluded: reference unavailable) |
| prospective `zero` evidence | `runs/e6-ar-shared/shared.jsonl` (all 7 `zero`, p_hat 0, n 10) |
| failed trajectories | the 10 estimate rollouts per task in `runs/e6-ar-shared/traces.jsonl` (the phase-3.4 designer saw the 3 seeded ones; the human designer read all 10) |
| verified rich expert reference | `runs/e6-ar-shared/privileged_references.jsonl` (reference_id = sha256 of the action list; archived copy `results/e6_low_assistive_rules/shared/privileged_references.jsonl`) |
| task goal | first observation of the failures |

The expert is not re-run for evidence. The regime is not re-estimated: the arm replays the 10
frozen estimate rollouts through the existing `FrozenSubstrate` (charged, no API call), exactly
as arm B of phase 3.4 did, so the **budget rule is matched**: cap 30 charged rollouts per task
including the 10 replayed = at most **20 new adaptation rollouts** per task (phase 3.4 arm B:
identical). The first current-policy call of this phase is the d = 1 measurement of a frozen
family.

## Restriction on family design (recorded, enforced by ordering)

The families are designed from: the task goal, the normal environment API / state
(`ENVIRONMENT_SURFACE`, the bridge's `AlfworldEnvState`), the failed trajectories, the verified
reference, a HarnessEvolve-style diagnosis, and the static EnvHarness Rules contract. They are
**not** designed from any phase-3.4 policy-response measurement (which dose was too easy on which
task, which generated family had leverage, which Stage cut was dead). The designer of this phase
(the assistant) had read the phase-3.4 tables; to make the restriction checkable, every family
follows one fixed rubric and one fixed dose semantics chosen before any task was designed (below),
no dose threshold is task-tuned, and the per-task record states the semantic evidence that
selected the mechanism. All seven families are constructed, validated offline and committed as
one batch before the first current-policy probe; after that commit no family code, dose
semantics or task-specific repair is permitted.

## Fixed rubric (applied identically to every task)

1. **Diagnosis** (compact): observed learner bottleneck; contrast with the successful reference;
   missing capability / environmental support need.
2. **One mechanism** of environmental support that addresses the bottleneck, drawn from the
   legal surfaces of the released Rules API (`filter_action` -> `Blocked`, `filter_observation`
   on text + `data["admissible_commands"]`, per-episode memory in `env_state.extras` / the
   instance). No new simulator hook, no Setup prefix, no transition edit that changes
   reward / termination / success.
3. **One dose semantics for all tasks: coverage.** W(d) delivers a fraction d of the support
   events the mechanism would deliver at full strength; W(0) delivers none (identity); the
   support set at d2 contains the support set at d1 for d1 < d2 (monotone by construction):
   - event-thinned support (blocking, annotation): the k-th eligible event is delivered iff
     floor(k * d) > floor((k - 1) * d), i.e. the first ceil(d * k) of the first k eligible
     events, in order; d = 1 delivers all, d = 0 none;
   - set-thinned support (pruning): the first floor(d * m + 1e-9) of the m eligible items in
     their eligibility order (d = 1 all, d = 0 none).
   No threshold is picked per task; no mapping is fitted to any success-rate data.
4. **Privilege boundary**: the code may use the target object *type*, the required object state
   and the target receptacle *type*, all read from the goal text; the policy's own observations
   (what it saw where); generic task-template knowledge of the ALFWorld task families ("hot"
   means heated in the microwave, "clean" means washed at the sinkbasin, "look at X under the
   desklamp" needs X in hand). It never uses a numbered object instance that only the reference
   exposes, never a reference action, never a location, never the verifier or reward.
5. **Non-solution**: the family never performs a task action, never moves objects and never
   ends the episode; at d = 1 the policy still has to find, take, transform and place.

## Bottleneck classes found and the mechanism per class

Three bottleneck classes cover the seven tasks (evidence in the per-task records under
`experiments/alfworld_e6/oracle_actuators/`):

| class | tasks | bottleneck (from the failures) | mechanism (single, legal) | eligible support events |
| --- | --- | --- | --- | --- |
| S: search coverage | 85, 109 | the policy re-inspects the same receptacles (fridge, cabinets) for 50 steps and never reaches the surface holding the goal object; the reference inspects each receptacle once | **explored-receptacle pruning** (O): while the goal object is not in hand, `go to R` for a receptacle R whose contents the policy has already seen (and that showed no goal-type object) is removed from the admissible commands and the text | set-thinned: the inspected, goal-free receptacles in inspection order |
| P: premature completion | 92, 97, 99, 107 | the policy issues the goal-completing action before its goal precondition holds (uses the desklamp without holding the object; puts the potato in the garbagecan without cleaning it) and then loops; the reference satisfies the precondition first | **precondition gating** (A): a premature goal-completing action is rejected with `Blocked(reason)` where the reason states the goal precondition in goal words ("the goal needs a clean potato: clean it before putting it in the garbagecan") | event-thinned: the premature attempts, in order |
| G: goal decomposition | 86 | the policy sees `plate 1` on countertop 1 among 11 objects and never takes it, searching 26 cabinets instead; "hot plate" is not decomposed into plate -> heat -> place; the reference takes the plate and heats it in the microwave | **goal-decomposition annotation** (O): the observation carries one line spelling the goal as its sub-steps in goal words ("find a plate and take it; heat it in the microwave; put it on a countertop") | event-thinned: the observations (reset and every step), in order |

Each family is written once per task from a class template with the goal-derived constants of
that task (object type, required state, completing action pattern, receptacle type), so the
mechanism is literally the same across dose and across the tasks of a class. If a task admitted
no defensible non-privileged family it would be recorded `NO_ORACLE_FAMILY`; this did not
occur (all seven fall in a class).

Relation to the phase-3.4 generated proposals is recorded descriptively per task (same idea /
related / different); it is not part of any decision.

## Controller: identical to phase 3.4 (frozen)

`Controller._stage_assist` is reused unchanged except for the family source: an experiment-side
**assist provider** (constructor argument `assist_provider`, default `None`; production never
sets it) returns the frozen `AssistDesign` (one family, no diagnoses text) instead of calling the
designer; the controller records an `oracle_actuator` event and an `oracle_families.jsonl` row
(family name, code sha256, mechanism) where the LLM path records a designer call, and marks the
corpus record `source = "oracle"` (new literal value; the LLM path keeps `"llm"`). Everything
else is byte-for-byte the phase-3.4 path: the existing oracle guard at d = 1 (`solvable`, expert
under W(1)); the 4 -> 8 measurement at d = 1; `too_hard` at d = 1 = **ORACLE_NO_LEVERAGE**
(controller reason `no_leverage`, no strengthening); `in_band` = search accept; `too_easy` =
the mirrored bracket inward (`assist_bracket`: lo = largest too_hard dose starting at 0, hi =
smallest too_easy dose, <= 4 bisections, `dose_order_violation`); a leveraged family that does
not land ends the task; cap 30 charged rollouts including the 10 replayed. No Stage, no cascade,
no repair, no second family, no grid, no extra budget. Bands B_T (0.4, 0.6), B_L (0.2, 0.8),
accept 3..5 of 8: `AEAConfig` defaults. No `method_version` is added: the arm runs under
`method_version = "llm_v1_assistive_rules"` with the provider injected, and every record of the
arm (manifest `stage = oracle_actuator_ceiling`, events, corpus `source = oracle`, run id
`e6-oa-*`) says oracle.

K16 (`stage_confirm`, evaluation-only, default reset for a Rules candidate as in the phase-3.4
correction) on every search-accepted environment; primary = p16 in B_L; B_T also reported.
Never fed back.

## Run layout

- run ids `e6-oa-O1`, `e6-oa-O2` (two processes over disjoint task subsets, 8 episodes in flight
  each = 16 total; rows merged as the single oracle arm **O**), `e6-oa-confirm`; shared evidence
  read from `runs/e6-ar-shared` (its sha256s recorded in the manifests).
- USD cap 30 over `runs/e6-oa-*` (probes <= 7 x 20 x 0.06 ≈ 8.4; confirmations <= 7 x 16 x
  0.05 ≈ 5.6); no designer cost.

## Gates (any failure = INCONCLUSIVE)

Runtime `method_version`; estimate equals the shared estimate; `reference_id` equals the shared
reference; no designer call (`designer_calls.jsonl` absent); exactly one family per task and its
code sha256 equals the frozen file; first probe of the family at d = 1; no guard
`by_construction`; no Setup prefix anywhere (`in_env_actions` empty in traces and corpus); no
Stage / family / cascade event; <= 30 charged rollouts per task including the 10 replayed;
provenance-based leakage audit (record hash == reference event; reference block absent from
every kept file; expert never re-run for evidence); `src/aea` unchanged from the freeze commit.

## Outcomes and decision

Primary: number of the 7 tasks with a K16-confirmed learnable oracle environment. Secondary:
family availability, offline validity, d = 1 leverage, search accept, K16 target, budget
exhaustion, dose-order violation, leveraged-unresolved, no leverage, unique doses, response
regimes along dose, policy rollouts and USD. Decomposition table per task (phase-3.4 generated
family: valid / leverage / accepted / K16 vs oracle family: available / leverage / accepted /
K16) with the interpretation. Decision rules (exact, ordered) in
`PREREG_LOW_ORACLE_ACTUATOR.md`: GENERATION_BOTTLENECK_SUPPORTED, ACTUATOR_EXISTS_BUT_CONTROL_
REMAINS_LIMITING, ASSISTIVE_RULES_ACTUATOR_NOT_SUPPORTED, ORACLE_CONSTRUCTION_INFEASIBLE,
INCONCLUSIVE. Thresholds are never lowered after results.

## Offline validation (before freeze; LLM-free; no current-policy call)

Per family: loads under the released `code_loader`; references DOSE; identity at d = 0
(`identity_at_zero`) and identity on a replay of the frozen reference at d = 0 on the real
environment; d = 1 legal (`validate_rules_template`); the structural `privilege_check` against the
frozen failures and reference; the reference actions replayed under W(1) still win (task
preserved, expert-solvable) and the support events they trigger are recorded; a scripted replay
of a frozen failure prefix under d in {0.25, 0.5, 0.75, 1} shows the support-event counts
non-decreasing in d (coverage semantics); the instantiated Rules never emit a task action. The
current Qwen policy is not used before the freeze.

## Tests (unit, experiment-only fixtures)

All seven family records frozen (files == registry, sha256 pinned); one family per task; d = 0
identity; d = 1 legal; the same mechanism across dose (support counts monotone in d on a
scripted fake episode); reference provenance exact (provider returns the frozen reference, id ==
shared); no future-reference leakage (no numbered instance constant, no reference action in any
family); no Setup prefix; the existing Rules control is reused unchanged (the provider path runs
the phase-3.4 controller branch on the fake dose world with identical d = 1-first / accept /
bracket behaviour; `rules_control` untouched); existing acceptance unchanged; matched rollout cap
(30 including the replayed 10); K16 evaluation-only (the controller never reads the confirm run).
Golden fixtures of the older variants are not modified.

## Not implemented (by design)

LLM repair of the phase-3.4 proposals, refinement rounds, Stage + Rules cascade, routers or
meta-selectors, family memory, prompt optimisation, more than one family per task, new control
algorithms or grids, larger budgets, new simulator hooks.
