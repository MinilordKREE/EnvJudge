# PREREG_LOW_STAGE_CONTROL — paired LOW-only comparison: `llm_v1_refalign` vs `llm_v1_stage_control` (phase 3.3b)

Written and committed before the first paid adaptation call. Tests the control hypothesis
motivated by phase 3.3a (`results/stage_profile.md`, STAGE_AXIS_SUPPORTS_CONTROL): given a
verified successful reference trajectory, can current-policy feedback control the amount of
reference-prefix assistance and locate a useful LOW operating point within the existing per-task
rollout budget? Design audit: `docs/design/AEA_LOW_STAGE_CONTROL.md` (written before code).
All earlier pre-registrations and results are immutable.

## Frozen method

| item | value |
| --- | --- |
| branch / worktree | `aea-llm-vnext`, `../EnvJudge-aea-llm` |
| method commit | `423011c` (`src/aea` frozen; `llm_v1`, `llm_v1_refalign`, `v0.4` unchanged, HIGH / MID identical across the llm variants by shared code path, asserted by tests) |
| arm A | `method_version = "llm_v1_refalign"`: one designer call, rich reference + explicit diagnosis, <= 2 reference-grounded Stage cuts, existing compile / oracle guard / 4 -> 8 probe (the current semantic Stage-selection baseline, unchanged since `48dc028`) |
| arm B | `method_version = "llm_v1_stage_control"`: no designer call for the cut; the SAME exact reference defines the family E_t; t_max = deepest exactly replayable NON-terminal prefix (simulator-side, never charged); first probe t_max; too_hard at t_max -> `no_stage_leverage`; too_easy -> hi = t_max, lo = 0 (the estimate's reset), then mid = floor((lo + hi) / 2) with the same 4 -> 8 measurement (0/4 too_hard, 4/4 too_easy, else top up to 8: 3..5 accept, 0..2 too_hard, 6..8 too_easy); too_hard raises lo, too_easy lowers hi; a depth is never probed twice; hi - lo == 1 without an in-band point -> `resolution_limited`; a measured too_easy depth below a measured too_hard depth -> `nonmonotonic_profile` (refinement stops, nothing repaired); existing oracle guard on every probed depth (`invalid_stage` if it fails) |
| method constants | `AEAConfig` defaults: B_T (0.4, 0.6), B_L (0.2, 0.8), K 16, accept 3..5 of 8, probe 4 -> 8, cap 30 charged rollouts per task |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5 (E3 `policy_qwen()`) |
| designer (arm A only) | DeepSeek V4 Pro, thinking off, temperature 0.7 (E3 `designer_deepseek()`); 1 call per task; arm B makes 0 cut-selection calls (designer cost reported separately, not equalised) |
| reference (both arms) | `ExpertReference` (ALFWorld handcoded expert from reset, 50 steps, observations + admissible commands + actions, verified `won`), generated ONCE per task in the shared stage and frozen (`runs/e6-sc-shared/privileged_references.jsonl`); both arms receive the same instance |
| substrate | released envharness @ fab7d574; `configs/corpus_aea.yaml`; staged config `configs/alfworld_config_100.yaml` |

## Tasks (frozen; verified programmatically from the frozen artifacts)

LOW_POOL_2 minus the six phase-3.3a characterisation tasks = **62, 66, 67, 70, 71, 73, 78, 79**
(all 0 / 16 with 0 errors in `frozen/low_pool2_k16.jsonl`, never rolled out since). Order
ascending. No substitution.

## Shared-evidence protocol (`scripts/e6_stage_control.py`, the machinery of `e6_refalign.py`)

1. `shared`: per task ONE normal regime estimation (controller schedule, real substrate,
   charged, frozen to `runs/e6-sc-shared`); the task must prospectively enter `zero`
   (`branch_not_reached` otherwise, never replaced); if `zero`, ONE rich reference, frozen.
2. `arms`: per task arm A then arm B over the `FrozenSubstrate` (estimate replayed from the
   shared evidence with no API call but still charged, so both arms see the same 30-rollout cap
   and the same seeded failure sample; probes real; reference = the frozen instance). Budget:
   30 total-equivalent rollouts per arm per task including the replayed estimate (10 on a
   decided zero task), i.e. at most 20 Stage-probe rollouts per arm; unused budget stays unused.
3. `confirm`: K = 16 on every accepted Stage of either arm, evaluation-only (p16 with B_L / B_T).
4. `tables`: `scripts/make_tables_e6_stage_control.py`.

Task concurrency 1, rollout batch concurrency 4. **USD cap 50** over `runs/e6-sc-*` (shared
estimation ≈ 8 × 10 × 0.079 ≈ 6, probes ≈ 2 × 8 × 20 × 0.05 ≈ 16 worst case, confirmations
≤ 16 × 16 × 0.05 ≈ 13, designer < 0.1), checked before every stage and task; STOP at the cap.
Endpoint gate: one ledgered probe call.

## Correctness gates (any failure = INCONCLUSIVE by protocol failure)

Per arm (as PREREG_LOW_REFALIGN): runtime `method_version`; `estimate` event equals the shared
estimate; `reference_id` equals the shared reference; <= 1 designer call per task (arm A) and
none (arm B: no `designer_calls.jsonl`); <= 2 parsed proposals (arm A); <= 30 charged search
rollouts per task; no midpoint / end fallback (`stage_candidates` source `designer` for A,
`control` for B); `reference` events only on `zero` tasks; arm A `mode = refalign`; arm B first
probe = t_max and no depth probed twice; provenance-based leakage audit per arm (recorded-hash
integrity; every Setup prefix attributed through the run's own candidate ids: a reference /
control prefix equals the recorded reference up to ITS OWN depth plus the compiler's `look`, a
failure prefix is the policy's own actions; reference block absent from every kept file;
designer records redacted; the expert never re-run); `src/aea` unchanged from `423011c`.

## Outcomes

Primary: number of tasks delivering an ACCEPTED Stage (3..5 of 8) per arm, paired. K16
confirmation reported separately (successes / 16, B_L, B_T). Secondary per arm: accepted,
K16-confirmed learnable, leveraged-but-outside-target (>= 1 probe success, not accepted), dead /
no leverage, budget, resolution_limited, nonmonotonic_profile, invalid Stage, probe rollouts,
designer USD; conversion = accepted / tasks with Stage leverage (>= 1 probed Stage with >= 1
success). Arm B additionally: T, t_max, t_max verdict distribution (the d = 1 test of the
original LOW intuition), unique cuts probed, final [lo, hi], accepted t and d = t / t_max.
Paired ordinal per task: dead < leveraged-outside-target < accepted < K16-confirmed accepted
(B_L); A better / tie / B better; no significance test at n = 8.

## Decision rule (exactly one; applied mechanically, evaluated in this order)

1. INCONCLUSIVE: a correctness gate fails, fewer than 6 of the 8 tasks prospectively enter
   `zero`, or a provider / infrastructure / budget interruption. Never for weak performance.
2. AXIS_ORDERING_BREAKS: >= 3 of the zero tasks end `nonmonotonic_profile`. (Under the bracket
   update rule this outcome is structurally unreachable, see the design audit; the count is
   reported and the rule kept as written.)
3. STAGE_CONTROL_SUPPORTED: arm B accepted >= 3 AND arm B accepted > arm A accepted (and not 2).
4. CONTROL_IMPROVES_BUT_RESOLUTION_LIMITS: arm B accepted < 3, arm B has strictly more paired
   wins than arm A or a strictly higher conversion, and >= 2 arm-B tasks end
   `resolution_limited`.
5. STAGE_CONTROL_NOT_SUPPORTED: otherwise.

The thresholds (>= 3 accepted, resolution_limited definition, K16 confirmation) are not changed
after the results. No further LOW mechanism, controller refinement or full E6 follows from this
phase; after the run: report (`results/e6_low_stage_control.md`), LOG, commit, push, STOP.
