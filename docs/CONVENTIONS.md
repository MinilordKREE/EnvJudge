# Conventions

These rules apply to every module of `aea`. They are copied from Project One's `ahd` M0
(`docs/reuse/M0.md` records the provenance) and adjusted where aea differs.

## Toolchain

- Python 3.12 (`requires-python = ">=3.12"`). `uv` manages the environment; `uv.lock` is
  committed and CI installs with `uv sync --locked`. ALFWorld/TextWorld are an optional extra
  (`make setup-alfworld`) that CI never installs.
- `src/` layout: the package is `src/aea`, built with hatchling. `third_party/envharness` is a
  git submodule at fab7d574, imported as the editable path dependency `envharness`, never edited.
- `ruff` lints and formats (line length 100); `mypy --strict` with the pydantic plugin checks
  `src/` and `tests/`; `pytest` runs tests. `make setup lint typecheck test` are the entrypoints.
  Pre-commit runs ruff, mypy, whitespace and private-key checks, and refuses any commit that
  stages `.env`.
- GitHub Actions runs lint, format check, mypy and the offline unit tests on every push and
  pull request. Integration tests (`@pytest.mark.integration`, LLM-free but ALFWorld-backed) are
  deselected by default and run with `make test-integration`.

## Configuration

- Run configuration is a YAML file validated into pydantic v2 models (`aea.core.config.RunConfig`).
  Every model extends `StrictModel` (`extra="forbid"`, frozen). No dict configs, no `.get()` with
  inline defaults. Every config file carries `schema_version`.
- The method's own frozen parameters are one `aea.config.AEAConfig`; its SHA-256 goes into every
  manifest (`aea_config_sha256`).
- `require_clean_tree` defaults to `true` for `kind: confirmatory`; a confirmatory run on a dirty
  tree refuses to start. Untracked files count as dirty.
- The config hash recorded in the manifest is the SHA-256 of the canonical JSON of the validated
  model (comments and key order do not change it; any default does).

## Secrets

- Secrets are read only by `aea.settings.Settings` (pydantic-settings) from the environment or
  `.env`. `.env` is gitignored; `.env.example` lists the variable names with empty values.
- Nothing in `src/` prints, logs, or writes a secret. Values are `SecretStr`; use
  `aea.settings.mask_secret` if a config echo must show one.
- A key is only ever sent to its own host (`aea.llm.client.ALLOWED_PAIRS`): `OPENROUTER_API_KEY`
  to `https://openrouter.ai/api/v1`, `DEEPSEEK_API_KEY` to `https://api.deepseek.com` and only
  for `deepseek*` models.

## Provenance headers

Every file reused or adapted from a reference repository starts with a module docstring naming
the source (`Adapted from: <owner>/<repo> @ <sha>`, `Original path`, `License`, `Changes`).
Files with no reference source say so. `THIRD_PARTY_NOTICES.md` lists every source repo, its sha,
license and the files reused; `docs/reuse/<module>.md` gives per-module provenance tables and the
envharness interfaces relied on, with file:line evidence.

The pilots under `docs/pilots/` are archived oracles: their behaviour is ported with tests whose
fixtures come from their archived outputs; nothing imports from `docs/pilots/` at runtime.

## Errors

- No silent fallbacks. A missing file, a corrupt ledger row, an unknown model in the price table,
  or a response without a usage block raises; it is never patched over with a default.
- `InfraError` (provider 429/5xx, network, timeouts, missing files, git, a dead engine) and
  `TaskFailure` (the policy or harness failed the task) are never conflated.
  `BudgetExhausted(TaskFailure)` names the budget that ran out; it is part of the estimand.
- `ConfigError` is raised only before a run starts. CLI exit codes: 0 ok, 2 `ConfigError`,
  3 `InfraError`, 4 `TaskFailure`.

## LLM calls

- Every provider implements `aea.llm.provider.Provider.complete(ChatRequest) -> ChatResponse`.
  The production client is `aea.llm.client.OpenAICompatibleClient` (OpenRouter or DeepSeek);
  envharness's policies and designer reach it through `aea.llm.envharness_client.AeaLLMClient`
  (`client_factory`), which reads the attribution from `AEA_*` environment variables the
  controller sets per episode.
- `reasoning_effort` is a top-level request parameter. DeepSeek thinking is toggled with
  `extra_body.thinking`; on OpenRouter, `reasoning: {enabled: false}` is sent unless a reasoning
  effort is requested.
- OpenRouter calls carry `provider.order=[pin]` with `allow_fallbacks=false` and `usage.include`.
  A response from another provider, or an upstream cost that disagrees with the price table by
  more than `cost_tolerance`, raises `InfraError` after the ledger row is written.
- Retried: HTTP 408, 409, 425, 429, every 5xx, connection errors, timeouts. Never retried:
  400, 401, 403. Backoff `min(max_delay, initial * multiplier**(attempt-1)) + uniform(0, jitter)`
  bounded by `max_attempts` and `total_timeout_s`. Every retry writes an `infra_retry` row.
- No response cache in experiments.

### Cost ledger

`ledger.jsonl`, append-only, one row per event (`aea.llm.ledger.LedgerRow`, schema v1):
`schema_version, ts, run_id, event, phase, budget, arm, task_id, seed, model, provider,
prompt_tokens, completion_tokens, cached_tokens, reasoning_tokens, latency_ms, usd,
pricing_version, pricing_tier, upstream_cost, attempt, status_code, error_kind, error,
request_sha256, rollout_uid, steps, success`.
Events: `call`, `rollout` (one policy episode charged to a named budget), `infra_retry`,
`infra_failure`, `task_failure` (`error_kind == budget_exhausted` counted on its own).
Budgets: `search` (capped per task per round), `confirm`, `train`, `probe_cert`, `designer`,
`eval`. `usd` comes from `configs/pricing.yaml` at call time; raw token counts and the
`pricing_version` are always stored.

## Run directory

`runs/<run_id>/` with `run_id = YYYYMMDDTHHMMSSZ-<6 hex>` unless supplied: `manifest.json`
(schema v1: run id, seed, config hash, `aea_config_sha256`, git sha and dirty flag, envharness
sha, versions), `config.resolved.yaml`, `events.jsonl` (controller events, envelope below),
`ledger.jsonl`, `log.jsonl`, and the envharness-format `traces.jsonl` / `corpus.jsonl` written
by `aea.io`. A run directory is never overwritten.

## Trace envelope and schema versions

Every `events.jsonl` line is `{"schema_version", "seq", "ts", "run_id", "kind", "payload"}`;
`seq` is contiguous from 1. Bump rule for every versioned schema (`TRACE_SCHEMA_VERSION`,
`LEDGER_SCHEMA_VERSION`, `MANIFEST_SCHEMA_VERSION`, `CONFIG_SCHEMA_VERSION`): any field added to
or removed from the envelope or record bumps the version; a new `kind` or a new payload key does
not.

## Logging

stdlib `logging`, loggers named `logging.getLogger(__name__)`. No `print` in `src/` outside
`aea/cli.py` (ruff T20). `aea.logs.configure_logging` installs a console handler and a JSON-lines
file handler per run.

## Tests

- Unit tests are fully offline: the transport is scripted (`tests/conftest.py`); no LLM, no
  ALFWorld. They pass with no `.env`; CI sets dummy keys.
- Integration tests need the `alfworld` extra and `ALFWORLD_DATA`; they are LLM-free.
- Tests that need git create a throwaway repository in `tmp_path`.
