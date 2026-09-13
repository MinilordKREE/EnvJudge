# `llm_v1` complexity audit (phase 2, implementation only)

Baseline: `05fc2fe` (phase-1 audit, v0.4 code). Measured with `git diff --numstat` on the
`aea-llm-vnext` branch after the implementation commit.

## Numbers

| quantity | value |
| --- | --- |
| new production LOC | `src/aea/designer.py` 573 lines (478 non-blank lines; docstrings included) + `src/aea/controller.py` +300 (six new methods, listed below) + `src/aea/config.py` +5 |
| old production LOC touched | 2 lines of v0.4-executed code changed: `start = self._start_dose(fam)` in `_try_family` (returns the identical v0.4 value under v0.4) and the controller import block; 2 lines added at the top of `_harden` and `_stage` (`if method_version == "llm_v1": return ...`); 1 constructor parameter (`reference=None`). Everything else in `controller.py` is new methods below the v0.4 code. |
| new modules | 1: `aea.designer` |
| new config fields | 1: `AEAConfig.method_version` (default `v0.4`; schema stays 4). No new `ImplConfig` field: evidence bounds are module constants (`designer.EvidenceBounds`). |
| new LLM calls per task | 1 (HIGH or LOW; 0 on band). Never a second call. |
| new policy rollout types | 0: the same `estimate`, `dose:<family>` and `probe` phases; the same 4 -> 8 rule and cap. The reference is an in-process expert session, not a rollout, and is not charged. |
| new method branches | 2 (the `method_version` switch at the two attachment points: HIGH family source, LOW candidate source). Inside `llm_v1`: no learner routing, no task-type routing, no library fallback, no midpoint fallback, no repair loop. |
| new event kinds | 3: `designer_evidence`, `reference`, `llm_stage_proposals` (+ a `source` field on `families` / `stage_candidates`). |
| new files in the run directory | 0 (`designer_calls.jsonl` existed for the v0.4 proposer; its rows gain `regime`, `method_version`, `evidence_sha256`, redacted `evidence`, `reference_used`). |

New controller methods: `_start_dose` (used by both versions), `_designer`, `_record_designer`,
`_harden_llm`, `_lazy_reference`, `_stage_llm`, `_probe_stages` (an `llm_v1` copy of the v0.4
probe walk, kept separate so the v0.4 walk is untouched).

## Can the method still be explained as Measure → Design → Control?

**YES.**

| paper-level primitive | code |
| --- | --- |
| 1. regime estimation | `aea.estimate` (unchanged) |
| 2. regime-conditioned LLM intervention design | `aea.designer` (`serialize_high` / `serialize_low`, `design_high` / `design_low`, the two tool contracts, `parse_high` / `parse_low`) |
| 3. empirical intervention control | `Controller._try_family` (guard, leverage test, bracket, cap; unchanged) and `Controller._probe_stages` (the 4 -> 8 probe on grounded stages) |

Everything else is infrastructure, not method: the evidence bounds, the goal extractor, the
redaction of the reference in the kept record, the event and ledger rows, the `method_version`
switch, the `ReferenceProvider` protocol and `ExpertReference` (a wrapper over the existing
`run_expert`), the compile / dedupe / guard reuse from `aea.stage`.

## What was deliberately not added

- LOW assistive Rules (a second calibration direction).
- A family-identity mechanism for generated families (warm start disabled instead).
- A fix for the v0.4 `in_band at d = 1` frontier omission (documented in the spec).
- Any fallback from `llm_v1` to the v0.4 library or midpoint heuristics.
- Any second designer role.
