# Independent privilege screening with witness verification

## Problem and precedent

The concise Prompt-4 validation retained two false-positive rejections: a generic
prerequisite was assigned hidden instance information, and public-goal ordering was
treated as a claim about the correct next action. Both decisions cited real candidate
material. Checking whether a quotation exists therefore does not establish that it
supports the alleged information or that this information is unauthorized.

[RefChecker](https://aclanthology.org/2024.emnlp-main.395.pdf), Section 4, separates
candidate claims from reference checking. [AgentCIBench](https://arxiv.org/html/2606.23189v1),
Appendix E, requires output-side support for judge-claimed disclosures.
[Curse of Knowledge](https://aclanthology.org/2025.findings-emnlp.805.pdf), Section 5.3.1,
documents reference-induced judgment bias. These motivate the following AEA adaptation;
none establishes its correctness or covers all our executable side channels.

## Bounded evidence-verification protocol

Keep the existing public PrivilegeDecision schema, model, settings, and admission
interface. Add an internal, strictly validated witness record and isolated calls:

1. Obtain the full-input privilege judgment.
2. For a semantic rejection, verify its information hypothesis in a fresh call using
   candidate source, exact runtime deltas, public task/contract information and original
   episode evidence. Exclude reference trajectories, designer history/change explanations,
   the original verdict/rationale, labels and previous outcomes.
3. If the witness is unsupported or independently authorized, perform one full-input
   reconsideration with the checked counterevidence. Invalid evidence never directly
   changes FAIL into PASS.
4. Verify any reconsidered rejection once more. Stop after at most four logical calls.

The host checks source/runtime anchors and activation scope. The semantic checker
separately assesses whether those anchors carry the same alleged information and whether
it is authorized. Malformed or unresolved verification blocks admission as UNCERTAIN;
transport, accounting and request-binding failures remain operational errors. Only PASS
admits. A reconsidered PASS is a new complete judgment, not a lexical veto override.

Operational choices count: an encoded preference for a destination can be a shortcut
without literally asserting an object's location. A narrower encoded choice requires
provenance reconsideration. Review complete source for delayed and dose-dependent branches;
do not require all source effects to have executed in sampled captures. A source predicate
must not be misrepresented as an observed runtime activation.

Reference-blind verification remains conditioned on the alleged information hypothesis.
It is not fully blind claim extraction, semantic non-interference, or a formal proof.
Exact citations do not prove entailment; model-based entailment can still be wrong.

## Authorized five-round campaign

The user authorizes evidence-verification repairs, concise prompt revisions and up to
five new validation rounds. Freeze each round before its first paid request; preserve its
records and report failures. Between failed complete rounds, revise only the evidence
verification or its short prompts, recording the concrete error and treatment. Keep the
four-call architecture, model/settings, public decision schema and LOW optimizer frozen.
Do not tune on partial paid results or silently restart an interrupted round.

Every round reuses the same 13 labeled core cases, four identical-input repeats and four
unlabeled saved-candidate inspections, in the same order with identical underlying input
bytes. Require nine leak FAILs, four legitimate PASSes, four repeat agreements, valid
schemas and evidence/request/accounting integrity. Saved inspections are not accuracy
labels. Synthetic unit tests verify implementation contracts separately; they do not
replace or relabel the frozen benchmark. These reused cases are engineering validation,
not a fresh generalization estimate.

Stop the campaign on the first audited success, five unsuccessful rounds, an operational
interruption, or the monetary limit. On success, freeze the judge and engineering prereg,
then run the previously authorized task154/159 saved admission replay and LOW engineering
test. Keep three designer calls per task, thirty adaptation episodes per task, endpoint
4-to-8, freeze/CONTROL boundaries, acceptance and evaluation-only fresh K16 unchanged.
No fresh task screening, D/I, E3 or E3-SL.

## Money, recipients and publication

Four prior validations incurred USD1.44588620 in conservative accounting. Preserve those
closed caps and journals byte-for-byte. The user's cumulative USD20 authorization includes
all old and new calls and retained failed-request reservations. The new campaign uses a
shared remaining envelope rather than the previous implementation's USD3/USD17 partition:
each new validation round is capped at min(USD2.50, remaining total), and conditional
engineering at min(USD17, remaining total after validation). This changes monetary
allocation only; task, episode and designer-call budgets do not increase.

Before every physical attempt, including client retries and all internal verifier calls,
reserve its conservative maximum cost through the existing transport guard. Reconcile and
freeze all predecessor ledgers before opening a new stage. No concurrent campaign stages,
cap resets, uncharged verifier calls or forgiveness of ambiguous reservations.

Use only the authorized DeepSeek endpoint for privileged judge/designer inputs. Only after
Phase A passes may the frozen OpenRouter/Qwen learner receive admitted learner-facing
inputs. Raw references, GT observations/actions, candidate inputs, prompts, surfaces,
verification records and decision prose remain local and gitignored. Public exports use
explicit metadata allowlists; retain hashes, counts, enum outcomes and synthetic tests.
Audit git diff/show and the publication history before each push. Earlier results,
including IMPLEMENTATION_FAILURE, remain unchanged.
