# Audit: `policy_skills` (skill injection for corpus-generation rounds ≥ 2)

Contract: the same retrieval as the released eval (top-5 MMR over bank_{r−1}); audit the released policy
for an injection hook; if none, wrap the released policy without touching third_party; identical for all arms.

## Reference

| what | where | reuse |
|---|---|---|
| Released eval: `bank.retrieve(task, k=top_k, mode, mmr_lambda)` once per episode on the task line, `build_memory_block(retrieved, style=inject_style)`, SkillOS template with history 4 | `experiments/alfworld/reasoning_bank_eval.py:74-160` | import the retrieval and the memory block builder |
| `Bank.load/retrieve` (cosine or MMR, embeddings via `embed_texts`) | `envharness/reasoning_bank/bank.py:64-152` | import |
| Corpus-protocol policy: `PolicyAgent(client, tools, task_prompt, action_format, max_history, temperature, prompt_builder_kwargs)`; system prompt = `task_prompt` for `think_action` (`_system_prompt`), history slicing keeps the system message | `policy.py:110-181, 209-230, 360-369`; built in `runner.py:146-156` from `PolicySpec` | **no injection hook exists** ✓ (the policy has no bank argument; `prompt_builder_kwargs` only feeds the webarena_rb builder) |
| `PolicySpec.task_prompt` is the whole system prompt for `think_action` | `runner.py:99-114`, `policy.py:360-369` | wrap: `policy_skills` renders `task_prompt + memory_block` per task before building the `EpisodeSpec` — no third_party change, identical text path for every arm |
| Pilot: in-process litellm wrappers for the eval (observe-and-route) | `docs/pilots/e1pilot/e1/p3a.py:39-95` | superseded by `AeaLLMClient` for the corpus protocol; the released eval keeps its own client path (Phase B decides whether the eval's `completion_with_retry` is wrapped the same way) |

## Invariants relied on

- ✓ The eval retrieves once per episode with the task text as the query (`reasoning_bank_eval.py:88-96`);
  `policy_skills` does the same for the corpus protocol, so rounds ≥ 2 see the same top-5 for a task
  as the eval would.
- Embedding calls are ledgered under budget `designer`-like accounting (`eval` for held-out); they are
  not policy rollouts.

## Decisions

- Injection point = `PolicySpec.task_prompt` (per task), because `SubprocessRunner` serialises the spec
  (runner.py:333-347) and the child rebuilds the policy from it — the memory block therefore travels to
  the subprocess unchanged.
