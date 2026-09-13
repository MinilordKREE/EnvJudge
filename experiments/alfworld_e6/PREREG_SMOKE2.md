# PREREG_SMOKE2 — E6 smoke 2: fresh six-task prospective mechanism smoke of `llm_v1` (phase 3.1)

Written and committed before the first paid call of smoke 2 (the commit SHA of this file is
recorded in `scripts/e6_smoke.py::SMOKES[2]["prereg_sha"]` and in the run manifest).
`PREREG_SMOKE.md` and the smoke-1 results (`results/e6_smoke*`) are immutable historical
records: smoke 1 = NO-GO by pre-registered gate 8, HIGH functionality PASS, LOW functionality
PASS. Smoke 2 is a mechanism smoke, not the E6 main experiment and not E6-SL.

## What changed since smoke 1 (correctness / interface only, no method change)

Commit `f63c47b` ("aea: fix llm_v1 audit provenance and designer interface"), 0 new method
branches, the paper-level method unchanged (MEASURE -> regime-conditioned LLM DESIGN -> EMPIRICAL
CONTROL):

| issue | change | why it is implementation / interface, not method |
| --- | --- | --- |
| A. audit recomputed a non-deterministic expert | the exact reference instance used by the designer is written to `privileged_references.jsonl` (audit-side only); the auditor reads it and never opens a second expert session; the gate is recorded-hash integrity + no leak | provenance of an audit input; the designer, the reference request and the learner-facing files are unchanged |
| B. HIGH designer did not know the interaction API | static `ENVIRONMENT_SURFACE` section in the HIGH contract: action representation (`Action(name="do", kwargs={"text": ...})`), observation text + `data["admissible_commands"]` both read by the policy, `env_state` fields, A/T/O hook semantics, `Blocked` instance | documentation of the released substrate's API; no task-specific hint, no new hook, no validator |
| C. evidence mislabelled action-only output as reasoning | the `reasoning:` line is emitted only from a genuine `<think>` block | data representation; nothing fabricated |

Not changed on purpose (recorded as limitations): step-like generated dose functions; LOW cuts
that unlock the policy but overshoot the band; the v0.2 baseline cleanup after E5.

## Frozen method

| item | value |
| --- | --- |
| branch / worktree | `aea-llm-vnext`, `../EnvJudge-aea-llm` |
| method / correctness commit | `f63c47b` (`src/aea` frozen; the driver records the tracked `src/aea` tree hash with a `+DIRTY` marker if it differs) |
| method_version | `llm_v1`; one `AEAConfig(method_version="llm_v1")` for both the substrate and the controller, `reference=sub.reference_provider(cfg)`; asserted offline by `tests/unit/test_e6_smoke_driver.py` |
| method constants | `AEAConfig` defaults: B_T (0.4, 0.6), B_L (0.2, 0.8), K 16, accept 3..5 of 8, probe 4 -> 8, cap 30 charged policy rollouts per task; `impl` defaults |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5, max_tokens 2048 (E3's `policy_qwen()`, unchanged) |
| designer | DeepSeek V4 Pro (`deepseek-v4-pro`), thinking off, temperature 0.7 (E3's `designer_deepseek()`, unchanged); HIGH 4096 / LOW 2048 output tokens |
| substrate | released envharness @ fab7d574; `configs/corpus_aea.yaml`; staged config `configs/alfworld_config_100.yaml` |
| designer prompts | as committed at `f63c47b` (`src/aea/designer.py`), not tuned on smoke-1 tasks |
| reference | `ExpertReference` (ALFWorld handcoded expert from reset, in-process, 50 steps), lazily on `llm_v1` + `zero` only; the exact instance recorded to `privileged_references.jsonl` |

## Task selection (frozen; fresh tasks)

Same frozen pools as smoke 1 (`experiments/alfworld_e6/frozen/`: `e2-shared_confirm_summary.json`
source sha `0a95bc61d6932043`, `e3-shared_confirm_summary.json` source sha `da42c9269b90ff62`).
Rule (`scripts/e6_smoke.py::select_tasks(exclude=(1, 7, 12, 8, 9, 10))`): HIGH pool = 16/16
with 0 errors; LOW pool = 0/16 with 0 errors; remove smoke 1's six tasks; take the three smallest
remaining ids of each pool; fewer than three would be a STOP.

| pool | eligible after exclusion | selected |
| --- | --- | --- |
| HIGH (16/16) | 13, 15, 22, 23, 24, 25, 29 | **13, 15, 22** |
| LOW (0/16) | 11, 14, 17, 20, 27 | **11, 14, 17** |

| task | source | successes / n | errors | p16 |
| --- | --- | --- | --- | --- |
| 13 | e3-shared | 16 / 16 | 0 | 1.0 |
| 15 | e3-shared | 16 / 16 | 0 | 1.0 |
| 22 | e3-shared | 16 / 16 | 0 | 1.0 |
| 11 | e2-shared | 0 / 16 | 0 | 0.0 |
| 14 | e2-shared | 0 / 16 | 0 | 0.0 |
| 17 | e2-shared | 0 / 16 | 0 | 0.0 |

No smoke-1 outcome, no llm_v1 output and no manual inspection of these tasks was used. No
substitution after this commit.

## Run

Task order 13, 15, 22, 11, 14, 17 (HIGH ascending then LOW ascending); task concurrency 1;
rollout batch concurrency 4. Regime NOT forced (prospective estimator; `branch_not_reached`
recorded, never replaced). Cap 30 charged policy rollouts per task. Runs `runs/e6-smoke2-llm-v1`
and `runs/e6-smoke2-confirm`. Confirmation: K = 16 on every accepted environment
(evaluation-only, never fed back); p16 reported with B_L / B_T membership. USD cap 30 over every
`runs/e6-*` ledger of this smoke (`runs/e6-smoke2-*`; smoke 1's USD 4.32 is a separate,
closed budget), checked before the search and before each confirmation, watchdog at the cap; STOP
at the cap, no raise. Endpoint gate: one ledgered probe call.

## Correctness gates (any failure = NO-GO, STOP, no repair-and-continue)

As smoke 1 (`scripts/e6_smoke.py::correctness_gates`): runtime `method_version = llm_v1`; no
fixed-family fallback (`families` / `stage_candidates` events all `source = designer`, no library
name); <= 1 designer call per task; <= 2 parsed proposals per call; <= 30 charged search rollouts
per task; no `solvable` event `by_construction`; `reference` events only on prospective `zero`
tasks; tasks exactly the six above in order; `src/aea` unchanged from `f63c47b`; no invalid
environment accepted. Gate 8 (leakage) is now evaluated against the EXACT recorded reference
(`privileged_references.jsonl`): recorded hash integrity (record = `reference` event = redacted
designer evidence), no candidate prefix carrying `reference[k:]` past any selected reference cut,
reference block absent from every kept file, designer record redacted; policy-emitted post-cut
actions counted by provenance (`independent_overlap`), never flagged; the expert is never re-run
(`expert_recomputed` must be false).

## Functionality criteria (identical to smoke 1)

HIGH, over pre-registered HIGH tasks that prospectively enter `saturated`: >= 2 tasks with >= 1
valid LLM-generated family AND >= 1 task with measurable leverage (a `leverage` event with
`has_leverage = true`). LOW, over pre-registered LOW tasks that prospectively enter `zero`: >= 2
tasks with >= 1 valid grounded Stage AND >= 1 Stage with >= 1 successful current-policy rollout
in its probe or an in-band acceptance. Fewer than 2 branch-reaching tasks on a side -> that side
INCONCLUSIVE. No replacement tasks.

## Descriptive delivery metrics (reported, never part of the decision)

`accepted environments / branch-reaching tasks` for HIGH and for LOW; HIGH leveraged-but-not-
accepted; LOW unlocked-but-too-easy; LOW dead.

## Decision

Exactly one of GO / NO-GO / INCONCLUSIVE by the gates and criteria above. No method patch is
derived from the result; if functionality and correctness pass but few environments are
delivered, that is reported as: LLM intervention generation can affect policy behaviour, but
controllability / target landing remains the bottleneck. After the run: report
(`results/e6_smoke2.md`), LOG, commit, push, STOP. Not started: the 30-task E6, E6-SL.
