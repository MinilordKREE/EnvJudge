# PREREG_LOW_ORACLE_ACTUATOR — oracle actuator ceiling for the LOW dose controller (phase 3.5a)

Written and committed after the actuator freeze and before the first current-policy call. Design:
`docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md`. Dossier: `experiments/alfworld_e6/oracle_actuators/`.
Phase 3.4 (`PREREG_LOW_ASSISTIVE_RULES.md`, decision RULE_GENERATION_FAILURE) is frozen and is not
re-run. **Oracle / ceiling experiment: the families are privileged experimental assistance; the
result is a bottleneck localisation, never AEA / llm_v1 / LOW performance and never a method
comparison.**

## Mechanistic question

If a valid, non-privileged, semantically appropriate assistive Rules family is supplied to the
existing LOW dose controller (phase 3.4, frozen), does the controller convert it into
K16-confirmed useful environments? Generation bottleneck vs actuator / control bottleneck.

## Frozen inputs

| item | value |
| --- | --- |
| tasks | 85, 86, 92, 97, 99, 107, 109 (phase-3.4 tasks with a verified reference; 87 excluded); ascending; no substitution |
| evidence | phase-3.4 shared stage `runs/e6-ar-shared` (prospective `zero` on all 7; the 10 estimate rollouts per task; the exact rich reference with `reference_id`; goal) — reused, never regenerated; sha256[:16] of `shared.jsonl` / `traces.jsonl` / `privileged_references.jsonl` recorded in every manifest |
| actuators | one family per task, class S / P / P / P / P / P / S for 85 / 86 / 92 / 97 / 99 / 107 / 109 (86 = G), frozen at commit **23e87aa** (`oracle_actuators/*.rules.py`, hashes in `REGISTRY.json`); offline validation `oracle_actuators/validation.md`: 7 / 7 offline-valid (validation.md: every family loads, identity at 0 on the smoke inner and the real environment, privilege check clean, reference wins under W(0) and W(1) with 0 blocks, support monotone in d, expert guard under W(1) ok) |
| controller | `Controller` with `method_version = "llm_v1_assistive_rules"` at the freeze commit, the experiment-side `assist_provider` injected (no designer, no LLM call); the phase-3.4 path otherwise byte-identical: oracle guard at d = 1, 4 -> 8 at d = 1, `too_hard` at d = 1 = ORACLE_NO_LEVERAGE (`no_leverage`), `in_band` = accept, `too_easy` = mirrored bracket inward (<= 4 bisections, `dose_order_violation`), a leveraged family that does not land ends the task |
| acceptance / bands | `AEAConfig` defaults: 0/4 too_hard, 4/4 too_easy, 1-3/4 -> 8; 0-2/8 too_hard, 3-5/8 accept, 6-8/8 too_easy; B_T (0.4, 0.6), B_L (0.2, 0.8) |
| budget (matched) | cap 30 charged rollouts per task INCLUDING the 10 replayed estimate rollouts (FrozenSubstrate, charged, no API call) = at most 20 new adaptation rollouts per task, exactly the phase-3.4 arm-B rule; no extra budget, no grid, no repair, no second family |
| policy | Qwen3-8B via OpenRouter, provider pin `alibaba`, thinking off, temperature 0.5 (E3 `policy_qwen()`), 50 steps |
| K16 | every search-accepted environment, K = 16, evaluation-only (`stage_confirm`, default reset for a Rules candidate), never fed back |
| runs | `e6-oa-O1` (tasks 85, 86, 92, 97) and `e6-oa-O2` (99, 107, 109) as two processes, 8 episodes in flight each (16 total), rows merged as the single oracle arm O; `e6-oa-confirm` at 16 |
| USD cap | **30** over `runs/e6-oa-*` (probes <= 7 x 20 x 0.06 ≈ 8.4, confirmations <= 7 x 16 x 0.05 ≈ 5.6); checked before every stage and task; STOP at the cap |
| substrate | released envharness @ fab7d574; `configs/corpus_aea.yaml`; original reset (no Setup prefix, no Stage) |

## Gates (any failure = INCONCLUSIVE by protocol failure)

Per process: runtime `method_version`; manifest stamped `oracle_actuator_ceiling` with the frozen
family hashes; `estimate` equals the shared estimate; `reference_id` equals the shared reference;
no designer call (`designer_calls.jsonl` absent); exactly one family per task and its code sha256
equals the frozen file with `source = oracle`; first probe of the family at d = 1; no guard
`by_construction`; no Setup prefix in any trace or corpus record; no Stage / family / cascade
event; <= 30 charged rollouts per task including the replayed 10; `reference` events only on
`zero` tasks; provenance-based leakage audit (record hash == reference event; reference block
absent from every kept file; expert never re-run for evidence); every task has an outcome;
`src/aea` unchanged from the freeze commit.

## Outcomes

Primary: **number of the 7 tasks with a K16-confirmed learnable oracle environment** (search
accept 3..5 of 8 AND p16 in B_L). Secondary: oracle family availability (a family exists and
validates at provide time), offline validity, d = 1 leverage (verdict at d = 1 not `too_hard`),
search acceptance, K16 target (B_T), budget exhaustion, `dose_order_violation`,
leveraged-unresolved, no leverage, number of unique doses, observed response regimes along the
dose, policy rollouts and USD (no designer cost). Six-level classification and the
generated-vs-oracle decomposition table per task against the FROZEN phase-3.4 rows
(`results/e6_low_assistive_rules_data.json`): generated valid / leverage / accepted / K16 vs
oracle available / leverage / accepted / K16, with the interpretation (generation failure
recovered by oracle actuator; both have no leverage; oracle has leverage but controller cannot
land; oracle delivers a useful environment). Phase-3.4 arm A (Stage control) shown descriptively.

## Decision rule (exactly one; applied mechanically, in this order)

1. INCONCLUSIVE: a gate fails, or a provider / infrastructure / budget interruption, unexpected
   environment breakage or corrupted frozen evidence. Never for weak performance.
2. ORACLE_CONSTRUCTION_INFEASIBLE: no scientifically defensible non-privileged family available
   on >= 2 of the 7 tasks (NO_ORACLE_FAMILY or invalid at provide time).
3. GENERATION_BOTTLENECK_SUPPORTED: family available on >= 6 / 7 AND d = 1 leverage on >= 5 / 7
   AND >= 3 / 7 K16-confirmed learnable.
4. ACTUATOR_EXISTS_BUT_CONTROL_REMAINS_LIMITING: available on >= 6 / 7 AND d = 1 leverage on
   >= 5 / 7 AND < 3 / 7 K16-confirmed learnable.
5. ASSISTIVE_RULES_ACTUATOR_NOT_SUPPORTED: d = 1 leverage on < 5 / 7 (with availability >= 6).
6. Any other combination is reported as INCONCLUSIVE (not a pre-registered state).

The ceiling criterion (3 / 7 confirmed), the bands and the classification are not changed after
the results; a 2 / 7 result is reported under rule 4 and discussed descriptively only. No LLM
repair, no EnvHarness-style refinement, no cascade, no full E6, no E6-SL follows from this phase.
After the run: `results/e6_low_oracle_actuator.md` + `.jsonl`, LOG, commit, push, STOP.
