# PREREG_LOW_POOL2 — fresh behavioural pool (phase 3.3a, part A)

Written and committed before any policy rollout of this pool. Pool construction is purely
behavioural classification of the current policy on ORIGINAL environments: no LLM designer, no
reference, no Stage, no Rules, no adaptation, no skill learner.

| item | value |
| --- | --- |
| branch / worktree | `aea-llm-vnext`, `../EnvJudge-aea-llm`; method code `src/aea` unchanged from `48dc028` (no method code is used beyond the substrate and the K16 helper) |
| task ids | **30, 31, ..., 79** (50 tasks): the next 50 smallest ids after the exclusion set {0..29} of `USED_TASKS_AUDIT.md`; the universe is the bridge's seed-based selection over the train split (`~/eh_alfworld_data`, `split train`, `repetition_threshold 0`), identical to E2/E3 |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5, max_tokens 2048, `retry` up to 10 attempts (E3's `policy_qwen()`, unchanged); task prompt from `configs/corpus_aea.yaml`; 50 policy steps per episode |
| environment | released envharness @ fab7d574 ALFWorld bridge, original environment (empty `Candidate()`), the corpus reset options |
| K | 16 rollouts per task (E3's `_k16` helper: `budget = eval`, one `rollout` ledger row per episode) |
| error handling | an episode with `Trace.error` counts as an error and is not a success; no re-run in this phase (an errored task is `invalid` for LOW purposes, as in the shared K16) |
| concurrency | 16 episodes in flight (the E3 total-eval-concurrency cap), tasks sequential |
| classes | `zero` = 0/16 with 0 errors; `middle` = 1..15 of 16 with 0 errors; `saturated` = 16/16 with 0 errors; `invalid` = any error |
| LOW definition | 16 valid rollouts, 0 successes, 0 errors (`zero`) - fixed before measurement |
| expected spend | measured cost per original-environment rollout: USD 0.079 (E2 shared, mostly 50-step failures) and 0.027 (E3 shared, mostly successes); 800 rollouts at an E2/E3-like mix (about 27 % zero) ≈ USD 35; all-zero worst case ≈ USD 64 |
| USD cap | **60** over `runs/e6-pool2-*`, checked before the run and every 5 tasks; STOP at the cap, report the partial pool, no raise |
| output | `runs/e6-pool2-k16/{confirm.jsonl, confirm_summary.json, ledger}` frozen to `experiments/alfworld_e6/frozen/low_pool2_k16.jsonl` (one row per task: task_id, successes, n, errors, p16, class) |
| next step | `LOW_POOL_2` = all `zero` tasks; if fewer than 6: report POOL_INSUFFICIENT and STOP (no automatic expansion); else the six smallest ids are the phase-3.3a characterisation sample (separate `PREREG_STAGE_PROFILE.md` before any Stage probe); the remaining `zero` tasks stay untouched for future prospective tests |

HIGH is not run in this phase; the number of `saturated` fresh tasks is reported as a pool
statistic only.
