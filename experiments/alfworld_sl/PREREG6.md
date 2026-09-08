> **SUPERSEDED (2026-09-07).** This pre-registration never governed a rollout. The pre-registration of record for E1-SL is `PREREG7.md` (spec `docs/spec/AEA_v2.md`); see `PREREG6_SUPERSEDED.md` for the five conflicts.

# E1-SL pre-registration — frozen 2026-09-07 (inputs: pilots through P5 @ 441310d)

Setting: ALFWorld; envharness @ fab7d574; backbone Gemini 3.1 Flash-Lite as designer, policy and consumer for all arms
(fallback: Qwen3-8B policy + DeepSeek V4 Pro designer for all arms, decided at Phase 0 by the cost rule); train tasks
seeds 0..N−1 (N ∈ {30, 50} by the Phase-0 projection); rounds 1–3; per-task per-round rollout cap 30 for R, G, A, O;
single-success induction for all arms; released eval on full ID/OOD splits × 3 seeds.

Definitions
- Learnable environment: an accepted environment (or unchanged band task) with p̂₁₆ ∈ [0.2, 0.8] under the round's policy
  (post-hoc confirmation, uncharged). Secondary: [0.4, 0.6].
- Rollouts: policy episodes charged to the arm during adaptation (estimation, validation, probes, confirmations that the
  arm itself performs); designer calls are logged separately.
- Held-out gain: success rate on the released ID / OOD splits (3 seeds) of the backbone with the arm's bank_r, minus N.

Claims
- C1 (round 1): learnable environments per 1,000 charged rollouts — A > R and A > G (point estimates; task-level bootstrap
  CIs reported). Also reported: unlocked zero tasks, frozen saturated tasks, hand-off count.
- C2 (each round): held-out ID and OOD — A ≥ R and A ≥ O (point) at every round, and at least one round in which A − R
  has a 95% CI excluding 0 on ID or OOD.
- C3 (rounds 2–3): A's learnable-environment count at round 3 ≥ 0.7 × its round-1 count and A's held-out gain is
  non-decreasing across rounds; R's round-3 count and gain are reported against its round-1 values (EnvHarness App. F.2
  reports ~1/3 of tasks producing nothing by round 3).

Stop rule after round 1: if A's held-out ID and OOD are both below R's by more than 0.03 (point), or A's learnable
environments per 1,000 rollouts are below R's, rounds 2–3 are not run until the cause is diagnosed and a new
pre-registration is filed.

Budget: E1-SL hard cap USD 500, soft gate 400; Phase 0 ≤ 60.
Reproduction sanity: our EnvRigger-released reproduction must reproduce the SIGN of EnvHarness Table 2's ALFWorld gains
(orig-skills > nobank on ID; EnvHarness > orig on OOD) or the gap is explained before round 1.
