# Audit: `handoff` (dead tasks → expert witness trajectory for demonstration-based induction)

Contract: expert shortest success rendered in the released trace format; used only by the AEA+Handoff arm.

## Reference

| what | where | reuse |
|---|---|---|
| Induction input: `traces_by_task: {task_id: [trace dicts]}`; `_pick_pair` sorts successes by `len(steps)` (shortest) and failures by length (longest); success-only input → `single_succ` | `scripts/induce_pair.py:81-134, 140-182` | import (the handoff trajectory is fed as one successful trace) |
| Trace step format the induction reads: `filtered_action.kwargs.text`, `filtered_observation.text`, optional `policy_raw_response` (`<think>…</think><action>…</action>`) | `envharness/reasoning_bank/induce.py:162-201` (`format_trajectory`) | import: the rendered witness carries `filtered_action`, `filtered_observation`, and a synthetic `policy_raw_response` of the form `<action>cmd</action>` only (no fabricated `<think>` text) |
| `Trace`/`Step` models (the JSONL the induction script reads via `TraceStore`) | `types.py:71-100, 172-197`, `storage.py:44-72` | import |
| Pilot: success-only induction control | `docs/pilots/e1pilot/p5/p5/induce_ss.py` | reference for the call shape (`_build_bank(condition, traces_by_task, llm_model, concurrency, embed_model, out_path)`) |
| Expert shortest success (3 attempts) | `docs/pilots/e1pilot/e1/p2b_run.py:30-40` | via `certs` |

## Invariants relied on

- ✓ `format_trajectory` falls back to `Action: …\nObservation: …` when `policy_raw_response` is absent
  (induce.py:198-200), so a witness without a think block is still valid input.
- The induction never reads `Trace.kind`; the handoff trace is marked `kind="exploration"` and
  `candidate_id="handoff"` so `io` can keep it out of the corpus.

## Decisions

- Handoff writes `handoff.jsonl` (one rendered `Trace` per dead task, `success=True`,
  `policy_model_id="expert:handcoded"`); the arm that uses it is a separate bank build, never the
  default corpus.
