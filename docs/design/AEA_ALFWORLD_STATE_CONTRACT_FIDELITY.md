# ALFWorld Rules state contract fidelity

Date: 2026-09-15. This inventory was written before the implementation change.
Scope: Step 1, structural-validator correctness only. No paid calls or LOW rerun.

## Baseline and evidence

- Research worktree: `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`.
- Starting commit: `5f959a4cd4002fd13aa3391e7f788829e4015dca`; research status clean.
- Main remains at `f97260589475bf4412f2310b1dfbcc1c34816547`; its pre-existing
  status is ` ? third_party/envharness`. This task does not modify that worktree.
- Read the [failed smoke report](../../experiments/alfworld_e6/results/e6_iterative_low_semantic_smoke.md),
  its `validator_state_reproduction.json` and `.py.txt` artifacts, and the exact
  archived task 126 D2, task 129 C1 and task 129 I2 source bytes before editing.
  The historical `IMPLEMENTATION_FAILURE` result remains unchanged and provides
  no efficacy evidence.
- Contract: `ENVIRONMENT_SURFACE` in `src/aea/designer.py`.
- Actual state: `AlfworldEnvState` and reset/step/schema methods in
  `third_party/envharness/envharness/bridges/alfworld/bridge.py`.
- Old validator: `_SmokeInner._State` in `src/aea/families.py`; also used by
  `identity_at_zero` in `src/aea/designer.py`.

## Complete field inventory before correction

“Advertised” below means the designer's explicit `env_state` paragraph.
The bridge's separate `env_state_schema` exposes all 13 real fields. “Old” means
the structural smoke state at the starting commit. Use counts are unique exact
generated source hashes in the inspected corpus, including rendered variants;
they are not counts of independent candidates.

| Field | Advertised to designer? | Real state? | Old validation state? | Used by generated Rules? | Type, default and real semantics |
| --- | --- | --- | --- | --- | --- |
| `goal_text` | Yes | Yes | **Missing** | Yes, 3 sources; includes 129 C1/I2 | `str`, `""`; goal extracted at reset and retained for the episode. |
| `obs_text` | Yes | Yes | Yes | Yes, 1 source | `str`, `""`; latest raw observation, replaced at reset and after a world step. Old smoke uses `"You see a room."`. |
| `admissible_commands` | Yes | Yes | Yes, shared class list | Yes, 2 sources | `list[str]`, fresh empty list; current engine commands, refreshed at reset/step and exposed through the observation. Old smoke uses `look`, `go to a`. |
| `won` | Yes | Yes | Yes | Yes, 5 sources | `bool`, `False`; current engine success flag, distinct from ending the episode. |
| `done` | Yes | Yes | **Missing** | None found | `bool`, `False`; engine termination OR bridge repetition truncation. |
| `step_count` | Yes | Yes | Yes | Yes, 67 sources | `int`, `0`; reset is 0, incremented before a nonempty valid `do` reaches the engine. Old smoke uses a fixed post-step value 1. |
| `last_action_was_effective` | Yes | Yes | **Missing** | Yes, 3 sources; includes 126 D2 | `bool`, `True`; reset True, then False iff the new observation contains `nothing happens` case-insensitively. This is the bridge heuristic, not privileged world knowledge. |
| `extras` | Yes | Yes | Yes, shared class dict | Yes, 20 sources | `dict[str, Any]`, fresh empty dict; Rules-owned episode storage. Bridge never reads it. |
| `inventory` | No; bridge schema only | Yes | Missing | None found | `list[str]`, fresh empty list. This bridge does not populate it from engine inventory; do not imply that it tracks carried objects. |
| `score` | No; bridge schema only | Yes | Missing | None found | `float`, `0.0`; reset 0, then engine score. |
| `max_score` | No; bridge schema only | Yes | Missing | None found | `float`, `1.0`; reset from engine info or 1, updated from engine info when provided. |
| `repetition_count` | No; bridge schema only | Yes | Missing | Yes, 2 sources | `int`, `1`; count of consecutive identical raw observations; resets to 1 when text changes. |
| `last_obs_for_repeat` | No; bridge schema only | Yes | Missing | None found | `str`, `""`; reset raw observation, then most recent distinct raw text used by repetition detection. |

All 8 designer-advertised fields are real. The old state supplies only 5 of 8,
and 5 of the 13 bridge-schema fields. In addition to the two observed missing
fields, `done` is a latent instance of the same defect. Shared class containers
also violate independent-episode storage semantics.

### Generated-source audit scope

The read-only scan searched structured `rules_code`/`template`/`source` values
and standalone Rules code under `runs/` and `experiments/`, excluding explicitly
authored oracle actuators. It inspected 75 matching files, 155 distinct exact
source hashes (93 templates), with no JSON or source parse errors. AST inspection
recognizes hook state parameters, simple aliases, attribute access and constant
`getattr`/`hasattr`/`setattr`. Dynamic field names and interprocedural alias flows
are outside this inventory's usage analysis. “None found” has that limited scope.

Other observed names, `location` and `reward_delay_pending`, are absent from both
the advertised and real schemas. Their generated uses supplied explicit
`getattr` defaults. This does not authorize adding them to the validator or
silently supplying arbitrary unknown attributes.

## Root cause and selected correction

The structural smoke duplicated an unrelated five-field schema instead of using
the ALFWorld state that the designer was instructed to program against. Therefore
ordinary access to an allowed field raised `AttributeError` before privilege
screening and incorrectly selected structural `REPAIR_CODE` feedback.

Use the actual `AlfworldEnvState` dataclass directly in `_SmokeInner`. Retain the
existing synthetic room, command list and `step_count=1`; other fields use the
canonical defaults. This is a fixed post-step structural fixture, not an engine
reset or a simulated trajectory. Preserve the existing observation and response
behavior. Both structural validation and d=0 identity already use this factory.

This is smaller than adding an adapter/protocol or a copied factory schema:
field additions, types and default factories come from the real bridge class.
Each instance receives its own containers. Unknown attributes still raise
`AttributeError`. A separate conformance test will parse the actual designer
contract and compare it with both the canonical state and bridge schema, so an
advertised field without real support fails permanently.

Importing this dataclass does not initialize ALFWorld. A fresh-process import
audit blocked `alfworld`, `textworld`, `gym`, `gymnasium`, `torch` and `ray`; none
was imported. The bridge loads the optional simulator lazily at environment
initialization. No new dependency or simulator initialization is needed here.

## Planned regression boundaries

- Contract-derived field coverage, canonical types/defaults and independent
  mutable containers; an unsupported future advertised field must fail the test.
- Hooks reading `goal_text`, `done`, and both boolean values of
  `last_action_was_effective`; d=0 identity for the same valid sources.
- An actually nonexistent field still fails structural validation.
- Replay the three exact archived candidates, with SHA-256 assertions. Only
  their false missing-field structural failures are expected to disappear;
  privilege acceptance is not implied.
- Verify structural → lexical → semantic → solvability → policy ordering using
  offline fixtures and retain fail-closed semantic rejection.
- Preserve designer prompts, optimizer, all privilege rules, reference inputs,
  D/I isolation, budgets, acceptance and historical smoke artifacts byte-for-byte.
- If downstream replay confirms a separate semantic-screen bug, document it and
  stop without repairing that component or starting an efficacy run.
