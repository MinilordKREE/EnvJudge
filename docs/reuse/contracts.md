# Binding module contracts (from the implementation prompt §3; stand-in for docs/spec/AEA_v2.md)

- `estimate`: batches [4, 2, 2, …], stop when any of P(p<0.2), P(0.2≤p≤0.8), P(p>0.8) ≥ 0.9 or n=16;
  returns regime, p̂, all traces; environment errors are retried once and never counted.
- `knobs`: `Knob(make(d) → rules_code | in_env_actions, axis, direction, nested: bool)`; exemplars are
  the single source of truth for both the few-shot prompt text and the runnable classes (rendered,
  not duplicated). FooterMask uses `sha256(f"{task_id}:{step}")` buckets (nested by construction);
  HorizonSqueeze checks `raw.success` before truncating and returns `truncated=True`; Displacement
  as piloted. Proposer output is validated: loads via `code_loader`, references `DOSE`, LLM-free
  smoke at d=1, certificate at d=1 unless O-axis.
- `dose`: one acceptance rule everywhere — 4 rollouts; 4/4 NOEFFECT; 0/4 ZERO; else top up to 8;
  accept iff 3–5/8; 1–2/8 lower, 6–7/8 raise; leverage test = the same rule at d=1; step 0.25
  halving; ≤4 evaluations; non-monotone responses logged.
- `stage`: compile prefix (drop ineffective, append `look`) → build Setup with `stage_budget=100` via
  `reset_options.config_path` → replay → certify that environment (expert ×3) → candidate id =
  `task_id + sha256(compiled prefix)`; fidelity check per task.
- `probe`: latest-first, 4 rollouts each; 1–3/4 accept and stop; 4/4 → `too_easy_stage` (recorded,
  not accepted); all non-learnable → `unresolved`.
- `certs`: ladder R_pol → R_exp(×3) → R_hint(≤3, charged to `search`); Session `done` reads
  stack-level terminated/truncated.
- `handoff`: expert shortest success rendered in the released trace format; used only by the
  AEA+Handoff arm.
- `budget`: per-task per-round hard cap 30 on `search`; `confirm` and `train` are separate ledgers;
  `BudgetExhausted` stops the task with status `budget_cap_hit`; no cross-task reallocation.
- `controller`: the loop in spec §9; resumable per (task, phase, attempt); task-level concurrency;
  corpus entries `band | knob | stage` with the `aea` metadata block; unresolved/frozen go to
  accounting only.
- `io`: corpus writer/reader round-trips through the envharness RL corpus loader and the
  orchestrator's `Candidate`; trace writer uses `TraceStore` format.
- `config`: one frozen `AEAConfig` (c=0.9, K_max=16, batch schedule [4,2,2,…], cap=30, B_T=[0.4,0.6]
  as 3–5/8, B_L=[0.2,0.8], dose step 0.25 halving, ≤4 dose evals, candidate fractions
  {1, 3/4, 1/2, 1/4}, ≤6 candidates, probe K=4, stage_budget=100, certificate attempts expert=3 /
  hint=3); its hash goes into every manifest.

Do-not list: no edits under `third_party/`; no runtime monkeypatching of envharness internals
(observe-only proxies allowed and documented); no runtime imports from `docs/pilots/`; no LLM calls
in unit tests; no acceptance decision by an LLM; no K16 write-back; no cross-task budget
reallocation; no Chain/Link axes in v1.
