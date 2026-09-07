# P5 — two decisive checks before the design meeting (PREREG5.md; inputs P4 @ b22f07d)

- P5.1 `p5/chs100.py`: Certified Hindsight Staging with the stage budget re-based (configs/alfworld_config_100.yaml via
  `reset_options.config_path`; runner max_steps 50). Certificates (LLM-free) → candidates (L, 3L/4, L/2, L/4 per
  trajectory, ≤ 6 per task) → probe ALL candidates (4 corpus rollouts) → selected = latest learnable (+8 rollouts, p̂_12).
  Outputs results/chs_certs.jsonl, chs_profile.csv, chs_selected.csv. K5 written to LOG as soon as known.
- P5.2 `p5/induce_ss.py`: single_succ induction control (released induce_memory_items, success=True, shortest success per
  task) for the 9 I-sat envs and their original counterparts; matched by seed 20260914; evals 3 reps → H5.
- P5.3 `p5/banksize.py`: seeded subsamples (20260915) of orig_m (23 items) at sizes 3, 6, 9, 15; evals 3 reps.
- P5.4 `docs/rl_audit.md`: Phase-A audit of third_party/envharness/rl (no runs).
- `p5/analyze.py` → results/report.md. Tests in tests/ are offline.
Ledger phases p5_chs, p5_induce, p5_eval; provider pinned alibaba; P5 ≤ USD 35 (P5.1 ≤ 20, P5.2 ≤ 6, P5.3 ≤ 9).
