# PREREG8-Z — E2 step 1: zero side, Qwen3-8B, ALFWorld (frozen 2026-09-09)

```
# PREREG8-Z — E2 step 1: zero side, Qwen3-8B, ALFWorld (frozen 2026-09-09)

Policy = Qwen3-8B via OpenRouter (provider pinned to alibaba, reasoning disabled, price 0.117/0.455 USD/M; the
E1-pilot client path). Designer = DeepSeek V4 Pro, thinking disabled, for EVERY arm (same generator for all arms).
Tasks = the 10 tasks of seeds 0–29 whose E1-pilot P1 regime map (K=16, corpus policy) gave p̂₁₆ = 0 or < 0.2:
zero {8, 9, 10, 11, 14, 17, 20, 27}, marginal-low {the two tasks with 1–3/16}. Same tasks for every arm.
Search cap = 30 policy rollouts per task per arm (search budget); designer calls logged, not charged.
Confirmation = K = 16 policy rollouts per accepted environment and on each task's original environment (shared),
budget confirm, never written back. Staged environments use the 100-step config (stage_budget = 100).
Learnable = p̂₁₆ ∈ [0.2, 0.8]. Unlocked = a task with shared original p̂₁₆ = 0 (this run) whose accepted
environment is learnable.

Arms
- Z (ours, zero side): the aea controller as in Round 1 (estimation → for zero: candidates from the policy's own
  failed rollouts, compiled-Setup certification with expert ×3, probes latest-first 4 each within the remaining
  budget, accept the latest learnable state). Tasks that estimate as band/saturated in this run are handled by the
  controller's normal path but reported separately (regime drift).
- G (EnvRigger two-sided): released orchestrator, App-G config (generic prompt, target band [0.4, 0.6]), K = 5, ≤ 5 attempts.
- R (EnvRigger released ALFWorld config, fail-targeted): as published.
- Z-full (reference, uncharged to the claim): Z's probe walk continued over ALL certified candidates after the cap,
  to measure what the cap costs (reported separately; not part of C).

Claims
- Z1: learnable environments per 1,000 charged search rollouts on the 10 tasks — Z > G and Z > R (point; CIs).
- Z2: unlocked zero tasks — Z ≥ 3 of the tasks whose shared p̂₁₆ = 0 (anchor: P5.1 found 3/8 without a cap), and
  Z's count ≥ G's count.
- Z3 (descriptive): Z's learnability profiles per task (late-learnable / poisoned / dead), the certified-state
  counts, and G's/R's accepted environments on the same tasks with their p̂₁₆.
Kill: Z unlocks ≤ 1 task or fewer than G → the zero-side claim is dead on this benchmark/agent; report and stop E2.

Budget: step 1 ≤ USD 90 (projection: Z 10×30 + G 10×30 + R ~10×10 + Z-full ≤ 10×24 ≈ 940 rollouts ≈ USD 53;
confirmations ≤ 30 envs × 16 + 10 originals × 16 ≈ USD 36).
```

Resolution of the task set from `docs/pilots/e1pilot/results/e1pilot/qwen_p16.csv` (p16_qwen): zero = {8, 9, 10, 11, 14, 17, 20, 27}
(0/16); marginal-low = {0, 18} (1/16 each; no other task below 0.2). Tasks = {0, 8, 9, 10, 11, 14, 17, 18, 20, 27}.
