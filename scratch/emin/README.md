# E-min — minimal validation experiment (pre-M0, temporary)

Everything under `scratch/emin/` is a temporary pre-M0 experiment. It will be archived to
`docs/emin/` when the `m0` tag is cut. Design: the E-min brief (2026-09-05); frozen
pre-registration in `PREREG.md` (sections 1–4 of the brief; committed before any rollout).

Layout

```
PREREG.md            frozen hypotheses / arms / verdict rules / budget gates
LOG.md               timestamped log of every step and deviation
configs/emin.yaml    frozen run configuration (paths, arms, models, K, temperature)
emin/witness.py      W probe (golden-vs-golden official path, h(t), answer_position parse)
emin/contracts.py    c1 unwrap_fence, c2 run_with_save_on_exception, c3 recalc
emin/score.py        both scoring paths (substrate = rethinkskill verify_spreadsheet;
                     official = vendored compare_workbooks after LibreOffice recalc)
emin/rollouts.py     one rollout = one DeepSeek call -> execute -> score both paths; ledger
emin/analyze.py      labels, unlock rates, dose table, A/A, P1–P8, verdict.md
emin/third_party/    vendored envharness online_judge_eval.py (Apache-2.0) + corpus.yaml
tests/               unit tests for score reasons and contracts
results/emin/        append-only outputs
```

Substrate: the switchHarness pilot (`/home/kree/work/switchHarness`): its venv, rethinkskill
1.1.0 + rethinkskill-spreadsheetbench 0.1.0, frozen pool-76 ids, parent skill, and the
answer-conditioned reference cache are imported/read in place, never copied or modified.
Secrets: `DEEPSEEK_API_KEY` via pydantic-settings from `EnvJudge/.env` (never read or logged).
