# HarnessEvolve vs. AEA `llm_v1` LOW — gap audit (phase 3.2)

Source read for this audit: Jiang, Chu, Tian, Zhang, Yang, Yang, Liu, Lv, Li, "HarnessEvolve:
Learning from Reference Trajectories for Reliable Agent Self-Evolution", arXiv:2609.00829
(submitted 2026-09-01; ICT AI Competence Center, Huawei), HTML version, sections 3.2 (Execution),
3.3 (Evaluation), 3.4 (Optimization), 3.5 (gates) and Appendix B (Algorithm 1, reference-guided
error diagnosis and clustering). The HTML does not contain the verbatim prompt of
`AnalyzeTrajectory`; where the paper gives only the field structure, the table says so. Benchmarks
in the paper: SearchQA, OfficeQA, SpreadsheetBench, CloudCoreNetwork-QA, Wireless-QA. Quoted
phrases are from the paper.

## 1. What HarnessEvolve actually does (paper facts)

- Execution (3.2): the same execution agent A_exec that is being evolved is given "both the
  questions and their ground-truth answers" and produces, "prior to the optimization loop", up to
  T_att = 5 attempts per training task; a trajectory is tau_i = [(o_1, a_1), ..., (o_T, a_T)] of
  observation/action pairs. "Once a trajectory passes verification, it is stored as the verified
  reference trajectory tau_i^+ in a global cache C"; otherwise "the task is left without a
  reference trajectory". Purpose: "successful execution paths that can be compared against
  failed trajectories to pinpoint the first point of divergence".
- Evaluation (3.3, App. B): the evaluation agent verifies references ("follows a legitimate
  reasoning chain ... rather than trivially restating the provided answer"). For each failed
  instance, `AnalyzeTrajectory(tau^-, tau^+, q)` when a reference exists, else
  `AnalyzeTrajectory(tau^-, q)`; the output is a structured error signal F_i = (s_i, m_i, h_i):
  severity, error cause (examples: "tool hallucination, argument omission, premature
  termination"), and a "natural-language fix hint". Divergence: "the first action divergence
  point t_i^* (the earliest step at which the action in tau^- deviates from that in tau^+)".
  Signals are clustered "by error cause m_i" into clusters (aggregated severity, shared cause,
  representative failed trajectories, "suggested fix direction derived from the fix hints of its
  members") with "Cause-Based Grouping", "Root-Cause Priority" (prioritise t^*) and "Long-Tail
  Protection" (keep single-member clusters).
- Optimization (3.4, 3.5): the optimization agent proposes a harness delta over "prompts,
  skills, tools, and execution logic"; a quality gate (LLM-as-judge; data-leakage score must
  exceed eta_leak = 0.8; injected in-context examples <= eta_blo = 5; rejections returned "with a
  rejection reason rho for revision"), a performance gate (improvement on the current batch and
  no significant degradation on the last R = 2 batches), a snapshot pool, epoch-end selection of
  the best snapshot on a validation set, and early termination after P_batch = 10 patient
  batches.
- Leakage protection: the reference verification gate, the quality gate's data-leakage check
  ("directly embed failed queries and their ground-truth answers into the harness files"), and
  an "isolated judge, structurally decoupled from the optimization agent".

## 2. Gap table

| mechanism | HarnessEvolve | current AEA `llm_v1` LOW | same / different | relevant to AEA LOW? | phase-3.2 decision |
| --- | --- | --- | --- | --- | --- |
| reference producer | the same execution agent A_exec, run with the ground-truth answer | the benchmark's hand-coded ALFWorld expert (`run_expert`), a different agent from the learner | different | A (the source is a separately testable dimension) | keep the benchmark expert; hold the source fixed across arms; same-policy GT-conditioned reference deferred |
| reference timing | up front for all training tasks, cached globally | lazy, only after a task is estimated `zero` | different | B for this experiment (timing does not change the diagnosis content) | keep lazy |
| reference information content | observation/action pairs (o_t, a_t) | action list only | different | **A** (the phase-3.2 variable) | Arm B: rich observation/action trajectory of the same expert run |
| reference verification | evaluation-agent check of a "legitimate reasoning chain" before caching | the simulator's success flag (`Session.won`); attempts and stuck/blocked detection | different in kind, same purpose | A | keep the simulator verifier (ground truth in ALFWorld is the world state; no LLM judge) and record `success` in the provenance file |
| failed trajectory representation | tau^- as (o, a) pairs | step-by-step observation, action, effect/blocked flags, reasoning excerpt when present | same | A | unchanged |
| reference/failed alignment | inside `AnalyzeTrajectory` (LLM), no hand-written aligner shown | none: the LLM sees both and picks cuts directly | different | **A** | Arm B: explicit diagnosis fields in the same tool call; no hand-written aligner |
| divergence localization | "first action divergence point t^*" | none | different | **A**, with a caveat: ALFWorld admits many valid orders, so first string mismatch is not root cause | Arm B asks for the first *consequential* divergence (failure step + reference step), with observations available for semantic reasoning |
| error representation | F = (severity, error cause, fix hint) | mechanism summary only | different | **A** | Arm B: `error_cause`, `fix_hint`, optional `evidence`; no severity |
| error aggregation / clustering | cause-based clustering across the batch, root-cause priority, long-tail protection | none | different | B: clustering serves shared harness updates; AEA's object is a task-local Stage | deferred (see section 4) |
| proposal generator | optimization agent from error clusters | one designer call from evidence | same role, different input | A | unchanged: one call, <= 2 proposals |
| object being modified | the harness: prompts, skills, tools, execution logic | the environment: a Stage (replayed prefix) on the learner's task | different by design | B | unchanged (AEA never edits the learner harness) |
| candidate validation | quality gate: LLM-as-judge leakage score, bloat cap, revision loop | compile the prefix, oracle solvability guard, no LLM judge, no revision | different | B (their gate protects harness files; ours protects environment validity) | unchanged |
| performance acceptance | performance gate on batch accuracy + regression buffer, snapshot pool, epoch selection | current-policy 4 -> 8 probe on the task, accept iff 3..5 of 8 | different | B | unchanged |
| GT leakage protection | reference verification, leakage judge on harness edits, isolated judge | privilege boundary: reference reaches the designer only; redacted records; exact-reference provenance file; post-run audit | different mechanism, same intent | A | unchanged; extended to rich references (observations too) |

Relevance classes used above: **A** credit-assignment mechanism directly relevant to LOW
environment design; **B** harness-evolution mechanism not directly relevant to task-local AEA;
**C** potentially useful later (same-policy GT-conditioned reference; cross-task aggregation once
interventions are shared across tasks).

## 3. Reference-source feasibility audit (ALFWorld)

| question | finding |
| --- | --- |
| ground-truth object of an ALFWorld task | the PDDL goal checked by the simulator (`Session.won` / `evaluate().success`); per task the data directory also carries `traj_data.json` with a `plan.high_pddl` (7 high-level PDDL steps for the inspected task) and `low_actions` (101 low-level Thor actions), and human `turk_annotations` |
| ground-truth action plan | yes, two forms: the hand-coded expert's plan exposed step by step by the TextWorld backend (`infos["extra.expert_plan"]`, what `run_expert` follows) and the static `high_pddl` plan in `traj_data.json` (not in TextWorld command syntax) |
| can the Qwen policy be run with privileged GT | in principle yes: the task prompt could carry the expert plan or the high-level PDDL steps; the released `PolicyAgent` takes `task_prompt` only, so it would be a prompt injection through the existing `skills_block` / task prompt path; it would need its own verification (success flag) and its own leakage argument; not built in this phase |
| can it produce a genuine interactive successful trajectory | plausibly for many tasks (the expert plan is complete); unknown rate; unknown whether it "trivially restates" the plan (HarnessEvolve's verification concern) |
| how would it be verified | the simulator success flag suffices for goal achievement; a "legitimate reasoning chain" check would need an LLM judge, which AEA does not use |
| benchmark expert as a rich trajectory | feasible without changing the simulator: `run_expert` already drives the expert closed-loop through a `Session`; the observation before each action and the admissible commands are simulator-visible state (`Session.stack.observe().text`, `Session.admissible()`); recording them is a read-only hook on the existing loop; success is the existing `Session.won` |

Decision: **use the benchmark expert as the successful reference producer, upgraded from an
action list to a rich observation/action trajectory, recorded in one session and frozen.** This
changes the credit-assignment information while holding the successful reference source fixed,
so the comparison isolates reference-guided alignment from reference-source identity. This is
"HarnessEvolve-style reference-guided diagnosis", not a faithful reproduction of HarnessEvolve
reference generation (different producer, lazy timing, no LLM verification). The same-policy
GT-conditioned reference remains a separately testable future dimension.

## 4. Why clustering is deferred

HarnessEvolve clusters error signals because its output is one harness update shared by all
tasks of a mini-batch; clustering decides which shared fix to make. AEA's LOW output is a
task-local environment intervention chosen from one task's failures and one task's reference;
there is nothing to aggregate across tasks in this experiment. If AEA later moves toward
reusable, cross-task environment interventions, cause-based aggregation becomes its own
hypothesis with its own pre-registration.

## 5. Phase-3.2 hypothesis (written before implementation)

The current LOW designer fails partly because an action-only successful reference does not
provide explicit credit assignment. Supplying a rich successful observation/action trajectory and
requiring explicit failed/reference divergence diagnosis will improve the quality of Stage
selection, without changing the Stage intervention or the empirical acceptance controller.

Held fixed: intervention class (Stage), acceptance (current-policy 4 -> 8, accept iff 3..5 of 8),
budget (30 charged rollouts per task), designer calls (1), proposals (<= 2), designer model and
settings, compile / guard / probe machinery, reference source (benchmark expert), and, in the
prospective comparison, the exact failed trajectories and the exact reference instance (shared
evidence). Varied: the reference information (action list vs. observation/action trajectory) and
the designer contract (direct selection vs. explicit diagnosis then reference-grounded selection).

Method variant: `method_version = "llm_v1_refalign"`, identical to `llm_v1` on MID and HIGH (same
code path, asserted by tests), different only in the LOW designer input and contract.

## 6. What AEA borrows, and what it deliberately does differently

Borrowed: reference-guided failure localization / credit assignment (a verified successful
trajectory compared with the failure to find the first consequential divergence and a structured
error cause + fix hint), used to choose the environment intervention.

Different by design: lazy references only for LOW; the benchmark expert as the reference producer
in this controlled experiment; a task-local environment Stage instead of a harness update; no
batch clustering; no LLM quality judge; current-policy environment-response acceptance instead of
batch-accuracy gates. AEA adapts reference-guided credit assignment to environment intervention
design; it does not implement HarnessEvolve.
