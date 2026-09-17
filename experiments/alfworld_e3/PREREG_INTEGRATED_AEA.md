# E3 integrated AEA — prospective layer-one run

Protocol: `e3-integrated-aea-v1`; implementation selector: `llm_v2_integrated`.
Prepared before new-arm paid execution. Frozen hashes: `frozen/integrated_aea.json`.
Design: [complete AEA integration](../../docs/design/AEA_INTEGRATED.md).

## Scope and authorization

Run the new AEA arm on the existing ALFWorld train task IDs/seeds 0–29. Reuse the already
published O, R, G and AEA v0.2 results from `results/e3_layer1_data.json`. Do not rerun those
arms, extend the task pool, tune the judge, collect a new screening benchmark, run D/I,
E3-SL or downstream learning. Latest user authorization explicitly requests full integration
then E3 without a monetary ceiling. Old pilot ledgers and their USD20 authorization remain
closed historical records; the new experiment uses a separate namespace and accounting.

Recipients remain DeepSeek `https://api.deepseek.com` for designer/judge inputs, including
privileged references and failed trajectories; OpenRouter `https://openrouter.ai/api/v1`
with Alibaba-pinned Qwen for admitted learner-facing inputs only. Nothing in this protocol
permits publishing privileged/raw materials. No further user confirmation is a startup gate.

## Frozen execution

- Learner: existing E3 `qwen/qwen3-8b`, Alibaba pin, reasoning off, temperature .5,
  max output 2048, 50 environment steps, unchanged policy prompt/history/action format.
- Designer: existing `deepseek-v4-pro`, thinking off, temperature .7. Existing HIGH request
  output bound 4096; existing iterative LOW request output bound 6144.
- LOW judge: exact frozen R5 `WitnessCheckingPrivilegeJudge` configuration/prompts/schema;
  no sixth judge-engineering round. Phase A remains NOT_READY. Only candidate PASS admits.
- Fresh original measurement: Beta posterior and .9 stopping confidence; batches 4 then2,
  at most16 valid episodes; maximum posterior-mass regime. No warm starts or prior history.
- LOW: at most3 designer calls; unchanged typed feedback, endpoint reserve16, privilege
  admission and solvability. HIGH: one designer call, at most2 families. MID: original.
- Endpoint: 4→8, 0/4 or4/4 no top-up, accept3–5/8. First viable family freezes permanently.
  CONTROL changes dose only, first interior .5, at most4 bisections. No CONTROL-to-DESIGN.
- Separate baseline≤16 plus adaptation≤30; **all** valid baseline+adaptation episodes count
  as charged search. This preserves the pilot LOW envelope and differs from old E3's
  cap30 including baseline. The new comparison is not described as budget matched.
- Fresh independent K16 for every accepted or kept final environment, including MID.
  B_L4–12/16, B_T7–9/16. No K16 outcome enters search, redesign, routing or acceptance.
- Original E3 task order (ascending historical shared p16, ties by ID) schedules execution
  only; original K16 does not supply measurement or feedback. At most16 policy episodes
  concurrently (4 tasks ×4 workers). One ledgered routing probe precedes the arm.
- No USD cap. Preserve frozen client retry bounds and method rollout/candidate limits.
  Every physical API attempt is journaled before dispatch, with exact request hashes and
  returned usage/cost. Ambiguous failures retain a separate upper-rate reservation estimate.
  A correctness, accounting or terminal infrastructure failure stops new dispatch; no
  implicit re-execution of partially completed tasks or confirmation batches.

## Analysis specified before outcomes

Primary: learner-facing K16-learnable environments per1000 charged search episodes,
including baseline. Secondary: transformed-only productivity; learner-facing coverage out
of30; accepted-transform precision; fresh K16 successes and target-band counts; original
band preservation; original-zero unlocks; saturated-subset transformed productivity;
designer/judge calls, candidate rejection categories, baseline/adaptation/eval episode costs,
returned logical USD, physical returned estimates and unresolved reservations.

Use the original E3 subset definitions from the frozen shared-original K16 and the original
10,000 task bootstrap procedure (seed20260911). Reuse historical comparator estimates/CIs.
O has30 original environments,6 learnable, zero adaptation charge; its per-search-rollout
productivity is undefined. Report absolute coverage for O, not an invented denominator.

Report the new arm's comparison with G/R/AEA v0.2 transparently: different search envelope,
later API execution, and exploratory reuse of an established cohort. It is an engineering
integration/performance comparison, not a paired causal isolation of iterative feedback.
Do not discard difficult tasks, relabel gate errors, or selectively rerun noisy confirmations.

## Required per-task output and publication

Unified task artifact: regime; measurement evidence; designer calls; candidate lineage;
privilege decisions; solvability; endpoint; control trace; final environment; rollout and
USD accounting; independent K16. Keep complete artifacts under
`runs/e3-integrated/private/`. Publish only allowlisted metadata/hashes plus implementation,
tests, protocol, audit and report. Verify all30 tasks, source freeze, fresh episode identity,
admission-before-policy and method-state immutability through K16 before final reporting.
Old implementation failures, R5 judge validation and task154/159 pilot results remain intact.
