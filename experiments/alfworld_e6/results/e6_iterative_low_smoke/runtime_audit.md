# Iterative LOW smoke: independent runtime audit

## Decision

**IMPLEMENTATION_FAILURE: semantic privilege leakage in task 110, shared C1.** The run stopped before any D/I C2 comparison or confirmation. This cannot answer whether feedback improves LOW interventions. The automatic driver summary's `INCONCLUSIVE` reflects the transport error produced by the explicit correctness stop; the preregistered correctness gate and `correctness_audit.json` take priority. Preserve both records and explain the override.

## Frozen provenance

- Implementation: `76e14b3b477e73ffe5f10540a5157dc99b6ab559`.
- Preregistration: `7c472fba573ca518152062028a327db5c456df72`.
- Frozen source tree: `c075947920a4ff35d31a9532e06ae355a264a418`.
- Runtime driver SHA256: `383fd906daa4974270efcc90fb390254f506e1918f971e693d2de1e51408a3ba`.
- Selected tasks: 110, 114, 115, 126; 129 remains untouched.
- Frozen rich references: available for 110, 114, 126; task 115 unavailable (`verifier_fail`). All four stay in the primary denominator. No replacement reference or original-policy evidence was collected.

Read-only checks passed for production tree, driver, preregistration, frozen e3/policy/pricing/substrate inputs, selected original failure hashes and all reference hashes. Baseline legacy checker also passed: the original designer, Rules control, guard, measurement, budget, I/O, estimator, brackets and Stage files are byte-identical; only the three approved original dispatch function bodies changed. No source edit occurred during the paid smoke.

## Exact privilege failure

Candidate ID: `110:C1:326d1b19f1d2b29dff831a2c445e2787ff0b40a36ef9d6be757dff5b64d28ded`.
Parent: none. Call index: 1; requested operation: PROPOSE. Source SHA256 is the suffix above.

1. Frozen original failed episodes are `436b877e58`, `5558bfec42`, `4ea28306dc`. Their only executed actions are `go to sidetable 1`, `examine sidetable 1`, `use desklamp 1`, and `look`. Across all 150 recorded observations, there are zero pillow mentions after removing the repeated task-goal paragraph. Sofa 1 appears only as a navigation option; these failures never establish the pillow-on-sofa association.
2. Frozen reference `14c924bb414ffd1e`, step 3, states: "You arrive at sofa 1. On the sofa 1, you see a pillow 1."
3. C1's diagnosis and mechanism summary explicitly use that location. The executable rank function, while the pillow is not held, gives `go to sofa` rank 1 and `examine sofa` rank 2, before generic destinations. This encodes the privileged object-location association through ordering, even though the code omits the numbered full reference action.
4. In evaluated episode `d6a9c60b0b`, step 1, the learner has just gone to sidetable 1 and has not observed the pillow. The modified admissible list begins `go to sofa 1`, `use desklamp 1`, `examine sidetable 1`, `go to coffeetable 1`, `go to diningtable 1`.
5. The actual frozen THINK_ACTION formatter (`third_party/envharness/envharness/agents/policy.py:370`) appends this ordered `obs.data["admissible_commands"]` list to the policy observation. A read-only reconstruction using `PolicyAgent._format_obs` confirms the privileged ranking reaches the learner.

Reconstructed exact policy-observation SHA256: `69567fcf4f37edb7eff255788123812d71a057ce759eb547458cc7426efb39ab`. Full compact machine-readable evidence, including the exact reconstructed policy observation: `/tmp/iterative_low_privilege_evidence.json`.

The frozen structural and lexical privilege validators passed C1. No full reference action string, full privileged-reference block, or Setup replay was found in evaluated code. Those narrow checks did not detect the semantic association leak. This is a privilege-gate failure, not valid evidence of LOW support efficacy.

Authoritative run artifacts (paths relative to research worktree):

- `runs/e6-iterative-low-smoke/task-110/D/proposals.jsonl`
- `runs/e6-iterative-low-smoke/task-110/D/candidates.json`
- `runs/e6-iterative-low-smoke/task-110/original_failures.json`
- `runs/e6-iterative-low-smoke/task-110/privileged_reference.json`
- `runs/e6-iterative-low-smoke/task-110/D/traces.jsonl`
- `runs/e6-iterative-low-smoke/correctness_audit.json`

## Observed gates and stop

The immutable C1 record reports structural/lexical passes, oracle success on attempt 1, and endpoint d=1:4/4 (`too_easy`). Its source was frozen. CONTROL measured d=.5:4/4 (`too_easy`), then began d=.25. Neither complete measurement is admissible evidence of a valid intervention after the semantic privilege finding. No search acceptance or K16 confirmation exists.

The root recorded the correctness failure at **2026-09-15T16:20:09.728989+00:00** and set the existing transport stop flag to `privilege_violation`. No production or designer change occurred. The last physical HTTP dispatch began at **2026-09-15T16:20:09.346508+00:00**, before the stop. Subsequent request attempts were blocked locally; all in-flight reservations settled. No new task or redesign was started.

The next d=.25 measurement produced four errored traces: one episode had already executed 42 actions, three executed zero actions. There is no completed d=.25 measurement/verdict. These errors are consequences of the explicit correctness stop, not evidence about the candidate's effect or provider outage.

## Call, rollout and cost reconciliation

| Quantity | Audited result |
|---|---:|
| Physical designer completions | 1 (shared C1 only) |
| Physical policy completions | 96 |
| Successful returned/ledgered API calls | 97 |
| Physical HTTP attempts | 105 |
| Ambiguous failed HTTP attempts | 8 (rate-limit retries) |
| Completed adaptation episodes | 8 (4 at d=1; 4 at d=.5) |
| Aborted/errored adaptation episodes | 4 at d=.25 |
| Scheduled and charged D adaptation episodes | 12, within cap20 |
| Policy actions in traces | 96 = 54 in completed episodes +42 in aborted episode |
| D or I C2 calls | 0 |
| Physical I calls/episodes | 0 |
| Confirmations | 0 |
| Priced ledger USD | 0.050144814 |
| Settled conservative peak USD | 0.058240374 |
| Retained uncertain reserve USD | 0.026578253 |
| Total conservative physical liability USD | 0.084818627 |
| Remaining in-flight reserve | 0 |

All paid work belongs to task 110. The policy's upstream-reported total is USD0.042049254; the designer's ledger charge is USD0.008095560; these sum to USD0.050144814. The conservative settled total uses peak designer pricing and therefore exceeds actual priced spend. The eight ambiguous rate-limit attempts retain full reservations; their actual charge is unknown, not assumed zero. Both the ledger total and conservative liability remain far below USD12.

The driver charged all12 requested episodes and did not refund stop-induced errors. For logical shared opportunity accounting, C1 and its common CONTROL observations belong equally to D and I:8 completed shared episodes,4 aborted shared episode requests, and1 shared designer call per arm. The independent I branch was never instantiated because D's shared-control execution was interrupted; there is no materialized I budget/candidate record and no completed paired outcome. Distinguish this shared attribution from physically executed I work (zero).

## I input, lineages and confirmation isolation

There was one actual designer request, the original C1 request with `feedback_supplied=false`; its recorded hash matches the exact saved privileged request. No second designer request exists, no typed feedback was sent, and no I request exists. Thus no evaluator feedback reached I, but the paid smoke never exercised the D-versus-I information contrast. The offline independent-request tests remain implementation evidence only.

C1's code hash, candidate identity and no-parent lineage recompute correctly. Every evaluated candidate has no Setup actions. The dose1 and dose.5 concrete code hashes match the frozen template rendered at those doses. No source rewrite, candidate2, parameter rescue, third chance, old-family fallback, K16 feedback, cross-task memory or broader experiment occurred.

## Scope of the conclusion

The smoke discovered that the existing lexical privilege guard can admit a reference-derived object-location association encoded through admissible-command ordering. It does not establish feedback benefit or absence of benefit; no paired C2 comparison was performed. It supports repairing and revalidating the correctness boundary before any later separately authorized experiment. No scale-up or method repair was performed by this audit.

Audit artifacts: `/tmp/iterative_low_runtime_check.py`, `/tmp/iterative_low_runtime_check.json`, `/tmp/iterative_low_privilege_evidence.json`. The runtime check script covers mechanical/hash/budget checks; the semantic privilege finding above is an additional source-and-trajectory audit, not captured by its narrow lexical scanner.
