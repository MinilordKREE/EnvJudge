# aea v0.3 — changelog (2026-09-12)

Method of record: `docs/spec/AEA_v0.3.md` (the v0.2 box with three edits). Evidence: the rows of
`experiments/alfworld_e3/results/e3_layer1.md` quoted below (E3 layer 1, PREREG9, arm A = aea v0.2 on seeds
0–29). Everything not listed here is unchanged from v0.2 (`docs/changelog_v0.2.md`): six constants, one
acceptance rule, one guard, cap 30, kept band tasks, three outcomes, the task pool, the persistent leverage
table, the engineering.

## 1. Population-seeded bracket (replaces "start at the last accepted dose")

Evidence (`e3_layer1.md`, "A per task", footer_mask rows): on tasks 3, 7, 12, 22, 29 the bracket is
`1.0:0/4 / 0.5:4/4 / 0.75:4/4 / 0.875:4/4 → budget`; on 13 `1.0:0/4 / 0.5:6/8 / 0.75:7/8 → budget`; on 25
`1.0:0/4 / 0.5:7/8 → budget`; the leverage table in `runs/e3-A/arm_manifest.json` records footer_mask
`tested 8, with_leverage 8, last_accepted_dose None`. The family had leverage on every saturated task it met
and its band lies in (0.875, 1.0]; every bracket started at 0.5; 15 of 30 tasks ended `dropped: budget`; the
v0.2 prior (start at the last accepted dose after ≥ 5 tasks at rate ≥ 0.9) never fired because the family was
never accepted.

Change: `LeverageTable` keeps, per family, `lo_pop` = the highest dose observed `too_easy` below d = 1 and
`hi_pop` = the lowest dose observed `too_hard`, over every bracket of every task (`record_dose`). A new task's
bracket starts at `bracket_seed(family)` = `[lo_pop, hi_pop]`, default `[0, 1]`, and `[0, 1]` again when
`lo_pop ≥ hi_pop`; the first bisection is the midpoint (`bracket(lo=, hi=)`). The d = 1 leverage test still runs
first and may lower `hi` to 1. Every dose in the bracket history is written as a `leverage` event
(`{family, dose, verdict}`) beside the rate events and replayed on resume (`Controller._restore_leverage`; a
v0.2 `accepted_dose` event is ignored). `ImplConfig.prior_min_tasks` / `prior_min_rate` are removed;
`AEAConfig.schema_version` = 3. The bracket event carries `seed: [lo, hi]` instead of `start`.

Tests (`tests/unit/test_evaluate_bracket.py`): `test_population_seed_reaches_a_late_band_within_the_cap` — a
scripted family with its band in (0.875, 1.0] is accepted at 22 rollouts (10 + 4 + 8) when seeded at
[0.875, 1.0] and ends `budget` at 30 when seeded at [0, 1] (the walk 0.5 → 0.75 → 0.875 and the first batch at
0.9375 spend the cap; both asserted); `test_bracket_population_seed_sets_the_first_bisection` — no population
data or an invalid seed starts at 0.5. `tests/unit/test_families.py` — the seed after the E3 walk is
[0.875, 1.0], `in_band` and a no-effect d = 1 leave it alone, an inconsistent observation resets it.
`tests/unit/test_leverage_persist.py` — resume rebuilds `lo_pop` / `hi_pop` from completed tasks only and the
resumed run's corpus bytes equal the uninterrupted run's.

## 2. Stage-side 4/4 tops up

Evidence (`e3_layer1.md`, "A per task", zero tasks): task 9 `50: 4/4 too_easy; 50: 4/4 too_easy; 25: 4/4
too_easy; 25: 4/4 too_easy → dropped too_easy (26)`; task 27 `50: 2/8 too_hard; 50: 4/4 too_easy; 25: 0/4
too_hard → dropped too_easy (26)`; E2 Phase D (`experiments/alfworld_e2/results/e2_step1_v02.md`) had accepted
the same states at t = 50 with 3/8 and 5/8, both learnable at K = 16 (10/16, 8/16). Under a uniform prior
P(p > 0.8 | 4/4) ≈ 0.67, so a 4/4 first batch is not decisive on the stage side, where no cheaper candidate
follows.

Change: `evaluate(run, config, top_up_full=True)` tops a full first batch up to 8 like a mixed batch; the
verdict comes from the 8 (3–5 in band, 6–8 too easy, 0–2 too hard). The stage loop passes `top_up_full=True`;
the harden loop does not (4/4 at a dose stays `no_effect` / `too_easy`: a cheaper next dose exists there).

Tests: `test_evaluate_tops_up_a_full_first_batch_on_the_stage_side` (4/4 → 7/8 `too_easy`, 4/4 → 5/8
`in_band`, harden 4/4 decides at 4, 0/4 decides at 4 on both sides);
`tests/unit/test_controller.py::test_staged_full_first_batch_tops_up_to_eight` (both outcomes through the
controller on the fake world: accepted at 10 + 8, and dropped).

## 3. Quarter-point candidates

Evidence (`e3_layer1.md`, "H100 control" and "A per task"): task 9 is 4/4 from every probed mid or late state
(t = 50 and t = 25) but 0/8 from the start at horizon 100; its learnable frontier is earlier than any end or
midpoint candidate.

Change: `candidate_states` yields end, midpoint and quarter (t = T/4) per failed rollout;
`build_stage_candidates` compiles every prefix, deduplicates by state hash (keeping the higher-priority label),
caps at 6 by `cap_by_priority` (drop quarter first, then mid; the latest end never drops; among equals the
candidate nearest in t to another kept one), then guards only the kept candidates; the walk stays latest-first.
A quarter state enters when ends or midpoints collapse to one state, as they do when the policy loops to the
step cap. `rejected` entries carry the kind.

Tests (`tests/unit/test_stage.py`): the nine states of three rollouts and their latest-first order; the
priority cap drops quarters first and never the latest end; collapsed ends and midpoints let a quarter in;
`build_stage_candidates` on three identical looping rollouts yields exactly end, mid and quarter.

## Verification

Unit suite 100 green (`tests/unit`), ruff and mypy --strict clean, LLM-free integration suite
(`tests/integration/test_alfworld.py`) green on the real ALFWorld bridge (see the Phase status below). Tag
`aea-v0.3`. Review packet: `docs/reuse/review_packet_v0_3.md`; module map: `docs/reuse/v0_3.md`.

Module docstrings of the changed modules (`config`, `evaluate`, `bracket`, `families`, `stage`, `controller`)
cite `docs/spec/AEA_v0.3.md`; unchanged modules keep their v0.2 citations (their text is the same in v0.3).
