# E3 complete AEA integration — layer-one performance

Implementation: `969e339281e71190d1df6aed579b2402513bcd45`. All 30 existing tasks completed; offline execution audit **PASS (117528 checks)**.

The new arm uses fresh baseline≤16 plus adaptation≤30, with all search episodes in the denominator. Historical R/G/AEA v0.2 use their original cap30 including baseline. This comparison is not budget matched. The same cohort and learner configuration are retained. The designer backbone is retained, while design contracts differ and the new arm adds an independent privilege judge. API execution occurs later; no old arm was rerun.

The integrated implementation completed the cohort, but its observed productivity did not improve on the historical comparators. It produced 8 final environments, of which 5 were K16-learnable. LOW produced no final environments. The intervals below describe task-bootstrap uncertainty; this historical comparison is not a causal estimate of the integration or iterative feedback.

## Learner-facing environments

| Arm | Environments | K16 learnable | Search episodes | Learnable /1000 [95% task bootstrap CI] |
|---|---:|---:|---:|---|
| O |30|6|0|undefined|
|R|4|3|330|9.09 [0.00, 21.05]|
|G|14|10|655|15.27 [6.99, 25.93]|
|AEA v0.2|9|9|730|12.33 [5.19, 21.54]|
|AEA integrated|8|5|710|7.04 [1.44, 14.08]|

K16 learnable means 4-12/16 successes; search acceptance remains 3-5/8. Fresh confirmations also cover kept MID tasks. O productivity is undefined because its search charge is zero.

## Adaptation and coverage

- Transformed-only: 2/3 learnable; 2.82 [0.00, 7.04] per1000 search episodes.
- Original-zero unlocks: 0 (none). Historical G:1; AEA v0.2:0; R:0.
- Original-band preservation: 3/6. Narrow B_T confirmations: 1.
- Saturated-subset transformed productivity: 5.32 [0.00, 12.82] per1000.
- Fresh measurement regimes: {"HIGH": 15, "LOW": 10, "MID": 5}.

## Branch outcomes and bottlenecks

| Fresh regime | Tasks | Search episodes | Final environments | K16 learnable |
|---|---:|---:|---:|---:|
| LOW |10|252|0|0|
| MID |5|38|5|3|
| HIGH |15|420|3|2|

LOW made 24 designer calls: six candidates stopped at fast privilege checks, and 18 independent judge decisions were 12 PASS, five FAIL and one UNCERTAIN. All 12 admitted candidates passed solvability. Every LOW task reached at least one admitted, certified endpoint, so the zero yield cannot be attributed entirely to gate exclusion. Eight endpoints were too hard and four were too easy; none was in band. Four tasks froze a viable family but exhausted CONTROL, five exhausted three DESIGN calls, and task18 stopped with 14 adaptation episodes remaining because the frozen reserve required 16. Fourteen actual redesign transitions used REPLACE_MECHANISM: eight privilege and six no-leverage. These dispositions do not establish judge accuracy or a causal feedback effect.

MID kept all five original environments without designer, reference or judge calls. Their fresh K16 results were 10, 3, 11, 8 and 14 successes for tasks4,5,6,16,26. Historical AEA v0.2 kept cases reused the shared-original confirmation; the new arm uses fresh K16. Lower confirmation counts on kept cases therefore cannot be interpreted as harm from a transformation. Fresh measurement also routed historical-band task19 to HIGH.

HIGH made 15 one-shot designer calls with 28 valid proposals. Nineteen certified endpoints were nine too easy and ten too hard; two other candidates failed solvability certification. Ten families froze: three were accepted, five exhausted CONTROL and two stopped for budget. Five other tasks dropped for no leverage. Seven valid secondary proposals remained untried after a family froze. Accepted tasks2,13,19 respectively confirmed at 11/16, 4/16 and 2/16, using their exact frozen sources and doses. Only the first two were learnable. Task15 and task28 each charged four episodes from an incomplete interior probe: a required four-episode top-up exceeded the two episodes remaining, so neither partial probe generated a completed verdict.

## Accounting and interpretation

Baseline 318; adaptation 392; confirmation 128 episodes. Logical returned-call cost **USD 41.228122** including the endpoint probe. Physical conservative total **USD 42.552570**, including retained ambiguous-attempt estimates. No monetary cap.

The run used 838 policy episodes in total, 39 designer calls, and 36 logical judge calls for 18 candidate decisions. All physical journals closed: 28,517 attempts, 28,496 returns, 21 ambiguous failures, zero in flight and zero invalid-usage records. The conservative total includes USD 0.072778 retained for ambiguous attempts; those estimates are not asserted provider charges.

LOW uses the unchanged R5 judge. Its historical Phase A remains NOT_READY; candidate PASS is admission, not a leakage ground-truth label. This evaluates integrated operation and environment productivity on a reused cohort, without isolating iterative feedback causally. No post-K16 redesign or judge retuning occurred.

Full references, requests/responses, candidate code and surfaces remain local/gitignored. Public JSON contains allowlisted numeric/category/hash metadata. See the prospective [protocol](PREREG_INTEGRATED_AEA.md) and [machine-readable report](results/integrated_aea/report.json).

## Reporting provenance

The original frozen report was preserved before applying the reporting-only unlock definition reviewed at 2026-09-17 13:12:46 UTC, before terminal outcomes. Unlocks count K16-learnable transformed environments on historical exact-zero tasks. The correction is NO_NUMERIC_CHANGE: zero unlocks under either definition; all task metadata, productivity values and experimental behavior are unchanged. The JSON records the original-report, review-memo and correction-helper hashes. Model/settings wording was qualified against the frozen configurations and historical manifests; the branch descriptions are offline summaries of the saved artifacts.

## Per-task results

| Task | Regime | Outcome | Designer calls | Search episodes | K16 | Learnable |
|---|---|---|---:|---:|---|---|
|0|LOW|dropped|3|20|—|False|
|1|HIGH|dropped|1|14|—|False|
|2|HIGH|accepted|1|38|11/16|True|
|3|HIGH|dropped|1|36|—|False|
|4|MID|kept|0|8|10/16|True|
|5|MID|kept|0|6|3/16|False|
|6|MID|kept|0|8|11/16|True|
|7|HIGH|dropped|1|30|—|False|
|8|LOW|dropped|2|34|—|False|
|9|LOW|dropped|1|30|—|False|
|10|LOW|dropped|1|34|—|False|
|11|LOW|dropped|3|18|—|False|
|12|HIGH|dropped|1|14|—|False|
|13|HIGH|accepted|1|22|4/16|True|
|14|LOW|dropped|3|14|—|False|
|15|HIGH|dropped|1|38|—|False|
|16|MID|kept|0|10|8/16|True|
|17|LOW|dropped|3|38|—|False|
|18|LOW|dropped|2|26|—|False|
|19|HIGH|accepted|1|44|2/16|False|
|20|LOW|dropped|3|18|—|False|
|21|HIGH|dropped|1|18|—|False|
|22|HIGH|dropped|1|14|—|False|
|23|HIGH|dropped|1|30|—|False|
|24|HIGH|dropped|1|30|—|False|
|25|HIGH|dropped|1|18|—|False|
|26|MID|kept|0|6|14/16|False|
|27|LOW|dropped|3|20|—|False|
|28|HIGH|dropped|1|44|—|False|
|29|HIGH|dropped|1|30|—|False|
