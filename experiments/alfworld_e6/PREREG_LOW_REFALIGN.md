# PREREG_LOW_REFALIGN — paired LOW-only comparison: `llm_v1` vs `llm_v1_refalign` (phase 3.2)

Written and committed before the first paid call of this experiment (the commit SHA of this file
and the method commit are recorded in `scripts/e6_refalign.py` and in every run manifest). Smoke 1
(`PREREG_SMOKE.md`) and smoke 2 (`PREREG_SMOKE2.md`) and their results are immutable historical
records. This is a mechanism-isolation experiment on the LOW side only; HIGH is not run.

## Hypothesis (written before implementation; docs/design/HARNESSEVOLVE_VS_AEA_LOW.md)

The current LOW designer fails partly because an action-only successful reference does not
provide explicit credit assignment. Supplying a rich successful observation/action trajectory and
requiring explicit failed/reference divergence diagnosis will improve the quality of Stage
selection, without changing the Stage intervention or the empirical acceptance controller.

## Frozen method

| item | value |
| --- | --- |
| branch / worktree | `aea-llm-vnext`, `../EnvJudge-aea-llm` |
| method commit | `48dc028` (`src/aea` frozen; the drivers record the tracked `src/aea` tree hash with a `+DIRTY` marker if it differs) |
| arm A method | `method_version = "llm_v1"` (the frozen LOW of smokes 1 and 2: direct Stage selection from failures + the action-only reference) |
| arm B method | `method_version = "llm_v1_refalign"` (identical to `llm_v1` on band and saturated by code path; LOW: rich observation/action reference + one tool call returning diagnoses then <= 2 reference-grounded stages) |
| method constants | `AEAConfig` defaults: B_T (0.4, 0.6), B_L (0.2, 0.8), K 16, accept 3..5 of 8, probe 4 -> 8, cap 30 charged policy rollouts per task; `impl` defaults |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5 (E3's `policy_qwen()`, unchanged) |
| designer (both arms) | DeepSeek V4 Pro, thinking off, temperature 0.7 (E3's `designer_deepseek()`); arm A 2048 output tokens (`design_low`, unchanged), arm B 3072 (`design_low_refalign`, the diagnosis fields need room); one call per arm per task; <= 2 proposals |
| reference source (both arms) | the ALFWorld handcoded expert run ONCE per task from the reset state through the locked in-process session (`ExpertReference`, 50 steps), verified by the simulator's success flag, recorded with observations, admissible commands and actions; arm A sees its action-list projection, arm B its observation/action trajectory (the same instance, same `reference_id`) |
| substrate | released envharness @ fab7d574; `configs/corpus_aea.yaml`; staged config `configs/alfworld_config_100.yaml` |
| designer prompts | as committed at `48dc028`; not tuned on the offline diagnostic (`results/refalign_offline.md`, descriptive only) |

## Tasks (frozen; fresh)

Same frozen pool as the smokes (`experiments/alfworld_e6/frozen/`). LOW-eligible = original
shared K16 successes 0, n 16, errors 0: {8, 9, 10, 11, 14, 17, 20, 27}. After excluding every
previous LOW smoke task (8, 9, 10, 11, 14, 17) the pool holds fewer than six tasks, so per the
brief ALL remaining eligible tasks are used and the exact count is pre-registered:

| task | source | successes / n | errors | p16 |
| --- | --- | --- | --- | --- |
| 20 | e2-shared | 0 / 16 | 0 | 0.0 |
| 27 | e2-shared | 0 / 16 | 0 | 0.0 |

**n = 2 tasks.** No substitution. Order 20 then 27.

## Shared-evidence protocol (`scripts/e6_refalign.py`)

1. `shared`: per task, ONE normal current-policy regime estimation with the controller's own
   estimator schedule (4, then batches of 2, early stop, K = 16) on the real substrate; every
   rollout charged and ledgered under `runs/e6-refalign-shared` and frozen to disk. The task must
   prospectively enter `zero`; a task that does not is `branch_not_reached` and is not replaced.
   If it is `zero`, ONE rich expert reference is recorded in one session and frozen to
   `runs/e6-refalign-shared/privileged_references.jsonl` (privileged, audit-side only).
2. `arms`: arm A = `Controller(llm_v1)` on `runs/e6-refalign-A`, arm B =
   `Controller(llm_v1_refalign)` on `runs/e6-refalign-B`, both over a `FrozenSubstrate` that
   replays the frozen estimate rollouts for the `estimate` phase (no API call; the controller
   still charges them, so both arms see exactly the same 30-rollout cap and the same seeded
   failure sample) and delegates the Stage probes to the real substrate; the reference provider
   returns the frozen instance. Everything after proposal generation is the unchanged controller:
   `compile_prefix`, oracle solvability guard, 4 -> 8 probe, accept iff 3..5 of 8, cap.
3. `confirm`: K = 16 current-policy rollouts on every accepted Stage of either arm
   (evaluation-only, never fed back), p16 with B_L / B_T membership.
4. `tables`: `scripts/make_tables_e6_refalign.py`.

Order within the run: `shared` for both tasks, then for each task arm A then arm B, then confirm.
Task concurrency 1, rollout batch concurrency 4. USD cap 15 over every `runs/e6-refalign-*`
ledger (shared estimation, probes of both arms, designer calls, confirmations; the offline
diagnostic's `runs/e6-refalign-offline` USD 0.079 is included by the glob), checked before every
stage and task; STOP at the cap, no raise. Endpoint gate: one ledgered probe call.

## Correctness gates (any failure = INCONCLUSIVE by protocol failure, STOP, no repair)

Computed per arm by `make_tables_e6_refalign.py::gates`: runtime `method_version` equals the
arm's version in the manifest and on every designer record; the arm's `estimate` event equals the
shared estimate (regime, p_hat, n) and its `reference_id` equals the shared reference; <= 1
designer call per task; <= 2 parsed proposals; <= 30 charged search rollouts per task; every
`stage_candidates` event `source = designer` (no midpoint/end fallback); `reference` events only
on `zero` tasks; arm B `mode = refalign` and arm A `mode = direct` on every zero task with a
reference; exact-reference leakage audit per arm (recorded-hash integrity across the privileged
record, the `reference` event and the redacted designer record; no candidate prefix carrying
`reference[k:]` past a selected cut; the reference block and the rich trajectory absent from every
kept file; designer records redacted; the expert never re-run); `src/aea` unchanged from `48dc028`.

## Outcomes

Primary: number of tasks delivering an ACCEPTED Stage (the existing current-policy criterion),
per arm. Secondary (per arm, over prospectively zero tasks): valid-proposal rate, certified-Stage
rate, unlock rate (>= 1 policy success in a probe), overshoot rate (`too_easy`), dead rate,
accepted rate, probe rollouts per accepted Stage. Paired ordinal outcome per task with
dead < unlock-but-outside-target < accepted: A better / tie / B better (diagnostic). Arm B
diagnosis usage: valid failure step, valid reference step, proposals linked to a diagnosis,
selected cut before / at / after the diagnosed reference step. Natural-language diagnoses are
reported verbatim, never scored by an LLM.

## Conclusion rule (exactly one; applied mechanically)

- INCONCLUSIVE: fewer than 2 tasks prospectively enter `zero`, or a correctness gate fails, or
  an infrastructure / provider / budget interruption. Never for ordinary poor performance.
- REFERENCE_ALIGNMENT_SUPPORTED: all gates pass AND arm B accepted >= 2 AND arm B accepted >
  arm A accepted.
- CREDIT_ASSIGNMENT_HELPS_BUT_CONTROL_REMAINS_LIMITING: not SUPPORTED, all gates pass, arm B
  has strictly more paired wins than arm A (ordinal above), and arm B accepted < 2.
- NO_EVIDENCE_REFERENCE_ALIGNMENT_HELPS: otherwise (all gates pass).

With n = 2, SUPPORTED requires arm B to accept both tasks; this is pre-registered as is. No
method patch is derived from the result; no neighbouring-cut search, assistive Rules or
reference enrichment is added afterwards in this phase. After the run: report
(`results/e6_low_refalign.md`), LOG, commit, push, STOP. Not started: full E6, E6-SL, the next
LOW hypothesis.
