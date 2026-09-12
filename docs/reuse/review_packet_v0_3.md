# aea v0.3 review packet

Method of record: `docs/spec/AEA_v0.3.md`. What changed and why: `docs/changelog_v0.3.md` (evidence rows of
`experiments/alfworld_e3/results/e3_layer1.md`). Module map: `docs/reuse/v0_3.md`. Everything not listed below is
as in `docs/reuse/review_packet_v0_2.md`.

## The three edits, line by line

| box line | code | test |
|---|---|---|
| bracket `[lo, hi] = [lo_pop(w), hi_pop(w)]`, default `[0, 1]`, first bisection at the midpoint | `families.LeverageTable.record_dose` / `bracket_seed`; `bracket.bracket(lo=, hi=)`; `controller._try_family` (seed read, doses recorded after the bracket) | `test_evaluate_bracket.py::test_population_seed_reaches_a_late_band_within_the_cap` (accepted at 22 from [0.875, 1]; budget at 30 from [0, 1]), `::test_bracket_population_seed_sets_the_first_bisection`, `test_families.py::test_leverage_table_orders_and_seeds_the_bracket` |
| the d = 1 leverage test still runs first and may lower `hi` to 1 | `controller._try_family` (`evaluate_at(1.0)` before the bracket), `bracket.bracket` (`hi = min(hi, 1.0)` on `too_hard`) | `test_controller.py::test_expert_policy_is_dropped_for_no_leverage` (10 + 4 + 4 unchanged), `test_evaluate_bracket.py::test_cap_arithmetic_10_4_8_8` |
| every dose seen updates the population; persisted as events, rebuilt on resume | `controller._record_dose` → `leverage` events; `controller._restore_leverage` (completed tasks only; v0.2 `accepted_dose` ignored) | `test_leverage_persist.py` (table and corpus bytes equal the uninterrupted run; interrupted attempts discarded; `lo_pop` / `hi_pop` rebuilt) |
| a 4/4 staged state is topped up; verdict from the 8 | `evaluate.evaluate(top_up_full=True)`; `controller._stage` | `test_evaluate_bracket.py::test_evaluate_tops_up_a_full_first_batch_on_the_stage_side`, `test_controller.py::test_staged_full_first_batch_tops_up_to_eight` (5/8 accepted, 7/8 dropped) |
| harden-side 4/4 unchanged (`no_effect` / `too_easy` at 4) | `evaluate.evaluate` default | same tests (harden branch), `test_evaluate_bracket.py::test_evaluate_tops_up_unless_extreme` |
| candidate states end, mid, quarter; dedupe by state hash; cap 6 by priority end > mid > quarter; latest first | `stage.candidate_states`, `stage.cap_by_priority`, `stage.build_stage_candidates` | `test_stage.py::test_candidate_states_end_mid_quarter_and_priority_cap`, `::test_build_stage_candidates_dedupes_and_guards` (identical looping rollouts → end, mid, quarter) |
| six constants unchanged; `impl` loses the prior constants; schema 3 | `config.AEAConfig` (`schema_version` 3), `config.ImplConfig` | `test_config_budget.py` |

## Unchanged and re-verified

Task pool byte-identical to sequential (`test_task_pool.py`), one session lock, budget invariants, corpus and
trace formats, the eval hook, the guard. Unit suite 100 green; ruff and mypy --strict clean; LLM-free integration
suite on the real ALFWorld bridge green (9 passed, 1 skipped needing `ray`).

## Do-not list (unchanged)

No edits under `third_party/`; released APIs only; every LLM call ledgered with provider pin and price guard; no key
in YAML or LOG; corpus/trace formats unchanged for envharness; the 100-step config for staged sessions.
