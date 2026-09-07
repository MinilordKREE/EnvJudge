# Review packet — aea Phase B + Phase C (tag `aea-v0.1`)

Spec of record: `docs/spec/AEA_v2.md`. Contracts summary: `docs/reuse/contracts.md`.
Provenance per module: `docs/reuse/phase_b.md`; substrate audits: `docs/reuse/all.md` and the
per-module `docs/reuse/*.md` from Phase A.

## 1. File tree (lines)

```
src/aea/
  __init__.py 3   cli.py 47   errors.py 73   settings.py 73   logs.py 87
  config.py 117   budget.py 118   estimate.py 143   certs.py 330   knobs.py 356
  exemplars/{__init__.py 41, footer_mask.py.txt 28, horizon_squeeze.py.txt 25, displacement.md 8}
  dose.py 141   stage.py 219   probe.py 89   handoff.py 111   policy_skills.py 61
  io.py 121   controller.py 361   substrate.py 152   runner.py 112
  core/{config.py 125, context.py 111, hashing.py 102, io.py 81, manifest.py 123, trace.py 136}
  llm/{attribution.py 71, client.py 281, envharness_client.py 111, fake.py 42, ledger.py 284,
       pricing.py 112, provider.py 21, retry.py 149, types.py 98}
tests/unit/ 12 files (offline, fake ALFWorld bridge stacked with the released Setup/Rules)
tests/integration/ test_alfworld.py (8 tests, real ALFWorld, LLM-free), capture_client.py, conftest.py
tests/fixtures/ fake_world.py, fake_substrate.py, stage8.json, failed_prefixes.json
configs/ pricing.yaml, alfworld_config_100.yaml
```
Source: 4,767 lines under `src/aea`; tests 3,093 lines.

## 2. How to run

```
make setup                 # uv sync --locked, pre-commit
make check                 # ruff, ruff format --check, mypy --strict (src + tests), unit tests
# integration (ALFWorld + TextWorld + game data; LLM-free):
PYTHONPATH=src ALFWORLD_DATA=~/eh_alfworld_data <alfworld-venv>/bin/python -m pytest tests/integration -m integration -o addopts=""
```
The `alfworld` extra (`make setup-alfworld`) installs ALFWorld/TextWorld into the uv environment;
the checks above were run with the pilot venv that already has them.

## 3. Verification results (2026-09-07)

| check | result |
|---|---|
| `ruff check .` / `ruff format --check .` | clean |
| `mypy --strict` (src + tests, 62 files) | clean |
| unit tests (offline, no keys) | 85 passed |
| integration (real ALFWorld, LLM-free, pilot venv) | 8 passed, 1 skipped (RL loader round-trip needs `ray`) — 13.5 min |

Integration coverage: C.1 config-100 route 12 vs 62 policy steps after the archived 38-action task-8
prefix; compiled-prefix replay reproduces the archived observation at the cut on three P1 failed
trajectories (tasks 9, 14, 20). C.2 FooterMask at d = 1: the final prompts the released
`PolicyAgent` sent contain no admissible-commands text; the d = 0.5 masked set computed in a separate
process equals the in-process set and is nested in d = 1. C.3 HorizonSqueeze on task 1: the expert's
plan of length m succeeds at exactly step m; one `look` earlier the episode ends `truncated=True`,
`terminated=False`, not won. C.4 saturated path with the expert as policy: estimate → dose search
events → traces readable by the released induction helpers. C.5 zero path with a prefix-then-random
policy: certified compiled Setups on the 100-config, probe profile, `unresolved` + handoff trace.
C.6 budget invariants: traces written = rollouts charged = substrate calls, no task above 30 on
`search`, accounting per task matches, no `confirm` rows.

## 4. Spec sections covered

| section | where |
|---|---|
| §0 budgets | `budget.py`, `controller._charged_rollouts`, `llm/ledger.py` (`rollout` rows by budget), `runner.py` |
| §1 bands | `config.py` (`accept_successes`, `learnable_successes`) |
| §2 estimation | `estimate.py` (exact incomplete beta; batches 4,2,2…; extremes stop at 10 by the rule) |
| §3 knobs | `knobs.py`, `exemplars/` (single-source templates), proposer validation, `propose_knobs` tool |
| §4 dose rule | `dose.py` |
| §5 stage / probe | `stage.py`, `probe.py`, `configs/alfworld_config_100.yaml` |
| §6 certificates | `certs.py` (ladder, stack-level done, ω) |
| §7 handoff | `handoff.py` (AEA+Handoff arm only) |
| §8 policy skills | `policy_skills.py` (released retrieval + memory block; `task_prompt` injection) |
| §9 controller | `controller.py`, `io.py` (corpus entries band/knob/stage with the `aea` block), `substrate.py` |
| §10 confirm | not in this prompt (script lands with E1-SL); the controller never writes K16 back |
| §12 verification | unit + integration tests listed in section 6 |

## 5. Known gaps (numbered)

1. `Displacement`'s ALFWorld builder (expert-discovered targets, validated action lists) is not
   ported; the knob is wired through `KnobContext.setup_builder` and reports infeasible without one.
2. The RL corpus-loader round-trip test needs `ray`/`gymnasium` (skipped here); the loader's parsing
   contract is asserted directly in the unit test.
3. `substrate.py` (the LLM-backed production substrate) is exercised only by construction and type
   checks; its first live use is the paid smoke (Phase D).
4. The released eval's accounting callback (owner decision: in-process litellm success callback,
   provider pin through `completion_kwargs`) is not written yet; it belongs to the E1-SL phase.
5. Probes are budget-limited rather than `budget_cap_hit` (see `phase_b.md`, deviations).
6. The proposer's LLM-free smoke exercises the three hooks once on a minimal fake inner env; it
   cannot prove nestedness of an arbitrary proposal (declared by the designer, tested only for the
   exemplars).

## 6. Items needing an owner decision (numbered)

1. Whether `unresolved` with `budget_limited: true` (probes cut by the remaining budget) is the
   intended status, or whether the task should be `budget_cap_hit`.
2. Whether hint rollouts (R_hint) should carry the expert plan in the task prompt (current: a
   one-line preamble with the action sequence) or as an in-observation hint.
3. `rollout` ledger rows carry no tokens (cost is on the per-call rows written in the worker); merge
   by `rollout_uid` is left to the analysis scripts — acceptable, or should the substrate sum them?

## 7. Deviations found by the integration run (fixed before tagging)

- Stage candidates are now taken at fractions of the trajectory length T (spec §5), compiled and
  certified individually; the pilot's per-prefix certificate sweep (every t, expert ×3) is not used
  by the controller — it took the pilot an hour per 8 tasks and is not what §5 specifies.
- The fidelity check keeps the synthetic trailing `look` only when the archived prefix itself ended
  with `look`.
