# LLM privilege judge: publication sanitization checkpoint

This checkpoint sanitizes the unpushed local implementation `ff8c633` before publication
on `MinilordKREE/EnvJudge`, branch `aea-llm-vnext`. The user explicitly authorized amending
that local commit and pushing the sanitized replacement. This checkpoint runs no paid
judge validation, designer adaptation, policy evaluation, or fresh task collection.

## Public and private artifacts

| Material | Storage |
| --- | --- |
| Implementation, judge prompt/schema/settings, design, synthetic unit fixtures | Public Git |
| Task/reference IDs, lengths, SHA256 digests, labels, categorical verdicts and numeric audits | Public Git |
| Full references, GT observations/actions, raw judge inputs and runtime surfaces | Gitignored local private store |
| Archived candidate source/arguments and raw designer evidence | Gitignored local private store |
| Full judge decisions, witness text, rejection reasons and raw error details | Gitignored local private store |

The private store is `runs/e6-iterative-low-llm-judge/private/`. Earlier local historical
archives stay under the already ignored `runs/` tree. The obsolete public `judge_inputs/`
path is explicitly ignored too. Public task154/159 candidate records contain source and
argument hashes and byte lengths, without candidate source, rationale or mechanism text.

The migration preserved all 17 unique frozen judge inputs byte for byte. The fixed
21-call manifest (13 labeled cases, four repeats, four unlabeled saved inspections) retains
its original labels, input hashes and settings. Full references remain available locally
to DESIGN and the independent judge. Public hashes do not reconstruct those inputs.
The real task159 C2 test source was replaced by a hand-written synthetic feedback hook;
the historical source is separately tested locally and represented publicly by its hash.

## Validation and audit evidence

`frozen/iterative_low_llm_judge/publication_preflight.json` records the final offline
checks, unchanged method bindings, local source regression, preservation checks and costs.
The independent input audit verifies 914,755 assertions, including all 2,601 probes per
saved candidate, without model calls. Export helpers validate metadata field values and
reject unexpected free text or nested data with a generic error before public serialization.

`frozen/iterative_low_llm_judge/publication_audit.py.txt` is the publication scanner.
It checks the new Git tree, index, worktree and every outgoing commit/tree/blob object
against full reference structures, action sequences, raw/escaped inputs, normalized
candidate source and credential markers. Its synthetic selfchecks and the unsanitized
commit provide negative and positive controls. The final invocation is run after the
amend and before push; its result binds the exact amended SHA and is preserved locally.

The repository/history search covers all known fingerprints against the existing origin
history. Already public historical task110 fixtures and earlier reports are classified
separately and preserved. A fingerprint in any newly published artifact fails the audit
even if the same text was already public. The scanner is a targeted publication check;
it does not claim to detect arbitrary paraphrases or encodings.

## Commit and execution boundary

The sanitized commit keeps `2295d1524798af9bdd17d1955082109a8b56a1bc` as its parent.
The superseded raw-input commit is retained only locally and is absent from the outgoing
branch ancestry. No force push or published-history rewrite is required.

Judge core, prompt/schema, admission decisions, LOW algorithm, solvability, endpoint,
CONTROL and budgets remain unchanged. Storage paths and public exports are the only
runtime-driver changes. Main and prior experiment records retain their starting state.
Paid validation remains unstarted at this checkpoint; the amended SHA and publication
audit must be reported before any later validation continuation.
