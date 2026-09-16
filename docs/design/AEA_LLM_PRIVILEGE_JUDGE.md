# Independent LLM privilege judge for iterative LOW

Status: implementation design, written before implementation. Starting research commit
`2295d1524798af9bdd17d1955082109a8b56a1bc`, branch `aea-llm-vnext`.
New variant: `llm_v2_iterative_low_llm_judge`. Earlier experiment decisions are immutable.
This task implements the gate and then, only after validation and freeze, performs engineering
acceptance on reused tasks 154 and 159. It collects no new screening tasks or scientific efficacy data.

## Precedent and scope

[HarnessEvolve](https://arxiv.org/pdf/2609.00829) §3.2 (p5) supplies evaluator-verified
references; §3.4 (pp5–6) uses these alongside failures to propose harness updates. §3.5 (p6)
and Algorithm 2 (p15, lines8–21) place an independent quality judge before performance
evaluation and return rejection reasons for bounded revision. Its experimental rule rejects
leakage scores above 0.8 (§4.1, p8); its three revisions follow an initial proposal.
AEA borrows structural judge separation and rejection-driven revision, not that numeric
threshold, four-proposal count, or a claim of identical information channels.

AEA environment changes can disclose private instance relations through ranking, filtering,
observation text, final policy prompts, blocked-action feedback, transitions, and delayed or
dose-dependent behavior. Task110 encoded a reference-only object/receptacle relation in command
ranking before discovery. Its archived IMPLEMENTATION_FAILURE and V3 INCONCLUSIVE remain
unchanged. Generic reminders accompanying that ranking do not excuse the hidden relation.

**This is semantic privilege screening by an independent LLM judge, not a proof of
non-interference.** Bounded replay does not prove safety on all unseen histories or real doses.

## Information domains

DESIGN may inspect historical failed trajectories, diagnostics, and the verified rich
reference. Those records do not grant a fresh learner knowledge. Learner authorization is
scoped to task, episode, and activation step: public instruction, observations already seen,
actions already taken, currently visible action/tool schemas, and explicitly allowed memory.
Only trusted original-environment observations establish this domain; transformed wrapper
content cannot authorize itself. Historical episodes are independently scoped replay contexts,
never pooled as fresh-episode knowledge. Reference-only locations, entity relations, routes,
successful future action sequences, and intermediate states remain privileged.

## Generic input, output, and independence

A compact benchmark-neutral `PrivilegeJudge` / `LLMPrivilegeJudge` module receives:
`task_spec`, `public_task_information`, `designer_evidence_summary`,
`learner_authorized_evidence`, `privileged_reference`, `candidate_artifact`,
`candidate_artifact_type`, `candidate_change_summary`,
`optional_runtime_surface_deltas`, and `benchmark_contract_summary`.
Core schema and prompt contain no ALFWorld vocabulary or ALFWorld-specific field names.
Source-only inputs are permitted for benchmarks without runtime adapters. Supplied runtime
effects and source must both be considered. Inputs are data, never instructions to the judge.

The fresh request contains one separate judge system prompt and one serialized input message.
It carries no designer conversation, optimizer role-playing, previous judge responses, or K16
results. The judge uses a distinct client invocation and request/response audit stream. Independent
module does not necessarily mean different model weights. Initial frozen configuration:
direct DeepSeek, `deepseek-v4-flash`, `https://api.deepseek.com`, temperature 0, seed 0,
thinking false, maximum 2048 output tokens, existing repository retry/ledger implementation.
The existing client records seed 0 for attribution but does not transmit a DeepSeek sampling
seed; repeated calls use identical wire settings and remain a stability check.
No fallback provider or model. Model ID is pinned as supported by this API; immutable remote
weights are not independently attested. The live [provider pricing page](https://api-docs.deepseek.com/quick_start/pricing/)
read 2026-09-16 says this legacy request alias is served by DeepSeek-V4.1-Flash.
Record full settings and prompt/schema/config hashes.

The existing endpoint uses a fixed named tool with required fields and `additionalProperties:false`.
[DeepSeek server strict mode](https://api-docs.deepseek.com/guides/tool_calls/) requires `/beta`;
we omit that wire flag and enforce the strict output schema locally before any admission.
Only successfully completed tool-call responses are eligible; text fallback is disallowed.
Exactly one required structured function call returns all fields: verdict
PASS/FAIL/UNCERTAIN; finite leakage_score in [0,1]; concise information, reference_evidence,
public_evidence_check, candidate_evidence, activation, and revision_reason; leak_type from
NONE, DIRECT_ANSWER, REFERENCE_ACTION, HIDDEN_ENTITY, HIDDEN_RELATION, HIDDEN_ROUTE,
SOLUTION_ORDERING, TRANSITION_DISCLOSURE, OTHER. Request evidence and decision only, no
chain of thought. Verdict is authoritative; score is diagnostic. Missing/malformed output
becomes audited UNCERTAIN. Transport, accounting, provenance mismatch, and integrity failures
remain explicit infrastructure/correctness errors, never disguised as semantic decisions.

The question is whether the artifact communicates, prioritizes, reveals, encodes, or exploits
reference-only task-instance information unavailable in authorized evidence at activation.
Generic prerequisites, public goal decomposition, tool instructions, generic domain knowledge,
and reminders of current-episode observed relations are legitimate. Ordering is legitimate when
grounded in those domains; reference-only ordering is leakage. Source-encoded associations
applied to public inputs, filtering, transition disclosure, delayed activation and dose changes
are explicit leak channels. Mere source coincidence with identity behavior is insufficient.

## Admission and feedback

New production path: schema/API checks -> zero-dose identity -> cheap hard privilege checks
-> independent LLM judge -> solvability -> endpoint policy -> freeze/CONTROL.
Old `alfworld-semantic-screen-v1` remains byte-preserved for regression/debugging and task110
reproduction, and is never invoked for admission by the new variant. Existing variants remain
available and retain their historical meaning. Verified references remain DESIGN inputs.

PASS binds the exact candidate source, full input, and covered doses before downstream work.
FAIL and UNCERTAIN both reject the candidate and return the existing REPLACE_MECHANISM
feedback while calls remain. The new adapter subclasses the existing optimizer directly;
the old local gate's task-terminal UNCERTAIN behavior is not inherited. Feedback identifies
code region, leak class, and the violated boundary without unnecessarily repeating hidden facts.
Only admission changes. No designer prompt, CONTROL, solvability, acceptance or HIGH changes.

Cheap checks continue rejecting direct reference copying, replay, and reward/verifier/termination
tampering. A minimal AST provenance exception permits unchanged response-field copies from the
actual transition hook response parameter into a response, including `reward=raw_response.reward`.
It does not authorize expressions that modify reward, alias/reassignment tricks, or mutation of
reward/success/termination. Targeted regressions cover the original false positive and mutations.

## Runtime adapter and coverage

An ALFWorld adapter reuses original snapshot capture and actual Rules hook/policy-formatter
replay. It does not call the local semantic grammar. It supplies generic before/after observations,
ordered actions/tools, transition feedback, and activation contexts. Every raw episode prefix
and every reachable bounded CONTROL dose (including zero) is retained. Original observations
and actions are de-duplicated with explicit prefix references; equal surface deltas may be
grouped only with all activation/evidence references retained. Exact prefix/suffix string spans
or complete before/after values preserve effects without quadratic repeated history diffs.
Raw probes remain separately hash-addressed audit artifacts. The frozen maximum serialized
input is 1,100,000 UTF-8 bytes. Exact shared activation/coverage tables and reversible string
edits keep the largest archived inspection below this bound; no evidence is sampled. This
input bound was set before paid validation and does not raise either physical dollar cap. No semantic labels select examples,
no new LLM summarizer rewrites evidence, no silent truncation. Missing capture or payload overflow
produces explicit safe UNCERTAIN. Full source/reference and coverage/omission metadata are visible.

## Offline checks, fixed validation, and freeze

Before any paid call: full unit suite; relevant LLM-free integration suite; validator contract
tests; task110 regression; unchanged old semantic benchmark as regression only; ruff, formatting,
mypy, and pre-commit. Tests cover schema, PASS, FAIL/UNCERTAIN bounded redesign, K16 exclusion,
request isolation, source/effect inclusion, evidence domains, lexical provenance, and absence of
old grammar calls on the new path.

Freeze labeled inputs and settings before the small paid validation: existing labeled leak and
legitimate fixtures plus public-goal decomposition. Required channels include task110 ranking,
observed-relation control, generic prerequisite, hidden ranking/filtering/encoded route,
transition disclosure, and delayed/dose disclosure. Repeat task110, observed relation, generic
prerequisite, and hidden route twice with identical inputs/settings. The four saved candidates
154C1 and 159C1/C2/C3 are a separate unlabeled inspection set; record judge and human review
separately, without retrospective labels. Labels, case names and historical gate verdicts are
excluded from judge input. All known leaks must FAIL, all core legitimate controls must PASS,
and repeats must agree. Any failed requirement means JUDGE_GATE_NOT_READY: stop, no LOW policy
and no iterative prompt tuning against 154/159. On PASS, commit/push prompt, schema, settings,
integration, lexical fix, tests and validation evidence; record implementation freeze SHA.
No prompt, threshold or label changes after freeze.

## Physical accounting and engineering acceptance

Validation has a separate hard physical USD3 cap and no policy. Engineering has a hard USD17 cap
covering judge, designer, adaptation policy, K16 and failed-request reservations. Before each
physical request, reserve full serialized wire bytes plus framing allowance at conservative
peak input prices and maximum output tokens. Failed/ambiguous requests retain their entire
reservation. Guard attribution is bound around each request; no shared V3 cap constants, no
silent increases, no unmetered validation client. Physical reservations retain conservative Flash input/output rates 0.44/1.32 USD per million
tokens. A separate `configs/privilege_judge_pricing.yaml` records the verified current Flash
peak cache-hit/cache-miss/output rates 0.006/0.3/1.2 and off-peak half rates for returned
usage; prior `configs/pricing.yaml` remains unchanged. Pro and policy rates remain unchanged. Record returned ledger costs
and conservative committed physical bounds separately. Admission never consumes policy-rollout
counts; costs still count against its phase's physical cap.

After freeze, first replay all four saved candidates through the full new stack, no policy or
new DESIGN. Then new actual DESIGN uses only exact V3 frozen failures/references for 154/159,
three designer calls maximum and 30 fresh adaptation rollouts per task. No baseline or reference
regeneration. Endpoint 4->8 behavior is unchanged: too_hard permits redesign, in_band freezes and
accepts, too_easy freezes and enters unchanged assist_bracket. First viable family freezes;
no CONTROL-to-DESIGN return. Search acceptance remains 3–5/8. Accepted environments receive fresh
evaluation-only K16, with historical B_L=4–12/16 and B_T=7–9/16. K16 cannot enter any judge/design
input. No new task collection, D/I, comparators, HIGH iteration, full AEA, E3 or E3-SL.

Correctness failure takes precedence and stops immediately without patch-and-continue. Otherwise
report all user criteria explicitly: safe endpoint/normal redesign exhaustion, search acceptance,
and K16 B_L. LOW_IMPLEMENTATION_WORKS requires the stated endpoint/exhaustion and search-accept
conditions; if completed K16 produces no B_L, the more specific
LOW_PIPELINE_FUNCTIONAL_BUT_NO_USEFUL_ENV applies. JUDGE_GATE_BLOCKING requires evidence of
repeated unusable admission precision on both tasks. A cap/infrastructure stop without enough
evidence is reported as incomplete with its direct blocker, never manufactured as an efficacy or
correctness conclusion. On K16 B_L, state end-to-end functional viability and recommend stopping
gate/infrastructure work and proceeding to full AEA integration only after review. End this task
with the required safety, provenance, validation, lineage, outcomes, costs, conclusion and blocker.

## Public artifacts and private runtime records

The public repository contains implementation, judge prompt/schema/settings, synthetic unit
fixtures, labels, and hash/provenance metadata. Real reference trajectories, GT-derived
observations/actions, archived candidate source and arguments, raw designer/judge inputs,
runtime surface captures, and free-text judge evidence remain in gitignored local storage.
The current private store is `runs/e6-iterative-low-llm-judge/private/`; earlier local archives
remain under the already ignored `runs/` tree. The obsolete `frozen/.../judge_inputs/` layout
is also ignored to prevent accidental reintroduction.

Public task154/159 records contain only identifiers, counts, hashes, categorical verdicts,
and non-sensitive audit metadata. Future public validation results use an explicit allowlist;
evidence text and rejection reasons remain local, bound by a SHA256 digest of the complete
record. The loader checks private payload bytes against public hashes before admission.
Missing private data fails closed; a public checkout cannot reconstruct it from metadata.

Publication sanitization moves exact previously prepared input bytes without changing the
judge prompt, schema, model, labels, LOW algorithm, or reference access during DESIGN.
The public reward-passthrough regression uses a hand-written synthetic feedback hook;
the historical candidate is checked locally and retained by source hash only. Existing
published historical records are preserved. The superseded unpushed commit is amended,
so its raw input blobs are absent from the outgoing commit ancestry.

This publication-only checkpoint authorizes no paid validation. Phase A requires a separate
continuation after the sanitized implementation SHA and material audit have been reported.

## Pre-call budget authorization amendment

After publication sanitization and before any API call, the user explicitly authorized the
specified external API processing and raised the experiment ceiling to USD20. This is a
combined ceiling: retain Phase A at USD3 and allocate USD17 to Phase B. Separate immutable
stage caps therefore bound all experiment API usage and failed-request reservations to
USD20 in total. The prior USD8 engineering allocation remains part of the earlier published
record; no existing cap or ledger was reset or increased after execution began.

The authorized destinations are DeepSeek (`https://api.deepseek.com`) for reference-aware
Flash judge and Pro designer calls, and OpenRouter (`https://openrouter.ai/api/v1`) with
Alibaba pinned for Qwen learner calls. Raw privileged materials remain gitignored and are
not published to GitHub. Judge inputs, labels, settings, admission rules, three DESIGN calls,
30 adaptation rollouts per task, CONTROL, acceptance, and K16 remain unchanged. Phase B still
requires Phase A acceptance and a pushed validation freeze/preregistration first.
