# PREREG12 — E5: soft warm start of the saturated-side dose search (frozen 2026-09-13)

Question: does the v0.4 soft warm start (`docs/spec/AEA_v0.4.md`: first interior probe = median of ≥ 3 previous
task frontiers, task-local interval always [0, 1]) improve saturated-side search efficiency over the v0.2 midpoint
start without introducing lock-in? One conceptual difference, everything else identical.

Arms (same code, tag aea-v0.4; the only difference is the warm start's minimum history):
- A2 = v0.2 saturated search: `impl.warm_start_min_history = 10^9` (first interior probe always 0.5).
- A4 = v0.4 soft warm start: `impl.warm_start_min_history = 3`.
Both: Qwen3-8B policy (alibaba pin, reasoning off), library families only (footer_mask, then horizon_squeeze;
proposer OFF, no LLM call), the v0.2 estimate (≤ 16, early stop), the same guard, the 4 → 8 verdict, the 3–5-of-8
acceptance, cap 30 charged policy rollouts per task, task concurrency 1 so the frontier history is the task order.
Rollout seeds cannot be paired (temperature sampling on a hosted endpoint); every rollout is ledgered.

Tasks (8 saturated tasks, run in this order by both arms): 3, 12, 13, 15, 22, 23, 24, 29. Chosen before the run
for: the E3 footer-mask narrow high-dose response (3, 12, 13, 22, 29: band in (0.875, 1]), tasks harmed by the v0.3
hard bracket in E3b (12, 15, 22, 23, 24, 29; 23 and 24 were lost), and the task-specific outlier 15 (E3: too hard
at 0.5, band near (0.25, 0.5)). A4's warm start is inactive on the first three tasks (no history yet) and active
from task 15 on.

Confirmations: K = 16 (budget `eval`, never written back) on every accepted environment of either arm, deduplicated
by (task, candidate); learnable iff p̂₁₆ ∈ [0.2, 0.8]. Confirmation does not change any search outcome.

Metrics per task and arm: outcome / reason; charged search rollouts; first interior probe; doses visited with
verdicts; accepted dose; final task-local interval; whether the warm start was helpful / neutral / harmful
(fewer / equal / more bisection probes than A2 on the same task, given the same verdict pattern; "n/a" while the
history is shorter than 3); whether A4 recovered after a harmful warm probe (accepted after the warm probe was on
the wrong side). Aggregates: accepted-in-band tasks / tested tasks; rollouts per task; rollouts per accepted task;
confirmed learnable / accepted (precision).

Decision rule (written before the run; no post-hoc rule change). Keep the soft warm start only if at least one of
  A. ≥ 20% reduction in saturated-side search rollouts per accepted task (A4 vs A2), or
  B. ≥ 1 additional confirmed (learnable at K = 16) accepted environment among the 8 tasks,
holds WITHOUT a meaningful loss on the other metric, AND no irreversible search collapse (A4 never censors a
task's interval by construction; the test is that every harmful warm start is followed by recovery), AND no worse
acceptance precision. Otherwise: delete the cross-task prior entirely and return to v0.2 midpoint search. If
neither arm accepts anything, the experiment is inconclusive and v0.2 stays.

Offline replay (no rollout, `experiments/alfworld_e5/replay_dose_search.md`, E3 evidence, 8 footer-mask tasks):
v0.2 reached the observed band on 2 tasks (92 rollouts), v0.3 on 6 with 1 task censored (76), v0.4 on 5 with 0
censored (76). Structural only; it does not predict this result.

Budget: ≤ USD 70 (2 arms × 8 tasks × ≤ 30 rollouts ≈ 45; confirmations ≈ 15; margin). No downstream induction,
no RL, no zero-side change.
