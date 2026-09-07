# Audit: `dose` (leverage test, sequential dose search, confirmation)

Contract: 4 rollouts; 4/4 NOEFFECT; 0/4 ZERO; else top up to 8; accept iff 3–5/8; 1–2/8 lower,
6–7/8 raise; leverage = same rule at d=1; step 0.25 halving; ≤4 evaluations; non-monotone responses logged.

## Reference

| what | where | reuse |
|---|---|---|
| Sequential band control (4 → 8), band {3,4,5}/8, near {2,6}/8 | `docs/pilots/e1pilot/e1/controller.py` (`classify_after4`, `classify8`) | port (unit-tested against the pilot's own tests) |
| λ search: start, step, halve, ≤4 evals, stop at IN-BAND, non-monotone counter | `docs/pilots/e1pilot/e1/lam_search.py` | port with the contract's direction rule (1–2/8 lower, 6–7/8 raise) and step 0.25 |
| Running a dose: 4 then 4 more rollouts through the runner | `docs/pilots/e1pilot/e1/p2b_run.py:43-53` (`run_dose`) | rewrite on `estimate`'s dispatcher (same batches, ledger rows) |
| Certificate before any rollout | `docs/pilots/e1pilot/e1/p2_run.py:77-105` (`certificate`) | `certs` module |
| Fixture: the P2b dose curves (task, family, dose, rollouts, successes, class, certificate) | `docs/pilots/e1pilot/results/e1pilot/p2b_curves.csv`, `p2b_doses.jsonl` | test fixture: replaying the recorded successes through the ported rule must reproduce the recorded classes and the recorded next doses |

## Invariants relied on

- The dispatcher returns exactly n traces per batch or raises (`estimate`); a rollout with `error`
  is retried once and never counted.
- Doses are evaluated on the same `reset_seed` as the estimate (✓ `orchestrator.py:998-1009` pattern).

## Decisions

- Leverage test = the acceptance rule at d = 1 (NOEFFECT at d = 1 → the family has no leverage on this
  task; no further doses). Non-monotone responses (a NOEFFECT above a ZERO) are logged as events, never
  corrected.
