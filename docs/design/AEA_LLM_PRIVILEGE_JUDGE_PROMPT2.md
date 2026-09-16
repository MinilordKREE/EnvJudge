# Independent privilege judge: prompt revision 2

## Problem and change

The validation at commit `244f0f1446d3b6a4911a9514ea8bc4976f99c0da` rejected all nine
known-leak core cases but also rejected three of four legitimate controls. Its completed
result is `JUDGE_GATE_NOT_READY`, published at `3f78d28a785739f1a218b1535a2408d3ad4e069b`.
Those results and their raw private records remain unchanged.

This revision changes only the judge's system prompt as the experimental treatment.
The old prompt already described generic support and current-episode authorization;
the revision strengthens the decision order and the evidence required to reject.
It tests whether those instructions improve the observed boundary errors. The previous
results do not establish that prompt wording is the sole cause or that a stronger model
would be unnecessary.

## Positive unauthorized-transfer witness

The judge first identifies an actual candidate effect, then checks the exact information
and selection criterion used by that effect against authorization at activation time.
Only then does it consult privileged evidence to establish a complete transfer witness.

FAIL requires all of the following for the same information and effect:

1. A concrete candidate-induced learner-facing effect.
2. A task-instance-specific fact, relation, route, or solution choice used by that effect.
3. No independent learner authorization for that information at activation.
4. Support for that information in privileged-only evidence.
5. Actual candidate use or communication, beyond resemblance or usefulness.

Public evidence dominates reference overlap. Observations acquired in the learner's current
episode authorize reminders after acquisition, within the memory contract. Reference overlap
does not invalidate public-goal structure, generic prerequisites, or generic tool semantics.
A desired goal does not establish that a hidden relation already holds.

Visible options do not authorize a hidden ranking criterion: the criterion itself must be
supported by public goal structure, generic semantics, or authorized evidence. The prompt
retains source inspection, exact runtime decoding, separate-effect analysis, early/late
activation distinctions, ranking/filtering, blocked-action/transition feedback, encoded routes,
and delayed/dose-dependent channels. A later observation cannot excuse an earlier leak.

Model-generated UNCERTAIN requires a concrete potentially transferred fact and a named missing
authorization link. Existing host handling for malformed responses, incomplete capture,
overlarge payloads, provider mismatch, and accounting errors is unchanged. FAIL and UNCERTAIN
remain non-admitting. Scores remain diagnostic; there is no threshold or voting change.

## Frozen comparison

- Requested judge: `deepseek-v4-flash`, DeepSeek, temperature 0, thinking false.
- Input schema, output/tool schema, client settings, and response validation unchanged.
- Exact same 13 labeled core cases, four identical-input repeats, four unlabeled saved
  inspections, case order, labels, candidate sources, user payload bytes, and runtime deltas.
- Same LOW implementation, designer prompt/evidence/reference access, three-call cap,
  adaptation budget, feedback routing, solvability, endpoint, freeze, CONTROL, acceptance,
  and evaluation-only K16.
- No additional examples or benchmark-specific noun whitelist in the judge prompt.
- Judge-record schema version remains unchanged; the new prompt hash and implementation
  commit identify this revision.

The fixed cases are reused engineering regressions. Improvements on them are a paired
prompt comparison, not fresh efficacy or evidence of general semantic isolation.

HarnessEvolve describes a narrower check for embedding failed queries and ground-truth answers
in harness edits, with a scored rejection rule and bounded revisions. This revision adopts
an explicit-witness approach while retaining AEA's wider learner-facing transfer boundary;
it does not import that paper's numerical threshold. [HarnessEvolve, Section 3.5](https://arxiv.org/html/2609.00829#S3.SS5).

## Separate records and cumulative budget

A separate operational launcher binds a new run directory and new preregistration/manifests
around the unchanged execution driver. It does not regenerate the benchmark, references,
failures, or runtime captures. Exact prepared private inputs are copied with hash checks;
public metadata contains only counts, IDs, categorical labels/verdicts, and hashes.

The prior run consumed USD0.35856656 in conservative physical accounting. This amount remains
part of the authorized USD20 combined ceiling. The new validation ceiling is the unused
portion of the existing USD3 validation allocation: USD2.64143344. Engineering retains its
USD17 allocation. Prior paid records and their cap are immutable; no previous cost is reset.
Every new physical attempt still uses the original reserve-before-dispatch guard.

All prior reports, frozen manifests, and private execution records remain unchanged. The new
launcher and its operational bindings are independently hash-bound and audited. They are
recording/budget controls, not a second change to the judge decision procedure or LOW method.

## Validation, freeze, and stop

Before paid calls, commit and publish the prompt, separate preregistration, exact source/input
bindings, offline checks, and a privileged-material publication audit. Re-run the original
21-call schedule once. Require all nine leak cases FAIL, all four legitimate controls PASS,
all four repeats agree, all 21 output schemas valid with no generated parsing uncertainty,
and exact request isolation/provenance and accounting integrity.

Inspect the old three false positives and task110 individually as well as the complete table.
No labels or prompt wording change after the first new paid result. If acceptance fails,
record `JUDGE_GATE_NOT_READY` and stop; do not patch and continue. A budget/infrastructure stop
is reported as incomplete under the original rules.

Only after passing validation is frozen and published may the original saved-candidate replay
and fresh task154/159 engineering sequence run. No fresh screening, D/I, model substitution,
HIGH iteration, full AEA, E3, or E3-SL. Privileged payloads are authorized only for the previously
specified API processing and remain excluded from the public repository.
