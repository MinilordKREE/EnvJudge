# aea v0.2 review packet (Phase C)

Method of record: `docs/spec/AEA_v0.2.md`. What changed and why: `docs/changelog_v0.2.md`. Module map:
`docs/reuse/v0_2.md`.

## The box, line by line, and where it lives

| box line | code | test |
|---|---|---|
| `p ← estimate(policy, E)`, ≤ 16, stop at P(regime) ≥ 0.9 | `estimate.py` (`config.k`, `impl.batch_*`, `impl.confidence`) | `test_estimate.py` |
| `if p in B_L: keep E` | `controller._run_task` → `kept` | `test_controller.py::test_kept_or_accepted_on_a_coin_policy` |
| families ordered by measured leverage | `families.LeverageTable.order` | `test_families.py::test_leverage_table_orders_and_starts_the_bracket` |
| `if not solvable(w(1)): continue` | `witness.solvable` (policy replay → oracle → uncertified / self-certify; O axis by construction) | `test_witness.py` (3 cases) |
| `r ← evaluate(w(1))` (4 → 8) | `evaluate.evaluate` / `verdict` | `test_evaluate_bracket.py::test_verdict_matches_the_box`, `::test_evaluate_tops_up_unless_extreme` (1/4 not accepted) |
| `no_effect → leverage 0` | `controller._try_family` → `no_leverage` event | `test_controller.py::test_expert_policy_is_dropped_for_no_leverage` (10 + 4 + 4) |
| bracket ≤ 4 bisections, order-violation stop | `bracket.bracket` / `order_violated` | `::test_bracket_bisects_and_accepts`, `::test_order_violation_stops_the_family`, `::test_cap_arithmetic_10_4_8_8` |
| prior seeds the first bisection point (d = 1 always tested) | `LeverageTable.start_dose` + `bracket(start=)` | `::test_bracket_prior_start_and_clipping`, `test_families.py` |
| candidate states: end + midpoint × 3, ≤ 6, latest first | `stage.candidate_states` / `build_stage_candidates` | `test_stage.py` |
| `solvable(Stage(E, s))` with the oracle only | `stage.build_stage_candidates(oracle=)` → `witness.solvable(policy_success=None)` | `test_stage.py`, `test_witness.py::test_no_oracle_self_certifies_after_a_failed_replay` |
| `evaluate(Stage(E, s))`, budget re-based | `controller._stage` (probe phase; 100-step config via `substrate.stage_reset_options`) | integration `test_config100_route_gives_12_vs_62_policy_steps`, `test_zero_path_with_prefix_then_random_policy` |
| every policy rollout counts against the cap; replays / oracle do not | `budget.Budget`, `controller._rollouts`; `session.py` never charges | `test_config_budget.py`, integration `test_budget_invariants_hold` |
| three outcomes + reason | `controller.TaskOutcome` | `test_controller.py` (kept / accepted / dropped(reason)); resume re-runs `infra_error` |

## Integration (real ALFWorld, LLM-free)

`tests/integration/test_alfworld.py` (v0.2): 100-step route (12 vs 62 policy steps), compiled-prefix fidelity
on 3 archived failures, footer-mask prompt snapshot (no admissible footer reaches the model) and nesting across
processes, horizon-squeeze boundary (truncated exactly past m), expert-as-policy harden path, prefix-then-random
stage path (guarded candidates, ≤ 6, unique), RL corpus loader round-trip, budget invariant (traces = charged =
accounting), eval hook on one released episode. Results (2026-09-11): 9 passed, 1 skipped (RL loader needs `ray`), 0 failed; unit suite 88 green.

## Do-not list (unchanged)

No edits under `third_party/`; released APIs only; every LLM call ledgered with provider pin and price guard;
no key in YAML or LOG; corpus/trace formats unchanged for envharness; the 100-step config for staged sessions.
