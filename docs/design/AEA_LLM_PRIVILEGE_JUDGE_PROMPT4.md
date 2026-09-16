# Independent privilege judge: concise prompt revision 4

## Precedent and change

[HarnessEvolve Section 3.5](https://arxiv.org/html/2609.00829#S3.SS5) describes an isolated
quality judge for edits embedding failed queries and ground-truth answers, with performance
evaluation following separately. It also checks injected-example count. We borrow the
focused shortcut question and separation from usefulness. The paper's numeric threshold
and example-count rule are not adopted; AEA retains its broader boundary for indirect transfer.

The paper and abstract did not link a verified author implementation or verbatim gate prompt
in the bounded search on 2026-09-16. This is an AEA adaptation of the stated criterion, not
a reproduction of an author prompt or a claim that the author's prompt was short.

Prompt-3 matched 11/13 core labels after Prompt-2's 12/13. The generic prerequisite error
persisted and public-goal emphasis regressed. The new user instruction authorizes a concise
rewrite and another fixed validation; all earlier decisions and records remain unchanged.

The only experimental treatment is replacing JUDGE_PROMPT with a short principle-based
screen: detect private solution information actually carried by the candidate; authorize
generic/public/current-episode assistance; keep usefulness and optimal-next-action judgments
outside this gate. Nonliteral behavioral encoding and activation-time evidence still matter.
There are no task-specific examples, noun lists, numeric thresholds, or accumulated per-case
patches. Detailed protocol/schema/runtime mechanics remain in their existing code and input
metadata. The exact old/new prompt sizes and hashes are bound in the preregistration.

## Frozen inputs and one validation

Keep DeepSeek deepseek-v4-flash, temperature0, thinking false, client/output settings,
schemas, 13 core cases, four identical-input repeats, four unlabeled saved inspections,
case order, labels, candidate inputs, source/deltas, and every LOW decision function fixed.
An operational launcher only binds the new record namespace and three-run budget carryover.
Exactly 23 private prepared files are copied byte-for-byte from the original frozen inputs.

Require 9/9 leaks FAIL, 4/4 legitimate controls PASS, four repeat agreements, all21 valid
schemas without generated uncertainty, plus request/accounting integrity. Run this schedule
once; no result-dependent prompt or label changes. Failure means JUDGE_GATE_NOT_READY and
no Phase B. A budget/infrastructure interruption retains the original reporting rules.

On full PASS, publish the passing freeze and engineering preregistration, then follow the
already authorized saved admission replay and task154/159 engineering sequence unchanged.
Three DESIGN calls/task,30 adaptation episodes/task,endpoint4->8,freeze,CONTROL,search3-5/8,
and fresh evaluation-onlyK16 remain as specified in AEA_LLM_PRIVILEGE_JUDGE.md. No screening,
D/I,E3,E3-SL,model/schema/pipeline changes or additional benchmark collection.

## Cost, recipients, and privacy

The first three validations consumed USD1.09190796 in conservative accounting. This run
can use only USD1.90809204 from the original USD3 validation envelope; engineering remains
USD17 and the cumulative hard cap remains USD20. Existing physical reserve-before-dispatch
guards remain in force. Read prior caps/journals/results without rewriting or resetting them.

Existing explicit authorization permits the frozen privileged judge/designer inputs to
https://api.deepseek.com. Only if Phase A passes may admitted learner-facing inputs go to
https://openrouter.ai/api/v1 with the frozen Alibaba/Qwen learner; this grants no learner
access to privileged references or designer-only evidence. Raw references,GT observations/
actions,code/arguments,prompts,surfaces and decision prose stay local and gitignored. Public
artifacts contain implementation,synthetic fixtures and non-sensitive metadata. Audit
diff/show and publication/history objects before pushing. These reused cases measure
engineering behavior, not fresh efficacy or guaranteed semantic isolation.
