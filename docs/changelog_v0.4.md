# aea v0.4 — changelog (2026-09-13)

Method of record: `docs/spec/AEA_v0.4.md` = v0.2 + a soft cross-task warm start of the dose search. Owner's
design constraint: method simplicity is hard; the repair of the E3b failure must make the method simpler than
v0.3, not more complex. Rule: **history proposes the first probe; the current task's evidence decides.**

## What is withdrawn from v0.3

| v0.3 edit | status in v0.4 | why |
|---|---|---|
| population bracket `[lo_pop, hi_pop]` (min / max over tasks, hard bound) | replaced by the soft warm start | E3b: one 0/4 at d = 0.5 on task 2 set `hi_pop` = 0.5 for the run; 7 later brackets bisected a vanishing sliver below 0.5 and never reached the (0.875, 1] band E3 had found; 0 accepted, tasks 23 and 24 lost. P(0/4 at p = 0.2) = 0.41; the bound was irreversible because every later bracket could only observe too easy below it. |
| stage-side 4/4 top-up | removed (v0.2 `evaluate` restored) | fired once in E3b, changed no outcome; removed so the saturated-side change is tested alone |
| quarter-point candidates | removed (v0.2 `stage` restored) | certified on 3 tasks, accepted on none; same reason |

The v0.3 code paths are gone, not flagged off: `evaluate(top_up_full=...)`, `cap_by_priority`, `KIND_RANK`,
`LeverageTable.record_dose` / `bracket_seed`, `FamilyStats.lo_pop` / `hi_pop`, `bracket(lo=, hi=)`.

## The one change from v0.2

v0.2 seeded the first bisection at a family's last accepted dose once its leverage rate was ≥ 0.9 over ≥ 5
tasks (`prior_min_tasks`, `prior_min_rate`); it never fired in E3 (the footer mask was never accepted). v0.4:

- `FamilyStats.frontiers`: one number per finished task-family search, `(lo_t + hi_t) / 2` of the task's final
  local interval (accepted, exhausted or censored by the cap all count).
- `LeverageTable.record_frontier(family, lo, hi)`; `LeverageTable.warm_start(family, min_history)` = the median
  of the frontiers when at least `impl.warm_start_min_history` (3) exist, else 0.5, clipped to (0, 1).
- `bracket(evaluate_at, config, leverage=, start=)`: the v0.2 code — `start` is the first interior probe
  only, the interval is `[0, 1]` and every later dose is its midpoint (v0.2 already had this parameter and
  this contract; only the source of `start` changed).
- `Controller._try_family`: `start = warm_start(...)` before the bracket; after it, the final local interval
  `[lo, hi]` from the history becomes one `leverage` event `{family, frontier, lo, hi}`; `_restore_leverage`
  replays those (v0.2 `accepted_dose` and v0.3 `dose` events are ignored). The bracket event carries `start`
  and `local`.
- `AEAConfig.schema_version` 4; `ImplConfig.warm_start_min_history = 3` replaces the two v0.2 prior constants.

## Method complexity guard (v0.2 → v0.4, `git diff --stat 08a09b7 -- src/aea`)

| item | count |
|---|---|
| new state variables | 1 (`frontiers`, a list per family; replaces `last_accepted_dose`) |
| new branches | 1 (`len(frontiers) >= min_history` → median, else 0.5; replaces the two-condition rate/count gate) |
| new scalar hyperparameters | 1 (`warm_start_min_history` = 3; replaces 2) |
| lines changed (4 files, docstrings included) | +65 / −50 |
| new method module / LLM call / rollout type / certificate type / threshold / regime boundary | none |

Against v0.3 (`git diff --stat main -- src/aea`): 6 files, +101 / −133, i.e. v0.4 is 32 lines shorter than v0.3.

## Tests (`tests/unit`, 99 green; ruff and mypy --strict clean; LLM-free integration suite green)

- A `test_warm_start_is_only_the_first_probe_local_interval_stays_0_1`: history near (0.875, 1] → first probe
  0.9375 ≫ 0.5, accepted; E: after a too-easy warm probe the next dose is `(start + 1) / 2`, after a too-hard
  one `start / 2`, so `[0, 1]` was intact before the probe whatever the history.
- B `test_leverage_table_orders_and_warm_starts`: three frontiers near 0.94 and one poisoned at 0.25 → the
  median stays 0.9375 (a hard bracket would have collapsed to 0.5).
- C `test_wrong_warm_start_costs_one_probe_and_recovers`: history 0.9, true band (0.3, 0.5): probes 0.9 (too
  hard) then 0.45 → accepted inside the band; the same task from 0.5 takes one probe fewer.
- D `test_no_history_reduces_to_v02_midpoint`: no history or fewer than 3 frontiers → 0.5; a boundary start is
  clipped back to 0.5; `warm_start(..., 10**9)` switches the mechanism off (the v0.2 arm of E5).
- Persistence: frontier events rebuilt on resume; interrupted attempts and legacy v0.2 / v0.3 events ignored.

## Offline replay (`scripts/replay_dose_search.py` → `experiments/alfworld_e5/replay_dose_search.md`)

Replayed on the E3 v0.2 bracket evidence with each task's observed gap as its band and its real remaining
budget: v0.4 censors no task (the kill condition), v0.3 censors the one footer-mask task whose band was low
(task 15, (0.25, 0.5)); the numbers are in the report and quoted in the E5 pre-registration. The E3b brackets
are replayed but not counted: their gaps are artifacts of the collapse.

## Paper-level pseudocode

In `docs/spec/AEA_v0.4.md`, "The saturated side in fifteen lines".
