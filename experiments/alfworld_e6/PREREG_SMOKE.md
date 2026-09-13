# PREREG_SMOKE — E6 smoke: six-task prospective mechanism smoke of `llm_v1`

Written and committed before the first paid call of this experiment (the commit SHA of this
file is recorded in `scripts/e6_smoke.py::PREREG_SHA` and in every run manifest). This is a
mechanism smoke, not the E6 main experiment and not E6-SL.

## Frozen method

| item | value |
| --- | --- |
| branch / worktree | `aea-llm-vnext`, `../EnvJudge-aea-llm` (the main worktree runs E5 and is untouched) |
| method commit | `47a0091` (`src/aea` frozen; the driver records the tracked `src/aea` tree hash and a `+DIRTY` marker if it differs from this commit) |
| method_version | `llm_v1` (`AEAConfig(method_version="llm_v1")`, built once by `scripts/e6_smoke.py::config` and passed to BOTH `AeaSubstrate(aea_config=cfg)` and `Controller(cfg, ..., reference=sub.reference_provider(cfg))`; asserted offline by `tests/unit/test_e6_smoke_driver.py`) |
| method constants | the six constants of `AEAConfig` at their defaults: B_T (0.4, 0.6), B_L (0.2, 0.8), K 16, accept 3..5 of 8, probe 4 -> 8, cap 30 charged policy rollouts per task; `impl` defaults |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5, max_tokens 2048 (E3's `policy_qwen()`, unchanged) |
| designer | DeepSeek V4 Pro (`deepseek-v4-pro`, api.deepseek.com), thinking off, temperature 0.7, max_tokens 4096 (E3's `designer_deepseek()`, unchanged); the method's own request settings apply (HIGH 4096 tokens, LOW 2048) |
| substrate | released envharness @ fab7d574 (never edited); `configs/corpus_aea.yaml`; staged config `configs/alfworld_config_100.yaml` |
| designer prompts | as committed at `47a0091` (`src/aea/designer.py`); not tuned |
| reference | `ExpertReference` (ALFWorld handcoded expert from reset, in-process, `impl.oracle_max_steps` = 50 steps), requested lazily only on `llm_v1` + regime `zero` |

## Task selection (frozen before any llm_v1 result)

Source: the frozen original-environment K = 16 shared measurements, copied byte for byte into
`experiments/alfworld_e6/frozen/`:

| file | from | sha256 (first 16) |
| --- | --- | --- |
| `e2-shared_confirm_summary.json` | `runs/e2-shared/confirm_summary.json` (E2 shared K16, 10 tasks) | `0a95bc61d6932043` |
| `e3-shared_confirm_summary.json` | `runs/e3-shared/confirm_summary.json` (E3 shared K16, 20 tasks) | `da42c9269b90ff62` |

(The underlying `confirm.jsonl` files are `7f6467970b29053a` and `7548c67f9171edcf`.)

Rule (`scripts/e6_smoke.py::select_tasks`): HIGH pool = tasks with successes 16, n 16, errors 0
(p16 = 1.0); LOW pool = successes 0, n 16, errors 0 (p16 = 0.0); take the three smallest task
ids of each pool; fewer than three in a pool would have been a STOP.

| pool | eligible task ids (frozen) | selected |
| --- | --- | --- |
| HIGH (16/16) | 1, 7, 12, 13, 15, 22, 23, 24, 25, 29 | **1, 7, 12** |
| LOW (0/16) | 8, 9, 10, 11, 14, 17, 20, 27 | **8, 9, 10** |

Frozen source records of the six tasks (all from the files above):

| task | source | successes / n | errors | p16 |
| --- | --- | --- | --- | --- |
| 1 | e3-shared | 16 / 16 | 0 | 1.0 |
| 7 | e3-shared | 16 / 16 | 0 | 1.0 |
| 12 | e3-shared | 16 / 16 | 0 | 1.0 |
| 8 | e2-shared | 0 / 16 | 0 | 0.0 |
| 9 | e2-shared | 0 / 16 | 0 | 0.0 |
| 10 | e2-shared | 0 / 16 | 0 | 0.0 |

No E5 result, no llm_v1 output, no designer output and no manual inspection of these tasks was
used. No substitution is allowed after this commit.

## Run

- Task order: 1, 7, 12, 8, 9, 10 (HIGH ascending, then LOW ascending). Task concurrency 1;
  rollout batch concurrency 4 (the existing E3 value); 4 episodes in flight.
- The regime is NOT forced: the normal sequential estimator runs prospectively. The manifest and
  the report record the expected regime (from the frozen K16) and the actual prospective regime;
  a task whose prospective regime differs is reported as `branch_not_reached` and is not replaced.
- Search budget: the frozen method cap, 30 charged policy rollouts per task. No extra budget.
- Run directories: `runs/e6-smoke-llm-v1` (search), `runs/e6-smoke-confirm` (K16).
- Confirmation rule: every environment accepted by the smoke (corpus kinds `knob` / `stage`)
  gets K = 16 current-policy rollouts (`budget = eval`, evaluation-only, never fed back). The
  report gives successes / 16, p16, and whether p16 lies in B_L = [0.2, 0.8] and in
  B_T = [0.4, 0.6]. Kept (band) tasks need no confirmation beyond the frozen source records.
- USD cap: 30 total over every `runs/e6-*` ledger (policy search, designer, confirmations);
  the driver checks before the search, before each confirmation, and a watchdog exits at the cap.
  Reference and guard sessions are in-process and cost nothing. Reaching the cap = STOP, partial
  results reported, the cap is not raised.
- Endpoint gate: one ledgered probe call before the search (`--stage probe`).

## Correctness gates (any failure = NO-GO, STOP, no repair-and-continue)

Computed from the run's own files by `scripts/e6_smoke.py::correctness_gates` into `gates.json`:

1. `method_version` = `llm_v1` in the manifest and on every designer record;
2. no fixed-family fallback: every `families` event has `source = designer` and contains neither
   `footer_mask` nor `horizon_squeeze`; every `stage_candidates` event has `source = designer`;
3. at most 1 designer call per task (rows of `designer_calls.jsonl`; ledger designer rows are
   reported alongside);
4. at most 2 parsed proposals per call;
5. at most 30 charged search rollouts per task (`task_done.n_search`);
6. no `solvable` event with `source = by_construction` (the LLM-declared axis never certifies);
7. `reference` events only on tasks whose prospective regime is `zero`;
8. reference leakage audit passes (below);
9. the tasks run are exactly the six above, in order;
10. `src/aea` unchanged from `47a0091` at launch and at the gate computation;
11. no invalid environment accepted (every accepted knob loads through the released loader and
    has a passing guard; every accepted stage was certified).

Leakage audit (`scripts/e6_smoke.py::leakage_audit`, per LOW task with an available reference):
the expert's action list is recomputed in-process and must match the hash the run kept; for every
reference cut k selected by the designer, no candidate prefix in `traces.jsonl` or `corpus.jsonl`
carries an action from `reference[k:]`; the reference block is absent from `events.jsonl`,
`designer_calls.jsonl`, `traces.jsonl` and `corpus.jsonl`; the kept designer record is redacted.
Post-cut actions that the policy emitted itself are counted by provenance
(`independent_overlap`) and never flagged.

## Functionality criteria (weak by design; applied mechanically by `scripts/make_tables_e6_smoke.py`)

HIGH, over the pre-registered HIGH tasks that prospectively enter `saturated`: at least 2 tasks
with >= 1 valid LLM-generated family AND at least 1 task with measurable leverage (the d = 1
verdict of some family is not `too_easy`, i.e. a `leverage` event with `has_leverage = true`).
An accepted environment is not required.

LOW, over the pre-registered LOW tasks that prospectively enter `zero`: at least 2 tasks with
>= 1 valid grounded Stage proposal AND at least 1 proposed Stage with >= 1 successful
current-policy rollout in its probe or an in-band acceptance.

Inconclusive rule: fewer than 2 HIGH tasks entering `saturated` -> HIGH = INCONCLUSIVE; fewer
than 2 LOW tasks entering `zero` -> LOW = INCONCLUSIVE. No replacement tasks.

## Decision

Exactly one of GO / NO-GO / INCONCLUSIVE:

- GO: all correctness gates pass, HIGH PASS, LOW PASS.
- NO-GO: any correctness gate fails, or a side with enough branch-reaching tasks fails its
  criterion.
- INCONCLUSIVE: gates pass but at least one side has too few branch-reaching tasks, and no
  side failed.

No method patch is derived from the result. After the run: report
(`experiments/alfworld_e6/results/e6_smoke.md`), LOG, commit, push, STOP. Not started in this
phase: the 30-task E6, E6-SL, any method change.
