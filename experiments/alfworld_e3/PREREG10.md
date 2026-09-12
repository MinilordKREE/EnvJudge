# PREREG10 — E3b: aea v0.3 on the E3 task set (frozen 2026-09-12)
Identical to PREREG9 except the arm: A_v0.3 (docs/spec/AEA_v0.3.md). Tasks seeds 0–29; Qwen3-8B policy (alibaba pin,
reasoning off); DeepSeek V4 Pro proposer; cap 30 charged policy rollouts per task. REUSED from E3, not re-run: the shared
original-environment K=16, arms G and R, the H100 control. New: A_v0.3's search, K=16 confirmations for every environment
it hands to the learner (kept tasks reuse the shared K=16), and its SL column.
Claims: E3b-1 learner-facing learnable per 1,000 charged rollouts — A_v0.3 > G (15.3) and > R (9.1). E3b-3 saturated
subset — A_v0.3 ≥ G (8.6). Reported: band preservation, unlocked zero tasks with H100 attribution, precision, family of
origin, per-task budget, and the v0.2 row beside every v0.3 row.
E3b-SL: banks and evaluation exactly as PREREG9 Addendum SL (released single-success induction, two inductions, item
matching to the minimum across A_v0.3_lf, G_lf, R_lf, O, full-bank and cascade rows supplementary, task-clustered
bootstrap). G_lf, R_lf, O, N and placebo evaluations are REUSED from E3-SL; only A_v0.3's banks are new.
Claim E3b-SL: item-matched, induction-averaged A_v0.3_lf ≥ G_lf and ≥ R_lf on ID or OOD with a 95% CI excluding 0.
Budget: ≤ USD 120 (search ≈ 35, confirmations ≈ 15, banks ≈ 1, SL evals ≈ 60, margin).
