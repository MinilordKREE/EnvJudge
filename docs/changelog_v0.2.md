# aea v0.2 — distillation changelog (Phase A, 2026-09-10; no code changed yet)

Method of record: `docs/spec/AEA_v0.2.md`. Rule: the method fits in one box with two operators, one acceptance
rule, one guard, one budget and six method constants; everything else is protocol (scripts/, experiments/),
reporting (tables) or removed. Untouched: ledger, manifest, provider/price guards, `AeaSubprocessRunner`
attribution, resumability, corpus/trace formats consumed by envharness, the 100-step route for staged sessions.

Line budget: `src/aea` is 3,881 lines today, of which the method modules (controller, dose, probe, estimate,
certs, stage, knobs, priors, handoff, displacement, budget, config, io, substrate, runner) are 3,033;
v0.2 targets ≤ ~1,500 for the method code excluding llm/, ledger and io.

## Items

| # | now (v0.1, anchor) | v0.2 | why (evidence) |
|---|---|---|---|
| 1 | `estimate.py`: batches 4, 2, 2, … until P(regime) ≥ `confidence` 0.9 or `k_max` 16 (`estimate.py:103-126`; `config.py:26-29`) | keep the code; the method says "K = 16 with early stop when the regime is decided"; `confidence`, `batch_first`, `batch_next` move to `AEAConfig.impl` | efficiency detail: the same decisions at n ≤ 16; extreme tasks stop at 10 (E2 step 1: 9 of the 10 tasks, all estimated zero, stopped at n = 10; task 0 ran to 16, `runs/e2-Z/events.jsonl`) |
| 2 | two rules: `dose.classify` (NOEFFECT / ZERO / LOW / IN_BAND / HIGH at 4 → 8, `dose.py:32-74`) and `probe.classify` (dead / learnable / too_easy_stage on 4 rollouts, 1–3 of 4 accepted, `probe.py:48-54`) | ONE `evaluate(env)`: 4 rollouts, top-up to 8 unless 0/4 or 4/4, `in_band` iff 3–5 of 8; both operators call it | E2 step 1 (`experiments/alfworld_e2/results/e2_step1.md`, Z3): two of Z's five accepted stages were accepted on 1/4 and confirmed at 1/16 (task 18) and 3/16 (task 20); the three accepted on 2/4 confirmed at 7/16, 11/16, 9/16. A single 8-rollout rule removes the 1/4 acceptances |
| 3 | `next_dose` fixed schedule 0.5 → 0.75 → 0.875 → 0.9375 with step halving (`dose.py:77-107`, `config.py:45-46`) plus A′ priors' median start (`priors.py:7-10`) | bracketed bisection on [lo, hi] with the 4 → 8 rule, at most 4 bisections, order-violation stop; priors seed the bracket | Round 1 cap arithmetic (`experiments/alfworld_sl/LOG.md` 2026-09-08 observation): estimate 10–16 + leverage 4 + 4 + 4 (+8) reached the cap of 30 before the footer mask's cliff above 0.9375 on 22/30 tasks; P2b's non-monotone dose response (`docs/pilots/e1pilot/results/e1pilot/p2b_curves.csv`, `dose.non_monotone_pairs`) was recorded but never acted on; a bracket that stops on an order violation acts on it |
| 4 | `priors.py`: `skip_after` 5 ZEROs skips the d = 1 test, `demote_after` 5 no-leverage results demotes, start dose = median accepted (`priors.py:35`) | one counter per family: leverage rate over the tasks where it was evaluated at d = 1; families ordered by it; rate ≥ 0.9 over ≥ 5 tasks → the bracket starts at the family's last accepted dose | one sentence in the paper instead of three rules; A′ was pre-registered (Amendment 3) but never run, so nothing published depends on the three-rule form |
| 5 | certificate ladder `by_construction → R_pol → R_exp ×3 → R_hint` with per-axis rules (`certs.py:33`, `certs.py:263-305`; hint rollouts charged in `controller._certify_knob`) | one `solvable(env, witness_sources)`; sources = [own success replay, oracle]; the hint search leaves the method (kept as an optional witness source in `scripts/handoff_demos.py` for the hand-off extension only) | certificates were decisive only where the oracle existed: E2 task 11 was dropped because the expert verifier failed on all six prefixes (`runs/e2-Z/events.jsonl`, `stage_candidates.rejected`); Round 1's accepted knobs were all `by_construction` footer masks (`results/r1/arms/A/corpus.jsonl`); R_hint charges policy rollouts to the cap for a witness, which the box forbids |
| 6 | nine task statuses (`controller.py:52-63`) | three outcomes `accepted / kept / dropped` + `reason`; reports group by reason | reporting, not method; the Round-1 status table (`round1.md`, "Per-arm task statuses") is reproducible from outcome + reason |
| 7 | `too_easy_stage` (probe class) and `unresolved_budget_limited` (status) | `dropped` with reasons `too_easy` / `budget` | same |
| 8 | `handoff.py` called from the controller's zero path (`controller.py:563-575`, `with_handoff`) | `scripts/handoff_demos.py`, an extension arm run on a finished corpus | Round 1b decision: A+H confounds the baseline comparison (demos are oracle output, not the method's) |
| 9 | Displacement knob + builder (`knobs.py:105`, `displacement.py`, `EXEMPLARS` at `knobs.py:128`) | removed from the library; module and its tests moved under `docs/legacy/` | no leverage on any policy tried: Round 1 A / A-ex accepted only footer masks (`round1.md`, family of origin); the pilots' Displacement results (`docs/pilots/e1pilot/results/e1pilot/report.md`) never produced an in-band environment |
| 10 | Chain / Link | already out (P4 notes) | — |
| 11 | budgets `search / confirm / train / probe_cert / designer / eval / none` (`llm/types.py:24`) | `search` (every policy rollout, the cap) and `eval` (K = 16 confirmations, never written back); designer calls stay ledgered with `budget: designer` for cost reporting only | one budget in the method; `probe_cert` and `train` were never charged in any run (`results/r1/spend.json`, `results/e2_step1/spend.json`) |
| 12 | `AEAConfig` with 25 fields (`config.py:24-59`) | six method constants (`band_t`, `band_l`, `k`, `accept` = (3, 5) of 8, `probe` = (4, 8), `cap` = 30) + `impl` block (`batch_first`, `batch_next`, `confidence`, `max_bisections` = 4, `proposer_cap` = 2, `n_failed_rollouts` = 3, `max_candidates` = 6, `stage_config`, `oracle_max_steps`) | reviewer legibility; the hash of the whole config still goes into every manifest |
| 13 | corpus entry kinds `band / knob / stage` + `aea` block (`io.py:25-45`) | kinds `kept / knob / stage`; the `aea` block keeps family, dose, state hash, p̂ and the outcome reason; RL loader shape unchanged | `band` was the regime label, `kept` is the outcome; downstream (`induce_pair`, the RL loader) ignores the block |

## Removed tests / rewritten tests

- Deleted with the mechanism: `test_dose.py` schedule tests (`next_dose` halving, `non_monotone_pairs`),
  `test_priors.py` (skip / demote / median), `test_certs.py` ladder cases (R_pol → R_exp → R_hint order,
  hint rollouts), `test_displacement.py` (moved to `docs/legacy/`), `test_skills_handoff_io.py` hand-off part
  (moved to a script test), status-enumeration assertions in `test_controller.py`.
- Rewritten against the new surface: `evaluate()` (4 → 8 on both sides; 1/4 is not accepted), the bracket
  (bisection, order-violation stop, cap arithmetic 10 + 4 + 8 + 8 = 30 reaches at most two bisections after the
  leverage test), the family ordering by leverage rate and the ≥ 0.9-over-≥ 5 start rule, candidate
  construction (end + midpoint × 3 failed rollouts, dedupe, ≤ 6, latest first), `solvable()` with a policy
  witness, with the oracle only, and with no source (self-certify), the three outcomes and their reasons,
  the corpus round-trip with kinds `kept / knob / stage`.
- Kept unchanged: ledger, pricing, retry, attribution/runner, manifest, config hashing, io/trace formats,
  eval hook and driver tests.

## Phase plan

- **A (this document + the spec): STOP for the owner's look.**
- **B:** implement; method code ≤ ~1,500 lines; tests as above.
- **C:** LLM-free integration on real ALFWorld (fidelity, config-100, footer prompt snapshot, horizon boundary,
  expert-as-policy saturated path, prefix-then-random zero path, budget invariant, corpus round-trip); review
  packet; tag `aea-v0.2`. STOP.
- **D (owner go):** re-run the zero side on the E2 step-1 tasks under v0.2 (10 tasks, cap 30, Qwen3-8B; the
  shared K = 16 on disk is reused), ≈ USD 25, reported next to v0.1 as `e2_step1_v02.md`. Round 1 stays v0.1.

## Phase B status (2026-09-10)

Implemented as planned; module map in `docs/reuse/v0_2.md`. Method code (config, estimate, evaluate, bracket,
families, witness, stage, budget, controller, exemplars): 1,697 lines (from 3,033 in v0.1); `session.py`
(239) and `substrate.py` are counted as substrate glue with io/runner. Unit suite: 88 tests green, ruff and
mypy --strict clean.

Two details settled during implementation, both in `impl`, neither a method constant:
- `order_tolerance` = 0.2, not 0.25: under the bracket invariant every later dose lies between a known
  too-easy and a known too-hard dose, so a violation can only show as a LOWER dose harder than a higher one
  by more than the tolerance; with 4 first-batch rollouts the smallest such gap is 0.25 (2/8 at d = 1 vs 0/4
  lower), so 0.25 could never fire. 0.2 is below one rollout in four.
- The prior seeds the first bisection point only (owner clarification 3); the d = 1 test always runs and is
  the first entry of every bracket history.

Removed with their tests: `dose.py`, `probe.py`, `priors.py`, `knobs.py` (Displacement to `docs/legacy/`,
the rest folded into `families.py`), `certs.py` (ladder gone; sessions in `session.py`, the guard in
`witness.py`), `handoff.py` (to `scripts/handoff_demos.py`, tested through the script). The v0.1
integration suite is archived at `docs/legacy/test_alfworld_v01.py`; Phase C rewrites it against v0.2.
The v0.1 protocol scripts are frozen under `scripts/v0_1/` (run against tag `aea-v0.1`).

## Phase C status (2026-09-11)

Integration suite `tests/integration/test_alfworld.py` on the real ALFWorld bridge, LLM-free: 9 passed,
1 skipped (the RL corpus loader round-trip needs `ray`, not installed here), 0 failed — the 100-step route
(12 vs 62 policy steps), compiled-prefix fidelity on three archived failures, the footer-mask prompt snapshot
and cross-process nesting, the horizon-squeeze boundary, the expert-as-policy harden path (d = 1 test runs,
outcome dropped/accepted with a reason), the prefix-then-random stage path (guarded, deduplicated candidates
≤ 6; probe profile; corpus entry with state hash), the budget invariant (traces = charged = accounting), and
the eval hook on one released episode. Unit suite 88 green; ruff and mypy --strict clean. Review packet:
`docs/reuse/review_packet_v0_2.md`. Tag `aea-v0.2`. Phase D (the zero-side re-run on the E2 step-1 tasks,
≈ USD 25, driver `scripts/e2_v02.py`) waits for the owner's go.
