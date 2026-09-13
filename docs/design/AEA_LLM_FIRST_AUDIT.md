# AEA LLM-first redesign — audit of the current method (phase 1, no code)

Written 2026-09-13 in the isolated worktree `../EnvJudge-aea-llm` (branch `aea-llm-vnext`, created
from `main` @ `0ac37bc171c28a50c765a8027c775fb5e3fa0153`) while E5 runs untouched in the main
working tree. Every statement below is read from the code at that commit; file references are
`path:line`. Nothing in this document is a design decision; section 8 lists what the redesign must
keep and where each new piece would attach.

Record taken before the worktree was created (safety rule of the brief):

| item | value |
| --- | --- |
| `git rev-parse HEAD` | `0ac37bc171c28a50c765a8027c775fb5e3fa0153` |
| `git status --short` | clean apart from the submodule line `third_party/envharness` (unchanged submodule @ fab7d574, shown because the worktree checkout does not populate it; copied read-only into the new worktree with rsync) |
| `git worktree list` | `/home/kree/work/EnvJudge  0ac37bc [main]` (the only worktree) |
| E5 processes seen | `runs/e5_chain.sh` (pid 769893), `scripts/e5.py --stage A4` |
| worktree created | `git worktree add -b aea-llm-vnext ../EnvJudge-aea-llm HEAD`; `uv sync --extra alfworld` inside it; `import aea, alfworld` ok |

## 1. CURRENT HIGH PATH (regime `saturated`, "harden")

Entry: `Controller._run_task` (`src/aea/controller.py:307-333`) runs the estimator
(`aea.estimate.estimate`, sequential Beta, K = 16 with early stop, `src/aea/estimate.py`) and
dispatches on `est.regime`: `band` -> corpus entry `kept`; `saturated` -> `_harden`; `zero` ->
`_stage`. The regime boundaries are `AEAConfig.band_l = (0.2, 0.8)` (`src/aea/config.py:58`).

`_harden` (`controller.py:382-406`):

1. `_await_predecessors` — the leverage table is a sequential dependency (task pool rule 2).
2. Evidence extracted from the estimate: the successful traces, their lengths
   (`duration_steps or len(steps)`), `FamilyContext(task_id, success_lengths)`, and the policy's
   shortest successful action list (`witness = policy_shortest_success(est.traces)`,
   `src/aea/witness.py:69-79`).
3. `_families` (`controller.py:348-376`): if `use_proposer` and the substrate has a designer and
   `impl.proposer_cap > 0`, one proposer call (`families.propose_families`, section 6) may add up
   to two `ProposedFamily`; then `leverage.order([*proposed, *LIBRARY])` orders proposed families
   before the two library families (`FooterMask` O-axis, `HorizonSqueeze` T-axis,
   `src/aea/families.py:74-100`) by leverage rate (unseen families keep proposer order).
4. For each family in that order, `_try_family` (`controller.py:408-516`):
   - `make(1.0)`; `None` -> `family_skipped: infeasible`.
   - Guard at d = 1 under `SESSION_LOCK`: `witness.solvable(top, open_session, config,
     policy_success=witness, oracle=substrate.has_oracle(), by_construction=(axis == "O"))`.
     O-axis families pass by construction; otherwise the policy's own success is replayed through
     the wrapped environment, then the ALFWorld handcoded expert is run (`impl.oracle_attempts = 3`,
     `impl.oracle_max_steps = 50`); failure -> `family_skipped: uncertified`.
   - Leverage test: `evaluate_at(1.0)` = the 4 -> 8 rule (`aea.evaluate.evaluate`,
     `src/aea/evaluate.py:52-60`; first batch 4, 0/4 -> `too_hard`, 4/4 -> `too_easy`, else top up
     to 8 and accept iff 3 <= successes <= 5). `too_easy` at d = 1 is `no_leverage` (recorded in the
     leverage table and as a `leverage` event, `_record_leverage`); `in_band` at d = 1 is accepted
     immediately; `too_hard` starts the dose search.
   - Dose search: `aea.bracket.bracket(evaluate_at, config, leverage=DoseEval(1.0, lev),
     start=warm_start)` (`src/aea/bracket.py`), task-local interval always [0, 1], at most
     `impl.max_bisections = 4` bisections, the first interior probe is
     `LeverageTable.warm_start(family, impl.warm_start_min_history = 3)` (v0.4: median of >= 3
     previous task frontiers, else 0.5). Outcome `accepted` -> `_accept_knob`; `exhausted` ->
     `dropped: exhausted`; `budget` -> `BudgetExhausted` -> `dropped: budget`.
   - After every finished search one frontier estimate is recorded (`_record_frontier`, event
     `leverage {family, frontier, lo, hi}`) and a `bracket` event with `start`, `local`, `status`
     and the full probe history.
5. Acceptance writes `corpus.jsonl` entry `kind = knob` with `family, source (library|llm), axis, d,
   p_hat, candidate_id = f"{task}:{family}:{d}"` (`_accept_knob`, `controller.py:518-548`;
   `AeaMeta`, `src/aea/io.py:31-49`).
6. Every policy rollout is charged to the one budget before it runs (`_rollouts`,
   `controller.py:153-180`; cap = `AEAConfig.cap = 30`); errored rollouts are refunded; each
   rollout is appended to `traces.jsonl` and summarised by a `rollouts` event.

What the HIGH path does NOT do today: it never shows the designer the task goal, any observation,
any action, any failure, or the Rules hook signatures beyond the two library exemplars; the designer
is optional and, in E3, was tried after both library families were ordered ahead of it whenever the
library had a better leverage rate (`LeverageTable.order`, `families.py:375-384`).

## 2. CURRENT LOW PATH (regime `zero`, "stage")

`_stage` (`controller.py:551-645`), no LLM anywhere:

1. `seeded_failures(est.traces, impl.n_failed_rollouts = 3, seed=task.seed)`
   (`src/aea/stage.py:78-81`): a seeded sample of three failed, non-errored, non-empty estimate
   rollouts; none -> `dropped: no_failed_rollout`.
2. `reset_options = substrate.stage_reset_options(task)` = the corpus reset options plus
   `config_path = configs/alfworld_config_100.yaml` (the 100-step config, so a staged prefix does
   not consume the policy's 50-step horizon; `stage.py:34-36`, `substrate.py:167-168`).
3. `build_stage_candidates` (`stage.py:129-160`) under `SESSION_LOCK`:
   - candidate states = the end and the midpoint of each sampled failure
     (`candidate_states`, `stage.py:84-103`), latest-first, capped at `impl.max_candidates = 6`
     by dropping the candidate nearest in t to another kept one;
   - each prefix is the failure's raw action texts up to t, compiled by replay on a fresh staged
     session (`compile_prefix`: keep admissible and effective actions, append `look`);
   - candidate id = `f"{task}:{sha256(compiled)[:16]}"`, deduplicated;
   - the candidate is `Candidate(in_env_actions=[Action("do", text=a) ...])`, run by the released
     `Setup` harness (`session.py:176-177`, identical to the released `build_env_stack`);
   - guard = `solvable(cand, open_fn, config, oracle=has_oracle())` with the ORACLE ONLY (no policy
     witness: a success from reset cannot witness a mid-trajectory state); without an oracle the
     candidate self-certifies;
   - one fidelity check per task: the replayed observation at the cut equals the archived one
     (`fidelity_check`, `stage.py:163-185`).
4. Certified candidates are walked latest-first; each is probed by the same `evaluate` (4 -> 8)
   with `reset_options = opts` (`_rollouts(task, c.candidate, n, "probe", reset_options=opts)`).
   First `in_band` -> corpus entry `kind = stage` with `t, state_hash, profile, stage_budget = 100,
   candidate_id, p_hat`; `BudgetExhausted` -> `dropped: budget`; otherwise `dropped: too_easy` if
   any probe was too easy, else `dropped: dead`.
5. Events: `stage_candidates {certified, kinds, rejected, fidelity_ok}` and `probe {profile,
   accepted, skipped}`.

The LOW path has one source of candidates (the policy's own failed prefixes cut at end/mid) and no
diagnosis of why the policy fails.

## 3. AVAILABLE TRAJECTORY INFORMATION

Everything the controller already holds at the branch point, for both regimes, is
`est.traces: list[Trace]` (the K <= 16 estimate rollouts, also persisted verbatim in
`traces.jsonl` by `TraceWriter.add`). Released `Trace` / `Step` fields
(`third_party/envharness/envharness/core/types.py:71-100, 172-196`):

| field | content on ALFWorld |
| --- | --- |
| `Trace.success`, `final_reward`, `duration_steps`, `error`, `subprocess_stderr` | outcome; errored traces are never counted |
| `Trace.episode_id`, `iteration_id` (`estimate-<task>-<i>`), `rollout_seed` (= task id), `candidate` | identity and the environment the rollout ran on |
| `Step.raw_action.kwargs["text"]` | the policy's chosen command (e.g. `go to countertop 1`) |
| `Step.filtered_action`, `blocked_reason` | `None` / reason when a Rules layer blocked the action |
| `Step.raw_observation.text` | the ALFWorld observation text, including the task goal on step 0 (`Your task is to: ...`) and the `Admissible commands:` footer |
| `Step.raw_observation.data["admissible_commands"]` | the admissible list |
| `Step.filtered_observation` | what the policy actually saw (after Rules filters; equals raw on the unmodified env) |
| `Step.info["effective"]` | whether the command changed the world (the stage compiler keeps only effective actions) |
| `Step.policy_raw_response` | the policy's full `<think>...</think><action>...</action>` output |
| `Step.terminated`, `truncated`, `raw_reward` | per-step flags |

Derived quantities already computed by the current paths: success rate `est.p_hat`, `est.n`,
regime posteriors `est.probabilities`; success lengths; the policy's shortest successful action
list (`policy_shortest_success`); the seeded failure sample and the compiled prefixes.

Not available at the branch point: rollouts on any modified environment (they exist only after a
probe), any human annotation, and the ALFWorld expert plan for a trajectory (the expert is reached
only through an in-process session, section 5, never through the released subprocess rollouts).

## 4. AVAILABLE TASK DESCRIPTION

- The policy's task prompt (`configs/corpus_aea.yaml` `policy.task_description`) is the generic
  ALFWorld instruction ("You are an agent in a text-based household environment ..."). It does not
  name the task; it is the same for every task.
- The task itself is identified by `TaskRef(task_id, seed)` where `task_id` is the string of the
  train-split seed (`scripts/e5.py:96`, `scripts/e3.py`), and by the game file
  `substrate.game_file(task)` (`substrate.py:159-164`; a relative `.../trial_T.../game.tw-pddl`
  path whose directory name encodes the task type and target, e.g. `pick_and_place_simple-...`).
- The natural-language goal is inside the step-0 observation of every rollout
  (`Step.raw_observation.text`, section 3), formatted by ALFWorld as `Your task is to: <goal>`.
- The orchestrator block's `task_description` ("Mutate train tasks where the Policy is currently
  weak ...") is the released HarnessAgent's brief, not used by aea.

Today the proposer receives only `task_description = f"task {task.task_id}"` and
`success_summary = f"successful episode lengths: {sorted(lengths)}"` (`controller.py:357-358`).

## 5. AVAILABLE ORACLE / REFERENCE INFORMATION

- ALFWorld ships a handcoded expert; `AeaSubstrate.has_oracle()` is `True` (`substrate.py:194`).
- It is reached only through an in-process `Session` (`src/aea/session.py`): the bridge's
  underlying TextWorld env is wrapped by `RecordingProxy`, and `Session.expert_next()` reads
  `infos["extra.expert_plan"][0]` after each step (`session.py:109-113`). `run_expert(sess,
  max_steps, retry_blocked=3)` (`session.py:228-269`) drives the expert closed-loop from the
  session's CURRENT state (so it works from a staged prefix), stops on win / done / cap /
  `expert_error` / `expert_stuck` / `blocked`, and returns `ReplayResult(ok, reason, step, n_steps,
  actions)` — the expert's action list from that state.
- `replay_actions(sess, actions)` replays a fixed action list verbatim (used for the policy
  witness).
- The only consumer today is the guard `witness.solvable()`; it records the expert's actions as
  `Solvable.witness` and the source (`by_construction | policy_replay | oracle | self_certify |
  uncertified`) in the `solvable` event. Sessions are never charged and never touch the budget.
- Every in-process session must be opened through `open_session` / under `SESSION_LOCK`
  (`session.py:38-40, 161-198`): one at a time per process, policy rollouts in subprocesses never
  take it.
- Cost: a session is a local TextWorld replay (no LLM call); the expert can be slow on some games
  (`expert_timeout` is mapped from the exception text, `session.py:246`).

There is no other reference: no stored expert trajectories, no human solutions, no ground-truth
plans outside the live expert.

## 6. CURRENT DESIGNER CONTRACT

`src/aea/families.py:186-331`:

- Tool schema `PROPOSE_TOOL` (`families.py:186-222`): `propose_families` with `families:
  [{name, axis in {O,T,A}, rules_code}]` (max 2) and an optional `ranking` list.
- `CONTRACT_TEXT` (`families.py:224-231`): emit `class _Rules(Rules)` with a class attribute
  `DOSE = __DOSE__`, difficulty must increase with DOSE, the task must stay solvable at DOSE = 1,
  only `Rules, Action, Blocked, Observation, EnvResponse` and the standard library are available,
  no Chain/Link, acceptance is decided by rollouts, do not re-propose the library families.
- Messages (`proposer_messages`, `families.py:234-249`): system = the contract; user = task
  description + success summary + the two library exemplars verbatim as few-shot
  (`aea.exemplars.prompt_text`, `src/aea/exemplars/*.py.txt`) + "Call propose_families."
- Request (`propose_families`, `families.py:290-331`): `temperature = 0.7`, `seed = task.seed`,
  `max_tokens = 4096`, forced tool choice, `Attribution(phase="propose", budget="designer")`;
  the call is ledgered by the designer client (`AeaSubstrate.designer()`, `substrate.py:180-189`,
  provider pin enforced by `OpenAICompatibleClient`) and NOT charged to the rollout cap.
- Validation (`parse_proposals` + `validate_rules_template`, `families.py:158-183, 259-287`):
  library copies rejected; the template must reference `DOSE`; it must load through the released
  `code_loader.load_rules_subclass` at `__DOSE__ = 1.0`; an LLM-free smoke drives the three hooks
  (`filter_action`, `modify_transition`, `filter_observation`) on a minimal inner env; axis must be
  O/T/A. Accepted proposals become `ProposedFamily(name, axis, template, source="llm")`, whose
  `make(d)` substitutes `__DOSE__` / `__TASK_ID__`.
- Record: `designer_calls.jsonl` (arguments, accepted, rejected, ranking) and the `proposer` /
  `proposer_failed` events.
- Where it is used: HIGH only (`_families`); LOW never calls the designer. Proposals enter the same
  guard / leverage / bracket loop as the library families (section 1); the LLM never sees rollout
  results and is never called again for the task.
- Drivers: `scripts/e3.py substrate(with_designer=...)` builds the designer as
  `designer_deepseek()`; E5 runs `use_proposer=False` (`scripts/e5.py:96`).

## 7. CURRENT DOWNSTREAM E3-SL ENTRY POINT

`scripts/e3sl.py` consumes a finished arm run directory by files only:

- `e3.learner_facing()` (`scripts/e3.py:764-...`) reads `runs/<arm>/corpus.jsonl` through
  `aea.io.read_corpus` and lists every environment an arm hands to the learner: entries of kind
  `kept` (empty candidate, shared K16 reused) and accepted transformed environments (`knob` or
  `stage`, candidate = `rules_code` + `in_env_actions`), keyed by `candidate_key(candidate)`
  (`scripts/e3.py:292-298`, sha256 of the candidate JSON).
- `lf_inputs(arm)` (`scripts/e3sl.py:199-215`) takes `runs/<arm>/traces.jsonl`, keeps successful
  non-errored traces, and keeps those that ran on the learner-facing environment (`_on_env`,
  `e3sl.py:218-224`: unchanged candidate for `kept`, matching candidate key otherwise; for A every
  such rollout counts, for G / R only `kind == accepted`).
- `induce()` (`e3sl.py:296-317`) hands `{task: [trace dicts]}` to the released
  `scripts/induce_pair.py::_build_bank` (single-success induction, DeepSeek extractor through the
  eval hook, OpenRouter embeddings); `induce_cascade()` runs the released Stage 2 on
  `cascade_traces(arm)` (`e3sl.py:227-249`: A's trace kinds remapped baseline / accepted /
  exploration by `iteration_id` prefix and candidate key).
- Then item matching, N / placebo anchors, the released `reasoning_bank_eval.py` through the hook,
  and `scripts/make_tables_e3sl.py` (task-clustered bootstrap).

Contract a new arm must satisfy to be evaluated by E3-SL unchanged: a run directory with
`corpus.jsonl` entries of kinds `kept | knob | stage` carrying a `Candidate` the released loader can
run, `traces.jsonl` whose rows carry `rollout_seed` (= task), `candidate`, `iteration_id`
(`estimate-` prefix for baseline), `success`, `steps`, and the `aea` block with `task_id`,
`candidate_id`. A reference-derived staged prefix is a `stage` entry like any other (the prefix is
learner-visible by construction; the reference actions BEYOND the cut must not appear in any
learner-facing trace — E3-SL only reads policy rollouts, so this holds as long as no oracle session
is ever written to `traces.jsonl`, which is true today: sessions are not traces).

## 8. Attachment points for the redesign (facts, not decisions)

| preserved item | where it lives | touched by the redesign? |
| --- | --- | --- |
| estimator, regime boundaries | `estimate.py`, `config.band_l` | no |
| 30-rollout cap, budget accounting, refunds | `Budget`, `_rollouts` | no (new rollouts go through `_rollouts`) |
| event ledger, resume | `EventWriter`, `completed_tasks`, `_restore_leverage` | new event kinds only |
| corpus format | `AeaMeta` kinds `kept/knob/stage` | no new kind needed (LLM-designed Rules = `knob` with `source = llm`; grounded prefix = `stage`) |
| 4 -> 8 probe, acceptance | `evaluate.py` | no |
| Rules code validation | `validate_rules_template` | reused as is |
| witness / oracle guards | `witness.solvable`, `session.run_expert` | reused; a `ReferenceProvider` would call `run_expert` through the same locked session |
| dose search, warm start | `bracket.py`, `LeverageTable.warm_start` | no (empirical control reuses `_try_family`) |
| designer client, ledger, provider pin | `AeaSubstrate.designer()` | reused for the diagnosis / design calls (`budget = designer`) |
| E3-SL pipeline | `scripts/e3sl.py`, `make_tables_e3sl.py` | no (E6-SL reruns it on new run dirs) |
| substrate | `third_party/envharness` | never |

Branch points where the new mode would attach: `_families` (HIGH proposer input and order) and
`_stage` step 1 (LOW candidate source). Both are reached only from `_run_task`, so a
`method_version` switch at those two call sites leaves every v0.4 path byte-identical when the
switch is off.
