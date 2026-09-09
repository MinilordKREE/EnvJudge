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

---
## Amendment 1 — 2026-09-08 (owner decision at the Phase 0b gate; committed before any round-1 rollout; text above unchanged)

Bank protocols (the text above ties "train = the search trajectories of accepted environments" to "learnable = accepted environment
or band task" without saying whether band tasks enter the bank; E0's R used the Table 2 protocol, transformed environments only):

```
Protocol T2 (primary for C2): bank = single-success over the arm's TRANSFORMED environments only
  (R/G: accepted candidates; A: knob + stage envs). Unchanged tasks enter no arm's bank; O = all tasks unchanged.
Protocol U (reported): bank = T2 ∪ unchanged tasks with ≥ 1 success during the arm's own search
  (R/G: skipped and all-rejected tasks; A: band, frozen, exhausted tasks).
C1 primary counts learnable TRANSFORMED environments per 1,000 search rollouts; secondary adds unchanged band tasks.
Both induction modes reported for every arm in round 1; single-success primary, released paired-diff + subset as the baseline-protocol row.
```

T2 is the published comparison and isolates the transformation itself; U answers "what the learner gets with the whole environment set".

Budget: E1-SL hard cap USD 560, soft gate USD 500 (covers the Phase 0b diagnosis and the second-induction-mode evaluations of round 1).
N = 30 and the Flash-Lite backbone are confirmed by the Phase 0b rules above.

---
```
# PREREG7 Amendment 2 (2026-09-08; owner decisions at the Phase-0b gate; no Round-1 rollout has run)

A2.1 Protocol per comparison (supersedes Amendment 1's single primary):
  - C1 (learnable transformed environments per 1,000 search rollouts): Protocol T2 for every arm.
  - C2 A vs O: Protocol U (both banks cover every task with ≥ 1 success; the comparison isolates what the
    transformed items add on the same base).
  - C2 A vs R (and vs G): reported under BOTH T2 and U; the pre-registered inequality A ≥ R is evaluated under U,
    T2 is the transformation-only isolation.
  - Definitions unchanged: T2 = single-success induction over the arm's transformed environments only;
    U = T2 ∪ single-success over the arm's unchanged tasks with ≥ 1 success during its own search
    (R/G: skipped and all-rejected tasks; A-family: band, frozen, exhausted tasks; O: all tasks).

A2.2 Evaluation seeds:
  - Primary arms A, R, O, N: 6 seeds (0, 1000, 2000, 3000, 4000, 5000), full ID (140) + OOD (134).
  - Ablation arms G, G+, A-ex, A+H: 3 seeds (0, 1000, 2000).
  - Seed-extension rule (sequential, pre-registered): after Round 1, if on ID either A − R (U) or A − O (U) has
    |gap| between 1 and 2 SE (pooled normal SE), A, R, O, N are extended to 12 seeds (6000…11000) before the
    stop rule is applied. No other extension.

A2.3 Second induction mode: the released Stage 2 verbatim (cascade + automatic mode) is run for A and R only
  (row "released-protocol"); all other arms single-success only.

A2.4 Concurrency: total eval concurrency ≤ 16; corpus arms ≤ 8 tasks in parallel.

A2.5 Budget: E1-SL hard cap USD 560, soft gate USD 500 (Phase 0 spent USD 99.08 under owner-approved diagnostics).

Standing differences recorded for the paper: backbone (Gemini 3.1 Flash-Lite via OpenRouter, Google AI Studio pin,
no thinking parameter) and N = 30 train tasks; EnvHarness Table 2's OOD sign was not reproduced in three attempts.
```

---
```
# PREREG7 Amendment 3 (2026-09-09; corrections after Round-1 review; no Round-2 rollout has run)
A3.1 Protocol U, corrected definition: U = T2 ∪ single-success induction over EVERY task with ≥ 1 success during the
  arm's own search, regardless of the task's final status (band, frozen_no_leverage, exhausted, budget_cap_hit,
  unresolved_budget_limited, skipped, all_rejected). Amendment 1's status enumeration omitted budget_cap_hit and
  excluded 22 of A's tasks; R_U and O_U were built under the corrected definition already. A_U, Aex_U, AplusH_U are
  re-induced and re-evaluated; the Round-1 versions are archived as *_U_v1.
A3.2 Bank-size controls (added): (a) placebo bank — 5 syntactically valid, task-irrelevant items in the released item
  format, evaluated on 6 seeds; (b) item-matched evaluation — every Round-1 bank subsampled (seed 20260916) to 8 items
  and to 20 items (banks with fewer items are evaluated at their full size and flagged), 3 seeds each.
  C2 differences are reported at matched item counts alongside the full-bank numbers; a bank whose gain is not
  distinguishable from the placebo at matched size is reported as "no content effect".
A3.3 Method revision A′ (cross-task priors), pre-registered:
  - Start dose per family = median of that family's accepted doses so far in this round (initial 0.5).
  - The d=1 leverage test of a family is skipped once the family has returned ZERO at d=1 on ≥ 5 tasks in this round
    (its leverage is then assumed and the search starts at the family's start dose).
  - A family that has shown no leverage on ≥ 5 tasks is moved to the end of the order; designer proposals count as
    families. Everything else identical to A (dose contract, acceptance rule, cap 30, certificates).
  - A′ runs as a separate arm on the same 30 tasks; A (Round 1) is not re-run. C1 and C2 are reported for both.
A3.4 Budget: hard cap USD 650, soft gate 600.
```
