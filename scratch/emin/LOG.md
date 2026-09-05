# E-min LOG (UTC timestamps; append-only)

## 2026-09-05 — setup
- Substrate survey: switchHarness pilot venv (Python 3.12.9, openpyxl 3.1.5, rethinkskill 1.1.0 with the two performance/preview PILOT PATCHes documented in its LOG). Pool 76 = `results/frozen/spreadsheetbench_ids_train_pool.txt` (matches `datasets/spreadsheetbench/train/items.json`). Every verified_400 task has exactly one (init, golden) case.
- H_sub cache found: `rethinkskill/runs/pilot/nothink/spreadsheetbench/references/SUMMARY.json` → tasks 76, accepted 37, verifier_pass_any 44 → pass 37 / restate 7 / fail 32 as the brief states.
- envharness is not on disk; vendored `online_judge_eval.py` and `experiments/spreadsheetbench/corpus.yaml` fetched from github.com/google-research/envharness @ fab7d57441f06b75c73a900e04561d4d7600f361 (Apache-2.0). Upstream path is `envharness/bridges/spreadsheetbench/online_judge_eval.py` (the brief's `bridges/spreadsheetbench/...` lacks the package prefix).
- DEVIATION (environment): LibreOffice is not installed and `sudo` requires a password in this session. Started a no-root fallback: LibreOffice-still AppImage extracted under `~/.local/opt/lo/squashfs-root` (headless `soffice` binary). Until it works, arms needing c3 (A3, A4, A6, A8, R1) and W(a) are blocked; the rest can run.
- DEVIATION (environment): `pydantic-settings` was absent from the pilot venv; installed (2.15.0) into `/home/kree/work/switchHarness/.venv` (additive only).
