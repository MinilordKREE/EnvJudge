# AEA v0.3 — the method of record (owner text, 2026-09-12)

Supersedes `docs/spec/AEA_v0.2.md` as the description of the METHOD: the v0.2 box with three edits, each
motivated by an evidence row of `experiments/alfworld_e3/results/e3_layer1.md` and listed in
`docs/changelog_v0.3.md`. Everything else — six constants, one acceptance rule, one guard, cap 30, kept band
tasks, the three outcomes, the budget, the engineering — is unchanged from v0.2 and its text is repeated here
so that this file stands alone.

## The box

```
Constants: target band B_T = [0.4, 0.6]; learnable band B_L = [0.2, 0.8]; K = 16 per task (early stop when the regime is
decided); accept iff 3–5 successes in 8; probe = 4 rollouts, topped up to 8 unless 0/4, or 4/4 on the harden side
(a 4/4 staged state IS topped up); cap = 30 policy rollouts per task.

for each task:
    p ← estimate(policy, E)                              # ≤ 16 rollouts, stop when P(regime) ≥ 0.9
    if p in B_L:               keep E                                       # outcome: kept
    elif p > 0.8:              # harden — synthesize a contrast
        for w in families ordered by measured leverage (cold start: proposer order):
            if not solvable(w(1)): continue
            r ← evaluate(w(1))                          # 4 → 8 rule
            if r == in_band: accept w(1); break
            if r == no_effect: record leverage 0; continue
            bracket [lo, hi] = [lo_pop(w), hi_pop(w)]   # the family's population seed (default [0, 1]);
                                                        # the failed d = 1 test may lower hi to 1
            up to 4 bisections at the midpoint with the 4 → 8 rule:
                too_easy → lo = d; too_hard → hi = d; in_band → accept w(d); break
                (a non-monotone family ends as exhausted; an order violation is recorded as a diagnostic)
            every dose seen updates the population: too_easy (d < 1) → lo_pop = max(lo_pop, d);
                                                    too_hard → hi_pop = min(hi_pop, d)
        else: drop                                                          # reason: no_leverage | exhausted
    else:                      # stage — discover an existing contrast
        for s in candidate states, latest first (≤ 6 after dedupe by state hash, priority end > mid > quarter:
                                                 end, midpoint and quarter (t = T/4) of 3 failed rollouts):
            if not solvable(Stage(E, s)): continue
            r ← evaluate(Stage(E, s))                   # 4 → 8 rule, a 4/4 first batch topped up; budget re-based
            if r == in_band: accept Stage(E, s); break
        else: drop                                                          # reason: dead | uncertified | budget
Families: parameterized wrappers w(d), d ∈ [0,1], harder with d, from the LLM proposer under the dose contract
(≤ 2 per task) and from a small library given to the proposer as few-shot examples.
solvable(): replay a known success (the policy's own, or the benchmark oracle when one exists); if no witness
source exists the guard is skipped and the probe self-certifies.
Every policy rollout counts against the cap; wrapper replays and oracle sessions do not.
```

## The three edits (v0.2 → v0.3)

1. **Population-seeded bracket** (replaces "start at the family's last accepted dose"). Per family, across the
   tasks of a run, `lo_pop` = the highest dose observed `too_easy` below d = 1 and `hi_pop` = the lowest dose
   observed `too_hard`. A new task's bracket for that family starts at `[lo_pop, hi_pop]` (default `[0, 1]`;
   `[0, 1]` again when the observations are inconsistent, `lo_pop ≥ hi_pop`); the first bisection is its
   midpoint. The d = 1 leverage test still runs first on every task and may lower `hi` to 1. Evidence: in E3 the
   footer mask had leverage on every saturated task it met (d = 1 → 0/4) with its band in (0.875, 1.0]; every
   bracket started at 0.5, walked 0.5 → 0.75 → 0.875 (all `too_easy`) and hit the cap; 15 saturated tasks ended
   `budget`; the last-accepted-dose prior never fired because the family was never accepted. Seeded at
   `[0.875, 1]` the band is one bisection away (10 + 4 + 8 = 22 ≤ 30). The population is persisted as
   `leverage` events beside the leverage rates and rebuilt on resume.
2. **Stage-side 4/4 tops up.** On a staged state a 4/4 first batch is topped up to 8 like a mixed batch; the
   verdict comes from the 8 (3–5 in band, 6–8 too easy, 0–2 too hard). Harden-side semantics are unchanged (4/4
   at a dose stays `no_effect` / `too_easy`: a cheaper next dose exists there). Evidence: E3 tasks 9 and 27 probed
   4/4 at t = 50 and were dropped `too_easy`; Phase D had accepted the same states at 3/8 and 5/8;
   P(p > 0.8 | 4/4) ≈ 0.67.
3. **Quarter-point candidates.** Candidate states per failed rollout: end, midpoint and quarter (t = T/4); every
   prefix is compiled and deduplicated by state hash, then capped at 6 by priority end > mid > quarter (a
   quarter state enters when ends or midpoints collapse to one state, as when the policy loops to the step
   cap); the walk stays latest-first. Evidence: E3 task 9 is 4/4 from every probed mid or late state but 0/8 from
   the start at horizon 100: its learnable frontier is early, and end + midpoint candidates cannot reach it.

## Reading the box (unchanged from v0.2 except where the edits apply)

- **Two operators.** `harden` wraps the environment with a family `w(d)`; `stage` restarts the environment from
  a state `s` reached by the policy's own failed rollout (a compiled Setup prefix; the staged session runs under
  the 100-step config so the replayed prefix does not consume the policy's horizon).
- **One acceptance rule.** `evaluate(env)`: 4 policy rollouts; 0/4 → `too_hard`; on the harden side 4/4 →
  `no_effect` (`too_easy` inside a bracket); on a staged state 4/4 is topped up; otherwise 4 more; `in_band` iff
  3–5 successes of 8; 1–2/8 → `too_hard`; 6–8/8 → `too_easy`. Both operators use it; an accepted environment is
  one that returned `in_band`.
- **One guard, asymmetric.** `solvable(env, sources)` replays a known success through the wrapped / staged
  environment and checks that it still reaches the goal. The sources differ by operator:
  - harden: (1) the policy's own shortest success on this task (from the estimate), then (2) the benchmark
    oracle when one exists;
  - stage: the oracle only (a success that starts from reset cannot witness a mid-trajectory state).
  Rule: any source passing → solvable. A failed replay is NOT evidence of unsolvability (A/T-axis changes close
  old paths by design; in O5H 31.8% of the candidates later shown solvable failed the old replay): replay fails →
  try the oracle; oracle fails → `dropped: uncertified`; replay fails and no oracle exists (or stage without an
  oracle) → continue, the probe self-certifies (an `in_band` evaluation is the evidence). Observation-axis
  families are solvable by construction and skip the guard. Replays and oracle sessions are not policy rollouts.
- **One budget.** Every policy rollout of a task (estimate, evaluations, brackets, stage probes) is charged to
  `search`, hard cap 30; the confirmation rollouts that define learnability (`eval`, K = 16, B_L) are never
  written back and are not part of the method's decisions. Designer (proposer) calls are ledgered under
  `designer` for cost reporting only and are not charged to the cap, in every arm: EnvRigger's designer calls
  are not charged either, so the arms are symmetric.
- **Six method constants.** B_T, B_L, K, the 3–5-of-8 acceptance, the 4 → 8 probe, the cap of 30. The batch
  schedule of the estimator, its stopping confidence, the bisection limit (4) and the proposer cap (2) are
  implementation constants in `AEAConfig.impl` and do not appear in the method section. (The v0.2 prior
  constants `prior_min_tasks` / `prior_min_rate` are gone with the prior they governed.)
- **Three outcomes.** `accepted` (with the environment), `kept` (E itself is learnable), `dropped` (with a
  reason: `no_leverage`, `exhausted`, `dead`, `uncertified`, `budget`, `too_easy`). Reports may group by reason.
- **Families and leverage.** A family's measured leverage is the rate, over the tasks where it was evaluated at
  d = 1, of not returning `no_effect`. Families are ordered by that rate (proposer order until a family has been
  seen). The d = 1 leverage test is ALWAYS run on every task. Per task and family the sequence is: evaluate w(1)
  (4 → 8); if `in_band` accept, if `no_effect` record leverage 0 and move on; otherwise bisect on the family's
  population seed `[lo_pop, hi_pop]` starting at its midpoint; at most 4 bisections (10 + 4 + 8 + 8 = 30). The
  bracket keeps `lo` = the largest dose known too easy and `hi` = the smallest known too hard; every dose the
  bracket evaluates, on every task, updates the population. The bracket invariant keeps verdicts consistent, so a
  non-monotone family shows up as a bracket that does not converge and ends as `exhausted`; an order violation
  (a higher dose with a success rate more than 0.375 above a lower dose's) is recorded as a diagnostic and never
  stops the search. The leverage table (rates and seeds) is a sequential dependency across tasks and is
  persisted as events.
- **Candidate states.** For each of three failed rollouts of the estimate (seeded sample), the end state, the
  midpoint state and the quarter state; duplicates by state hash removed; at most six by priority
  end > mid > quarter; walked latest-first.

## What stays outside the box

- Experimental protocol: task sets, seeds, arms, bank protocols, evaluations, the released baselines, the
  hand-off extension, all in `scripts/` and `experiments/`.
- Engineering rigor, unchanged: the ledger (one row per LLM call, provider pin, price guard), the run manifest,
  `AeaSubprocessRunner` attribution, resumability, the corpus / trace formats consumed by envharness, and the
  task pool (`Controller.run(concurrency)`: wall clock only; in-process sessions serialized under one lock; the
  leverage table a sequential dependency; corpus / accounting / per-task charges byte-identical to the
  sequential run; the pool size in the manifest).
- The paper shows the box; anything else it claims is shown necessary by an ablation or omitted.
