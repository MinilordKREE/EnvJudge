# AEA v0.2 — the method of record (owner text, 2026-09-10)

Supersedes `docs/spec/AEA_v2.md` as the description of the METHOD. Everything in that document that
is not in the box below is experimental protocol (it lives in `scripts/` and `experiments/`),
reporting detail (it lives in the tables), or a v0.1 mechanism removed by `docs/changelog_v0.2.md`.
Every method module's docstring cites this file.

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
            bracket [lo=0, hi=1]; up to 4 bisections with the 4 → 8 rule:
                too_easy → lo = d; too_hard → hi = d; in_band → accept w(d); break
                order violated → stop this family
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

## Reading the box

- **Two operators.** `harden` wraps the environment with a family `w(d)`; `stage` restarts the environment from
  a state `s` reached by the policy's own failed rollout (a compiled Setup prefix; the staged session runs under
  the 100-step config so the replayed prefix does not consume the policy's horizon).
- **One acceptance rule.** `evaluate(env)`: 4 policy rollouts; 0/4 → `too_hard`, 4/4 → `no_effect`
  (`too_easy` inside a bracket), otherwise 4 more; `in_band` iff 3–5 successes of 8; 1–2/8 → `too_hard`;
  6–7/8 → `too_easy`. Both operators use it; an accepted environment is one that returned `in_band`.
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
  implementation constants in `AEAConfig.impl` and do not appear in the method section.
- **Three outcomes.** `accepted` (with the environment), `kept` (E itself is learnable), `dropped` (with a
  reason: `no_leverage`, `exhausted`, `dead`, `uncertified`, `budget`, `too_easy`). Reports may group by reason.
- **Families and leverage.** A family's measured leverage is the rate, over the tasks where it was evaluated at
  d = 1, of not returning `no_effect`. Families are ordered by that rate (proposer order until a family has been
  seen). The d = 1 leverage test is ALWAYS run on every task: the prior changes only the first bisection point.
  Per task and family the sequence is: evaluate w(1) (4 → 8); if `in_band` accept, if `no_effect` record
  leverage 0 and move on; otherwise bisect on [lo = 0, hi = 1] starting at the midpoint, or, when the family's
  leverage rate is ≥ 0.9 over ≥ 5 tasks, at the family's last accepted dose; at most 4 bisections
  (10 + 4 + 8 + 8 = 30). The bracket keeps `lo` = the largest dose known too easy and `hi` = the smallest known
  too hard; a result that contradicts the order (a harder dose measurably easier than an easier one) stops the
  family for that task.
- **Candidate states.** For each of three failed rollouts of the estimate (seeded sample), the end state and the
  midpoint state; duplicates by state hash removed; at most six; walked latest-first.

## What stays outside the box

- Experimental protocol: task sets, seeds, arms, bank protocols (T2 / U), evaluations, the released baselines,
  the hand-off extension, all in `scripts/` and `experiments/`.
- Engineering rigor, unchanged from v0.1: the ledger (one row per LLM call, provider pin, price guard), the run
  manifest, `AeaSubprocessRunner` attribution, resumability, and the corpus / trace formats consumed by
  envharness.
- The paper shows the box; anything else it claims is shown necessary by an ablation or omitted.
