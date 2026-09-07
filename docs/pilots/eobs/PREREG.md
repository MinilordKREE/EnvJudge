# E-obs pre-registration (ALFWorld observation study) — frozen 2026-09-0X

Substrate: envharness @ fab7d57441f06b75c73a900e04561d4d7600f361, experiments/alfworld/corpus.yaml unchanged except model/credentials/paths/concurrency (sha256 recorded in LOG); ALFWorld train split, first N tasks in the config's order, task-offset 0; policy = designer = DeepSeek V4 Pro, non-thinking, temperature per config (else 0.7); K=5 baseline and validation, ≤5 revisions (EnvRigger defaults).

Definitions
- E_t: base env of task t (seeded deterministic reset). π: EnvRigger's policy agent. Expert: ALFWorld expert planner, queried from a state s; plan(s) executed in E is a candidate witness.
- W_base(t) = 1 iff plan(s_0) passes the verifier in E_t.
- p̂_16(t): success rate over EnvRigger's 5 baseline rollouts + 11 extra independent rollouts (same code path). p̂_5(t): EnvRigger's own 5.
- Candidate c: one (rules_code, in_env_actions) set that received K=5 validation rollouts; SR_c its validation success rate; axis(c) ⊆ {S0,A,T,O} by overridden hooks.
- Certificates: R_old(c) base expert plan replayed verbatim in E′_c; R_exp(c) expert re-planned step by step from E′_c's initial state; R_hint(c) ≤3 policy attempts with the expert plan as hint (only for SR_c=0 or R_old=0; cap 60 candidates). certified(c) = R_old ∨ R_exp ∨ R_hint. ŝ=0 (unresolved) is inconclusive by definition.
- D(c): decision ∈ {ACCEPT, REFINE, REJECT} and reverse_or_loosen flag from the designer's text.
- Recoverability: for a failed base-env trajectory τ⁻, C(s_t)=1 iff plan(s_t) passes the verifier; L(τ⁻) = max{t: C(s_t)=1}; monotone iff no 1 after a 0.

Predictions (each decides a design branch; thresholds anchored in EnvHarness App. G/F.2 and E-min)
- O1 witness coverage: W_base ≥ 0.95 of tasks. Decides: free-witness availability; the size of the no-witness bucket on ALFWorld.
- O2 bimodality: share of tasks with p̂_16 ∈ [0.2, 0.8] ≤ 0.35. Decides: whether saturated/zero regimes dominate under DeepSeek.
- O3 0/5 unreliability: among tasks with p̂_5 = 0, share with p̂_16 > 0 ≥ 0.20. Decides: sequential estimation vs fixed K=5.
- O4 transformation-induced zero success (contribution-2 gate): (a) candidates with SR_c = 0 are ≥ 0.15 of validated candidates; (b) among them, certified ≥ 0.30; (c) among certified SR_c=0 candidates, share treated as unsolvable by the designer (REJECT or reverse_or_loosen) ≥ 0.30. Decides: whether a certification layer changes any decision.
- O5 old-witness false alarm (axis-taxonomy gate): among certified candidates with A or T in axis(c), share with R_old = 0 ≥ 0.30; among certified O-only candidates, share with R_old = 1 ≥ 0.90. Decides: per-axis certificates vs single replay.
- O6 recoverability (contribution-3 gate): among failed trajectories, share with L ≥ 2 is ≥ 0.50; share non-monotone ≥ 0.20; report the distribution of L/T. Decides: whether a certified self-prefix Stage has material to work with and whether bisection is admissible (it is not if non-monotone ≥ 0.20).
- O7 saturated waste: among tasks with p̂_5 = 1, share with no ACCEPT within the revision budget ≥ 0.25. Decides: harden branch (freeze/reallocate vs keep hardening).
- O8 descriptive, no threshold: validation rollouts spent on SR_c=0 candidates as a share of all validation rollouts; rollouts per ACCEPT; R_hint cost per certified candidate.

Stop rule S1: if O4(a)∧O4(b)∧O4(c) all fail AND O6 (L ≥ 2 share) fails, stop the CEA line on ALFWorld and report. Otherwise proceed to method design with the branches selected above. This study has no GO/NO-GO on the method; it selects branches.

Statistics: 10,000 task-level bootstrap resamples for every rate; candidate-level rates resample tasks. Report point estimates with CI; "CI-decisive" only when the CI excludes the threshold; no bold except the S1 outcome. All nulls and deviations reported.

Budget: hard USD 120; soft gate USD 80 (pause + interim report). Phase-0 projection sets N ∈ [15, 30].
