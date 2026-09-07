# EnvJudge → `aea` (Asymmetric Environment Adaptation)

`aea` is a small controller that adapts ALFWorld environments to a policy's regime on top of the
released [envharness](https://github.com/google-research/envharness) substrate (submodule at
`fab7d574`, untouched): sequential regime estimation, dose-searched knobs for saturated tasks,
certified hindsight staging for zero tasks, witness certificates, named rollout budgets and an
append-only ledger. The substrate runs the environments and the released downstream (ReasoningBank
induction and evaluation); `aea` only decides what environment each task gets.

The pilots that validated every behaviour here (E-min, E-obs, E-obs-F, E1-pilot P1–P5) are
archived under `docs/pilots/` (tag `m0`); the E1-SL pre-registration lives in
`experiments/alfworld_sl/`.

## Layout

```
configs/            pricing.yaml (versioned prices), run configs
docs/               CONVENTIONS.md, spec/ (spec of record), reuse/ (per-module provenance and
                    envharness interface audits), pilots/ (archived scratch experiments)
src/aea/            the package
  errors.py settings.py logs.py cli.py
  core/             hashing, atomic io, StrictModel + RunConfig, run context, manifest, event trace
  llm/              types, retry, pricing, ledger, OpenAI-compatible client with provider guard,
                    fake provider, envharness LLMClient adapter
  (Phase B)         config, budget, estimate, certs, knobs + exemplars, dose, stage, probe,
                    handoff, policy_skills, io, controller
third_party/envharness   git submodule (Apache-2.0), imported as the `envharness` path dependency
experiments/alfworld_sl  configs and scripts for E1-SL (PREREG6.md)
tests/unit          offline (no LLM, no ALFWorld)
tests/integration   LLM-free, needs the `alfworld` extra; @pytest.mark.integration
```

## Setup

```
cp .env.example .env                 # OPENROUTER_API_KEY, DEEPSEEK_API_KEY
git submodule update --init third_party/envharness
make setup                           # uv sync --locked, pre-commit install
make setup-alfworld                  # optional: ALFWorld/TextWorld for integration tests
export ALFWORLD_DATA=~/eh_alfworld_data
```

## Checks

```
make test                 # offline unit tests
make lint typecheck       # ruff, ruff format --check, mypy --strict
make test-integration     # ALFWorld-backed, LLM-free
```

License: MIT (`LICENSE`); third-party notices in `THIRD_PARTY_NOTICES.md`.
