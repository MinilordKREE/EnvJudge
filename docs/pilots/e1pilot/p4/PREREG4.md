# P4 pre-registration — behavioral novelty vs interface difficulty (frozen 2026-09-0X; inputs E1-pilot @ 103b285)

Definitions
- Confirmed in-band environment: p̂_16 ∈ [0.25, 0.75] under the corpus protocol.
- Witness survival ω(E′): share of the policy's successful P1 trajectories on that task that pass the verifier when
  replayed verbatim in E′. O-axis transformations have ω = 1 by construction (replay ignores observations); Chain has
  ω = 0 by construction (a single-task success cannot complete the chain); CHS staged environments: ω not defined
  (reported n/a). Behavioral novelty := solvable (certified) ∧ ω ≤ 0.5. Interface difficulty := solvable ∧ ω > 0.5.
- Arms: I-sat = confirmed P2b in-band envs (ω ≈ 1 except the F_H env); N-sat = confirmed behavior-breaking envs
  (F_H with ω ≤ 0.5; Chain); N-zero = CHS staged envs on the 8 zero tasks with a learnability-selected start state.
- Controls: orig_c(arm) = released induction on 8 original-environment P1 trajectories per task on the arm's task set.
- Primary comparison: item-matched banks (subsampled to min items, seed 20260912); full banks supplementary.
- Held-out: P3's 30 ID + 30 OOD tasks, 3 same-task replicates; paired per-task differences; 10k task-level bootstrap.

Predictions (in-distribution split unless stated; threshold −0.02 as in K3)
- H1 interface replication: I-sat(m) − orig_c(I)(m) ≤ −0.02, CI reported.
- H2a saturated-side novelty: N-sat(m) − orig_c(N-sat)(m) ≥ −0.02.
- H2b zero-side novelty: N-zero(m) − orig_c(N-zero)(m) ≥ −0.02 and N-zero(m) − nobank ≥ 0 (point estimate).
- H3 unlock: with the N-zero bank, share of the 8 zero tasks with ≥ 1 success in 8 original-environment rollouts
  (eval protocol) ≥ 0.25 and greater than nobank's share under the same protocol.
- H4 ω ordering (descriptive, not a gate): arms with ω ≤ 0.5 show ID gains ≥ arms with ω ≈ 1.
- K2b correction: share of the 9 P2b in-band envs confirmed at K = 16 ≥ 0.60; otherwise K2b is restated on the
  confirmed count.

Kill / branch rule K4
- H2a and H2b both fail → skills from any transformed environment do not help this consumer; the SL line is dead;
  the RL Study is the downstream evidence.
- H2b holds, H2a fails → the SL evidence in the paper is zero-side (CHS) only; the saturated side is evaluated in RL.
- H2a holds, H2b fails → the saturated side stays in SL; CHS is evaluated in RL.
- H1 fails (I-sat not worse than its control) → the interface/novelty distinction is not supported by these data;
  the K3 result is attributed to bank size/composition, reported as such.

Budget: P4 ≤ USD 70; pilot hard cap 115, soft gate 100. Seeds: N-zero trajectory sample 20260913, bank subsampling
20260912, Chain partner = next saturated task id.
