# E-obs-F pre-registration — decision rules, frozen 2026-09-0X (inputs: E-obs @ 8ee43da)

D1 (saturated side; from F1, attempt-level on S_H, task-resampled CIs):
  let a = share of failed attempts that are NOEFFECT, b = share OVERSHOOT ∪ ZERO, c = share INBAND-but-not-accepted.
  a ≥ 0.50  → expressivity branch (the operator repertoire cannot lower SR; dose control alone will not fix O7H).
  b ≥ 0.50  → dose branch (hardening overshoots; a certificate-guarded dose search is the fix).
  neither   → both branches; report a, b, c and the controllability rates (a loop that moves toward the band at
              P < 0.5 is not a controller).
  c ≥ 0.25  → acceptance-rule branch (the designer rejects in-band candidates; the acceptance criterion, not the
              operator, is the sink) — reported alongside, not exclusive.

D2 (zero side; from F3, n = 40 trajectories):
  flip rate ≥ 0.10 → a recoverability certificate needs ≥ 3 expert attempts (or a policy-success suffix) per state.
  non-monotone_any3 ≥ 0.20 → bisection stays inadmissible (PREREG O6 stands); < 0.20 → single-run non-monotonicity
  was expert noise; the O6 non-monotone figure in verdict.md is annotated with the de-noised value in the report.
  L_any3 ≥ 2 share ≥ 0.50 keeps the CHS branch (as O6).

D3 (consumer; from F5): zero + edge-low share under Flash ≥ 0.30 → the zero side has SL targets with Flash as
  consumer (CHS evaluable in SL); < 0.30 → CHS is evaluated in the RL Study only. Regime shares for both consumers
  are reported as the regime-vs-strength table regardless.

Budget: hard USD 10; F5 ≈ USD 2–3; all else LLM-free. Sampling seeds: F3 20260907; F5 recoverability 20260908;
F6 review list 20260909.
