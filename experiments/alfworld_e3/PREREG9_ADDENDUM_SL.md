# PREREG9 Addendum SL (2026-09-11): downstream skill evaluation of the E3 learner-facing sets

Amendment: the PREREG9 stop rule "if E3-1 fails, the downstream columns are not run" is replaced by "E3-3 failing
returns the saturated side to design; the SL evaluation runs regardless of E3-1 and E3-3 and is reported as such".

Banks (single-success induction, DeepSeek V4 Pro extractor, thinking off, released `_build_bank` fed success-only
trajectories; shortest success per environment):
- A_lf: A's learner-facing set (kept tasks + accepted transformed environments; trajectories = A's own search
  successes on kept tasks, the accepted environments' search successes).
- G_lf, R_lf: accepted transformed environments only (their learner-facing set).
- O: no adaptation — the 30 original tasks, successes from the shared K=16.
- Supplementary, same for every arm: the released cascade (accepted environment where one exists, else the task's own
  baseline successes) with the released automatic induction mode.
Two independent inductions per bank (extractor sampling seeds 20260920, 20260921); every reported number is the mean of
the two, with both shown.
Item matching: the primary comparison subsamples every bank to the minimum item count across A_lf, G_lf, R_lf, O
(seed 20260922); full-bank rows are supplementary.
Anchors: N (no bank); placebo (5 task-irrelevant items in the released item format, vocabulary-checked).
Eval: released reasoning_bank_eval.py through the eval hook, Qwen3-8B consumer (alibaba pin, reasoning off), SkillOS
prompt, history 4, temperature 0.4, top-5 MMR; full ID (140) + OOD (134); seeds 0 / 1000 / 2000. Paired per-task
differences with 10k task-level bootstrap CIs; per-seed values shown.

Claim E3-SL: item-matched, induction-averaged — A_lf ≥ G_lf and A_lf ≥ R_lf on ID or OOD with a 95% CI excluding 0.
Gaps within 3 points are reported as indistinguishable. Also reported: each bank minus N and minus placebo; full-bank
rows; the released-cascade rows; item counts and item types per bank.
Budget: ≤ USD 180 (inductions ≈ 2; matched evals 6 conditions × 2 inductions × 3 seeds × 274 ≈ USD 100; full-bank and
cascade rows ≈ USD 70). Hard stop at 180.
