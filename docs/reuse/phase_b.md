# Phase B provenance — what each module imports, wraps, or rewrote

| module | lines | imports (envharness) | wraps | rewritten from (pilot oracle) | spec |
|---|---|---|---|---|---|
| `aea/config.py` | 117 | `StrictModel` (aea core) | — | — | §0–§6 parameters |
| `aea/budget.py` | 118 | — | — | pilot watchdog/ledger caps (docs/pilots/e1pilot/e1/watchdog.py) as a pattern | §0 |
| `aea/estimate.py` | 143 | `Trace` | dispatch pattern of `orchestrator.py:986-1046` (caller supplies rollouts) | `e1/regime_map.py` (fixed K=16 → sequential Beta) | §2 |
| `aea/certs.py` | 330 | `Action`, `Candidate`, `Setup`, `load_rules_instance`, `AlfworldEnv` (lazy) | bridge `_env` through an observe-only `RecordingProxy` | `eobs/eobs/replay.py` (Session, replay_actions, run_expert, bridge cache), `e1/p2_run.py:certificate`, `p4/p4/omega.py` | §6 |
| `aea/knobs.py` + `aea/exemplars/` | 356 + 3 templates | `RulesCodeError`, `load_rules_subclass`, `Action`, `Candidate`, `EnvResponse`, `Observation` | the released `propose_candidate` tool shape (`harness_agent.py:124-198`) as `propose_knobs` | `e1/operators/{o_footer,h_horizon,s0_displace}.py` (FNV → sha256 buckets; terminated → truncated with the success check first) | §3 |
| `aea/dose.py` | 141 | `Trace` | — | `e1/controller.py` (classify), `e1/lam_search.py` (search), `e1/p2b_run.py:run_dose` | §4 |
| `aea/stage.py` | 215 | `Action`, `Candidate`, `Trace` | `Setup` via `certs.open_session` (the runner's stack order) | `p5/p5/chs100.py` (staged_actions, select_candidates), `eobs/eobs/recover.py:c_at` | §5 |
| `aea/probe.py` | 89 | `Trace` | — | `p5/p5/chs100.py:probe` (walk → all-candidates → latest-first with early stop) | §5 |
| `aea/handoff.py` | 111 | `Action`, `Candidate`, `Observation`, `Step`, `Trace` | the trace shape `induce.py:162-201` reads | `p5/p5/induce_ss.py` (success-only input) | §7 |
| `aea/policy_skills.py` | 60 | `build_memory_block`, `extract_task` (`envharness/prompts/alfworld_skill_prompt.py`), `Bank` | `PolicySpec.task_prompt` injection (no released hook) | `e1/p3a.py` (eval-side retrieval settings) | §8 |
| `aea/io.py` | 121 | `Action`, `Candidate`, `Trace`, `TraceStore` | RL corpus loader shape (`rl/envharness_rl/alfworld/envs.py:119-146`) | `eobs/eobs/hooks.py` (accounting extraction pattern) | §9 |
| `aea/controller.py` | 360 | `Candidate`, `Trace` | everything above through the `Substrate` protocol | `e1/controller.py`, `p4/p4/nsat.py`, `p5/p5/chs100.py` (the three pilot loops, unified) | §9 |
| `aea/substrate.py` | 150 | `PolicySpec`, `EnvSpec` (via `aea.runner`), `SubprocessRunner` | `scripts/run_harness.py:173-236` spec construction; `AeaLLMClient` as `client_factory` | `e1/p2_run.py:Runner`, `p4/p4/nsat.py:Runner` | §9 |
| `aea/runner.py` | 112 | `EnvSpec`, `EpisodeSpec`, `PolicySpec`, `SubprocessRunner`, `Candidate`, `Trace` | `SubprocessRunner._child_env` (attribution export) | — | §0 |

Invariants verified in unit tests with the offline `FakeBridge` (a real `ActionableEnv` stacked with the
released `Setup` and `Rules` classes, `tests/fixtures/fake_world.py`): stack-level truncation is seen
by `Session.done`; a `Blocked` action leaves the world unchanged; `Setup` replays before the first
observation; FooterMask removes both the footer text and `data["admissible_commands"]`;
HorizonSqueeze returns `truncated=True` one step late and leaves a success at step m untouched.

Deviations from the contracts noted for review:
- Probes are limited to the candidates the remaining `search` budget can afford (spec §5: probes
  ≤ 5 × 4 within the cap); skipped candidates are recorded (`probe_skipped_budget`), the task ends
  `unresolved` with `budget_limited: true` rather than `budget_cap_hit`. Dose search past the cap is
  `budget_cap_hit` as specified.
- The band success counts are explicit config fields (`accept_successes = (3, 5)`,
  `learnable_successes = (4, 12)`) because rounding `band_t × K` does not give 3–5/8.
- Non-monotone dose responses are counted as pairs whose success rate rises with the dose.
- `Displacement`'s ALFWorld builder (expert-discovered targets) is not ported yet; the knob is
  wired (`KnobContext.setup_builder`) and reports infeasible when no builder is supplied.
