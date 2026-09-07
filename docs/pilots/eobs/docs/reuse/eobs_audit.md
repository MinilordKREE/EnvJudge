# E-obs Phase-0 audit of envharness @ fab7d57441f06b75c73a900e04561d4d7600f361

All paths relative to `third_party/envharness/`. Verified 2026-09-05 against the installed submodule; empirical
checks ran in `~/eobs_venv` with the released code (nothing modified).

## (a) Task enumeration and order on the train split

- `envharness/orchestration/orchestrator.py:412` — `task_id = base_seed + task_idx * task_id_stride + task_id_base_offset`;
  `experiments/alfworld/corpus.yaml` sets `base_seed: 0`, `task_id_stride: 1`, `task_id_base_offset: 0` → task_id = task_idx = 0..N-1.
- `orchestrator.py:870` (`_rollout_baseline_k`) and `:986` (`_rollout_k`) build `EpisodeSpec(env=EnvSpec(reset_seed=task_id), task_id=self.config.task_id)`;
  `envharness/orchestration/runner.py:200` resets with `options={**reset_options, "task_id": spec.task_id}` where `spec.task_id` is the
  orchestrator label `"alfworld-corpus-ours-release"`, not a gamefile.
- `envharness/bridges/alfworld/bridge.py:206-209` — an unknown `task_id` falls back to seed-based selection; `:702` `_safe_seed(n)`:
  TextWorld `seed(n)` shuffles the gamefile order and `reset()` plays the head ("NOT an index", docstring at `:40-46`).
- Empirical: seeds 0–29 → 30 distinct train games (of 3,553); types: pick_cool 7, pick_clean 8, pick_two 7, pick_and_place 2,
  look_at_obj 3, pick_heat 3 (seed→gamefile table stored with Phase-1 `tasks.csv`). "First N tasks in the config's order" = seeds 0..N-1.

## (b) Where per-rollout actions / observations / success are persisted

- `orchestrator.py:819` baseline traces (`kind="baseline"`) and `:665` candidate traces (`kind="accepted"|"exploration"`) go to
  `TraceStore.add` (`envharness/orchestration/storage.py:57`, JSONL at `storage.trace_path`).
- `Trace` (`envharness/core/types.py`): `candidate` (rules_code, in_env_actions, rationale), `candidate_id`, `rollout_idx`,
  `rollout_seed` (= task_id), `success`, `duration_steps`, `steps[]` with `raw_action.kwargs.text`, `blocked_reason` (`runner.py:266`),
  `raw_observation`, `info` (won, admissible_commands, effective, …), `policy_raw_response` (`runner.py:274`), `error`
  (`"subprocess timeout"` from `runner.py:362`). `discard_rollout_steps_after_decide: false` in corpus.yaml keeps steps.

## (c) Rejected / refined candidates

- Every validated candidate's K traces are persisted (kind=exploration) with the full `candidate` object → `rules_code`,
  `in_env_actions`, `rationale` are on disk for every attempt, not only ACCEPTs.
- `orchestrator.jsonl` events (`orchestrator.py:493 candidate_evaluated` [attempt, candidate_id, k, success_rate, n_errors];
  `:510 mutator_decision` [decision, failure_axis/label, rationale[:200]]; `:594 candidate_refined`; `:604 candidate_reproposed`;
  `:456 task_skipped_passthrough`; `budget_stop`; `task_aborted`).
- Full designer text: `envharness/infra/llm.py:453` `LoggingLLMClient` writes `agent_calls.jsonl` with the tool-call arguments of
  every `propose_candidate` / `decide_on_traces` call (`:506-509`): the decision rationale and the next candidate's full code and
  rationale. `scripts/run_harness.py` wires it when `logging.log_agent_calls: true` (corpus.yaml: true).
- Therefore no in-process hook is needed. `eobs/hooks.py` is a post-hoc, observe-only extractor that joins traces.jsonl,
  orchestrator.jsonl and agent_calls.jsonl (sequence-aligned per task) into `candidates.jsonl`. Gap: `agent_calls` truncates
  MESSAGES to 8,000 chars (responses are complete); the objective text shown to the designer is reconstructed from
  `objective.evaluate` (DifficultyZone with the no-op band [0,1] → always "in target band"/bootstrap text).

## (d) Deterministic reset and mid-state restore

- `bridge.py:399-412` `save_state` / `from_state` store only `(reset_seed, reset_options)`; valid at episode boundaries.
  `bridge.py:61` docstring: "snapshot/restore: NOT implemented … the realistic implementation is replay (seed, action-list)".
- Mid-episode states are reached by reset + replay of the action list (the Setup harness does exactly this:
  `envharness/harnesses/setup.py:77-88`). `eobs/replay.py` reuses `runner.build_env_stack` (`runner.py:129`) so E′_c is built
  exactly as the orchestrator builds it, then replays actions through the stack.
- Empirical: same seed → same game and same expert trajectory across sessions (seeds 0/1/7/9 repeated).

## (e) Expert plan from the current state

- ALFWorld (`alfworld/agents/environment/alfred_tw_env.py:75-84`, installed 0.4.2): with `expert_type: handcoded`
  (vendored `envharness/third_party/alfworld/base_config.yaml:18`) the `AlfredExpert` wrapper writes
  `state["extra.expert_plan"] = [handcoded_expert_next_action]` after every step, computed by the stateful handcoded expert
  from the current game facts. It is one action of look-ahead; a "plan" is obtained closed-loop.
- The bridge discards `extra.expert_plan` (`bridge.py:281` keeps admissible/won/gamefile only). Access beneath the bridge:
  `eobs/replay.py:RecordingProxy` wraps `bridge._env` (the TextworldBatchGymEnv) and records the last infos; all
  attribute access is delegated, so `_set_env_gamefiles` / `_safe_seed` keep working. Observe-only; third_party untouched.
- Empirical: closed-loop expert from reset passes on seeds 0, 1, 7, 9 (7/12/7/5 steps, all ≤ 50); from a mid-episode
  state (2 expert steps + `look` + `inventory`) it passes; after a full expert prefix the state is already won.
  recover_mode = `handcoded_closed_loop` for the whole study (the `suffix` fallback is not needed).

## (f) Hooks a Rules candidate can override on ALFWorld; how Blocked surfaces

- `envharness/harnesses/rules.py:93` `filter_action` (A), `:97` `modify_transition` (T), `:102` `filter_observation` (O).
  S0 is `in_env_actions` via `Setup` (`setup.py:77-88`); R is not exposed.
- `rules.py:127-137`: a `Blocked` return leaves the env unchanged and returns `Observation(text="[blocked] <reason>\n\n<fresh obs>",
  data={..., "blocked": True, "blocked_reason": ...})`, `info={"blocked_reason": ...}`; the runner records it on
  `Step.blocked_reason` (`runner.py:266`). The bridge's repetition guard is disabled in corpus.yaml (`repetition_threshold: 0`).
- The ALFWorld designer block forbids hiding admissible commands and custom block messages (corpus.yaml:56-70) but the
  mechanism remains available; `eobs/axis.py` flags `blocked_possible` when the A hook's source mentions `Blocked(`.

## (g) ALFWorld designer SR rules (exact text)

`experiments/alfworld/corpus.yaml:42-51` (agent.extra_instructions, PHASE 1):
```
- If baseline_sr >= 0.8: SKIP. The Policy already solves this task; no new skill to extract. Emit
  `Candidate(rules_code="", in_env_actions=[], rationale="skip-easy-task")` and the orchestrator will move on.
- If 0.0 < baseline_sr < 0.6: TARGET. The Policy struggles here. Proceed to Phase 2.
- If baseline_sr == 0.0: TARGET if you can diagnose a recoverable failure mode from the baseline trajectories. Otherwise SKIP.
```
`corpus.yaml:83-84` (PHASE 4): "Run K=5 rollouts. The harness succeeds if mutated SR > baseline_sr by at least 0.2".
Generic system prompt `envharness/agents/harness_agent.py:492-516`: "PITFALL -- DO NOT MAKE THE TASK MATHEMATICALLY
UNSOLVABLE … SR=0 from impossibility … your NEXT propose() must REVERSE the offending restriction (or loosen it)";
`:543-544`: "If baseline_sr is 0 or near 0, 'make it harder' is nonsensical".
`skip_passthrough_candidates: true` (corpus.yaml) → an empty Candidate ends the task with no validation rollouts
(`orchestrator.py:456`).

## Other substrate facts recorded

- Objective: `DifficultyZone(target_band=[0.0, 1.0], window=20)` — the band is a no-op; the acceptance criterion is the
  designer prompt. Budget `CappedAdaptive(max_k=5)`: ≤ 5 write–validate attempts, stop at ACCEPT.
- Policy: `action_format: think_action`, `temperature: 0.5`, `max_history: 200`, `max_episode_steps: 50`,
  `rollout_concurrency: 5`, subprocess runner timeout 500 s. `baseline_cache_dir: null` → no baseline cache.
- litellm 1.99.0 moves a leading `<think>…</think>` block into `reasoning_content`
  (`litellm/litellm_core_utils/prompt_templates/common_utils.py:1552-1572`, applied in
  `llm_response_utils/convert_dict_to_response.py:670`); `policy_raw_response` therefore lacks the think text (see LOG).
- Model routing without code changes: `LiteLLMClient(**defaults)` forwards `api_base` and `extra_body` to `litellm.completion`
  (`infra/llm.py:145-200`); `run_harness._client_from_block` passes a non-default `client_factory` through untouched.
