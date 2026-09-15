# Iterative LOW semantic-gate efficacy smoke

## Decision: IMPLEMENTATION_FAILURE

The smoke cannot answer whether candidate-specific feedback improves LOW redesign. A frozen
structural validator rejects documented, real ALFWorld state attributes because its minimal
test state omits them. This falsely classifies task126 D2 as a code failure and supplies the
wrong mechanical feedback category for task129 C1. The production method was not patched.
No candidate reached solvability, policy evaluation, CONTROL, search acceptance or K16.

Seven physical designer requests cost **$0.031449528** in the frozen-price ledger. Conservative
peak-token accounting was **$0.11483736**, with zero ambiguous-request reservation; both are
below the USD12 cap. Policy and confirmation spend were zero.

The automatic pre-audit summary is preserved as `automatic_summary_before_audit.json`.
Its preliminary `NO_FEEDBACK_SIGNAL` label is superseded by the preregistered correctness
priority and the user's explicit stop-on-method-defect instruction. It is not an efficacy
conclusion. This report concerns only the new namespace; the previous task110 smoke and its
permanent IMPLEMENTATION_FAILURE record were not changed.

## 1. Starting state, implementation and preregistration

| Item | Frozen value |
|---|---|
|Starting HEAD|`4d368fea2d6ab06d3656420e6f99c561bb9d50cf`|
|Branch/worktree|`aea-llm-vnext`, `/home/kree/work/EnvJudge-aea-llm`|
|Starting research status|clean|
|Main HEAD|`f97260589475bf4412f2310b1dfbcc1c34816547`|
|Main status|pre-existing ` ? third_party/envharness`, unchanged|
|Production implementation|`7555cc3bf0594cb132250949fa57e18fecf10982`|
|Production source tree|`ee579f05b9ab51cc4686d98e5c5c1ef95fb03ada`|
|New prereg commit|`dcd37c514f30fc9e6f626922ec6f3f7e7791d40e`|
|Variant|`llm_v2_iterative_low_semantic_gate`|
|Semantic screen|`alfworld-semantic-screen-v1`|
|Semantic source SHA256|`ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd`|
|Driver SHA256|`22112d20634d5e4d9b06439a7c1355d60de6aaa1ab9a32286a76d431e4bdfb6d`|

[Preregistration](../PREREG_ITERATIVE_LOW_SEMANTIC_SMOKE.md) was committed and pushed before
the first paid request; startup also checked ancestry of the prereg commit on the remote
tracking branch and exact source/manifest hashes. No checkout/reset/merge/rebase/clean/stash/pull
was used. Only new experiment driver, tests, audit scripts and records were added. Optimizer,
prompts, gate, solvability, evaluator, CONTROL, thresholds and budgets were unchanged.

## 2. Task, evidence and reference freeze

The programmatic audit scanned **2,931 historical adaptation and trace files**, with no parse
errors, and inventoried frozen LOW pools. LOW_POOL_3's 13 confirmed 0/16 tasks minus prior
adaptation use yielded exactly **114,115,126,129**, in that order. Task110 was already consumed
and appeared only in pre-run offline regression, never in this efficacy sample.

Each task reused three complete 50-step failed trajectories: first ten frozen original K16
episodes, then unchanged `seeded_failures(...,3,seed=task)`. No new original rollouts, K16
classification or richer designer evidence was collected. Full evidence, episode and source
hashes are in [the committed input manifests](../frozen/iterative_low_semantic_smoke/prepared.json)
and [pool audit](../frozen/iterative_low_semantic_smoke/pool_audit.json).

|Task|Original|Reference|Rich steps|Reference ID|Protocol|
|---|---|---|---:|---|---|
|114|0/16|available|10|`9f1502115cd92a43`|reuse exact verified provider record|
|115|0/16|unavailable: verifier_fail|0|none|reuse exact failed provider outcome; no retry|
|126|0/16|available|10|`de1683aefd48799c`|reuse exact verified provider record|
|129|0/16|available|30|`056434ac2d25319a`|one existing local expert-provider invocation|

Primary denominator **4**; referenced denominator **3**. Task115 received no designer request
and no substitute. Successful references were never regenerated for audit. Independent
cross-checks verified exact record hashes, action/step alignment and reference IDs.

## 3. Pre-run checks

|Check|Result|
|---|---|
|Full unit suite|298 passed, 11 integration tests deselected|
|LLM-free integration|10 passed, including real task110; 1 existing optional RL-loader dependency skip (ray absent)|
|Frozen semantic benchmark|14/14 matched: 3 PASS,9 FAIL,2 UNCERTAIN|
|Archived task110 C1|FAIL in benchmark and real-state integration|
|New driver tests|8 passed, including five exact D/I prompt-isolation cases|
|Ruff / format|passed; 176 files formatted|
|Strict mypy|passed; 93 source files|
|Pre-commit --all-files|passed; commit hooks also passed|

The newly discovered field-coverage defect was not covered by these passing preflight tests.
It predates this smoke and is present in the frozen implementation. See
[preflight records](../frozen/iterative_low_semantic_smoke/preflight_checks.json).

## 4. Shared C1 and candidate outcomes

C1 was physically generated once per referenced task. Both arms inherited its exact source,
hash and immutable gate record. Full source files and candidate details are in
[task_tables.json](e6_iterative_low_semantic_smoke/task_tables.json); hash prefixes below
identify the corresponding full source hashes there.

|Task|Shared C1 hash|Mechanism|Structural|Lexical privilege|Semantic|Exact recorded C1 type|
|---|---|---|---|---|---|---|
|114|`db95316167cc`|cloth/clean/sink/toilet prerequisite reminder; promote already-admissible cloth/clean commands|pass|pass|UNCERTAIN|SEMANTIC_UNCERTAIN|
|115|—|no reference|not run|not run|not run|no C1|
|126|`1b682d5d2c08`|encode potato-in-microwave hints and command priority|pass|fail|not run|PRIVILEGE_FAIL|
|129|`58529c8cffb9`|reveal butterknife at countertop2 and promote its navigation command|false fail: missing goal_text|not reached|not run|STRUCTURAL_FAIL, invalidated by audit|

All C1 solvability/endpoint/final-environment results are **not reached**. None was viable.
Task114's single physical semantic screen stopped both arms without C2. It executed
**2,601 aligned probes** (three 51-state raw prefixes ×17 doses). The screen could not ground
the added reminder under its bounded grammar; a representative finding was:
`Changed text has unsupported or ungrounded semantics`. This is screening uncertainty,
not a confirmed privilege leak. See [semantic_index.json](e6_iterative_low_semantic_smoke/semantic_index.json).

|Task|C2_D request / hash|C2_D recorded result|C2_I hash|C2_I recorded result|Raw ordinal comparison|
|---|---|---|---|---|---|
|114|none|shared semantic UNCERTAIN|none|shared semantic UNCERTAIN|unranked|
|115|none|reference unavailable|none|reference unavailable|coverage outcome|
|126|REPLACE_MECHANISM / `ee62c351c25c`|generic goal reminder; false STRUCTURAL_FAIL on last_action_was_effective|`fcc0fb5f0c67`|microwave-location salience; PRIVILEGE_FAIL|invalid-tier tie, scientifically unusable|
|129|REPAIR_CODE / `2bd72ab1ed26`|retained hidden countertop2 hint; PRIVILEGE_FAIL|`d1caa3b5014b`|countertop priority/reminder; false STRUCTURAL_FAIL on goal_text|invalid-tier tie, scientifically unusable|

Every C2 stopped before semantic screening, solvability, endpoint and CONTROL. There was no
duplicate and no C3. The observation that some candidates themselves encode hidden location
information does not excuse the validator's incorrect API diagnosis. Conversely, successful
API reproduction does not establish that those candidates deserve semantic admission.

## 5. D2 feedback and I2 isolation

|Task|Exact feedback given to D2|Remaining logical budget|D2 request SHA256|
|---|---|---|---|
|126|privilege / REPLACE_MECHANISM: embedded `go to microwave 1`, privileged `potato 1` constant|1 call,20 rollouts|`fd584059f9185ed56f8d82ab6af41d087b3b6d446be3678e4b66f9dec1b94aca`|
|129|mechanical / REPAIR_CODE: `_State` lacks `goal_text`|1 call,20 rollouts|`4ed92527003f56c03ccaf303583793c81b833940ff87e26885ad98ecd265000f`|

The second row faithfully transmitted the frozen implementation's feedback, which was
itself wrong. It asked the designer to preserve and repair a privileged location mechanism.
Both packets retained exact C1 source/hash/mechanism. Neither contained endpoint or policy
feedback because none existed. Semantic input hashes for these C1s are absent because both
stopped before semantic admission; this is recorded rather than fabricated.

|Task|I2 request SHA256|Independent audit|
|---|---|---|
|126|`6a6746b53f2433aef4e9a18fe2a7c79cd764f5b36abb792b7c361665bea1ecfc`|exact original evidence/reference + neutral prior source; no evaluator fields|
|129|`9c4ebf8f058728b0d299f3137b4a82d8a2d315695a3b5c32dd2eabba5585f8b7`|exact original evidence/reference + neutral prior source; no evaluator fields|

Five pre-run sentinel cases tested semantic verdict/reason, solvability, endpoint s/n,
too_hard/too_easy, validator errors and rollout text. Actual I2 requests were independently
reconstructed and matched exactly with feedback=None; D2 packets matched frozen C1 outcomes.
Privileged exact requests remain under `runs/e6-iterative-low-semantic-smoke/task-*/{D,I}/`
in `privileged_designer_requests.jsonl`, separate from learner artifacts. Public audit records
contain hashes and provenance. No K16 data existed to enter feedback.

## 6. Correctness finding and independent reproduction

`src/aea/families.py:129` defines `_SmokeInner._State` with only a few fields. It lacks
`goal_text` and `last_action_was_effective`, both explicitly advertised by
`src/aea/designer.py:415` and provided by the actual ALFWorld state dataclass in
`third_party/envharness/envharness/bridges/alfworld/bridge.py`.

The frozen validator therefore rejected these actual source hashes on missing fields:

- task126 D2 `ee62c351c25cdb805f849447db5ac28dfad0678ef2e60aa460133a5c9fe220d8`;
- task129 C1 `58529c8cffb9de778977d1984e0ee4a49dd4353512f38b49fe7be88004fc6008`;
- task129 I2 `d1caa3b5014b7c637fd72f44a28cfe198878acfb8fb89fea42af38d2fd4f2466`.

Independent offline reproduction loaded those exact bytes, confirmed the validator errors,
then passed the actual `AlfworldEnvState` dataclass to their observation hooks. All **12**
checks (three candidates ×d0/d1 ×effective true/false) executed without that exception;
every d0 case preserved identity. These are synthetic records of the real state class,
not new simulator episodes or a bypassed admission experiment. No API, policy rollout,
reference generation or production edit was used. The proof establishes state-schema
fidelity failure only; it does not certify the candidates' semantic safety or efficacy.

See [reproduction](e6_iterative_low_semantic_smoke/validator_state_reproduction.json) and its
[exact script](e6_iterative_low_semantic_smoke/validator_state_reproduction.py.txt).
The defect invalidates the paired comparison: the pipeline rejected an allowed API access
and changed which feedback the optimizer received. It must not be scored as ordinary poor
candidate quality or interpreted as absence of feedback benefit.

No semantic leak reached policy: there were no policy calls. The same frozen admission
rules applied to D/I; exact prompt isolation, provenance and accounting checks passed.
Their passing scope does not override this separate admission-correctness failure.

## 7. Gate-stage and delivery counts

Raw frozen ordering produced two C1-failed invalid-tier ties (126,129), zero D wins/losses,
zero D2-over-C1 improvements and zero I2-over-C1 improvements. Task114 was unranked due to
semantic uncertainty; task115 remained in the four-task coverage denominator. These are
descriptive execution records only, not valid paired scientific outcomes after the audit.

- Search accepted: **D0/4, I0/4**.
- K16-confirmed B_L: **D0/4, I0/4**; B_T: **D0/4, I0/4**. No confirmations were eligible.
- Physical semantic decisions: **PASS0, FAIL0, UNCERTAIN1**; shared logically by two arms.
- Earlier terminal checks: **3 lexical privilege rejections,3 structural rejections**.
  All three structural rejections exhibit the state-schema defect above.
- Solvability, endpoint and CONTROL measurements: **0**.

The frozen B_L=[.2,.8] and B_T=[.4,.6] definitions, 4-to-8 evaluator,20-rollout budget and16-rollout reservation,
two-call cap and freeze boundary were retained; this run provides no efficacy observations
of their downstream behavior.

## 8. Logical opportunity, physical cost and stop chronology

|Task|Logical designer D/I|Physical designer|Logical adaptation D/I|Physical shared/adaptation|Actual designer USD|
|---|---|---:|---|---|---:|
|114|1 /1|1|0 /0|0 /0|0.007585468|
|115|0 /0|0|0 /0|0 /0|0|
|126|2 /2|3|0 /0|0 /0|0.011639980|
|129|2 /2|3|0 /0|0 /0|0.012224080|
|Total|5 /5|7|0 /0|0 /0|0.031449528|

Each active arm retained all20 adaptation rollouts; task115 never entered adaptation.
No budget top-up or third call occurred. Shared designer C1s were physically billed once.
Logical opportunity USD totals were D **0.026243536**, I **0.026468596**; their sum is not
physical expenditure.

|Physical accounting category|USD|
|---|---:|
|Designer ledger, frozen prices|0.031449528|
|Policy adaptation|0|
|K16 confirmation|0|
|Conservative failed-request reservation|0|
|Conservative settled peak-token cap account|0.114837360|
|Hard cap|12.000000000|

All seven HTTP attempts returned; no retry/ambiguous failure or in-flight request remained.
The ledger total was independently recomputed at frozen prices. Conservative peak pricing
explains the larger cap account; it is not a second bill or measured provider invoice.

UTC timeline on 2026-09-15:

- First request: **18:20:28.139641**, after prereg push and startup verification.
- Next request: **18:29:01.473794**. The513-second interval includes initial generation and
  the full task114 local screen; exact screen wall time was not separately instrumented.
  Source inspection indicates repeated-history text comparison is a likely cost center.
- Last request started: **18:29:44.225199**; last response: **18:29:54.052497**.
- Correctness stop persisted: **18:30:23.294941**, once the validator discrepancy was
  confirmed. The quick remaining designer requests had already completed. No requests
  occurred after the stop, and no paid run was resumed.

The existing report-only audit override produced the final IMPLEMENTATION_FAILURE label;
no driver or method patch was made. The audit/reproduction afterward was entirely offline.

## 9. Audit artifacts and interpretation

The new results directory contains exact generated source bytes, candidate tables, compact
semantic findings/input hashes, priced calls, cap attempts, freeze metadata, correctness
reproduction and independent provenance audit. The full32MB execution result and exact
privileged prompt/surface inputs remain in the isolated local run namespace. No old run or
offline semantic benchmark result was overwritten.

The independent provenance/accounting audit passed **10,580 checks**, including exact
shared C1, D2/I2 requests, source/lineage hashes, original/reference identity, all2,601
same-state probes, logical accounting, no K16 feedback and no post-stop HTTP attempts.
Its conclusion is explicitly scoped to provenance/accounting while the experiment's
overall correctness decision remains IMPLEMENTATION_FAILURE.

This smoke establishes an actionable validator/contract mismatch and shows that the tested
prompt isolation and accounting paths retained their intended boundaries. It does **not**
establish feedback efficacy or inefficacy, K16 delivery, LOW capability, semantic-gate recall
on newly admitted families, generalization, learner improvement or outer AEA efficacy.

Final decision: **IMPLEMENTATION_FAILURE**. Work stopped for review. No production repair,
C3, budget increase, replacement tasks, additional smoke, R arm, HIGH iteration, outer loop,
full E6 or E6-SL was performed.
