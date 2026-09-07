# P4 Link audit (Phase A, no rollouts) — envharness @ fab7d574

Question: can a 2-task chain run under the released runner (`envharness/orchestration/runner.py`) without modifying it?

- **Composition**: `envharness/harnesses/link.py:107-128` — `Link(env_a, env_b, carry_context, a_done_via, carry_chars)` is an
  EnvHarness holding env_a in `inner` and env_b in `_env_b`. `a_done_via="terminated"` (link.py:47-53) is the ALFWorld mode:
  stage A ends on `terminated or truncated` (`_a_is_finished`, link.py:483-492), which the bridge sets when the game is won
  or the engine ends the episode (bridge.py: `terminated=engine_done`).
- **Per-part reset**: `Link.reset` (link.py:172-227) resets env_a with `(seed, a_opts)` and stashes `b_opts`/`b_seed`;
  env_b is reset lazily at handoff (`_step_a`, link.py:268-286) with `(b_seed, b_opts)`. Options are routed ONLY when the
  dict carries a reserved key `a`/`b`/`link` (`_split_options`, link.py:227-239); otherwise the whole dict is env_a's and
  env_b resets with `(None, None)` → the bridge would play the shuffled iterator's next game (non-deterministic partner).
  The released runner passes `options={**reset_options, "task_id": spec.task_id}` (runner.py:200): with structured
  `reset_options` the extra top-level "task_id" is ignored, so the partner task is fixed via `link.b_seed` (`p4/chain_env.py`).
- **Goal text at the switch**: B's first observation is `env_b.reset().observation` (bridge `_observe`: "Task: <goal>\n\n<obs>\n\n
  Admissible commands: …") with, when `carry_context=True`, a banner + a tail of A's last observation spliced in front
  (`_splice_handoff`, link.py:494-523; wording mentions "a different repository" — SWE-bench phrasing, generic otherwise).
  Chat history of stage A is kept by the policy (max_history 200).
- **Verdict combination**: `_step_b` caches `b_success` at B's termination and returns `terminated=True` with
  `combined_success = a_success and b_success` (link.py:310-345); `evaluate()` returns `success = a_success and b_success`
  (link.py:363-414). The runner reads `env.evaluate().success` (runner.py:277-284) → chain success requires both parts.
- **Step budget**: the runner loops `for _ in range(spec.max_steps)` and breaks only on `terminated or truncated`
  (runner.py:225-276); Link masks A's termination (`terminated=False`, link.py:257-263), so `max_episode_steps = 50`
  applies to the WHOLE chain, not per part. Under the corpus protocol a Chain-2 must be solved within 50 steps in total.
- **Construction under the runner**: `build_env_stack` instantiates `import_symbol(spec.env.import_path)()` with no arguments
  (runner.py:129-141) — Link cannot be named directly, but a subclass with a no-arg constructor can (`p4/chain_env.py:
  ChainEnv(Link)` builds two AlfworldEnvs; it is our code, not third_party). `_base_env(env)` walks `.inner` to env_a
  (runner.py:157-162), so the policy's tool schema comes from AlfworldEnv (think_action needs exactly one tool).
- **save_state / from_state**: both raise NotImplementedError (link.py:527-546); `run_episode` never calls them (only the
  orchestrator's ACCEPT checkpoint path does), so they are not needed for P4's direct-runner rollouts.
- **Certificate**: concatenated expert witnesses (A's then B's, each from its own reset; ≤ 50 steps in total) replayed
  through ChainEnv; ω = 0 by construction (a single-task success terminates A and leaves B unsolved).

Conclusion: a 2-task chain CAN run under the released runner via `ChainEnv` + structured reset_options. Chain stays in P4.3
(≤ 6 tasks, the six saturated tasks with the shortest L_exp), subject to the 50-step total budget.
