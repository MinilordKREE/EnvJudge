# Frozen used-task audit for iterative LOW viability

**Smallest unused train bridge-seed task ID: 130.** The first 20 unused IDs are
**130–149**, ascending. Actual historical rollout records independently contain
exactly **0–129**. No prospective task content was inspected.

## Scope and reproducibility

The read-only scan hashed 55,841 files (12,666,611,588 bytes)
across both worktrees: all run and experiment artifacts, archived ALFWorld pilots,
real integration sources/fixtures, and task-universe implementation. The full local
source inventory SHA-256 is `040566eec200d16345743eddb2ac7e33a996b81775043edbf08efe4b858689fa`.
The compact audit links exact script and full-inventory hashes, all-consumption
evidence metadata, and three real rollout-trace files that together independently
witness every consumed ID. Large local manifests contain paths/hashes/numeric
metadata only; raw prompts and traces are not exported.

## Domain separation

- `rollout_seed` and `reset_seed` identify actual bridge use. Historical task labels
  produce the same 130-ID union; no ambiguous extra ID is silently excluded.
- Task 129's C2 designer request has RNG `seed=130` and attribution `task_id=129`,
  `budget=designer`. This does **not** consume train task 130.
- E0/E3-SL/R1 evaluation seeds refer to `eval_in_distribution` and
  `eval_out_of_distribution`; they are separate from the train-split universe.
- Reference sampling and bank extraction/matching RNG seeds are not bridge seeds.
- Fake unit-fixture identifiers are excluded. Real integration calls/fixtures
  cover 0, 1, 2, 5, 8, 9, 14, 20, 110, already inside the consumed set.
- Supplemental task-ID-array and CSV-label parsing found no additional IDs.

Generic seed review left **zero unclassified values**. The immutable audit uses
the first 20 nonnegative integers absent from the consumed set; it does not infer
freshness by taking a remembered maximum. All prior smokes retain their previous
conclusions. This audit used no API call or fresh environment reset and changed
neither worktree.
