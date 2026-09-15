# Iterative LOW smoke: IMPLEMENTATION_FAILURE

2026-09-15. **Stopped on the first task after confirming a semantic privilege leak.**
The generated family encoded the reference-only pillow–sofa association through command
ordering. The frozen lexical guard passed it. No feedback comparison or K16 confirmation
was completed. All remaining paid work stopped; the method stayed frozen.

## 1. Starting safety status

Research worktree: `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`.
Starting HEAD: `01654104c1fbf4e169280ca45bf1e5c91d0c8148`. Only the two preceding design
documents were untracked. Main stayed at `f97260589475bf4412f2310b1dfbcc1c34816547`, with
its pre-existing `? third_party/envharness` status. No checkout/reset/merge/rebase/clean/
stash/pull occurred. Main worktree files were untouched.

## 2. Implementation architecture

New experimental `llm_v2_iterative_low`: bounded DESIGN → freeze viable family → existing
CONTROL. `LowEnvironmentOptimizer` owns original evidence/reference, two-call state, immutable
candidate lineage, typed rejection history and remaining budget callbacks. One family per
call. Mechanical failure requests REPAIR_CODE; semantic/privilege/solvability/no-leverage
failure requests REPLACE_MECHANISM. Existing structural, identity and privilege validators,
solvability, 4→8 evaluator and `assist_bracket` are reused. No CONTROL→DESIGN return.

## 3. Files changed

Production: `src/aea/low_optimizer.py` (new), `controller.py` (adapter/dispatch), `config.py`
(new version), `substrate.py` (reference-provider dispatch). Existing designer code is unchanged;
the new variant's prompt builder lives in `low_optimizer.py`.

Tests: `tests/unit/test_iterative_low.py`, `test_iterative_low_smoke.py`.
Driver: `scripts/e6_iterative_low_smoke.py`. Documentation: the two LOW research documents and
`docs/design/AEA_ITERATIVE_LOW_V2_IMPLEMENTATION.md`. Experiment artifacts: preregistration,
frozen task/evidence/reference hashes, this report and its audit data directory.

## 4. Implementation freeze

**`76e14b3b477e73ffe5f10540a5157dc99b6ab559`**, committed and pushed before paid calls.
Frozen `src/aea` tree: `c075947920a4ff35d31a9532e06ae355a264a418`.
The final source tree still matches it. The only later driver change affects report labeling;
see section21 and [the correction log](e6_iterative_low_smoke/DRIVER_CORRECTIONS.md).

## 5. Legacy/HIGH/MID proof

An independent audit compared 213 original definitions. Only three existing function bodies
changed: `Controller._llm`, `Controller._stage`, and `reference_provider`, to admit the new
version. All existing HIGH/MID/LOW designer, guard, evaluator, bracket and acceptance functions
matched their original ASTs. Eleven reused modules, including `designer.py`, `rules_control.py`,
`families.py`, `witness.py`, `evaluate.py`, `budget.py` and `io.py`, are byte-identical to the
starting commit. HIGH/MID event-stream comparisons and old LOW/v0.4 golden tests passed.

## 6. Offline validation

Before paid calls: **253 unit tests passed**; **9 LLM-free integration tests passed, 1 skipped**
(optional RL-loader test; ray and gymnasium absent). Full Ruff check/format, strict mypy
(85 files) and full pre-commit passed. Independent implementation/driver review passed.
The later audit-only reporting correction has six focused offline driver tests, including
the confirmed-privilege-failure priority case; all passed. No tests used paid APIs.

## 7. Preregistration freeze

**`7c472fba573ca518152062028a327db5c456df72`**, committed and pushed before paid calls.
[Preregistration](../PREREG_ITERATIVE_LOW_SMOKE.md) SHA256:
`046e5c7fa943aabe8e4d53d622b943f2d7f18f61ed1236ac274283dcf293402b`.
Policy, pricing, substrate configs, original evidence and reference hashes were checked before
the paid task. The preregistration is unchanged.

## 8–11. Tasks, references, shared C1 and paired outcomes

Event and independent trajectory audits both found untouched confirmed zeros
`110,114,115,126,129`; selected the four smallest. **129 stayed untouched.** All selected
tasks had complete frozen 0/16 original traces. Three seeded failures from the first ten were
reused with the historical serializer; **zero new original policy rollouts**.

| Task | Frozen rich reference | Shared C1 | D | I |
|---|---|---|---|---|
|110|Available, 5 steps; ID `14c924bb414ffd1e`|Static/guard passed; endpoint4/4 too_easy; semantic audit invalid|CONTROL0.5:4/4;0.25 interrupted; no C2/accept|Same shared family; no physical I call; no completed outcome|
|114|Available, 10 steps; ID `9f1502115cd92a43`|Not generated after correctness stop|Not run|Not run|
|115|Unavailable: verifier_fail|Not generated; task retained|No reference|No reference|
|126|Available, 10 steps; ID `de1683aefd48799c`|Not generated after correctness stop|Not run|Not run|

The primary denominator remains **4**; usable-reference denominator3; paid C1 attempts1.
Recorded endpoint viability is1/1 attempted (1/4 selected), but that candidate violates the
semantic contract, so it is not valid evidence of admissible endpoint delivery.

## 12. Typed feedback actually sent to D

**None.** The automatic gates classified C1 as viable, so DESIGN froze after its first call.
The semantic audit was discovered during CONTROL and was never supplied as an extra designer
opportunity. No manual repair, third chance or post-freeze guard change occurred.

## 13. Independent-arm isolation

No physical I request was made, so no evaluator feedback entered I in this run. The driver
constructs I2 directly from original Evidence plus a neutral previous-source reminder; its
offline paired test verifies exact request construction, shared C1 equality and absent feedback.
This establishes the implemented boundary offline; the paid smoke did not exercise I2.

## 14. Candidate identity and lineage

One candidate, no parent:
`110:C1:326d1b19f1d2b29dff831a2c445e2787ff0b40a36ef9d6be757dff5b64d28ded`.
Full source SHA256: `326d1b19f1d2b29dff831a2c445e2787ff0b40a36ef9d6be757dff5b64d28ded`.
Maximum-dose code SHA256: `cf2de873e76605f6d59c926cc0142d18de76af68743a8ca1fea5e9ddea5e56ec`.
Family: `prioritize_pillow_subgoal`; dose-dependent command priority and subgoal reminder.
[Immutable record](e6_iterative_low_smoke/candidates_110.json) and
[exact source](e6_iterative_low_smoke/candidate_110_C1.py.txt) are retained.

## 15–17. Gate comparison, search acceptance and K16

**Zero completed paired outcomes; zero C2 proposals; zero search accepts; zero K16 runs.**
C1 reached the recorded endpoint-viable stage, but independent semantic audit invalidated it.
No D-better/I-better/tie performance conclusion is available. CONTROL below0.5 was not
completed, and no calibration-resolution conclusion is justified by the partial trace.

## 18. Logical and physical rollout accounting

| Measurement | Physical requested | Complete/error | Logical D | Logical I |
|---|---:|---:|---:|---:|
|Shared C1, d=1|4|4/0|4|4|
|Shared frozen CONTROL, d=0.5|4|4/0|4|4|
|Shared CONTROL, d=0.25, interrupted|4|0/4|4|4|
|Total|12|8/4|12|12|

These are conservatively charged opportunities, not twelve valid measurement outcomes.
At0.25, one episode contains42 actions and three contain none; all four ended with the
transport-stop error and yield no verdict. Each arm has8 of20 adaptation slots unused.
Shared logical designer calls: D1/I1; physical designer calls1. Original evidence is reused
and excluded from fresh adaptation. Later tasks and all confirmation budgets are unused.
[Budget](e6_iterative_low_smoke/rollout_budget_110.json),
[episode manifest](e6_iterative_low_smoke/rollout_manifest.json).

## 19. Physical API spending

**Ledger-priced returned calls: $0.050144814** = designer$0.008095560 + policy$0.042049254.
There were97 returned/priced calls (1 designer,96 policy) and8 rate-limited HTTP attempts,
105 physical attempts total. The conservative account is **$0.084818627**:
peak-priced returned usage$0.058240374 plus$0.026578253 reserved for failed requests.
No in-flight liability remains. No HTTP dispatch began after the correctness stop.
Both logical arms inherit the shared $0.050144814; this is not twice the physical bill.

Returned token usage: designer9,125 input/1,047 output; policy334,522 input/6,396 output.
Policy responses reported4,985 reasoning tokens despite the unchanged thinking-off request
configuration; these are included in completion usage, not added again. All policy responses
identified Alibaba. No provider or pricing guard mismatch was observed. The failed requests'
actual billing is unknown, so their full reservations remain in the conservative bound.
[Priced calls](e6_iterative_low_smoke/priced_calls.json),
[final summary](e6_iterative_low_smoke/summary.json).

## 20. Decision

**IMPLEMENTATION_FAILURE** — the preregistered privilege-isolation correctness gate failed.
This takes priority over the incomplete paired sample and the stop-induced infrastructure
errors. It is neither NO_FEEDBACK_SIGNAL nor a performance-based inconclusive result.

## 21. Issues discovered and post-freeze handling

The reference says the pillow is on sofa1. The three frozen failures only visit/examine the
sidetable, use the lamp or look; none reveals the pillow location. C1's diagnosis explicitly
uses that reference fact, and its source ranks `go to sofa`/`examine sofa` while the pillow is
not held. The policy formatter appends the reordered admissible actions, exposing sofa1 first
before the learner discovers the pillow. Removing the object number from the prefix evaded
the lexical guard while preserving the privileged association.

[Exact evidence](e6_iterative_low_smoke/privilege_evidence.json) includes the reconstructed
policy observation: SHA256 `69567fcf4f37edb7eff255788123812d71a057ce759eb547458cc7426efb39ab`,
episode `d6a9c60b0b`, step1. This proves the information reached the policy surface; it does
not quantify how much of the success came from that information versus the general reminder.

At **2026-09-15T16:20:09.728989Z**, the existing persistent transport stop was set to
`privilege_violation`. The source and prompts stayed frozen. The generic driver initially
labeled the resulting interrupted batch INCONCLUSIVE; the permitted audit-only report fix
makes the documented correctness failure take priority. The original automatic summary is
preserved, and no paid rerun followed. Transient provider429s are reported separately.

## 22–23. What this supports and does not support

The offline evidence supports the bounded state-machine implementation and legacy-path
preservation. This smoke supplies a concrete counterexample to the existing lexical
privilege gate: visible vocabulary can encode an unseen reference-only relationship.

It supplies **no paid evidence about D2 versus I2**, no evidence that feedback improves LOW,
no valid LOW delivery claim, and no EnvHarness comparison, transfer, learner improvement or
outer-loop result. The next review must address this semantic boundary before interpreting
future intervention performance. No larger pilot, additional rounds, budget increase,
parameterization rescue, R arm, HIGH iteration, E6 or E6-SL was started.

**Stopped for review.** Raw local traces remain in `runs/e6-iterative-low-smoke/`.
