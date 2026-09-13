## Narrative (hand-written after the run; every number above comes from the tables script)

### Decision

**NO-GO**, by the pre-registered correctness gates. Ten of the eleven gates passed; gate 8
(reference leakage audit) is `false` because, for task 9, the expert reference recomputed by the
audit did not match the hash the run kept. Read-only diagnosis after the run (`refdiag`, scratch
directory, in-process, no API call): the ALFWorld handcoded expert is not deterministic across
sessions within one process. On task 9 it returned `take alarmclock 2 from shelf 2` on a fresh
process (hash `f258ef11ef94abe8`, matching the run) and `take alarmclock 1 from shelf 2` on later
sessions in the same process (hash `ac093f26f8a95933`); both are valid solutions of the same
goal. The audit ran after the search in the same process and hit the second variant. No leak was
found in any file for any task (`leaks: []` everywhere; the reference block is absent from
`events.jsonl`, `designer_calls.jsonl`, `traces.jsonl`, `corpus.jsonl`; the kept designer records
are redacted). For task 9's selected cut k = 4 the post-cut action is `use desklamp 1` under both
expert variants, and the 94 occurrences counted are the policy's own emissions in its 7-of-8 and
4-of-4 probe successes (provenance: `raw_action` of policy steps, never a candidate prefix). The
gate is therefore a failure of the audit tool's determinism assumption, not observed leakage; but
the gate was pre-registered as written and the decision follows it. The pre-registration forbids
repairing and continuing, so this is reported as an implementation issue (below) and the smoke is
not re-run in this phase.

Functionality criteria, for the record: HIGH PASS (3 of 3 tasks with 2 valid families each; 1
task with measurable leverage), LOW PASS (3 of 3 tasks with 2 valid grounded proposals each; 1
task with policy unlocks). Had gate 8 passed, the decision would have been GO. No environment was
accepted on any of the six tasks, so no K16 confirmation ran (`e6-smoke-confirm`: 0 envs).

### HIGH mechanism

Did trajectory-conditioned LLM generation produce executable, nontrivial and empirically
effective actuators? Executable: yes on every task (6 of 6 proposals loaded through the released
loader and passed the LLM-free smoke, 0 rejected). Nontrivial: yes in intent (each summary names a
concrete cue the policy relies on: egg index, sink affordance, statue name in room text,
container labels, alarmclock identity, shelf shortcut). Empirically effective: one of six. On task
12 `distractor_alarmclocks` took the policy from 10 of 10 to 0 of 4 at d = 1, so the empirical
controller entered the bracket; the response was a step function (0 of 4 or 4 of 4 at every
probe, flipping between 0.3125 and 0.375), the bracket exhausted its four bisections at
[0.3125, 0.375] and the cap ended the task at 30 rollouts. The other five families were 4 of 4
at d = 1 (`no_leverage`).

Why the five had no effect, from the generated code (not scored by any LLM):

- `sink_dislocate` (task 1, declared A) filters on `action.name == "clean"`, but ALFWorld
  actions arrive as `Action(name="do", kwargs={"text": ...})`; the hook never fires. The HIGH
  contract text does not describe the action representation.
- `egg_identity_swap` (task 1, O) rewrites text only when `egg 1` and `egg 2` co-occur in one
  observation, which is rare.
- `obscure_statue_location` and `scramble_room_labels` (task 7, O) rewrite `obs.text` only; the
  released policy also receives the admissible-command list from `obs.data`, which the library's
  `FooterMask` removes and these do not.
- `relocate_target_alarmclocks` (task 12, declared A) only deletes the two target alarmclocks
  from the shelf description; it was never leverage-tested because the first family had already
  consumed the task's budget.

Two of the six axis labels (`sink_dislocate` A, `relocate_target_alarmclocks` A) describe code
that touches observations only; the label is unreliable, which is why the phase-2.1 rule that the
declared axis never certifies solvability mattered: every guard ran by policy replay
(`policy_replay`, 6 of 6), none by construction.

### LOW mechanism

Did failure plus privileged reference produce grounded restart interventions that changed learner
behaviour? Grounded: yes, 6 of 6 proposals pointed at real supplied steps (0 rejected), 6 of 6
compiled and were certified by the expert from the restarted state. Changed behaviour: on task 9
both cuts unlocked the policy (failure cut after step 6: 7 of 8; reference cut after step 4 of 5:
4 of 4), overshooting the target band (`too_easy`), so nothing was accepted. On tasks 8 and 10
all four failure cuts stayed at 0 of 4 (`dead`). The reference was available on all three tasks
(7, 5 and 39 expert actions), was present in the designer evidence on all three (the reference
block is placed before the failures; task 10's evidence hit the 24 000-character bound and lost
failure steps, not the reference), and was used as a cut source once (task 9). On tasks 8 and 10
the designer described the failures accurately (soapbar never acquired; cup taken but never
heated) and chose failure cuts; the states it chose did not help the policy.

### Automation

Did llm_v1 operate without fixed fallback or manual task logic? Yes. Every `families` event has
`source = designer` and no library name; no `candidate_states` fallback ran; exactly one designer
call per task (6 ledger rows, 6 records); at most two proposals per call; no rollout-feedback
rewrite; the regime was estimated prospectively on every task (all six matched the frozen K16
regime); the six tasks are the pre-registered ones in order; `src/aea` unchanged from `47a0091`.

### Complexity

Did the experiment require any new paper-level primitive? No: Measure -> Design -> Control. The
driver added only experiment infrastructure (frozen selection, wiring assertion, gates, audit,
tables).

### Implementation issues discovered (recorded, not fixed)

1. Leakage audit assumes a deterministic expert. `ExpertReference` returns whichever valid
   solution the handcoded expert produces in the current session; recomputation in a long-lived
   process can differ (task 9). A future audit must either keep a privileged hash-and-compare of
   the exact reference used at run time in a clearly privileged file, or recompute in a fresh
   process before any other session, or compare the post-cut action SET across all expert
   variants. This is the cause of the NO-GO.
2. The HIGH contract does not describe the action representation (`Action(name="do",
   kwargs={"text": ...})`) or that the policy also reads `obs.data["admissible_commands"]`; two
   families were dead code for that reason.
3. The evidence's `reasoning:` line repeats the `<action>` tag when the policy runs with thinking
   off (no `<think>` block to extract); harmless but noisy.
4. Generated dose functions are often step functions (`int(DOSE * 100) >= 50`, `round(DOSE *
   4)`), which the bracket cannot calibrate into the band (task 12).
5. LOW: the designer preferred failure cuts even when a short reference was supplied (5 of 6
   cuts), and the successful unlocks overshot the band; the 4 -> 8 probe accepts only 3..5 of 8.

### Spend

USD 4.32 of the 30 cap (policy search 4.29 over 3 698 ledgered policy calls; designer 0.03 over
6 calls; confirmations 0). Reference and guard sessions cost nothing.
