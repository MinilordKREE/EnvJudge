# PREREG_LOW_POOL3 — fresh behavioural pool (phase 3.4, part A)

Written and committed before any policy rollout of this pool. Pure behavioural classification of
the current policy on ORIGINAL environments: no designer, no reference, no Stage, no Rules, no
adaptation. Identical protocol to `PREREG_LOW_POOL2.md`.

| item | value |
| --- | --- |
| task ids | **80, 81, ..., 129** (50 tasks): the next 50 smallest ids after the programmatically derived exclusion set 0..79 (`USED_TASKS_AUDIT_POOL3.md`); ALFWorld bridge seeds over the train split (`~/eh_alfworld_data`, `split train`, `repetition_threshold 0`) |
| method code | `src/aea` unchanged from `423011c` (only the substrate and the K16 helper are used) |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5, max_tokens 2048, retry up to 10 attempts (E3 `policy_qwen()`); corpus task prompt; 50 policy steps |
| environment | released envharness @ fab7d574 ALFWorld bridge, original environment (empty `Candidate()`) |
| K | 16 per task (E3 `_k16`; `budget = eval`) |
| error handling | an episode with `Trace.error` is an error, not a success; no re-run; any error -> `invalid` |
| concurrency | 16 episodes in flight, tasks sequential (the owner asked for more parallelism; the K16 stage already ran at the 16-in-flight cap and the provider throttles above it, so the pool keeps 16 and the adaptation stages of this phase run the two arms as parallel processes) |
| classes | `zero` 0/16 and 0 errors; `middle` 1..15; `saturated` 16/16; `invalid` any error |
| LOW definition | 16 valid rollouts, 0 successes, 0 errors (`zero`) |
| expected spend | pool 2 measured USD 0.048 per rollout -> ≈ USD 38 for 800 rollouts |
| USD cap | **60** over `runs/e6-pool3-*`, checked before the run and every 5 tasks; STOP at the cap, no raise |
| output | `runs/e6-pool3-k16` frozen to `experiments/alfworld_e6/frozen/low_pool3_k16.jsonl` |
| next step | `LOW_POOL_3` = all `zero` tasks; fewer than 8 -> STOP (no automatic expansion; a new pre-registration is required); else the eight smallest ids are the phase-3.4 paired sample (separate `PREREG_LOW_ASSISTIVE_RULES.md`), the remaining zero tasks untouched |
