# Oracle actuator dossier (phase 3.5a)

One hand-verified, non-privileged assistive Rules family per phase-3.4 task with a verified
reference (85, 86, 92, 97, 99, 107, 109; 87 excluded: reference unavailable). Privileged
experimental assistance: an oracle ceiling for the LOW dose controller, never a method result and
never comparable to an automated method. Design: `docs/design/AEA_LOW_ORACLE_ACTUATOR_CEILING.md`.

Files: `<task>.md` (the auditable record: bottleneck, reference-derived evidence, mechanism, dose
semantics, fields used, privilege analysis, relation to the phase-3.4 proposal, code hash),
`<task>.rules.py` (the frozen family source with the `__DOSE__` placeholder; generated from the
registry `scripts/oracle_actuators.py`, which the tests pin byte-for-byte), `REGISTRY.json`
(specs + hashes), `validation.json` / `validation.md` (the LLM-free offline validation written by
`scripts/e6_oracle_offline.py` before the freeze: loader + smoke at d = 1, identity at d = 0 on the
smoke inner and on the real environment, structural privilege check against the frozen failures
and reference, the frozen reference replayed under W(0) and W(1), a frozen failure prefix replayed
at d in {0.25, 0.5, 0.75, 1} with support counts, the existing expert guard under W(1)).

**Design restriction (recorded).** The families were designed from the task goal, the normal
environment API / state, the frozen failed trajectories, the verified reference, a
HarnessEvolve-style diagnosis and the static Rules contract only. No phase-3.4 policy-response
measurement (which dose or Stage cut was too easy / dead on which task, which generated family had
leverage, which dose almost worked) selected a mechanism or a dose mapping: one rubric and one
coverage-dose semantics were fixed before any task was designed, no threshold is task-tuned, and
the current Qwen policy was not called before the freeze. All seven families were constructed,
validated and committed as one batch; after that commit no family code, dose semantics or
task-specific repair is permitted.

Mechanism classes: S explored-receptacle pruning (85, 109), P precondition gating (92, 97, 99,
107), G goal-decomposition annotation (86). Coverage dose for all: W(d) delivers the first
fraction d of the eligible support events / items; W(0) = E.
