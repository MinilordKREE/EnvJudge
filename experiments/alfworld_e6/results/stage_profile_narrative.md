## Narrative (hand-written after the run; every number above comes from the tables script)

### Decision

**STAGE_AXIS_SUPPORTS_CONTROL**, by the pre-registered rule applied in its pre-registered order:
6 of 6 references verified, 30 of 30 anchors valid, 24 probeable; L = 5 tasks with leverage
(max - s(0) >= 3 of 8), F = 5 tasks with frontier evidence (1 useful-band anchor + 5 dead-to-easy
crossings), N = 0 meaningful reversals, so rule 3 (L >= 4, F >= 3, N < L / 2) fires before the
step-like residual rule. The rule was written with dead-to-easy crossings counted as frontier
evidence ("a crossing suggesting an intermediate frontier"); the caveat below is part of the
result, not a reinterpretation of it.

### What the surface looks like (raw, four probeable anchors per task)

| task | t / T -> successes of 8 | shape |
| --- | --- | --- |
| 33 | 0: 0, 0.22: 0, 0.44: 3, 0.78: 8 | dead -> useful -> easy: the one ORDERED_FRONTIER with a measured useful anchor |
| 43 | 0: 0, 0.25: 0, 0.50: 8, 0.75: 8 | dead -> easy within one anchor gap (3 expert actions) |
| 53 | 0: 0, 0.27: 0, 0.50: 0, 0.73: 0 | dead at every probeable anchor; the last 6 of 22 expert actions are never handed over |
| 54 | 0: 0, 0.27: 1, 0.53: 0, 0.73: 8 | dead -> dead -> easy within one gap (3 actions); one non-meaningful dip (1 -> 0) |
| 56 | 0: 0, 0.26: 8, 0.52: 8, 0.74: 8 | the first 6 of 23 expert actions already make the task trivial |
| 58 | 0: 0, 0.25: 0, 0.50: 2, 0.75: 8 | dead -> near-useful (2 of 8) -> easy |

Leverage: 5 of 6. Ordering: no meaningful reversal anywhere; fraction nondecreasing 1.0 on five
tasks and 0.667 on task 54 (a single 1 -> 0 step). Frontier crossing: 5 of 6 cross from dead
(<= 1) to easy (>= 6). Useful band directly observed: 1 of 6 (task 33, 3 of 8); task 58 sits one
success below it (2 of 8) at the same 50 % anchor.

### Interpretation, kept to the four separate properties

- Leverage: reference progress is a broadly effective LOW intervention axis for this policy
  (5 of 6 fresh zero tasks go from 0 of 8 to 8 of 8 somewhere before the terminal state).
- Ordering: at this resolution the responses are nondecreasing in t on every task up to noise
  (one 1-success dip); nothing observed contradicts an ordered axis, but four anchors per task
  cannot establish monotonicity between them.
- Resolution: the transition from dead to easy happens within one anchor gap (3 to 6 expert
  actions) on four of the five leveraged tasks and is only resolved on task 33 (and nearly on
  58). Whether an intermediate state that lands in 3..5 of 8 exists inside those gaps is
  unmeasured. This is the STEP_LIKE majority the category table shows, and it is exactly the
  question a control experiment would have to answer; it is not evidence that no such state
  exists, and it is not evidence that one does.
- Controllability: not tested here. Nothing in this phase shows that a search over t would land
  in the band within the 30-rollout cap.

Sanity anchors: t = 0 was 0 of 8 on all six tasks (consistent with their 0 of 16 classification);
t = T was terminal (won) on all six, as the ALFWorld semantics audit predicted, so the 75 % anchor
is the strongest probeable point on every task.

### What phase 3.3a establishes

- A fresh, frozen behavioural pool of 50 tasks (14 zero, 19 middle, 17 saturated, 0 invalid),
  with 8 zero tasks (62, 66, 67, 70, 71, 73, 78, 79) untouched for prospective tests.
- On six fresh zero tasks, silently replaying a verified expert prefix is a strong lever on
  current-policy success (5 of 6), the response is ordered at anchor resolution (0 meaningful
  reversals), and the dead-to-easy transition lies inside a known interval of at most 6 expert
  actions on each leveraged task.

### What it does NOT establish

- That p(t) is monotone between anchors, or that a useful-band state exists inside every
  dead-to-easy gap (observed directly on 1 of 5 leveraged tasks).
- That binary search, neighbouring-cut search or any Stage-depth controller would find such a
  state within budget; no controller was run.
- Anything about tasks without leverage at these anchors (task 53: the expert's final 6 actions
  were never staged because t = T is terminal; a finer anchor near the end was not measured and
  must not be added post hoc).
- Anything about downstream learners (no skill learning was run) or about HIGH.

### Recommended scientific question for phase 3.3b (not implemented)

Given that the dead-to-easy transition is confined to one anchor interval on most leveraged
tasks, the next hypothesis to pre-register is about resolution and controllability inside that
interval: does the response surface within a dead-to-easy gap contain a state whose current-policy
response lies in 3..5 of 8, and can a bounded, pre-specified refinement (a fixed number of
additional cuts inside the bracketing interval, evaluated with the same fixed K) locate it within
the existing 30-rollout cap? The experiment should be prospective on the eight untouched zero
tasks, should compare a fixed-K refinement against the existing 4 -> 8 acceptance probe on the
same cuts, and should treat "no useful state exists in the gap" as a valid outcome. It should
not assume monotonicity, and it should not be built into the method before that test.

### Post-hoc overlay (descriptive, no new LLM call)

The phase-3.2 designer's reference cuts on other tasks (20: t = 3 and 5 of 8; 27: t = 2 and 3 of
8) all fell in the 25-60 % range of their references and produced 0/4 or 4/4; on the present
profiles that range is exactly where the dead-to-easy transition sits (33: 44-78 %, 43: 25-50 %,
54: 53-73 %, 58: 50-75 %). No diagnosis was used to pick anchors here.

### Spend

Fresh-pool K16 USD 38.13 (800 rollouts, cap 60); reference generation USD 0 (in-process);
Stage-profile probes USD 10.33 (192 rollouts, 0 errors, 0 re-runs, cap 35).
