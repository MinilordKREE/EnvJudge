# PREREG_LOW_ASSISTIVE_RULES — paired LOW-only comparison: `llm_v1_stage_control` vs `llm_v1_assistive_rules` (phase 3.4)

Written and committed before the first paid adaptation call. Design audit written before code:
`docs/design/AEA_LOW_ASSISTIVE_RULES.md`. Earlier pre-registrations and results are immutable.

## Hypothesis

LOW failure is partly caused by the coarse granularity of reference-prefix Stage interventions
(phase 3.3b: `resolution_limited` on 3 of 6 referenced tasks with one-action gaps). An LLM
conditioned on failed policy behaviour and a verified successful reference can generate a
parameterised assistive Rules family W(d), d in [0, 1], whose intervention strength varies more
finely than Stage depth, allowing the same empirical controller to locate useful operating points
more often. The manipulated variable is the intervention family only.

## Frozen method

| item | value |
| --- | --- |
| implementation commit | `09bc8b0` (`src/aea` frozen; production diff vs `423011c`: +528 / -8 plus `aea/rules_control.py` 69 lines; 0 new paper-level primitives: MEASURE -> DESIGN INTERVENTION AXIS -> CONTROL OPERATING POINT) |
| arm A | `method_version = "llm_v1_stage_control"` (frozen at `423011c`, unchanged): reference-prefix depth, t_max first, closed-loop integer refinement, 4 -> 8 rule, 30-rollout cap |
| arm B | `method_version = "llm_v1_assistive_rules"`: rich failure + reference evidence -> ONE designer call (`diagnose_and_propose_assistance`: diagnoses, then <= 2 `easier_with_d` Rules families with name / axis / mechanism / why / code) -> validation (released loader + LLM-free smoke at d = 1; identity at d = 0; structural privilege check: no task-specific reference action embedded, no inner `step`, no won / success / reward / terminated shortcut, no Setup replay, no object token present only in the reference) -> per family in order: existing oracle guard at d = 1, 4 -> 8 measurement at d = 1 (too_hard = no leverage -> next family; in_band = accept; too_easy = mirrored bracket inward on [0, 1], <= 4 bisections, lo = largest too_hard dose starting at 0, hi = smallest too_easy dose); a leveraged family that does not land ends the task (no second family gets fresh budget); `dose_order_violation` (a measured too_easy dose below a measured too_hard dose) stops the family; no cascade to Stage, no repair, no second call, no cross-task warm start |
| designer prompt hash | sha256 of contract + environment surface + objective + tool schema: `91a2c5b60d556de3` (`aea.designer` at `09bc8b0`); not tuned on outcomes (the offline check `results/assist_offline.md` fixed one privilege-check false positive only) |
| method constants | `AEAConfig` defaults: B_T (0.4, 0.6), B_L (0.2, 0.8), K 16, accept 3..5 of 8, probe 4 -> 8, cap 30 charged rollouts per task; `impl.max_bisections` 4 |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5 (E3 `policy_qwen()`) |
| designer (arm B only) | DeepSeek V4 Pro, thinking off, temperature 0.7, max_tokens 6144 for this contract (E3 `designer_deepseek()`); 1 call per task; arm A makes none; designer USD reported separately |
| reference (both arms) | `ExpertReference` (ALFWorld handcoded expert from reset, 50 steps, observations + admissible commands + actions, verified `won`), generated ONCE per task in the shared stage and frozen (`runs/e6-ar-shared/privileged_references.jsonl`); exact-reference provenance as in phases 3.1-3.3b |
| substrate | released envharness @ fab7d574; `configs/corpus_aea.yaml`; staged config `configs/alfworld_config_100.yaml` (arm A) |

## Tasks (frozen)

LOW_POOL_3 (`PREREG_LOW_POOL3.md`, `frozen/low_pool3_k16.jsonl`, sha256 `f415aced6c442335`) =
{85, 86, 87, 92, 97, 99, 107, 109, 110, 114, 115, 126, 129}; the eight smallest ids:
**85, 86, 87, 92, 97, 99, 107, 109**; 110, 114, 115, 126, 129 stay untouched. Order ascending.
No substitution.

## Protocol (`scripts/e6_assist.py`; machinery of `e6_refalign.py`)

1. `shared`: per task ONE normal regime estimation (controller schedule, real substrate,
   charged, frozen to `runs/e6-ar-shared`; tasks run in a pool of 4 with 4 episodes each = 16 in
   flight); the task must prospectively enter `zero` (`branch_not_reached` otherwise, never
   replaced); if `zero`, ONE rich reference, frozen.
2. `arms`: arm A and arm B run as two parallel processes (8 episodes in flight each = 16), each
   over the `FrozenSubstrate` (estimate replayed from the shared evidence, no API call, still
   charged; probes real; reference = the frozen instance). Budget: 30 total-equivalent rollouts
   per arm per task including the replayed estimate (10 on a decided zero task); unused budget
   stays unused; no extra budget for promising candidates.
3. `confirm`: K = 16 on every search-accepted environment of either arm (16 in flight),
   evaluation-only, never fed back; p16 with B_L / B_T.
4. `tables`: `scripts/make_tables_e6_assist.py`.

**USD cap 60** over `runs/e6-ar-*` (shared ≈ 8 × 10 × 0.08 ≈ 6, probes ≤ 2 × 8 × 20 × 0.06 ≈
19, confirmations ≤ 16 × 16 × 0.05 ≈ 13, designer < 0.2), checked before every stage and task;
STOP at the cap. Endpoint gate: one ledgered probe call. Concurrency never changes charged
numbers.

## Correctness / privilege gates (any failure = INCONCLUSIVE by protocol failure)

Per arm: runtime `method_version`; `estimate` equals the shared estimate; `reference_id` equals
the shared reference; <= 30 charged search rollouts per task; `reference` events only on `zero`
tasks; provenance-based leakage audit (recorded-hash integrity between the privileged record and
the reference event, and the redacted designer evidence when a designer record exists; arm A's
Setup prefixes equal the recorded reference up to their own depth; arm B writes no Setup prefix
at all; the reference block absent from every kept file; the expert never re-run; arm B's
accepted `rules_code` passes the structural privilege check by construction). Arm A: no designer
call, candidate source `control`, first probe = t_max, no depth probed twice. Arm B: <= 1
designer call per task, <= 2 valid families, `mode = assist`, no Stage candidate / family event
(no cascade), first probe of every family at d = 1, no guard `by_construction`. `src/aea`
unchanged from `09bc8b0`.

## Outcomes

Primary: **K16-confirmed learnable deliveries** = search-accepted (3..5 of 8) AND K16 p16 in
B_L = [0.2, 0.8], per arm, paired. Secondary per arm: search-accepted, K16 in B_T, leverage
(>= 1 probed intervention with >= 1 success), leverage -> search-accept and -> K16 conversion,
budget, probe rollouts, designer USD; arm B additionally valid-family rate, solvability rate,
d = 1 leverage rate, `dose_order_violation`, `no_valid_proposal`, `uncertified`, `exhausted`; arm
A additionally `resolution_limited` and the final integer gaps. Resolution metric (descriptive):
per arm, the number of tasks with at least one intermediate probe (0 < successes < n) along the
same family / axis. Six-level paired classification: reference_unavailable < no_leverage <
leveraged_unresolved < search_accepted_k16_failed < k16_confirmed_learnable <
k16_confirmed_target; A better / tie / B better; no significance test at n = 8.

## Decision rule (exactly one; applied mechanically, in this order)

1. INCONCLUSIVE: a gate fails, fewer than 6 tasks prospectively `zero`, fewer than 4 verified
   references, or a provider / infrastructure / budget interruption. Never for weak performance.
2. ASSISTIVE_RULES_SUPPORTED: arm B K16-confirmed learnable >= 3 AND > arm A's.
3. RULE_GENERATION_FAILURE: arm B upstream failures (`no_valid_proposal` + `uncertified` +
   `no_leverage` + `dose_order_violation`) on more than half of the referenced tasks.
4. ASSISTIVE_RULES_HAVE_LEVERAGE_BUT_CONTROL_LIMITED: arm B K16-confirmed < 3, arm B leverage on
   more than half of the referenced tasks, and arm B has strictly more tasks with an
   intermediate probe than arm A.
5. ASSISTIVE_RULES_NOT_SUPPORTED: otherwise.

The threshold of 3 confirmed deliveries, the B_L confirmation and the classification are not
changed after the results. No LLM repair, refinement round, cascade, router, meta-selector, family
memory, prompt optimisation, learner routing or skill learning follows from this phase. After the
run: report (`results/e6_low_assistive_rules.md`), LOG, commit, push, STOP.
