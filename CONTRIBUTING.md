# Contributing

Read `docs/CONVENTIONS.md` first. Every rule in it is checked in review.

## Pull request checklist

- [ ] `make check` passes locally (ruff, ruff format, mypy --strict, offline tests).
- [ ] New or changed behaviour has a unit test that runs offline (no LLM, no ALFWorld).
- [ ] No `print` in `src/` outside `aea/cli.py`; no secret value in any log, trace, ledger,
      manifest or test fixture.
- [ ] Every file adapted from a reference repo has the provenance header (repo, sha, original
      path, license, changes) and is listed in `THIRD_PARTY_NOTICES.md` and the module's
      `docs/reuse/<module>.md`. Fresh files say "No reference source".
- [ ] Nothing under `third_party/` is edited; nothing imports from `docs/pilots/` at runtime.
- [ ] Any change to a record shape (trace envelope, ledger row, manifest, config) bumps the
      corresponding schema version and updates `docs/CONVENTIONS.md`.
- [ ] Any change to `configs/pricing.yaml` bumps `pricing_version` and updates `as_of`.
- [ ] Infra failures raise `InfraError`; task outcomes raise `TaskFailure`; neither is caught and
      turned into a default value.
- [ ] `uv.lock` is updated (`make lock`) if `pyproject.toml` dependencies changed.

## Commit hygiene

- Commit messages describe the behaviour change, not the file list.
- Never commit `.env`, `runs/`, or `.cache/`. Pre-commit refuses `.env` explicitly.
