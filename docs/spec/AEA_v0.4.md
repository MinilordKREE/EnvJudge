# AEA v0.4 — the method of record (owner text, 2026-09-13)

v0.4 = v0.2 + a soft cross-task warm start of the dose search, and nothing else. It supersedes v0.3
(`docs/spec/AEA_v0.3.md`), whose three edits are withdrawn: the population bracket collapsed in E3b
(`docs/changelog_v0.4.md`), and the two zero-side edits are removed with it so that the saturated-side
change can be tested alone. Everything below that is not the warm start is the v0.2 text.

## Three principles

1. Measure before adapting.
2. Move only the tasks outside the useful signal region.
3. History and the LLM propose; the current task's rollout measurements decide.

## The box

```
Constants: target band B_T = [0.4, 0.6]; learnable band B_L = [0.2, 0.8]; K = 16 per task (early stop when the regime is
decided); accept iff 3–5 successes in 8; probe = 4 rollouts (topped up to 8 unless 0/4 or 4/4); cap = 30 policy
rollouts per task.

for each task:
    p ← estimate(policy, E)                              # ≤ 16 rollouts, stop when P(regime) ≥ 0.9
    if p in B_L:               keep E                                       # outcome: kept
    elif p > 0.8:              # harden — synthesize a contrast
        for w in families ordered by measured leverage (cold start: proposer order):
            if not solvable(w(1)): continue
            r ← evaluate(w(1))                          # 4 → 8 rule
            if r == in_band: accept w(1); break
            if r == no_effect: record leverage 0; continue
            lo, hi ← 0, 1                               # the task-local interval, whatever the history
            d ← median of w's previous tasks' frontiers if ≥ 3 exist, else 0.5     # the soft warm start
            up to 4 bisections with the 4 → 8 rule:
                too_easy → lo = d; too_hard → hi = d; in_band → accept w(d); break
                d ← (lo + hi) / 2
            record w's frontier for this task: (lo + hi) / 2                      # accepted, exhausted or censored
        else: drop                                                          # reason: no_leverage | exhausted
    else:                      # stage — discover an existing contrast
        for s in candidate states, latest first (≤ 6: end and midpoint of 3 failed rollouts):
            if not solvable(Stage(E, s)): continue
            r ← evaluate(Stage(E, s))                   # same 4 → 8 rule, budget re-based
            if r == in_band: accept Stage(E, s); break
        else: drop                                                          # reason: dead | uncertified | budget
Families: parameterized wrappers w(d), d ∈ [0,1], harder with d, from the LLM proposer under the dose contract
(≤ 2 per task) and from a small library given to the proposer as few-shot examples.
solvable(): replay a known success (the policy's own, or the benchmark oracle when one exists); if no witness
source exists the guard is skipped and the probe self-certifies.
Every policy rollout counts against the cap; wrapper replays and oracle sessions do not.
```

## The saturated side in fifteen lines (paper pseudocode)

```
harden(task, families):
  for w in families ordered by leverage rate:
    if not solvable(w(1)): continue
    r = evaluate(w(1))                      # 4 → 8 rule
    if r == in_band:  return accept(w, 1)
    if r == no_effect: leverage[w] += 0; continue
    lo, hi = 0, 1                           # task-local interval: never narrowed by history
    d = median(frontiers[w]) if len(frontiers[w]) >= 3 else 0.5
    for _ in range(4):                      # 10 + 4 + 8 + 8 = 30
      r = evaluate(w(d))
      if r == in_band:  frontiers[w] += (lo+hi)/2; return accept(w, d)
      if r == too_easy: lo = d  else: hi = d
      d = (lo + hi) / 2
    frontiers[w] += (lo + hi) / 2           # exhausted or censored searches count too
  return drop
```

## The one change from v0.2, and its contract

- **What it replaces.** v0.2 seeded the first bisection at the family's last accepted dose once the family had
  a leverage rate ≥ 0.9 over ≥ 5 tasks (two constants); that prior never fired in E3 because the footer mask,
  with leverage on every saturated task, was never accepted: its band lies in (0.875, 1.0] and every bracket
  walked 0.5 → 0.75 → 0.875 to the cap.
- **What v0.3 did wrong.** It made history a hard constraint: `hi_pop` = the lowest dose ever seen too hard on
  any task. One 0/4 at d = 0.5 (probability 0.41 at p = 0.2) became a permanent ceiling for every later task,
  and every later bracket, confined below it, could only observe too easy, so the error could never be
  corrected (E3b: 7 seeded brackets, 0 accepted, 4 tasks lost).
- **The contract of v0.4.** History may choose where to probe first; it never removes any part of a new task's
  feasible interval. Each finished task-family search contributes one frontier estimate, `(lo_t + hi_t) / 2` of
  its final local interval, whether it accepted, exhausted or hit the cap. A new task's first interior probe is
  the median of those estimates once at least three exist (`impl.warm_start_min_history`), otherwise 0.5; the
  task-local interval starts at [0, 1] regardless, and every later dose is its midpoint. A wrong warm start
  costs one probe and nothing else. The median, not a min or max, so one poisoned task cannot move the start.
- **State and constants.** One new state variable per family (the list of frontier estimates), one new
  hyperparameter (the minimum history count, 3), one new branch (use the median or not). No new module, LLM
  call, rollout type, certificate, threshold or regime boundary.

## Reading the box (unchanged from v0.2 except where the warm start applies)

- **Two operators.** `harden` wraps the environment with a family `w(d)`; `stage` restarts the environment from
  a state `s` reached by the policy's own failed rollout (a compiled Setup prefix; the staged session runs under
  the 100-step config so the replayed prefix does not consume the policy's horizon).
- **One acceptance rule.** `evaluate(env)`: 4 policy rollouts; 0/4 → `too_hard`, 4/4 → `no_effect`
  (`too_easy` inside a bracket), otherwise 4 more; `in_band` iff 3–5 successes of 8; 1–2/8 → `too_hard`;
  6–7/8 → `too_easy`. Both operators use it; an accepted environment is one that returned `in_band`.
- **One guard, asymmetric.** `solvable(env, sources)` replays a known success through the wrapped / staged
  environment and checks that it still reaches the goal: harden tries the policy's own shortest success, then
  the benchmark oracle; stage the oracle only. Any source passing → solvable; replay fails → try the oracle;
  oracle fails → `dropped: uncertified`; no oracle → the probe self-certifies. Observation-axis families are
  solvable by construction. Replays and oracle sessions are not policy rollouts.
- **One budget.** Every policy rollout of a task is charged to `search`, hard cap 30; confirmations (`eval`,
  K = 16, B_L) are never written back. Designer (proposer) calls are ledgered under `designer` for cost
  reporting only and are not charged, in every arm.
- **Six method constants.** B_T, B_L, K, the 3–5-of-8 acceptance, the 4 → 8 probe, the cap of 30. The
  estimator's batch schedule and stopping confidence, the bisection limit (4), the proposer cap (2) and the
  warm start's minimum history (3) are implementation constants in `AEAConfig.impl`.
- **Three outcomes.** `accepted`, `kept`, `dropped` (with a reason: `no_leverage`, `exhausted`, `dead`,
  `uncertified`, `budget`, `too_easy`).
- **Families and leverage.** Leverage rate = the rate, over the tasks where a family was evaluated at d = 1, of
  not returning `no_effect`; families are ordered by it (proposer order until seen). The d = 1 test is ALWAYS
  run. The bracket keeps `lo` = the largest dose known too easy and `hi` = the smallest known too hard for THIS
  task; a non-monotone family ends as `exhausted`; an order violation (more than 0.375 above a lower dose) is a
  diagnostic. The leverage table (rates and frontier histories) is a sequential dependency across tasks and is
  persisted as events.
- **Candidate states.** For each of three failed rollouts of the estimate, the end state and the midpoint
  state; duplicates by state hash removed; at most six; walked latest-first.

## What stays outside the box

Experimental protocol (`scripts/`, `experiments/`); engineering rigor (ledger, manifest, attribution,
resumability, corpus / trace formats, the task pool). The paper shows the box; anything else it claims is shown
necessary by an ablation or omitted.
