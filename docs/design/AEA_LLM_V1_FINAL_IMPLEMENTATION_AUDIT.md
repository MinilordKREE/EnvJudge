# `llm_v1` final implementation audit (phase 2.1)

Scope: implementation correctness only. Nothing here is a statement about experimental
performance; no experiment has run on `llm_v1`. Code state: branch `aea-llm-vnext` after the
phase-2.1 commit (three correctness fixes over `0a77e0f`); baseline for v0.4 is `05fc2fe`.

## 1. Method-to-code mapping

| paper-level primitive | code | notes |
| --- | --- | --- |
| MEASURE | `aea.estimate.estimate` called from `Controller._estimate` / `_run_task`; regime boundaries `AEAConfig.band_l` | unchanged from v0.4 |
| DESIGN | `aea.designer`: `serialize_high` / `serialize_low` (LLM-free evidence), `design_high` / `design_low` (one call each), `parse_high` / `parse_low`, the two tool contracts | HIGH: <= 2 dose-parameterised Rules families; LOW: <= 2 grounded Stage cuts |
| CONTROL | `witness.solvable` (guard), `Controller._try_family` (leverage test, bracket, cap; unchanged), `Controller._probe_stages` (4 -> 8 probe on grounded stages), `aea.evaluate` | the current policy's rollouts are the only acceptance |

Infrastructure, not primitives: `ExpertReference` / `ReferenceProvider` (a wrapper over the
existing `run_expert`), `AeaSubstrate.reference_provider` (wiring), evidence bounds and
redaction, `designer_calls.jsonl`, the events, the ledger, the `method_version` switch.

Primitive count: 3. Method-level branches added in phase 2.1: 0. One designer model, one
controller.

## 2. v0.4 compatibility

- `AEAConfig.method_version` defaults to `v0.4`; a YAML without the field is v0.4; schema 4.
- `tests/fixtures/golden_v04.json` (recorded at `05fc2fe`) is byte-identical after phases 2 and
  2.1 (`git diff` empty). `test_method_version_compat.py` reproduces it with the default config,
  with explicit `v0.4`, and with every `llm_v1` entry point replaced by a trap.
- The E5 arm configs (`scripts/e5.py::config_for`) and the E3 default config resolve to `v0.4`.
- v0.4-executed lines changed since `05fc2fe`: the bracket start now goes through `_start_dose`
  (same value under v0.4); the guard's `by_construction` gains an `and method_version != "llm_v1"`
  conjunct (true under v0.4); two early returns at the top of `_harden` / `_stage` (false under
  v0.4). The E3 driver's Controller site passes `reference=sub.reference_provider(cfg)`, which
  is `None` under v0.4.

## 3. HIGH `llm_v1` path

`_harden_llm`: evidence (goal from the step-0 observation; regime, p_hat, n; shortest and
longest success and the first failure step by step; success lengths) -> one designer call with
the contract and the two library families as few-shot examples -> `parse_high` (released loader
+ LLM-free smoke at d = 1; library copies, empty mechanism summary, bad axis and duplicate names
rejected; at most two) -> the unchanged `_try_family` in designer order.

Invariants re-verified (tests 4, 5, 12, issue-1 A/B): the library is never executed under
`llm_v1`; zero valid proposals -> `dropped: no_valid_proposal`; the designer is called once
(test 7/10/11); the warm start is 0.5 for generated identities (`_start_dose`).

## 4. LOW `llm_v1` path

`_stage_llm`: the `impl.n_failed_rollouts` seeded failures -> lazy reference (section 5) ->
evidence (goal; regime; the reference block; the failures labelled F1..) -> one designer call ->
`parse_low` (each cut must name a supplied failure with a step in 1..length, or `reference` with a
step in 1..len(reference) and only when one was supplied; at most two; no repair) ->
`compile_prefix` on the 100-step staged config, dedupe by compiled-prefix hash,
`Candidate(in_env_actions=...)`, `solvable()` with the oracle only -> `_probe_stages` in designer
order -> first `in_band` = corpus entry of kind `stage`.

Invariants re-verified (tests 21, 31, ordering): no end / mid / quarter / `candidate_states`
fallback exists in `_stage_llm`; reference failure -> failure-only designer; zero valid grounded
proposals -> `dropped: no_valid_proposal`.

## 5. Reference lifecycle

1. Wiring: `AeaSubstrate.reference_provider(config)` returns `None` unless
   `config.method_version == "llm_v1"`, else an `ExpertReference` over the substrate's own
   `open_session` with `impl.oracle_max_steps`. Constructing it runs nothing.
2. Request: only `Controller._lazy_reference`, called only from `_stage_llm` (regime `zero`
   under `llm_v1`). Band and saturated tasks never call it (tests 14, 15, issue 3).
3. Execution: `ExpertReference.__call__` takes `SESSION_LOCK`, opens a reset-state session on the
   unmodified task, runs `run_expert`, closes the session; any exception becomes
   `Reference(ok=False, reason)`. Never charged; no trace is written.
4. Use: the LOW designer prompt (the reference block first, so the size bound cannot remove it;
   `reference_used` is read from the bounded text) and the selected prefix `actions[:k]`
   compiled into a Stage.
5. Records: `reference` event (`requested`, `available`, `n_steps`, `reason`),
   `designer_evidence` (`reference_used`), `designer_calls.jsonl` with the reference block
   replaced by its length and hash. No privileged file is written.

## 6. Trust boundaries

| signal / component | may propose? | may certify solvability? | may accept? |
| --- | --- | --- | --- |
| LLM designer | yes (<= 2 per task, one call) | no | no |
| LLM-declared axis | metadata only (`llm_v1` never derives `by_construction` from it) | no | no |
| LLM mechanism summary | metadata only (recorded) | no | no |
| privileged reference | diagnosis context; a prefix of it may become a Stage | no (the compiled Stage is still guarded by `solvable()`) | no |
| oracle (expert) / policy witness | no | yes, solvability only (`solvable()`) | no |
| current-policy rollout (4 -> 8) | no | no | yes (the only acceptance) |
| dose search (bracket) | no | no | calibrates; acceptance is still the probe |
| trusted library (v0.4 only) | yes (always tried) | O-axis by construction (v0.4 only) | no |
| downstream learner / E3-SL | consumes `corpus.jsonl` + `traces.jsonl` | no | no |

Issue 1 fix: `by_construction=fam.axis == "O" and self.config.method_version != "llm_v1"`
(`controller.py`, `_try_family`). Under `llm_v1` the guard always runs: the policy's own
success is replayed through the wrapped environment, then the oracle; a family that blocks the
witness and defeats the oracle is `uncertified` and skipped (issue-1 test B).

## 7. Leakage boundaries

| place | reference content allowed? | enforced by |
| --- | --- | --- |
| LOW designer prompt | yes (the block) | `serialize_low` |
| `designer_calls.jsonl` | metadata only (length, hash, `[content withheld]`) | `Evidence.redacted` |
| `events.jsonl` | metadata only (`n_steps`, reason, selected cut) | `_lazy_reference`, `llm_stage_proposals` |
| `corpus.jsonl` | the compiled prefix `actions[:k]` (learner-visible by construction) | `_probe_stages` writes the candidate only |
| `traces.jsonl` | policy rollouts only; the candidate carries the prefix only | sessions are never traces |
| policy prompt / observations | never | the substrate's task prompt is fixed at construction; the Setup replays the prefix silently |
| skill induction (E3-SL) | never | E3-SL reads `corpus.jsonl` + `traces.jsonl` only |

Tests: 17/18/27, `test_leakage_reference_prefix_before_the_cut_only`, issue-2 tests.

## 8. Budget boundaries

Unchanged: every policy rollout is charged before it runs through `_rollouts` (cap 30 per task);
errored rollouts refunded. Designer calls are ledgered as `budget = designer` and not charged.
Reference sessions, guard replays and oracle runs are in-process sessions, never charged.

## 9. Failure behaviour

| situation | outcome |
| --- | --- |
| designer provider / network / parse failure | `infra_error` (re-run on resume), never a v0.4 fallback |
| no designer configured under `llm_v1` | `infra_error` (kind `config`) |
| 0 valid HIGH / LOW proposals | `dropped: no_valid_proposal` |
| expert error / stuck / timeout / no success | `reference {available: false, reason}`, failure-only designer |
| no reference provider wired | `reference {available: false, reason: no_provider}`, failure-only designer |
| every HIGH family infeasible / uncertified / no leverage | `dropped: no_leverage` |
| bracket exhausted / cap | `dropped: exhausted` / `budget` |
| no certified stage / no in-band stage | `dropped: uncertified` / `dead` / `too_easy` |

## 10. Remaining known limitations (recorded, not fixed)

- LOW reference representation: expert actions only; no observations, reasoning or alignment.
- No semantic identity across generated HIGH families, hence no cross-task warm start for them.
- LOW interventions are Stage-only; no assistive Rules.
- Learner-specific utility routing deferred; the behavioural regime is common to all learners.
- No task-type router; task semantics live in the designer context only.
- The v0.4 `in_band at d = 1` path accepts before recording a frontier (irrelevant under
  `llm_v1`, documented in the spec).
- The fidelity check of v0.4 staging (replayed observation equals the archived one) is not run
  for designer-selected cuts; the oracle guard still certifies every cut.
