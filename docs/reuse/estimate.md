# Audit: `estimate` (sequential Beta regime estimation)

Contract (docs/reuse/contracts.md): batches [4, 2, 2, …]; stop when any of P(p<0.2), P(0.2≤p≤0.8),
P(p>0.8) ≥ 0.9 under the Beta posterior or n = 16; returns regime, p̂, all traces; environment errors
retried once, never counted.

## Reference

| what | where | reuse |
|---|---|---|
| K-rollout dispatch: one `EpisodeSpec` per rollout with `reset_seed = task_id`, thread pool, `candidate_id`/`rollout_idx`/`kind` stamped afterwards | `orchestrator.py:986-1046` (`_rollout_k`), `870-923` (`_rollout_baseline_k`) | rewrite (aea owns the batch schedule and the ledger); the runner call itself is reused |
| Episode execution and error surface (`Trace.error` on subprocess death, policy or env exception) | `runner.py:171-300`, `316-420` | wrap |
| Pilot oracle: regime labels from p̂₁₆ with 16 fixed rollouts; zero = 0/16, saturated ≥ 0.875 in P2 targets | `docs/pilots/e1pilot/e1/regime_map.py:97-140`, `results/e1pilot/qwen_p16.csv` | fixture only (regime labels of the 30 pilot tasks are the expected outputs when all 16 rollouts are replayed through the estimator) |

## Invariants relied on

- Every rollout of one task uses the same `reset_seed` (✓ `_rollout_k` 998-1009), so regime estimates
  are per task, not per game sample.
- A `Trace` with `error` set is an infrastructure outcome, not a failure (✓ `runner.py:237-254`,
  `356-382`): `estimate` retries it once and excludes it from n; a second error is an `InfraError`.
- `Trace.success` comes from `evaluate()` on the base env (✓ `runner.py:283-291`).

## Decisions

- Posterior Beta(1+s, 1+f) with a uniform prior; the three probabilities are regularised incomplete
  beta values (numpy/scipy-free implementation with a small numeric integrator, unit-tested against
  closed forms at n = 4, 8, 16).
- Batches are dispatched through the released `SubprocessRunner` with `rollout_concurrency` = batch
  size; each rollout is a `rollout` ledger row on budget `search` (or `confirm` for K16 post-hoc).
