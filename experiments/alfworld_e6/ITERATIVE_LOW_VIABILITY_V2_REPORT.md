# Iterative LOW viability V2

**Final decision: INCONCLUSIVE**

Screening outcome: `SCREENING_COST_LIMIT`. The four-task primary sample did not form. Iterative LOW was not evaluated, and screening alone provides no LOW efficacy result.

## Safety, scope and freeze

- Starting HEAD: `d88d2e1b7be3279f89944f155fc41cf1c18a5c2a`; research branch `aea-llm-vnext`.
- Starting research status: clean. Main HEAD: `f97260589475bf4412f2310b1dfbcc1c34816547`; its pre-existing ` ? third_party/envharness` status is unchanged.
- Starting worktrees: `/home/kree/work/EnvJudge` at `f972605` on `main`; `/home/kree/work/EnvJudge-aea-llm` at `d88d2e1` on `aea-llm-vnext`. Terminal research HEAD before this reporting commit: `b6cd05418f619ad23318e55916aaae2a96d07875`, clean.
- All work remained in the research worktree. No active-worktree checkout, reset, merge, rebase, clean, stash or pull was used. Production source was not modified.
- Scope: new screening driver `scripts/e6_iterative_low_viability_v2.py`, screening tests, correction design note, preregistration and audit/report artifacts. ZERO now means 0 successes among 16 valid completed episodes. Up to three fresh executions can obtain each next valid episode (at most 48 executions per task); within-request provider retry is unchanged; recovered provider errors preserve valid outcomes. Unknown billing retains its reservation. LOW, designer prompts, gates, solvability, validator, CONTROL, acceptance, lineage and production `src/aea/` stayed frozen.
- [Correction design note](../../docs/design/AEA_ZERO_SCREENING_INFRASTRUCTURE_SEMANTICS.md); [pool preregistration](PREREG_ITERATIVE_LOW_VIABILITY_POOL_V2.md). The audit derived next unused ID 150 programmatically; task choice followed ascending IDs without semantic selection.
- Pool preregistration: `b6cd05418f619ad23318e55916aaae2a96d07875`; viability preregistration: `NOT_RUN`.
- Preflight before paid calls: **369 unit tests passed**, including 25 V2 driver cases; strict mypy passed on 97 source files, Ruff passed, formatting passed for 185 files, and pre-commit passed. Eleven unrelated integration cases were deselected because production code was unchanged.
- Independent final screening, physical accounting, terminal evidence and preservation audits: **PASS**. All 2,732 original checked files (including 215 historical run files) and all frozen runtime/configuration bindings are unchanged.
- Method/validator commit: `bec74ed8a6ff40e119b2299c92b07b8602ff5fef`; frozen method `llm_v2_iterative_low_semantic_gate`.
- V2 driver SHA256: `c230bcfaea60b3c1b346018a5a7380c96d67c25e4f8fbe75702aef517d6129f4`.
- Pool preregistration SHA256: `016253fade139b52526fe0248254baddc7ee729d4279f5884d9536d895cd00b4`.
- Semantic gate: `alfworld-semantic-screen-v1`, SHA256 `ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`.
- The prior 130–149 report remains permanently `INSUFFICIENT_FRESH_LOW`; both earlier failed implementation smokes retain `IMPLEMENTATION_FAILURE`.

## Fresh screening

Starting ID 150; deterministic ascending order. Inspected 13 IDs: 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162.
Qualified tasks: [154, 158, 159]; infrastructure-inconclusive tasks: [162].

| Task | Valid s/n | Outcome | Invalid returned / unreturned | Recovered physical / episode failures | Ledger USD | Retained failed USD |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 150 | 1/1 | NON_ZERO | 0 / 0 | 1 / 0 | 0.002174692 | 0.002769208 |
| 151 | 1/1 | NON_ZERO | 0 / 0 | 1 / 0 | 0.001250535 | 0.002554747 |
| 152 | 1/1 | NON_ZERO | 0 / 0 | 0 / 0 | 0.002689752 | 0.000000000 |
| 153 | 1/1 | NON_ZERO | 0 / 0 | 0 / 0 | 0.020890688 | 0.000000000 |
| 154 | 0/16 | CONFIRMED_ZERO | 0 / 0 | 116 / 0 | 1.473525274 | 0.743309372 |
| 155 | 1/2 | NON_ZERO | 0 / 0 | 19 / 0 | 0.056040634 | 0.058230016 |
| 156 | 1/1 | NON_ZERO | 0 / 0 | 3 / 0 | 0.023685532 | 0.009987744 |
| 157 | 1/1 | NON_ZERO | 0 / 0 | 1 / 0 | 0.014394211 | 0.004304599 |
| 158 | 0/16 | CONFIRMED_ZERO | 0 / 0 | 88 / 0 | 1.591417685 | 0.655985902 |
| 159 | 0/16 | CONFIRMED_ZERO | 0 / 0 | 33 / 0 | 1.493669827 | 0.253373172 |
| 160 | 1/2 | NON_ZERO | 0 / 0 | 2 / 0 | 0.065899028 | 0.003972488 |
| 161 | 1/1 | NON_ZERO | 0 / 0 | 0 / 0 | 0.004440059 | 0.000000000 |
| 162 | 0/11 | INFRA_INCONCLUSIVE | 1 / 0 | 10 / 0 | 1.413069268 | 0.097151639 |

Executions that end without a valid behavioral result are missing observations. Recovered request errors preserve completed outcomes. ZERO requires exactly 16 valid failures; the first valid success ends a task. All 275 physical failures were HTTP 429 responses and recovered at request level: 274 occurred in valid completed episodes, and one occurred in the final episode later interrupted by the cap. There were zero unrecovered provider requests and one missing behavioral outcome. The task-level recovered-physical column includes only recoveries associated with valid completed episodes.

Task 162 stopped at valid slot 12, attempt 1, on the global cost cap rather than retry exhaustion. It retained 11 valid failures and one invalid twelfth execution; that invalid execution contributes zero behavioral observations. It is `INFRA_INCONCLUSIVE`, not ZERO. IDs 150–162 are now scientifically consumed by this run. IDs 163–169 were not executed in this run; the preregistered scan was not extended.

## Costs and budgets

- Screening: 71 requested executions, 70 valid outcomes, 9 successes.
- Designer calls: 0; adaptation episodes charged: 0; K16 episodes requested: 0.
- Physical requests: 3499 (3224 returned, 275 ambiguous failures, 0 reconciled orphans, 0 unresolved).
- Ledger USD: $6.163147185; conservative returned USD: $6.163147185; retained failed USD: $1.831638887; in-flight USD: $0.000000000.
- Committed cost: **$7.994786072**. Hard caps: screening $8; whole run $20. No double counting of orphan reconciliation. All spending belongs to screening; references, design, adaptation and confirmation each cost $0.
- One local cap denial occurred at `2026-09-16T02:14:32.288837Z`, before a new physical request was sent: the next conservative reservation would exceed $8. The ledger retained $0.005213928 of uncommitted headroom. No physical request or episode dispatch followed the denial.
- All 3,499 physical attempts are settled. Episode operations: 70 completed, one interrupted, zero still dispatched. The $20 total was never reset or raised; the separate $8 screening cap is binding.
- Per-task limits remain three designer calls and 30 adaptation episodes; K16 is evaluation-only. Historical B_L is 4–12/16; B_T is 7–9/16.

## LOW, CONTROL and confirmation

Confirmed-ZERO evidence is frozen in `screening_qualified_evidence.json`: all sixteen valid episode identities/hashes and the exact historical three-trace seeded selection for each qualified task. This remains screening provenance; no adaptation input pool formed.

- Task 154: n=16, seed=154; selected episode IDs ['01485264d7', 'cae8a438ba', '5cabc8ef59']; selected evidence SHA `d4b442dff2c824f6d42a22114448f92ca178ddba2b5d0a5ee7f14c2a2b8e735f`.
- Task 158: n=16, seed=158; selected episode IDs ['7f461cecb1', '7729b3343a', '50434a07d4']; selected evidence SHA `46b84d32279a0843d6a64bd73ae49d005f776f8f913fc9f76ab5c5254deb7445`.
- Task 159: n=16, seed=159; selected episode IDs ['e0fc323400', 'f3583ad1e1', '45c3700f83']; selected evidence SHA `55a935664362fa036ea6ab84853661a3437cb8e9571626706bb97c44e9517b0a`.

| Required viability field | Result |
| --- | --- |
| Reference availability | NOT_RUN; zero reference-provider calls. No `REFERENCE_UNAVAILABLE` claim. |
| Four-task input manifest / viability prereg SHA | NOT_CREATED / N/A; qualification stopped at three tasks. |
| C1/C2/C3 lineage / candidate count | NOT_RUN; zero candidates and zero designer calls. |
| Typed feedback | NOT_RUN; no feedback packets. |
| Structural, d=0 identity, lexical and semantic candidate gates | NOT_RUN / N/A. Semantic FAIL and UNCERTAIN were not measured. |
| Solvability / d=1 endpoint outcomes | NOT_RUN / N/A. |
| CONTROL histories | NOT_RUN; no CONTROL episodes. |
| Search acceptance | Zero accepted environments; no candidate was evaluated. |
| Fresh adaptation rollouts | 0. |
| K16 episodes / B_L / B_T | 0 episodes; both confirmation results N/A. |

**Primary K16 B_L result: N/A.** No four-task efficacy denominator applies; this is not a 0/4 LOW result. The candidate failure funnel was not assessed. The available three tasks were retained without substitution; no reference regeneration or failure-only fallback was used.

## Interpretation and next action

Stop this run. Keep LOW frozen; review the cost of forming a four-task fresh ZERO input pool before separately preregistering any further paid collection. No LOW mechanism change follows from these data.

Single direct blocker: The fourth confirmed ZERO task was not obtained before the fixed $8 screening committed-cost cap stopped collection. The LOW method itself was never evaluated.

Raw screening traces, request ledgers and subprocess logs remain local. No candidate, privileged reference, gate input or feedback artifact was produced. Compact JSON records episode identities, screening decisions, counts and hashes; artifact_manifest.json binds local source files. Historical reports remain unchanged.

## Audit artifacts and reporting correction

[Compact result](results/iterative_low_viability_v2/result.json), [screening table](results/iterative_low_viability_v2/screening.tsv), [qualified evidence](results/iterative_low_viability_v2/screening_qualified_evidence.json), [source artifact hashes](results/iterative_low_viability_v2/artifact_manifest.json), [screening audit](results/iterative_low_viability_v2/screening_audit.json), [physical audit](results/iterative_low_viability_v2/physical_audit.json), [terminal audit](results/iterative_low_viability_v2/terminal_audit.json), and [preservation audit](results/iterative_low_viability_v2/preservation_audit.json) accompany this report. Audit source snapshots are archived with the results.

An initial supplemental checker incorrectly required numeric `trace.task_id`. The real trace schema uses corpus label `alfworld-corpus-ours-release` in `task_id` and numeric bridge identity in `rollout_seed`, as the existing passing screening auditor already checks. The corrected supplemental audit passes 3,897 checks and preserves the initial 48 false failures and their source hashes. This was an offline reporting-check correction; no method code, prospective rules or run artifact was patched.

The report makes no claim about semantic admission or LOW efficacy because those stages never ran. Stop here; no D/I, mechanism additions, HIGH iteration, outer AEA integration, E3 or E3-SL was executed.
