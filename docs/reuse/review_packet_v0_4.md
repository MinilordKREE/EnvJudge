# aea v0.4 review packet

Method of record: `docs/spec/AEA_v0.4.md` (v0.2 + soft warm start). What changed and why:
`docs/changelog_v0.4.md`. Everything not listed below is as in `docs/reuse/review_packet_v0_2.md`; the v0.3
packet (`review_packet_v0_3.md`) describes withdrawn code.

## The one change, line by line

| box line | code | test |
|---|---|---|
| `lo, hi ← 0, 1` for every task, whatever the history | `bracket.bracket` (v0.2 code: `start` is the first probe only, the interval starts at [0, 1]) | `test_evaluate_bracket.py::test_warm_start_is_only_the_first_probe_local_interval_stays_0_1` (Test E: the dose after the warm probe is `(start + 1) / 2` or `start / 2`) |
| `d ← median(frontiers[w])` if ≥ 3 exist, else 0.5 | `families.LeverageTable.warm_start(family, min_history)`; `config.ImplConfig.warm_start_min_history` = 3 | `test_families.py::test_leverage_table_orders_and_warm_starts` (Tests A, B, D), `::test_no_history_reduces_to_v02_midpoint` |
| a wrong warm start costs one probe | `bracket.bracket` (midpoint of the task-local interval after the first probe) | `::test_wrong_warm_start_costs_one_probe_and_recovers` (Test C) |
| record w's frontier: the accepted dose, else `(lo + hi) / 2` of the final local interval, accepted / exhausted / censored alike | `controller._try_family` → `_record_frontier` → `leverage` event `{family, frontier, lo, hi}`; `families.record_frontier` | `test_leverage_persist.py` (rebuilt on resume from completed tasks only; v0.2 `accepted_dose` and v0.3 `dose` events ignored) |
| v0.2 evaluate and stage unchanged | `evaluate.py`, `stage.py` restored byte-for-byte from the E3 code state (08a09b7) | `test_evaluate_bracket.py::test_evaluate_tops_up_unless_extreme`, `test_stage.py` (v0.2 tests) |

## Method complexity guard

1 new state variable (`frontiers` per family), 1 new hyperparameter (`warm_start_min_history`, replacing two),
1 new decision (median or midpoint) plus the accepted-dose-else-midpoint choice of the recorded frontier; 4
files, +65 / −50 lines against v0.2; 32 lines shorter than v0.3. No new module, LLM call, rollout type,
certificate type, threshold or regime boundary. Saturated-side pseudocode in 15 lines in the spec.

## Verification

Unit suite 99 green; ruff and mypy --strict clean; LLM-free integration suite on the real ALFWorld bridge
(see the changelog for the run). Offline replay: `experiments/alfworld_e5/replay_dose_search.md` (v0.4 censors
no task on the E3 evidence; v0.3 censors task 15).

## Do-not list (unchanged)

No edits under `third_party/`; released APIs only; every LLM call ledgered with provider pin and price guard; no
key in YAML or LOG; corpus/trace formats unchanged for envharness; the 100-step config for staged sessions.
