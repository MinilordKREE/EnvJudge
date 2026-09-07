# Audit: substrate interfaces every module relies on (`third_party/envharness` @ fab7d574)

Legend — **import**: used as-is; **wrap**: called through an aea object that adds accounting only;
**rewrite**: behaviour re-implemented in aea because envharness has no reusable entry point.
All line numbers are in the pinned submodule. Invariants marked ✓ were verified by reading the code
named; nothing is assumed.

## Types (`envharness/core/types.py`) — import

| type | lines | used for |
|---|---|---|
| `Action(name, kwargs)` (`extra="forbid"`) | 46-50 | every replayed / staged action (`Action(name="do", kwargs={"text": …})`) |
| `Blocked(kind="blocked", reason)` | 53-57 | return value of `Rules.filter_action` for A-axis knobs |
| `Observation(text, data)` (`extra="allow"`) | 60-63 | O-axis hook output; `data["admissible_commands"]` is what the policy normalises against |
| `Step` (raw/filtered action + observation, `terminated`, `truncated`, `info`, `policy_raw_response`) | 71-100 | traces consumed by induction (`policy_raw_response` gives `<think>…</think><action>…</action>`) |
| `EnvResponse(observation, reward, terminated, truncated, info)` | 101-107 | T-axis hook; `truncated=True` ends the episode (runner.py:280) |
| `Candidate(rules_code, in_env_actions, rationale)` | 137-141 | the corpus unit; `io` emits exactly this shape |
| `Trace` (`episode_id, iteration_id, task_id, candidate, candidate_id, rollout_idx, rollout_seed, steps, final_reward, success, duration_steps, kind ∈ {accepted, exploration, baseline}, policy_model_id, error, subprocess_stderr`) | 172-197 | every rollout record; `io` writes Traces through `TraceStore` |

## ActionableEnv (`envharness/core/actionable_env.py`) — import

`reset(seed, options)` 106; `step(action)` 111; `observe()` 114; `evaluate()` 125 (success is read
from the BASE env: `Rules`/`Setup` inherit delegation, rules.py:158, setup.py:98);
`notify_replay_complete()` 208 (called by `Setup` after replay); `close()` 236.

## Runner (`envharness/orchestration/runner.py`) — wrap

- `build_env_stack(spec)` 129-142: base env → `Setup(inner, actions)` iff `in_env_actions` →
  `load_rules_instance(rules_code, inner)` iff `rules_code`. Exactly the stack aea must reproduce
  for replays (the pilot's `open_session` mirrors it; `stage`/`certs` build the same stack).
- `run_episode(spec)` 171-300: `env.reset(seed=reset_seed, options={**reset_options, "task_id": task_id})`
  (196-199); policy built from the BASE env's `tool_schemas()` (207-209); loop `for _ in range(spec.max_steps)`
  (231) — ✓ **the runner enforces the policy step cap; the bridge has no cap of its own**
  (bridge.py `step` 263-339 only counts `step_count`); a Rules-blocked action is recorded with
  `filtered_action=None` (256-266); the loop breaks on `terminated or truncated` (280-281) — so a T-axis
  `truncated=True` ends the episode; `success` comes from `env.evaluate()` (283-291). A policy or env
  exception returns a `Trace(error=…)` with the steps so far (237-254); a `RulesCodeError` returns a
  cheap `Trace(error="RulesCodeError: …")` before any engine boots (186-192).
- `EpisodeSpec(env=EnvSpec(import_path, reset_options, reset_seed), candidate, policy=PolicySpec(...),
  iteration_id, task_id, max_steps=50)` 84-127. `reset_options` is passed verbatim to the bridge, so
  `config_path` (the 100-step config) travels through the released runner unchanged.
- `SubprocessRunner` 316-420: one Python subprocess per episode (`episode_worker.py`), the spec as JSON on
  stdin (333-347), the Trace as the last stdout line (383-388); timeouts and non-zero exits become
  `Trace(error=…)` (356-382). `_child_env` 397-419 pins `PYTHONPATH` to the parent's package root.
  aea uses this runner unchanged; the per-episode attribution reaches the child through `AEA_*`
  environment variables (inherited by `subprocess.run(env=…)`, 397-403).
- `PolicyAgent` (`envharness/agents/policy.py`): `think_action` parses the FIRST `<action>` (305-323),
  normalises against `obs.data["admissible_commands"]` captured in `act` (186-189), and `_format_obs`
  appends an admissibles reminder from `obs.data` (370-395). ✓ So an O-axis knob that hides the footer
  must also drop `admissible_commands` from `obs.data` (the pilot's FooterMask does, docs/pilots/e1pilot/e1/operators/o_footer.py).
  `last_raw_response` (309) is what the runner stores as `Step.policy_raw_response` (runner.py:270).

## Bridge (`envharness/bridges/alfworld/bridge.py`) — import (observe-only proxies allowed)

- `reset` 143-215: `options` keys honoured — `split`, `config_path` (149; else `$ALFWORLD_CONFIG`),
  `repetition_threshold`, `obs_style`, `train_subset_path`, `subset_authoritative`, `task_id`
  (pins a gamefile when it matches; the orchestrator's label does not, so `seed` selects the game).
  The engine is built once per instance and split (177-178) — one bridge per config per process.
- `step` 263-339: ✓ **`effective` is set by the bridge per step**: `effective = "nothing happens"
  not in obs_text.lower()` (284), stored on `state.last_action_was_effective` (305) and in
  `info["effective"]` / `info["result"]["effective"]` (324, 329). `step_count` increments BEFORE the
  engine step (275), so an O/T hook sees the post-action count. `terminated=engine_done`,
  `truncated` only from the repetition guard (288-290, 310-312).
- `evaluate` 341-352: `success = state.won`; T-axis termination does not flip `won`.
- `notify_replay_complete` 412-429: rewinds `step_count`, repetition counters only; the engine's own
  step limit keeps counting (docs/pilots/e1pilot/p4/docs/stage_budget_audit.md).
- `_observe` 717-745: wrapped style = `Task: …` + obs + `"Admissible commands: " + ", ".join(...)`
  joined by blank lines; `data` carries `goal_text` and `admissible_commands`.

## Harnesses — import

- `Setup` (`envharness/harnesses/setup.py` 41-133): ✓ **replays before the first observation** —
  `reset` calls `inner.reset`, then `inner.step(a)` for every action, then `notify_replay_complete`,
  then returns `inner.observe()` (77-92). `save_state` → `{"actions": [{"name", "kwargs"}]}` (101-107).
- `Rules` (`envharness/harnesses/rules.py` 77-190): hooks `filter_action(action, env_state) -> Action | Blocked`
  (93), `modify_transition(action, raw_response, env_state) -> EnvResponse` (97), `filter_observation(obs,
  env_state) -> Observation` (102); `reset` applies the O hook to the initial observation (110-121);
  `step` = A → inner.step → T (post-step state) → O (124-155); a `Blocked` returns the current
  observation prefixed `[blocked]` with `data["blocked"]=True` and no env change (128-142). `from_state`
  compiles `rules_code` through `load_rules_subclass` (177-188).
- `code_loader` (`envharness/core/code_loader.py`): namespace = `Rules, Action, Blocked, Observation,
  EnvResponse` (54-66); the code must define a top-level `_Rules(Rules)` (68-107); `load_rules_instance`
  sets `instance.rules_code` (110-117). Exemplars must therefore be self-contained (helpers defined in the
  same string, as the pilot's FNV hash is).

## Orchestrator (`envharness/orchestration/orchestrator.py`) — reference only

- `_rollout_baseline_k` 870-923 and `_rollout_k` 986-1046: K `EpisodeSpec`s with `reset_seed = task_id`
  for every k (variance from policy temperature only), run through a thread pool of
  `rollout_concurrency`, `trace.candidate_id` / `rollout_idx` / `kind="exploration"` stamped on return.
  `estimate` mirrors this dispatch with its own batch schedule.
- Event log `_OrchLog.event(kind, **fields)` 224-254 writes `orchestrator.jsonl` (`ts`, `iso`, `kind`,
  fields); aea's `events.jsonl` keeps the same one-object-per-line shape under the M0 envelope.

## HarnessAgent (`envharness/agents/harness_agent.py`) — wrap (proposals only)

`PROPOSE_TOOL` 124-198 (`propose_candidate(rules_code, in_env_actions, rationale)`),
`_candidate_from_args` 982-1013 (tolerant parsing into `Candidate`), `LLMHarnessAgent.propose` 613-622.
aea calls the released agent only to propose knob shapes; `decide`/`refine` (624-672) are never used
— acceptance is the dose rule.

## LLM client (`envharness/infra/llm.py`) — wrap

`LLMClient.chat(messages, tools, tool_choice, temperature, max_tokens, **kwargs) -> ChatResponse`
(115-123); `Message(role, content, tool_calls, tool_call_id, name)`, `ToolCall`, `ChatResponse(content,
tool_calls, raw)` (20-44). `AeaLLMClient` (M0) implements this ABC over the aea client; the released
`LiteLLMClient` sends no reasoning parameter unless configured (145-232; `model.py:387-422`).

## Storage (`envharness/orchestration/storage.py`) — import

`TraceStore(path)` 44-72: JSONL of `Trace.model_dump_json()`, one per line, cache on load. `io` writes
policy rollouts with `TraceStore.add` so the released induction (`scripts/induce_pair.py`) reads them.

## RL corpus loader (`rl/envharness_rl/alfworld/envs.py`) — round-trip target

`_load_corpus` 119-146: one JSON object per line keyed by `game_file` (relative paths resolved against
`$ALFWORLD_DATA`); per reset the worker reads only `in_env_actions` (186) and `rules_code` (193).
✓ **Unknown keys are ignored** (the record is stored whole, never validated), so the `aea` metadata
block is safe.

## Pilot oracles (docs/pilots) — behaviour ported, never imported

`eobs/eobs/llm.py` (provider guard, ledger; now `aea.llm.client`), `eobs/eobs/settings.py` (secrets,
prices; now `aea.settings`, `configs/pricing.yaml`).
