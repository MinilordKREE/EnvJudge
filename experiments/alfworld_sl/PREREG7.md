# E1-SL v2 pre-registration — frozen 2026-09-07 (spec docs/spec/AEA_v2.md; aea @ cfc292f; supersedes PREREG6, under which no rollout ran)

Budgets: search = 30 policy rollouts / task / round, hard cap, every adaptation arm; confirm = 16 / accepted environment, evaluation only,
never written back; train = the search trajectories of accepted environments (single-success induction uses the shortest success),
no extra sampling. Errored rollouts are refunded and counted as infra_errors. Designer calls are logged, not charged.
Bands: B_T = [0.4, 0.6] (accept iff 3–5/8); B_L = [0.2, 0.8] (learnable iff 4–12/16 at confirmation).
Statuses reported per task: band | accepted_knob | accepted_stage | frozen_no_leverage | exhausted | unresolved |
unresolved_budget_limited | budget_cap_hit | no_failed_trajectory; hand-off only on exhaustive unresolved (A+H).

Definitions
- Learnable environment: accepted environment or band task with p̂₁₆ ∈ B_L under the round's policy. Secondary: B_T.
- Unlocked zero task: task with estimated regime zero whose accepted environment is learnable.
- Held-out gain: released-eval success (3 seeds) of the backbone with the arm's bank_r minus N.
- Rounds: policy_r = backbone + bank_{r−1} injected through PolicySpec.task_prompt with the eval's retrieval (top-5 MMR); task set fixed.

Claims
- C1 (round 1): learnable environments per 1,000 charged search rollouts — A > R and A > G (point estimates, task-level bootstrap CIs).
  Reported alongside: unlocked zero tasks, frozen/exhausted/unresolved counts, family-of-origin of every accepted A environment.
- C2 (each round): held-out ID and OOD — A ≥ R and A ≥ O (point) every round, and at least one round with A − R having a 95% CI
  excluding 0 on ID or OOD. A+H reported as a separate row, never pooled with A.
- C3 (rounds 2–3): A's learnable-environment count at round 3 ≥ 0.7 × round 1 and A's held-out gain non-decreasing; R's round-3
  count and gain reported against its round 1.
- Ablations (round 1): A-ex and G+ against A and G; supplementary released-mode induction row.

Stop rule after round 1: if A's held-out ID and OOD are both below R's by more than 0.03 (point) or A's C1 rate is below R's,
rounds 2–3 do not run until a diagnosis and a new pre-registration.
Reproduction sanity (Phase 0b): our EnvRigger-released reproduction must reproduce the SIGN of EnvHarness Table 2's ALFWorld
gains (orig > N on ID; EnvRigger > orig on OOD) or the gap is explained before round 1.
Backbone rule (Phase 0b): Flash-Lite corpus episode > USD 0.10 → fallback backbone for all arms; N = 50 if the projection ≤ USD 450 else 30.
Budget: E1-SL hard cap USD 500, soft gate 400; Phase 0 ≤ 60.
