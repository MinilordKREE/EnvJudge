# Used-task audit (phase 3.3a, written before the fresh pool was measured)

Task universe: an AEA task id is the integer seed `t` passed to the released ALFWorld bridge
(`TaskRef(str(t), t)`; `AeaSubprocessRunner` passes it as `reset_seed`; the bridge's
`reset(seed=t)` shuffles the train-split game list with that seed and plays the head, since the
corpus `task_id` label never names a game file, `bridge.py:183-208`). The mapping seed -> game is
deterministic for the fixed data directory (`~/eh_alfworld_data`, split `train`, 3553 games,
`repetition_threshold 0`). All prior experiments used this universe.

| experiment | task ids | provenance |
| --- | --- | --- |
| E2 step 1 shared K16 | 0, 8, 9, 10, 11, 14, 17, 18, 20, 27 | `scripts/e3.py::E2_TASKS`; `runs/e2-shared` |
| E3 layer 1 (shared K16, arms A/G/R, H100) | 0..29 | `scripts/e3.py::TASKS = range(30)`; `runs/e3-shared`, `runs/e3-*` |
| E3-SL | the same 0..29 (banks from those runs) | `scripts/e3sl.py` |
| E3b | 0..29 | `scripts/e3.py::set_variant("e3b")` (same `TASKS`) |
| E4 | subsets of 0..29 (regime groups of the shared K16) | `scripts/e4.py` |
| E5 | 3, 12, 13, 15, 22, 23, 24, 29 | `scripts/e5.py::TASKS` |
| smoke 1 | 1, 7, 12, 8, 9, 10 | `PREREG_SMOKE.md` |
| smoke 2 | 13, 15, 22, 11, 14, 17 | `PREREG_SMOKE2.md` |
| phase 3.2 refalign (+ offline diagnostic on 8, 9, 10, 11, 14, 17) | 20, 27 | `PREREG_LOW_REFALIGN.md` |

**Exclusion set: {0, 1, ..., 29} (30 ids).** No other id has ever been rolled out by any AEA
experiment in this repository (all drivers derive their tasks from `range(30)` or from the frozen
K16 of those 30).

Fresh pool rule (PREREG_LOW_POOL2): the next 50 smallest previously unused ids, i.e. **30..79**,
selected without inspecting any task's content or type.
