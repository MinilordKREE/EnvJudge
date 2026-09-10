# PREREG9 — E3 first-layer main table, Qwen3-8B, ALFWorld seeds 0–29 (frozen 2026-09-11)
Setting as in §1; aea v0.2 (docs/spec/AEA_v0.2.md) with persistent priors; EnvRigger released and App-G configs unchanged
except client blocks and paths; cap 30 per task per arm; K = 16 confirmations, never written back; B_L = [0.2, 0.8].

Definitions: learner-facing set = the environments an arm hands to the learner (A: kept tasks + accepted transformed
environments; R, G: accepted transformed environments). Learnable = p̂₁₆ ∈ B_L. Charged rollouts = every policy rollout
of the arm's search (estimate, validation, probes); designer calls are logged, not charged, for every arm.

Claims
- E3-1 (primary): learner-facing learnable environments per 1,000 charged rollouts — A > G and A > R (point estimates,
  task-level bootstrap CIs reported).
- E3-2 (band preservation): the number of originally-learnable tasks still learnable in the learner-facing set — A ≥ G
  and A ≥ R.
- E3-3 (saturated subset): learnable transformed environments per 1,000 on tasks with original p̂₁₆ > 0.8 — A ≥ G.
- E3-4 (zero subset): unlocked zero tasks — A ≥ G (E2 Phase D anchor: 2 vs 2; reported, not a gate).
- H100 (control): if a task's 100-step original-start success is ≥ its staged p̂₁₆, that unlock is attributed to horizon,
  not to staging, and the paper's zero-side claim is restated accordingly.

Stop rule for downstream: if E3-3 fails (A below G on the saturated subset) the saturated side returns to design before
any skill or RL evaluation; if E3-1 fails, the downstream columns are not run.

Budget: E3 hard cap USD 330 (shared originals ≈ 25, R ≈ 40, G ≈ 60, A ≈ 90, confirmations ≈ 90, H100 ≈ 10, margin 15).
Extension: seeds 30–49 may be added later under the same pre-registration by resuming A's persisted priors; tables are
regenerated for N = 50 and reported next to N = 30.
