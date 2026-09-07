# P5 pre-registration — CHS fork test, induction-mode control, bank-size dose (frozen 2026-09-07; inputs P4 @ b22f07d)

Definitions
- Re-based staged environment: Setup replay of the student's own prefix (no-ops dropped, ending with `look`) on a
  bridge configured with max_nb_steps_per_episode = 100 via the released reset_options.config_path; the runner's
  max_steps = 50 is the policy budget. Certificates C_any3 recomputed under the same configuration.
- Learnable candidate: 1–3 successes in 4 corpus-protocol rollouts. Selected env: latest learnable candidate;
  confirmed iff p̂_12 ∈ [0.2, 0.8]. Learnability profile: p̂_4 as a function of t for all probed candidates.
- Induction-mode control: single_succ induction (released induce_memory_items, success=True, shortest success per
  task) for both the I-sat environments and their original-environment counterparts; item-matched by seeded subsampling.

K5 (fork; from P5.1): number of the 8 zero tasks with a confirmed selected env
- ≥ 4 → zero side alive: CHS is the primary operator of the method; the design meeting proceeds on that basis.
- 2–3 → marginal: report; the design meeting decides with the learnability profiles in hand.
- ≤ 1 → CHS has no working targets for this policy on this substrate (failure is uniform along the trajectory):
  the environment-control line needs a different consumer or benchmark before any further design.

H5 (from P5.2; in-distribution, paired per task, matched items)
- H5a: isat_ss(m) − origc_isat_ss(m) ≥ −0.05 → environment content not shown harmful; the P3/P4 deficits are
  attributed to induction mode and bank size; the interface/Goodhart claim is withdrawn from the method's claims.
- H5b: difference < −0.05 with a 95% CI excluding 0 → interface-environment content is harmful even in success-only
  induction; the claim survives at pilot grade.
- Otherwise inconclusive; reported with the CI.

P5.3 is descriptive: ID/OOD vs bank size {3, 6, 9, 15, 23}; the retrieval top_k regime is marked.

Budget: P5 ≤ USD 35 (P5.1 ≤ 20, P5.2 ≤ 6, P5.3 ≤ 9); pilot hard cap 150, soft gate 130.
Seeds: trajectories 20260913 (as P4.2); bank subsampling 20260914; bank-size subsamples 20260915.
