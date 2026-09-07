# Audit: `certs` (witness ladder R_pol → R_exp ×3 → R_hint ≤3)

Contract: ladder R_pol → R_exp(×3) → R_hint(≤3, charged to `search`); the replay `Session.done` reads
stack-level `terminated`/`truncated`.

## Reference

| what | where | reuse |
|---|---|---|
| Replay session over the released stack (`build_env_stack` order), bridge reused per process and per `config_path` | `docs/pilots/eobs/eobs/replay.py:133-160` (`_base_bridge`, `open_session`), `runner.py:129-142` | port |
| `Session.done` = bridge `state.done` OR stack-level `terminated`/`truncated` (the P4 fix: a T-axis termination is invisible to the bridge) | `docs/pilots/eobs/eobs/replay.py:84-120` (`Session.ended`, `step_text`), `docs/pilots/e1pilot/LOG.md` BUG entry 23:40 UTC | port with a unit test (fake stack that truncates) |
| `replay_actions` (verbatim, stop at win/done, `env_error`) and `run_expert` (closed-loop handcoded expert from `infos["extra.expert_plan"]`, classes `expert_stuck` / `expert_timeout` / `expert_error` / `blocked` / `verifier_fail`) | `docs/pilots/eobs/eobs/replay.py:167-228` | port |
| Observe-only proxy around the bridge's engine (`_env`) to read `infos` beneath the bridge | `docs/pilots/eobs/eobs/replay.py:38-64` (`RecordingProxy`); permitted by the do-not list ("proxies that only observe") | port; documented here |
| Certificate ladder as used in the pilots (R_pol → R_exp ×3 → uncertified; hint only when SR_c = 0 or R_old failed) | `docs/pilots/e1pilot/e1/p2_run.py:77-105`, `docs/pilots/eobs/eobs/certs.py` (`certified`, `needs_hint`) | port; R_hint = ≤3 policy rollouts with the expert plan as a hint, charged to `search` (contract) |
| ω (witness survival: policy successes replayed verbatim) | `docs/pilots/e1pilot/p4/p4/omega.py` | port as `witness_survival` (used by the controller's report, not for acceptance) |
| Expert length from reset (shortest of 3) | `docs/pilots/e1pilot/e1/p2b_run.py:30-40` | port (handoff uses the same call) |

## Invariants relied on

- ✓ `Rules.evaluate` / `Setup.evaluate` delegate to the base env, so `stack.evaluate().success` is the
  bridge's `won` (rules.py:158, setup.py:98, bridge.py:341-352).
- ✓ `extra.expert_plan` exists only on the train split with `expert_type` configured
  (`alfred_tw_env.py:263-267`); the expert is stochastic (pilot: 3 attempts).
- The `_env` attribute is a private bridge member: the proxy reads it and never writes (M0 do-not list).

## Decisions

- R_pol witnesses are the policy's own successful rollouts recorded during estimation (verbatim
  action lists); none exist for zero tasks, so staged envs go straight to R_exp.
