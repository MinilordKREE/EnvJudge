# Experimental iterative LOW v2 implementation

Date: 2026-09-15. Starting commit: `01654104c1fbf4e169280ca45bf1e5c91d0c8148`.
Variant: `llm_v2_iterative_low`.

**This version tests iterative DESIGN only. It does not yet implement a full iterative AEA
outer loop.** The implementation follows the smaller two-call smoke specification, which
supersedes the larger budgets and parameterization rescue proposed in
[LOW_ITERATIVE_RSI_REDESIGN.md](LOW_ITERATIVE_RSI_REDESIGN.md).

## Scope and state machine

`MEASURE → DESIGN → CONTROL` remains the method. MID keeps the environment. HIGH calls the
existing llm_v1 designer and controller. Only ZERO/LOW dispatches to the new adapter.

`LowEnvironmentOptimizer` in `src/aea/low_optimizer.py` owns the frozen original evidence,
verified reference, immutable proposal records, typed rejection history, current/frozen
family, source hashes and remaining call/budget information. Certification, policy measurement
and the remaining rollout count are callbacks. It cannot access confirmation results.

1. Reuse the historical three seeded failures and rich reference serializer.
2. Make one designer call for exactly one `W(d)` assistive Rules family.
3. Check the schema and reuse `validate_rules_template`, `identity_at_zero`, and
   `privilege_check`. Every source has a full SHA256 identity and parent link.
4. Run the existing solvability guard at `d=1`, with no by-construction exemption.
5. Measure the endpoint with the unchanged 4→8 evaluator.
6. On previability failure, make at most one feedback-conditioned proposal if the policy
   reserve permits it. A duplicate source never receives another policy evaluation.
7. An `in_band` or `too_easy` endpoint ends DESIGN and freezes the family. `in_band` accepts;
   `too_easy` enters the existing `assist_bracket`. Failed CONTROL ends unresolved.

`run()` is single-use. There is no return from CONTROL, third call, Stage fallback, fixed
library fallback, parameterization rescue, cross-task memory, population or policy update.

## Typed feedback

| Failure | Requested operation |
|---|---|
| Schema, missing placeholder, undefined DOSE, constructor/API error | `REPAIR_CODE`: preserve support mechanism, repair implementation |
| Changed hook at dose zero, privilege/task-preservation violation | `REPLACE_MECHANISM`: choose different legal support |
| Guard cannot certify candidate (`blocked`/`verifier_fail`) | `REPLACE_MECHANISM`, with exact guard result |
| Endpoint `too_hard` | `REPLACE_MECHANISM`, with source/hash/mechanism, s/n/verdict and one compact failed rollout |
| Duplicate source | Reject without new policy evidence; no extra opportunity |

Behavioral feedback retains the episode ID and blocked/no-effect flags using the existing
trajectory renderer (six head and three tail steps). Both original failures and the reference
remain available to the designer. No K16 information is accepted by this interface.

Missing reference/oracle, expert error/timeout/stuck, environment errors and incomplete policy
batches stop as inconclusive. A successful later oracle attempt remains certified despite
earlier failed attempts. `verifier_fail` is bounded non-certification, not proof of universal
unsolvability. Existing smoke identity and lexical privilege checks remain incomplete semantic
guarantees; this version does not add an LLM judge or strengthen their policy.

## Freeze and identity records

The frozen `AssistFamily` holds source, mechanism, direction and dose semantics. CONTROL gets
only that family and its measured endpoint. The adapter writes `low_family_frozen` with its
full source hash and DESIGN candidate ID. The accepted outcome links that ID/hash to the
existing corpus family/dose record. Existing corpus serialization is unchanged.

Every completed proposal appends a frozen `CandidateRecord`: candidate and parent IDs,
call index, requested operation, source/hash, mechanism, structural/privilege reasons,
solvability result, endpoint tuple, rejection and remaining calls/rollouts. Earlier records
are never overwritten. A `finally` block retains completed candidates if a later provider
call fails. Successful oracle witness actions are omitted from these gate records.

References stay in the existing privileged reference file. Designer call evidence uses the
existing reference redaction; generated source and typed rejection packets are audit artifacts,
not policy input. Actual candidate code still passes the unchanged privilege gate.

## Budgets and unchanged primitives

`MAX_OPTIMIZER_CALLS = 2` is frozen in the module. Before a proposal, remaining policy budget
must cover the worst-case endpoint plus one full calibration measurement: `2 * probe[1]`,
16 with the frozen defaults. This conservative check also applies before C1. The existing
controller cap includes original estimation; typical zero estimation costs 10 of 30, leaving
20. The smoke directly reuses frozen evidence and gives each arm exactly 20 fresh adaptation
rollouts. Shared C1 evidence is charged logically to both arms and physically once.

One 0/4 endpoint leaves 16, allowing C2. A mixed too-hard endpoint costing eight leaves 12,
so C2 is withheld with `budget_unresolved`. Unused budget is not replenished. CONTROL keeps
the existing batch charging, 3–5/8 acceptance, inward bisection and four-bisection limit.
Confirmations remain outside search and are never sent to DESIGN.

There is no new field in the old configuration defaults, preserving old configuration hashes.
Only the method-version Literal and two dispatch predicates admit the new version. The
original `designer.py`, `rules_control.py`, `families.py`, `witness.py`, `evaluate.py`,
`budget.py`, `io.py`, `estimate.py`, `bracket.py`, `stage.py`, and `stage_control.py` are
byte-identical to the starting commit. Among existing function bodies, only `_llm`, `_stage`,
and `reference_provider` change to dispatch the new variant.

## Validation and smoke boundary

`tests/unit/test_iterative_low.py` covers HIGH/MID event-stream equality, all feedback routes,
C1/C2 freeze and acceptance, unresolved CONTROL, duplicate suppression, both caps, immutable
lineage, provider outage, recovered oracle success, reference/K16 isolation and old LOW/v0.4
golden behavior. Existing tests remain unchanged. Full unit/integration/lint/type and
pre-commit results are recorded with the implementation freeze and smoke report.

The separate experiment driver imports the production optimizer, guard, evaluator and CONTROL.
It constructs I's second input independently from the original evidence and a neutral previous
source reminder. It caches shared C1 and confirms identical final environment hashes once.
An experiment-only transport reserves a conservative cost bound before every physical HTTP
attempt, including retries and concurrent requests, against USD12. Its conservative account
is reported separately from the ordinary priced API ledger.

The preregistration fixes four unused LOW_POOL_3 tasks, evidence/reference instances, arm
definitions, call/rollout/cost caps and decision rules before any paid call. Source, prompts,
optimizer behavior and thresholds are frozen at the implementation commit. Any subsequent
driver/audit correction must be logged. The smoke ends for review without automatic scale-up.

## Pre-freeze verification record

- Full unit suite: 252 passed (212 existing plus 40 new tests), 10 integration tests deselected.
- Full LLM-free integration suite: 9 passed, 1 optional RL-loader dependency skip; 361.78 s.
- Full Ruff check and format check passed; strict mypy passed on 85 source files.
- Full pre-commit hooks passed, including private-key/large-file checks and strict mypy.
- Independent AST audit: 213 original definitions inspected, only the three allowed dispatch
  functions changed; all other original functions matched. Main worktree status remained
  `main` with its pre-existing `? third_party/envharness` entry.
- Offline cost-driver tests exercise reservation denial before HTTP, uncertain retry charging,
  shared-C1 static/guard/policy reuse, equal logical charging, C2 regression reporting,
  independent prompt construction and shared final K16. No paid API call was used by tests.

The last driver-only hardening preserves a sticky monetary stop and gives bound/accounting
violations priority as `IMPLEMENTATION_FAILURE`; its focused tests and pre-commit are rerun
before the implementation commit. Exact final counts appear in the smoke report.

## Smoke outcome (method remains frozen)

The preregistered smoke stopped on task110 as **IMPLEMENTATION_FAILURE**. C1 encoded the
reference-only pillow–sofa association by ordering learner-visible commands; the unchanged
lexical privilege gate missed this relationship-level leak. No C2, search accept or K16
ran. The core method was not repaired after its freeze. The report-label correction is
audit-only and separately logged. See
[the complete smoke report](../../experiments/alfworld_e6/results/e6_iterative_low_smoke.md).
