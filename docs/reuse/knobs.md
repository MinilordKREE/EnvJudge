# Audit: `knobs` + `exemplars` (dose contract, hand library, proposer validation)

Contract: `Knob(make(d) → rules_code | in_env_actions, axis, direction, nested)`; exemplars are the
single source of truth for prompt text and runnable classes; FooterMask buckets by
`sha256(f"{task_id}:{step}")` (nested by construction); HorizonSqueeze checks `raw.success` before
truncating and returns `truncated=True`; Displacement as piloted; proposer output validated (loads via
`code_loader`, references `DOSE`, LLM-free smoke at d=1, certificate at d=1 unless O-axis).

## Reference

| what | where | reuse |
|---|---|---|
| Hook signatures and the `Blocked` / `Observation` / `EnvResponse` constructors available inside rules code | `rules.py:93-104`, `code_loader.py:54-66` | import (the namespace is fixed: exemplars use only `Rules, Action, Blocked, Observation, EnvResponse`) |
| `_Rules` requirement, compile/exec errors as `RulesCodeError` | `code_loader.py:68-107` | import (validation step 1) |
| `Rules.step` ordering A → inner.step → T(post-step state) → O, blocked handling | `rules.py:124-155` | invariant |
| `env_state.step_count` = post-action count during T/O hooks; `env_state.won` | `bridge.py:275, 300-305` | invariant for HorizonSqueeze and FooterMask step indexing |
| Policy normalises against `obs.data["admissible_commands"]` and its reminder line reads the same key | `policy.py:186-189, 370-395` | invariant: FooterMask drops the key from `obs.data` too |
| Designer proposals: `PROPOSE_TOOL` schema, `_candidate_from_args`, `LLMHarnessAgent.propose` | `harness_agent.py:124-198, 982-1013, 613-622` | wrap (proposer only; never `decide`) |
| Pilot FooterMask (FNV-1a bucket over `f"{task_id}:{s}"`, footer cut at `"\n\nAdmissible commands: "`, key dropped) | `docs/pilots/e1pilot/e1/operators/o_footer.py` | rewrite with sha256 buckets (contract); the footer string matches `bridge.py:733` |
| Pilot HorizonSqueeze (T hook: `terminated=True` when `step_count ≥ m and not won and not raw.terminated`) | `docs/pilots/e1pilot/e1/operators/h_horizon.py` | rewrite: check `raw_response.info["success"]`/`env_state.won` first and return `truncated=True` (contract) — the runner breaks on either flag (`runner.py:280`) and `evaluate()` still reads `won` (`bridge.py:341-352`) |
| Pilot Displacement (expert-discovered targets, seeded destinations, validated action lists ending with `look`) | `docs/pilots/e1pilot/e1/operators/s0_displace.py` | port as piloted (Setup action list; LLM-free) |
| ALFWorld expert plan exposed as `infos["extra.expert_plan"]` (train split only) | `alfworld/agents/environment/alfred_tw_env.py:263-267` (site-packages) | observe-only proxy (`certs`) |
| TextWorld `Limit` counts the replayed prefix | `docs/pilots/e1pilot/p4/docs/stage_budget_audit.md` | invariant (stage budget) |

## Invariants relied on

- Rules code runs inside `exec` with a fixed namespace (✓ `code_loader.py:54-66, 85`); helpers must be
  defined inside the same string. Exemplars are rendered from one template per knob with `DOSE` substituted.
- `Blocked` leaves the env unchanged and returns the current observation (✓ `rules.py:128-142`).
- `Observation` allows extra fields (`extra="allow"`, `types.py:60-63`) but `Action`, `EnvResponse` do not.

## Decisions

- `nested=True` means the affected step set at dose d is a subset of the set at any d′ > d for the same
  task (bucket rule); Displacement is nested by construction of its k-levels; HorizonSqueeze is nested
  in m. Proposer knobs declare `nested` and are tested for it at d ∈ {0.5, 1} in the LLM-free smoke.
