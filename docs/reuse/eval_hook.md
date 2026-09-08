# Audit: `evalhook` (accounting and guards for the released evaluation)

Owner decision (2026-09-07 review): the released `reasoning_bank_eval.py` keeps its own
`completion_with_retry` path; accounting is in-process; provider pin and reasoning setting are
supplied without editing the eval; a guard mismatch aborts the run.

## What the released path offers

| what | where | finding |
|---|---|---|
| The eval's LLM call | `experiments/alfworld/reasoning_bank_eval.py:118-127` | `completion_with_retry(messages=[...], **completion_kwargs(cfg["model"]["name"], temperature, max_tokens, api_key))` |
| `completion_kwargs` | `envharness/infra/model.py:434-453` | returns model, `drop_params`, provider auth, temperature, max_tokens — no request extras (`client_kwargs` 323-360) |
| The yaml `model` block | `experiments/alfworld/reasoning_bank_eval.yaml` | `name`, `temperature`, `max_response_tokens` only; extra keys are not forwarded |
| `litellm.success_callback` | litellm 1.99 `Logging._success_handler_body` (custom function branch) | called in a logging thread inside `try/except`: it can neither route nor abort |

So the eval yaml cannot carry a provider pin, and a success callback cannot enforce one. The pilot's
form (docs/pilots/e1pilot/e1/p3a.py `install_wrappers`) is kept: an in-process wrapper of
`litellm.completion` that routes and accounts. It is the one observe-and-route proxy in aea and is
confined to the evaluation driver.

## `aea.evalhook`

- `EvalHook.route(kwargs)`: the released kwargs plus `api_base`, the key, and `extra_body` from
  `build_wire_request` (provider pin, `usage.include`, reasoning setting: `None` sends nothing for the
  Gemini arms, `False` switches Qwen's reasoning off).
- `EvalHook.account(response)`: one `call` ledger row on budget `eval` (attribution from the
  contextvar when the driver binds one, else `phase=eval`), priced from `configs/pricing.yaml`.
- Guards: provider ≠ pin or |upstream cost − table| > tolerance → `infra_failure` row,
  `guard_failure.json` in the run directory, `InfraError`. The released eval records a per-episode
  error and continues, so the driver calls `check_guard(run_dir)` after `rbe.main` returns and treats
  the marker as an abort of the whole run.
- `install(hook)` swaps `litellm.completion` in the driver process; the eval's worker processes are
  forked from it and inherit the wrapped module.

Tests: unit (`tests/unit/test_evalhook.py`: routing, rows, both guards, the wrapper) and integration
(`tests/integration/test_alfworld.py::test_eval_hook_on_one_released_eval_episode`: one released
episode on the real bridge with a scripted litellm beneath the hook, LLM-free).

## Owner requirements (2026-09-07) and where they are met

1. **Byte-identical wire request except routing.** `EvalHook.route` may add or replace only
   `ROUTING_KEYS` = {api_base, api_key, extra_body, reasoning_effort, model, drop_params}; an
   assertion in `route` enforces it and `test_wire_request_is_byte_identical_except_routing`
   proves messages, temperature and max_tokens (and therefore the released history slicing, which
   happens before the call) reach litellm unchanged.
2. **One pipeline for every arm.** `aea.evaldriver.run_eval` is the only way held-out numbers are
   produced: it installs the hook, binds `budget=eval` with the arm label, calls the released
   `main`, restores litellm, and aborts on the guard marker. N and R go through it exactly like A
   (`test_driver_installs_the_hook_for_every_arm`). The same Google endpoint pin is therefore
   applied to the corpus stage (substrate) and the eval stage (hook) — AI Studio and Vertex are
   different endpoints on OpenRouter and are never mixed.
3. **Guard failures are never retried.** The guard raises `GuardError(InfraError)`, which is not
   one of litellm's transient classes the released `completion_with_retry` / `LiteLLMClient` retry
   (`test_guard_error_is_never_retried_by_the_released_client`); the released eval records the
   episode error, the marker makes the driver abort the whole run.
