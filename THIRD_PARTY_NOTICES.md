# Third-party notices

## envharness (google-research/envharness)

- Location: `third_party/envharness` (git submodule); imported as the editable path dependency `envharness`.
- Upstream: https://github.com/google-research/envharness
- Pinned commit: `fab7d57441f06b75c73a900e04561d4d7600f361` (2026-08-20)
- License: Apache License 2.0 (see `third_party/envharness/LICENSE`)
- Use: run as released (bridges, Setup/Rules harnesses, orchestrator, runner, ReasoningBank induction and
  evaluation). No file under `third_party/envharness/` is modified. `aea` wraps its `LLMClient` ABC
  (`src/aea/llm/envharness_client.py`) and consumes its types; nothing is copied. The vendored ALFWorld
  `base_config.yaml` inside it carries its own upstream license; `aea` ships a copy with only the
  `max_nb_steps_per_episode` entries changed (`configs/alfworld_config_100.yaml`, Phase B).

## Project One: agent_harnesses_diagnostic (`ahd`)

- Upstream: the owner's own repository (MinilordKREE/agent_harnesses_diagnostic), commit
  `db5807f1f0608184b141c80d37488e1c842d1d49`; MIT.
- Files adapted: the M0 scaffold listed in `docs/reuse/M0.md` (errors, settings, logs, core/*, llm/*,
  tests/conftest.py, tooling). `ahd` in turn adapted the functions below from public repositories; those
  attributions are preserved in the module docstrings:

| Repo | Commit | License | aea files |
|---|---|---|---|
| microsoft/AutoSaddler | `30e20ce004486c58e7ee97c66182a8d0d41ec90e` | MIT | `core/hashing.py`, `core/io.py`, `core/trace.py` |
| RUCAIBox/Evo-Bench | `e1dc9386a193cab1ee8630824c085e5e26d0c730` | Apache-2.0 | `core/hashing.py` (dir hash), `core/io.py` (jsonl), `llm/retry.py` (status set) |
| scaleapi/vero | `0b0e86764d836c456aee5b8dff80d765fdbba77c` | MIT | `core/config.py` (`StrictModel`), `llm/retry.py` |

## Archived pilots

- `docs/pilots/emin/emin/third_party/online_judge_eval.py`: copy of envharness's
  `online_judge_eval.py` at the pinned commit, Apache-2.0; provenance header in the file.

## Obligations

- MIT: retain the copyright and permission notice in any reused file (the per-file provenance header)
  and keep this notices file in distributions.
- Apache-2.0 (envharness, Evo-Bench): retain attribution notices, reproduce any NOTICE contents for
  reused portions, and mark modified files as changed (the only modified copy is the ALFWorld config
  with the step cap changed, marked in its header).
