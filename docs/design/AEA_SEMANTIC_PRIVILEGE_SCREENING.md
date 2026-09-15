# Independent semantic privilege screening

Date: 2026-09-15. Scope: implementation and offline validation only.
Experimental code variant: `llm_v2_iterative_low_semantic_gate`.
Predecessor: `5675632ae4b1838fe9f14b62923d1716b18dd532`.
Offline preregistration: `3073895`,
[protocol](../../experiments/alfworld_e6/PREREG_SEMANTIC_PRIVILEGE_OFFLINE.md).

## Problem and resulting behavior

Task 110's candidate used the privileged pillow/sofa relationship to prioritize sofa
commands. Its source omitted numbered reference strings, so the lexical guard passed.
The policy formatter displayed the modified command order. The completed smoke remains
`IMPLEMENTATION_FAILURE`; this implementation does not revise or resume that experiment.

The new variant preserves full privileged reference access in DESIGN. An independent,
local semantic screen now checks actual candidate hook effects against the original
learner's evidence before solvability or any candidate policy probe. FAIL requests the
existing privilege/REPLACE_MECHANISM operation; UNCERTAIN stops without another proposal.

This is a method implementation change in candidate admission. It is **independent semantic
privilege screening**, not guaranteed semantic isolation. The implementation is an offline,
evidence-grounded relation/route analyzer with conservative handling of unsupported changes.
It is not an LLM-as-judge accuracy experiment, and no remote judge was queried or added.

## Architecture and unchanged optimizer

```text
LLM candidate
  -> existing schema/API/template/identity checks
  -> existing lexical privilege checks
  -> semantic screen of source and executed same-state surface deltas
  -> existing solvability
  -> existing d=1 measurement
  -> existing feedback or family freeze
  -> existing CONTROL and acceptance
```

`ScreenedLowOptimizer` subclasses the original optimizer and overrides its validation
boundary. It reuses the complete existing state machine. Semantic FAIL returns through the
existing privilege rejection branch. UNCERTAIN appends an immutable attempted-candidate
record, unwinds validation, and returns `inconclusive`; it supplies no repair feedback.
Unexpected screening/audit errors also stop without certification or policy measurement.

`src/aea/low_optimizer.py` is byte-identical to the predecessor. Its two-call cap, original
designer messages, REPAIR_CODE/REPLACE_MECHANISM vocabulary, D/I input construction,
16-rollout endpoint/calibration reservation and freeze behavior remain unchanged.
`rules_control.py`, `evaluate.py`, `budget.py`, `witness.py`, designer contracts, and
acceptance helpers remain unchanged. HIGH/MID and all old variants retain their old paths.
The legacy `llm_v2_iterative_low` explicitly remains the historical implementation.

Changes to existing production files are limited to config variant registration, controller
admission wiring and reference-provider dispatch. New modules are:

- `semantic_privilege.py`: evidence/result records, relation/route extraction, surface analysis.
- `privilege_surfaces.py`: original local replay capture and actual hook/formatter execution.
- `semantic_low.py`: admission adapter, bounded probe schedule, audit and exact-dose checks.

## Evidence domains

1. **Designer evidence:** selected original failed trajectories and diagnosis material.
   Historical discoveries are useful for design, but never unioned into learner knowledge.
2. **Privileged reference:** the separately supplied verified successful trajectory.
3. **Learner-authorized evidence:** one task, episode and step; original reset and subsequent
   raw observations through that point, executed original actions, goal, and currently
   displayed original commands. Observation/action counts must agree with the prefix index.

A target state described in a task goal is not evidence of the current object location.
Negated or otherwise unsupported location statements do not establish positive relations.
Numbered entities remain distinct. Available commands such as `take pillow 1 from sofa 1`
can themselves expose a relation; a list containing `go to sofa 1` alone does not.

The capture producer is trusted to supply original evidence. It rejects wrapped sessions;
the misleading `raw_observation` field of a wrapped runtime Trace is never used as a public
baseline. Reference observations are not spliced into production learner prefixes. Candidate
outputs and candidate-written `extras` never enter authorized evidence. Raw evidence strings
cannot authenticate their own provenance; explicit construction and audit are required.

The intended reference transfer is choice of generic assistance. Task-specific hidden
locations, associations and routes cannot be encoded in that assistance. Remembering a
relation the learner already observed can pass; selecting a hidden location from the
reference cannot. Public goal emphasis and generic prerequisites are supported controls.

## Executed surfaces and scope

Production capture replays the selected failures' action prefixes in an original local
session, without a learner or model. Deep copies preserve original observations, states and
responses. Each candidate/dose gets a fresh Rules instance; the instance and its `extras`
persist across its prefix. The actual released Rules reset/step implementation invokes the
hooks, and the actual PolicyAgent observation formatter produces the policy-facing text.
The configured action format is propagated; unsupported formats fail closed.

Probes retain observation text/data, command lists including order, action mapping, block
reasons, transition fields and formatted observation history. Immutable original evidence
is distinct from candidate history. A remapped action cannot reuse the original action's
response. Blocking/remapping or unsupported state mutation records the visible effect and
marks further replay unsupported. Concrete leaks in that captured effect still take FAIL
priority over uncertainty about later execution.

The standard four-bisection CONTROL can visit 17 unique doses including 0 and 1. All are
screened before certification. The adapter verifies exact source bytes and dose admission
again before each measurement. CONTROL itself is unchanged. The bounded capture supports
up to 50 actions per prefix and 33 doses (five bisections); a larger configuration stops as
UNCERTAIN rather than silently weakening coverage or increasing the search budget.

These are fixed-prefix probes, not live on-policy trajectories. Unseen histories, other
real-valued doses, alternate action branches and opaque semantic encodings remain outside
the evidence. Passing this finite suite does not establish universal non-interference.
Generated Python uses the existing loader and is not a security sandbox.

## Verdict and audit

Every result records `PASS / FAIL / UNCERTAIN`, `information`, `reference_evidence`,
`public_evidence_check`, `candidate_evidence`, `activation`, detailed findings, detector
version, candidate source hash and complete input hash. FAIL has a concrete supported leak
witness. Unsupported semantics, missing evidence, malformed prefixes and execution failures
are UNCERTAIN. Identity and supported grounded changes can PASS on the supplied probes.

Source analysis detects embedded ordered reference routes and unresolved reference-specific
constants. Executed delta analysis checks relations and preferences, including action ranking
and filtering. Generic support has a deliberately bounded grammar; unfamiliar but legitimate
support may be rejected as UNCERTAIN. This cost must be measured in later use.

The audit writes exact privileged gate inputs to deterministic gzip JSON, addressed by their
SHA256, and indexes verdicts in `semantic_privilege.jsonl`. Feedback is a compact summary
through the existing designer-only packet; no gate evidence enters policy prompts.
A failed rescreen revokes an earlier admission for the same source. Source edits and
unscreened doses cannot inherit admission.

A future matched D/I driver must use this same gate and probe construction for both arms.
Shared C1 can be screened once physically; both arms receive its admission result, with
candidate-specific rejection feedback available only to D. No new D/I driver behavior or
paid experiment is implemented here. This local detector has zero model cost; a future
remote judge would require separate versioning, validation and cost accounting.

## Offline validation and interpretation

[Benchmark driver](../../scripts/semantic_privilege_benchmark.py) runs actual candidate hooks
and the actual detector on archived task 110 evidence and labeled synthetic extensions.
The fixture records hashes and provenance of the exact archived source/reference/original
failure. Required labels were fixed before the first benchmark run. Additional adversarial
regressions and any corrections are reported separately; labels are not changed to improve
reported accuracy. Scripted verdicts are used only in admission control-flow tests.

Validation covers the requested ten cases, temporal/public-evidence controls, unsupported
semantics and errors, then additional evidence-parser adversarial cases. Admission tests
check zero solvability/policy work after FAIL/UNCERTAIN, existing typed feedback and call cap,
actual PASS through certification/CONTROL, byte/dose binding, audit hash reproduction and
old-path equivalence. Full unit/integration/lint/type/pre-commit results and final source
hashes are recorded in the offline results report.

A passing regression suite supports this bounded screen and its integration. It does not
establish broad detector accuracy, success of iterative feedback, or readiness for a large
experiment. No new D/I smoke, policy/model API call, K16 confirmation, task pool or learner
training is part of this implementation task.
