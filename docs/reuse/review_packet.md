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
make setup-alfworld        # ALFWorld/TextWorld extra into the uv environment (Phase 0a)
ALFWORLD_DATA=~/eh_alfworld_data make test-integration   # LLM-free, real bridge
```

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

## 6. Owner decisions (2026-09-07 review) and how they were applied

1. Probes cut by the remaining budget end the task as `unresolved_budget_limited` (own status,
   counted separately in the main table); `budget_cap_hit` is the hard stop mid-search. Hand-off
   fires only on an exhaustive `unresolved`.
2. R_hint rollouts carry the expert plan in the task-prompt preamble; their traces are marked
   (`candidate_id = "hint"`, iteration id `hint:*`) and `aea.io.training_traces` excludes them from
   induction and bank building (asserted in tests).
3. `rollout` rows carry no tokens; `aea.llm.ledger.per_task_totals` merges rollout counts with the
   per-call cost rows per task (asserted in tests).

## 7. Review fixes applied before Phase D

- Dose direction: LOW (1-2/8) lowers, HIGH (6-7/8) raises; the leverage test is not a search
  evaluation, so the sequence from a 0/4 leverage is 0.5 -> 0.75 -> 0.875 -> 0.9375 and the P2b
  footer curve is reachable within the 30 cap (10 + 4 + 4 + 4 + 8) — tested.
- A family that ends `exhausted` no longer ends the task; the loop moves to the next family.
- Errored rollouts are refunded to the search budget and counted as `infra_errors` in accounting.

## 7. Deviations found by the integration run (fixed before tagging)

- Stage candidates are now taken at fractions of the trajectory length T (spec §5), compiled and
  certified individually; the pilot's per-prefix certificate sweep (every t, expert ×3) is not used
  by the controller — it took the pilot an hour per 8 tasks and is not what §5 specifies.
- The fidelity check keeps the synthetic trailing `look` only when the archived prefix itself ended
  with `look`.

## 8. Phase D paid smoke (2026-09-07; runs/smoke-20260907, runs/smoke2-designer-20260907)

Qwen3-8B via OpenRouter (Alibaba, reasoning off) as policy, DeepSeek V4 Pro (thinking off) as
designer, executed with the pilot venv before the uv ALFWorld extra existed (Phase 0a added it). Total spend USD 1.36.

| task (pilot regime) | outcome | rollouts | USD |
|---|---|---|---|
| 6 (band, p16 0.5) | `band` after 8 rollouts (p_hat 0.5); corpus entry unchanged env | 8 | 0.30 |
| 1 (saturated) | `accepted_knob`: footer_mask 1.0 ZERO -> 0.5 NOEFFECT -> 0.75 NOEFFECT -> 0.875 3/8 IN_BAND, exactly at the 30 cap (the P2b curve, live) | 30 | 0.35 |
| 9 (zero) | `accepted_stage`: 6 compiled Setups certified on the 100-config, fidelity ok, latest state t = 50 learnable 3/4; one candidate skipped for budget | 14 | 0.50 |
| 7 (saturated, second run) | `budget_cap_hit`: footer_mask exhausted (cliff above 0.9375), loop moved to horizon_squeeze, the cap stopped it | 30 | 0.19 |

Ledger: every priced row provider Alibaba; rollout rows by budget `search` only; per-task totals
merge (`per_task_totals`) consistent with the accounting table.

Live bugs found and fixed: (1) the designer request carried no thinking flag, so DeepSeek answered
400 "thinking mode does not support this tool_choice" — the config's `thinking` now applies to
every request (cb97026); (2) the designer re-emitted the exemplars verbatim (one with an unfilled
`__M__`), which validation now rejects as duplicates, the contract asks for new families only, and
raw designer calls are recorded (213793e); (3) corpus `game_file` was absolute, now relative to
`$ALFWORLD_DATA`.

Confirmed after the fix (three direct designer calls, USD 0.006): DeepSeek V4 Pro proposed two
validated new families for a pick_and_place task — `observation_whitespace_noise` (O axis, nested)
and `action_list_shuffle` (declared A; permutes the footer order) — both loading through the
released `code_loader`, referencing `DOSE`, and passing the d = 1 smoke; no exemplar copies.
