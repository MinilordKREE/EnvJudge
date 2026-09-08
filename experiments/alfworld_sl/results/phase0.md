# E1-SL Phase 0b — E0 reproduction, cost and projection (STOP)

Run `e0-20260907` (aea @ 76ad56c for corpus/banks/eval, report @ HEAD; envharness @ fab7d574, unmodified).
PREREG7 unchanged. Every number below is produced by `scripts/e0.py --stage report`
(copied verbatim from `results/e0-20260907/phase0b_report.md`); ledger totals in
`results/e0-20260907/ledger_totals.json`; full ledgers/traces stay in `runs/e0-20260907/` (git-ignored).

## 1. Table (next to EnvHarness Table 2, ALFWorld)

Seeds (released eval rounds): seeds-0, seeds-1000, seeds-2000; splits ID n=140, OOD n=134 per seed; success % pooled over seeds (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| N | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig | 68.6 (n=420) [74.3 / 60.7 / 70.7] | 69.2 (n=402) [70.1 / 72.4 / 64.9] | 63.3 | 61.4 |
| EnvHarness | 68.6 (n=420) [72.9 / 64.3 / 68.6] | 63.2 (n=402) [66.4 / 64.9 / 58.2] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +6.9 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -6.0 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +6.9, OOD -0.7 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points; per-seed sign in the table above):
- orig minus N: ID +6.9 ± 3.3, OOD +5.2 ± 3.3
- EnvRigger minus orig: ID +0.0 ± 3.2, OOD -6.0 ± 3.3
- EnvRigger minus N: ID +6.9 ± 3.3, OOD -0.7 ± 3.4

Corpus: 180 policy episodes, USD 4.30 (USD 0.0239 per episode); designer USD 0.06; induction USD 0.04.
Eval: 2466 episodes, USD 29.13 (USD 0.0118 per episode).

Projection N=30: corpus USD 84 + confirmations USD 149 + evals USD 136 = USD 369
Projection N=50: corpus USD 140 + confirmations USD 248 + evals USD 136 = USD 524
Backbone rule: corpus episode USD 0.0239 <= 0.10 -> Flash-Lite stays.

Conditions: N = no bank; orig = single-success bank induced from the released EnvRigger corpus's
baseline (unmodified-environment) successes; EnvHarness (R) = single-success bank from the accepted
(rule-modified) environments of the same corpus. Corpus: released `corpus.yaml` on seeds 0–19
(20 tasks; only the two client blocks and the storage/logging paths differ, pinned by
`aea.e0config.ALLOWED_CHANGES`). Banks: orig 52 items / 19 tasks, R 39 items / 14 tasks
(`banks.json`). Eval: released `reasoning_bank_eval.py`, SkillOS prompt, history 4, top-5 MMR,
ID n=140 and OOD n=134 per seed, seeds 0 / 1000 / 2000, 0 errored episodes, no guard marker.

## 2. Sign check and the OOD mismatch

- **orig > N on ID: reproduced** (+6.9 ± 3.3; positive in all three seeds). Our N (61.7 / 63.9)
  sits within 2 points of Table 2's N (62.6 / 60.7) despite the different backbone.
- **EnvRigger > orig on OOD: not reproduced** (−6.0 ± 3.3; R is below orig in all three seeds and
  equals N on OOD in two of three). On ID, R equals orig (+0.0 ± 3.2), so the R bank carries the same
  ID gain as the orig bank and no OOD gain.

Designed differences from the released headline pipeline (`experiments/alfworld/README.md`:
corpus → induce → subset → eval, `N_TASKS_TOTAL=100`) that can explain the OOD sign, in the order
I would test them:

1. **Corpus size 20 vs 100 tasks.** The R bank covers 14 tasks (39 items) against orig's 19 (52).
   Fewer accepted environments → less OOD coverage for top-5 retrieval. Cheapest check: extend the
   corpus to the released 100 tasks (≈ USD 17 corpus + USD 0.2 banks + USD 20 eval for orig/R × 3 seeds).
2. **Induction mode.** PREREG7 fixed single-success induction for E0; the released Stage 2 uses
   paired-diff wherever a task has both a success and a failure (`induce_pair.py:93-108`), which is
   exactly where the rule-modified environments produce failures. Check: rebuild orig/R with the
   released default (≈ USD 0.1) and re-evaluate (≈ USD 20).
3. **No Stage 3 subset.** The headline banks are 1 item per task (`scripts/subset.py`); ours keep every
   induced item. Check: apply the released subset (no LLM cost) and re-evaluate (≈ USD 20).
4. **Backbone.** Gemini 3.1 Flash-Lite (pre-registered) vs the released eval default `gpt-4.1-mini`.
   Not testable within the E1-SL budget; reported as a standing difference.

The mismatch does not touch PREREG7's claims (C1–C3 compare A against R/O/N under the same pipeline),
but PREREG7 requires the gap to be explained before round 1; items 1–3 are the candidate diagnosis,
each ≈ USD 20–40 of eval, for the owner to choose or waive.

## 3. Endpoint, thinking, caching (owner requirements)

- Manifest (`results/e0-20260907/manifest.json`): `policy_endpoint_pin` and `designer_endpoint_pin`
  = `google-ai-studio`, `thinking: null`. Every completion row in the corpus, banks and eval ledgers
  reports provider "Google AI Studio" (68,772 calls); the only rows without a provider are the
  embedding calls (`google/gemini-embedding-001` through OpenRouter, which reports none; priced from
  the table, USD 0.004 total).
- No thinking parameter was sent on either path (corpus: `LLMConfig.thinking=None`; eval: the hook's
  route adds no `reasoning` key when `thinking` is None). `reasoning_tokens` is 0 on every row.
- Implicit caching: corpus prompts (~8.5k tokens, ~59% cached) were charged at the cache rate with
  `usage.cost` equal to the table on every call; eval prompts (~870 tokens) are below Gemini's cache
  minimum and report 0 cached tokens. Pricing guard tolerance 1e-6, no guard fired.

## 4. Cost

| item | episodes / calls | USD |
|---|---|---|
| backbone probe (5 calls) | 5 | 0.006 |
| first corpus launch, aborted (attribution bug) | 276 calls | 0.294 |
| corpus policy (search) | 180 episodes / 3,932 calls | 4.300 |
| corpus designer | 37 calls | 0.057 |
| induction + embeddings | 43 calls | 0.036 |
| eval (3 seeds × 3 conditions × 274) | 2,466 episodes / 64,770 calls | 29.127 |
| **Phase 0 total** | | **33.82** (cap 60) |

Per corpus episode USD 0.0239 (policy only; designer adds 0.0003). Per eval episode USD 0.0118.

## 5. Projection and decisions (PREREG7 rules)

- **Backbone rule:** corpus episode 0.0239 ≤ 0.10 → **Flash-Lite stays** for all arms.
- **N rule:** projection N=50 = USD 524 > 450 → **N = 30** (projection USD 369). Projection
  assumptions (`scripts/e0.py`): 13 adaptation arm-rounds (round 1: R, G, G+, A, A-ex, A+H; rounds 2–3:
  R, A, O) each at the full 30-rollout search cost per task (O counted at full cost — an upper bound),
  confirmations 16 rollouts per task per arm-round, evals 14 arm-rounds (adaptation arms + N) × 3 seeds
  × 274 episodes at the measured USD 0.0118. E1-SL total with Phase 0 ≈ USD 403, at the soft gate 400
  and under the hard cap 500; the diagnosis runs of §2 are extra (≈ USD 20–40 each).

## 6. Deviations and incidents (all in LOG)

- First corpus launch aborted after task 0 (USD 0.29): policy rows unattributed because the released
  orchestrator dispatches episodes from a thread pool (no contextvars); fixed in aea (`AeaSubprocessRunner`
  default attribution per episode, commit ecd6006); run dir kept as `runs/e0-20260907-aborted-attribution`.
- The 33 induction completion rows carry `phase=eval`, `arm=none` (released induction thread pool);
  every call is ledgered and pinned; `EvalHook.default` added (76ad56c); the report selects induction
  rows by budget.
- Eval seeds ran as three parallel invocations of the released driver (one seed each, concurrency 8,
  `eval/seeds-<s>/`), identical to one three-round invocation (rounds are independent).

## 7. Owner decisions at the gate (2026-09-08; LOG, PREREG7 Amendment 1 @ ba8bdfc)

1. Diagnosis: rebuild orig and R on the same 20-task corpus with the released pipeline and evaluate
   on 3 seeds; sign returns → attributed to induction mode + subset; else D1 (R on 100 tasks); else
   release with backbone and N as standing differences. Round 1 reports both induction modes for
   every arm (single-success primary, released mode as the baseline-protocol row). See §8.
2. N = 30 and Flash-Lite confirmed by rule. Regime map of the 20 corpus tasks from the 100 baseline
   rollouts (`scripts/e0.py --stage regime`, `results/e0-20260907/regime.md`):

| task | baseline s/n | class | accepted candidates | rejected | accepted-env s/n |
|---|---|---|---|---|---|
| 0 | 5/5 | saturated | 1 | 0 | 5/5 |
| 1 | 5/5 | saturated | 1 | 0 | 5/5 |
| 2 | 5/5 | saturated | 0 | 0 | 0/0 |
| 3 | 5/5 | saturated | 1 | 0 | 5/5 |
| 4 | 4/5 | high | 1 | 0 | 4/5 |
| 5 | 5/5 | saturated | 1 | 0 | 4/5 |
| 6 | 5/5 | saturated | 0 | 0 | 0/0 |
| 7 | 5/5 | saturated | 0 | 0 | 0/0 |
| 8 | 3/5 | mid | 1 | 0 | 5/5 |
| 9 | 5/5 | saturated | 1 | 0 | 5/5 |
| 10 | 5/5 | saturated | 1 | 0 | 5/5 |
| 11 | 0/5 | zero | 1 | 1 | 0/5 |
| 12 | 5/5 | saturated | 1 | 0 | 5/5 |
| 13 | 5/5 | saturated | 1 | 0 | 5/5 |
| 14 | 5/5 | saturated | 0 | 0 | 0/0 |
| 15 | 5/5 | saturated | 1 | 0 | 5/5 |
| 16 | 5/5 | saturated | 1 | 0 | 5/5 |
| 17 | 5/5 | saturated | 0 | 0 | 0/0 |
| 18 | 5/5 | saturated | 1 | 0 | 5/5 |
| 19 | 5/5 | saturated | 1 | 0 | 5/5 |

Classes on the baseline rollouts: zero = 0/n; marginal-low = 1/n; mid = 2-3/5; high = 4/5; saturated = n/n.
Counts: zero 1, marginal-low 0, mid 1, high 1, saturated 17 (of 20).
Zero + marginal-low: 1/20 = 5% (below the owner's 10% thin-evidence line).
Designer: 15/20 tasks with an accepted candidate (15 accepted, 1 rejected).

   Reading: Flash-Lite is saturated on 17/20 released tasks; the released designer's accepted
   candidates leave 13 of the 14 scaffolded tasks at 4–5/5, i.e. the accepted environments are not
   harder for this policy (consistent with the owner's mechanism note: the scaffold does steps for
   the policy). Zero + marginal-low = 1/20 (5%) is below the 10% line, so the round-1 zero-side
   evidence will be thin on this task set; no design change (paper-level decision on a second
   consumer). Correction to the note's count: 15/20 tasks had a candidate accepted (one rejection);
   R's bank covers 14 because task 11's accepted environment scored 0/5.
3. PREREG7 Amendment 1 committed before any round-1 rollout: Protocol T2 (primary for C2) and
   Protocol U (reported); C1 primary counts learnable transformed environments; both induction
   modes for every arm in round 1.
4. E1-SL hard cap USD 560, soft gate USD 500.

## 8. Diagnosis (decision 1): released Stage 2 + Stage 3 on the E0 corpus

Premise check against `experiments/alfworld/reproduce.py`: the released headline evaluates the
FULL Stage-2 banks; the Stage-3 one-per-task subsets are built as a secondary reference only.
Stage 2 (`scripts/induce_pair.py` main) differs from E0's banks in two ways at once: paired-diff
wherever a task has both a success and a failure, and a per-task cascade for "ours" (accepted
rollouts where the task has them, else the task's baseline rollouts, so ours covers the same 20
tasks as orig — closer to Protocol U than to T2). The diagnosis therefore runs the released Stage 2
verbatim (`--stage banks_released`, both banks), builds the subsets at no cost, and evaluates the
full banks (`orig_rel`, `R_rel`) on seeds 0/1000/2000 (~USD 20); the subset eval (another ~USD 20)
is held for the owner since it is not part of the headline.

Result (`scripts/e0.py --stage report`, verbatim; N row shared with §1):

Seeds: seeds-0, seeds-1000, seeds-2000; success % pooled (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| nobank (N) | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig_rel (orig) | 68.6 (n=420) [71.4 / 63.6 / 70.7] | 69.4 (n=402) [70.9 / 70.9 / 66.4] | 63.3 | 61.4 |
| R_rel (EnvHarness) | 68.1 (n=420) [72.1 / 65.0 / 67.1] | 68.9 (n=402) [72.4 / 69.4 / 64.9] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +6.9 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -0.5 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +6.4, OOD +5.0 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points):
- orig_rel minus nobank: ID +6.9 ± 3.3, OOD +5.5 ± 3.3
- R_rel minus orig_rel: ID -0.5 ± 3.2, OOD -0.5 ± 3.3
- R_rel minus nobank: ID +6.4 ± 3.3, OOD +5.0 ± 3.3

Reading:
- The released Stage 2 on this corpus is almost entirely single-success: paired-diff fired on 1
  of 20 tasks (`banks_released.json`: orig_full 47 single_succ + 1 single_fail; ours_full 46
  single_succ + 1 paired_diff + 1 single_fail), because Flash-Lite is saturated on 17/20 tasks and
  there are no failures to pair. The induction-mode explanation therefore cannot be tested on this
  corpus; what the diagnosis changed is the per-task cascade (ours covers all 20 tasks: 15 accepted
  + 5 baseline fallback, where E0's R covered the 14 transformed tasks only) and one induction resample.
- With the cascade, R's OOD deficit against N disappears (E0: −0.7; released: +5.0 ± 3.3) and R sits
  level with orig on both splits (−0.5 ± 3.2 ID, −0.5 ± 3.3 OOD). The Table 2 sign (EnvRigger > orig
  on OOD by +9.0) does not return: on this backbone the transformed environments add nothing over
  the baseline trajectories of the same tasks. The E0 −6.0 OOD gap was coverage (14 vs 19 tasks),
  not a penalty from the transformed environments.
- orig_rel reproduces E0's orig within noise (ID 68.6 both; OOD 69.4 vs 69.2): the single-success
  induction resample is stable at this scale.
- Per the owner's decision tree the sign has not returned → D1 (R on 100 tasks) runs next; if it
  still does not return, backbone and N are recorded as standing differences and round 1 proceeds.

Cost of the diagnosis: banks USD 0.045; evals USD 20.14 for 1,644 recorded episodes (USD 9.30 of it
in the run interrupted by the machine reboot, whose in-flight episodes were re-run; see LOG).
Phase 0 spend to date after D2+D3: USD 54.0 (see §9 for the final total).

## 9. D1: released pipeline on a 100-task corpus (run `e0d1-20260908` + E0's tasks)

Corpus: task ids 20–99 through the orchestrator's `explicit_task_ids` override (corpus.yaml
unchanged; stride 1 / offset 0, so the ids equal a 100-task sweep's), 80 tasks, 840 traces (400
baseline, 325 accepted, 115 exploration = 23 rejected candidates), 0 failed tasks. Banks: released
Stage 2 on the merged 100-task traces — orig_full 208 items / 87 tasks (183 single_succ, 18
single_fail, 7 paired_diff); ours_full 215 items / 90 tasks by cascade (80 accepted + 20 baseline
fallback; 199 single_succ, 7 paired_diff, 9 single_fail); subsets 82 + 82 built, not evaluated.
Paired-diff fires on 7/100 tasks: the backbone is saturated on 72/100 (regime map
`results/e0d1-20260908/regime.md`: the 80 new tasks are 55 saturated, 5 high, 10 mid, 3 marginal-low,
7 zero; pooled over 100 tasks zero + marginal-low = 11/100, at the 10% line).

Result (`scripts/e0.py --stage report --run-id e0d1-20260908 --n-from e0-20260907`, verbatim; N
cells from E0):

Seeds: seeds-0, seeds-1000, seeds-2000; success % pooled (per-seed values in brackets).

| condition | ID (ours) | OOD (ours) | ID (Table 2) | OOD (Table 2) |
|---|---|---|---|---|
| nobank (N) | 61.7 (n=420) [63.6 / 57.1 / 64.3] | 63.9 (n=402) [66.4 / 67.2 / 58.2] | 62.6 | 60.7 |
| orig_100 (orig) | 72.4 (n=420) [75.7 / 67.9 / 73.6] | 65.4 (n=402) [64.2 / 67.9 / 64.2] | 63.3 | 61.4 |
| R_100 (EnvHarness) | 69.5 (n=420) [75.7 / 67.9 / 65.0] | 63.2 (n=402) [68.7 / 61.2 / 59.7] | 66.2 | 70.4 |

Sign check (PREREG7 reproduction sanity):
- orig > N on ID: ours +10.7 pts (Table 2 +0.7) -> REPRODUCED
- EnvRigger > orig on OOD: ours -2.2 pts (Table 2 +9.0) -> NOT reproduced
- (reported, not a gate) EnvRigger vs N: ID +7.9, OOD -0.7 (Table 2 +3.6 / +9.7)

Pooled gaps with normal-approximation SE (points):
- orig_100 minus nobank: ID +10.7 ± 3.2, OOD +1.5 ± 3.4
- R_100 minus orig_100: ID -2.9 ± 3.1, OOD -2.2 ± 3.4
- R_100 minus nobank: ID +7.9 ± 3.3, OOD -0.7 ± 3.4

Reading:
- At 100 tasks the Table 2 sign still does not return: R_100 is below orig_100 on both splits by
  2–3 points (within one SE). Corpus size was not the cause of E0's mismatch.
- The banks' OOD gain over N shrinks as the corpus grows (orig: +5.2 at 20 tasks, +1.5 at 100;
  R: −0.7 / +5.0 / −0.7 across E0, D2+D3, D1), while the ID gain holds or grows (orig +6.9 → +10.7).
  With Flash-Lite and top-5 MMR over a larger bank, OOD transfer from any ALFWorld bank is small.
- **Decision per the owner's tree:** the sign did not return after D2+D3 and D1, so the backbone
  (Gemini 3.1 Flash-Lite vs the released eval's default) and N are recorded as standing differences
  and round 1 proceeds; C1–C3 are same-pipeline comparisons and do not depend on the Table 2 sign.
  The three reproductions (E0 T2-strict, released 20-task, released 100-task) all reproduce
  orig > N on ID and none reproduces EnvRigger > orig on OOD.

Costs (merged ledgers only; `results/e0-20260907/phase0_spend.json`):

| item | USD |
|---|---|
| D1 corpus (policy 24.70 + designer 0.31 + released induction 0.22) | 25.23 |
| D1 evals (1,644 episodes, USD 0.0121 per episode) | 19.84 |
| D1 total (owner estimate ~37) | 45.07 |
| **Phase 0 total** (probe, aborted launch, E0, D2+D3 incl. the crashed run, D1) | **99.08** |

The D1 corpus cost USD 0.31 per task against 0.22 in E0 (harder tasks draw more designer rounds).
With that per-task cost the N = 30 projection is USD 396 (E0-based: 371); adding Phase 0 gives
~USD 495 against the soft gate 500, and the round-1 second-induction-mode evaluations (~USD 68 per
decision 4) take the E1-SL total to ~USD 563 against the hard cap 560. **Budget flag for the owner:**
either the second-induction-mode row is limited (e.g. A and R only, ~USD 20), or the hard cap moves,
before round 1 launches. Operational note: 24 concurrent eval episodes (three seeds × 8) drew
transient 429s from OpenRouter on two seeds (retried by the released client, no episode lost);
round 1 keeps total eval concurrency at 16.

## STOP

Phase 0b complete. Settled: N = 30, Flash-Lite, Amendment 1 (T2/U, both induction modes in round 1),
caps 560/500, standing differences (backbone, N) recorded. Owner input needed before round 1: the
budget flag above.
