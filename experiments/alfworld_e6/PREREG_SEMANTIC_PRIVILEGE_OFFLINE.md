# Semantic privilege screening: offline validation preregistration

Recorded before the new benchmark is executed, 2026-09-15.
Starting commit: `5675632ae4b1838fe9f14b62923d1716b18dd532`.
Worktree: `EnvJudge-aea-llm`; branch: `aea-llm-vnext`.

## Scope and version

Implement independent semantic privilege screening in the explicit experimental variant
`llm_v2_iterative_low_semantic_gate`. Retain the privileged successful reference in DESIGN.
This changes candidate admission; it is a method implementation change, not an audit repair.
The previous smoke and its `IMPLEMENTATION_FAILURE` remain immutable.

This preregistration authorizes only local implementation and offline validation. No new D/I
smoke, paid model call, policy rollout, pool screening, confirmation, or training is part of
this work. A later four-task smoke requires its own concrete preregistration and authorization.
Do not inherit the old four tasks' unused status: task 110 has already been used.

## Frozen method components

Keep `src/aea/low_optimizer.py`, its prompts, two-call cap, typed operations,
D/I input construction, freeze boundary, CONTROL algorithm, policy rollout budget,
measurement, solvability and acceptance unchanged. Old method variants remain available.
The new admission adapter calls the existing optimizer and validators without a second
optimizer state machine. HIGH/MID use their existing paths.

Order: structural/schema/API and identity checks; lexical privilege checks; semantic
screening; solvability; endpoint policy probe; existing feedback/freeze/CONTROL.
FAIL permits the existing privilege/REPLACE_MECHANISM feedback. UNCERTAIN stops without
certification, policy probes or another designer attempt. Missing evidence or screening
errors cannot authorize a probe. Candidate admission checks cover a fixed offline prefix
suite and all doses reachable by the configured bounded CONTROL; selected dose authorization
is checked before measurement. This finite screen is not a proof over arbitrary execution.

## Information domains and evidence

The designer may read original historical failures and the verified reference.
Learner authorization is scoped to task, episode and step: goal, declared public task
structure, original observations and actions up to that point, and current original
admissible commands. Historical episodes' discoveries are not unioned into fresh-episode
knowledge. Candidate outputs and candidate-written extras never justify their own disclosure.

Execute actual candidate hooks against copies of the same original state/history. Record
original/transformed policy observation formatting, observation data, command ordering and
filtering, action mapping/block reasons, and transition feedback. Preserve a candidate
instance along a prefix to exercise delayed activation, separately for every dose.
Record incomplete, unsupported or divergent replays explicitly.

The required result has PASS/FAIL/UNCERTAIN, information, reference_evidence,
public_evidence_check, candidate_evidence and activation. Audit source, inputs, detector and
fixture hashes. The default offline detector must execute its evidence-grounded checks;
scripted expected labels or a mocked LLM response are not semantic accuracy validation.
If a separate LLM adapter is implemented, mocked tests validate only its protocol/error
handling. No empirical reliability claim about an unqueried remote judge is permitted.

## Required labeled regression suite

| Case | Expected |
|---|---|
| Archived task 110 candidate, undiscovered pillow/sofa relation | FAIL |
| Reminder after learner has directly observed pillow at sofa | PASS |
| Generic prerequisite reminder | PASS |
| Hidden-location command ranking | FAIL |
| Hidden-location command filtering | FAIL |
| Hidden-location transition feedback | FAIL |
| Delayed activation of hidden information | FAIL |
| Dose-dependent hidden information at its triggering dose | FAIL |
| Emphasis of information already stated in task goal | PASS |
| Directly encoded reference action sequence | FAIL |

Additional checks: historical-failure knowledge separation, self-generated evidence
laundering, action block/remapping, runtime errors/missing evidence, and legitimate generic
assistance. Exact task 110 source is reused with provenance; synthetic extensions are marked
as development regressions, not a held-out benchmark. Negative controls must exercise an
actual transformed surface, not only identity wrappers.

## Decision and reporting

Require every required case to match its expected label, task 110 to fail reproducibly,
and integration spies to demonstrate zero solvability/policy calls after FAIL/UNCERTAIN.
Verify semantic FAIL uses existing REPLACE_MECHANISM and the two-call cap; UNCERTAIN stops;
PASS follows the existing certification/measurement path. Verify old variants/HIGH/MID,
optimizer/prompt/control/budget/acceptance hashes and old results remain unchanged.

Run full offline unit tests, LLM-free integration tests, Ruff, formatting, strict mypy and
pre-commit. Report exact test counts, skips, benchmark results, source/fixture hashes and
implementation/freeze commits. A failure requires a documented implementation correction
and rerun; no retrospective relabeling to improve accuracy. Even a fully passing regression
suite establishes bounded regression coverage, not general semantic isolation or D/I benefit.
