# ALFWorld validator fidelity: final implementation audit

Date: 2026-09-15. Scope: Step 1 implementation correctness only.

## Safety and scientific boundary

Work was confined to `/home/kree/work/EnvJudge-aea-llm`, branch `aea-llm-vnext`,
starting from `5f959a4cd4002fd13aa3391e7f788829e4015dca` with a clean research
worktree. Main's HEAD remains `f97260589475bf4412f2310b1dfbcc1c34816547` and its
pre-existing ` ? third_party/envharness` status remains unchanged. No checkout,
reset, merge, rebase, clean, stash or pull was used.

No designer/policy API, D/I smoke, fresh-task screening or efficacy experiment
was performed. The historical-candidate audit uses local original-environment
replay, with no optimizer run or reference regeneration. The required existing
offline test suites also exercise deterministic optimizer fixtures, local experts
and handcoded/random policy paths; these are tests, not a new LOW experiment.
The previous smoke remains `IMPLEMENTATION_FAILURE` and supplies no efficacy
evidence. This correction does not reinterpret its feedback or results.

## Root cause, inventory and correction

The [pre-implementation inventory](AEA_ALFWORLD_STATE_CONTRACT_FIDELITY.md)
audits all 8 designer-advertised fields and all 13 real/bridge-schema fields,
including types, defaults, update semantics and observed generated-code uses.
The old unrelated `_SmokeInner._State` supplied only five fields, omitting the
advertised `goal_text`, `done` and `last_action_was_effective`. Its mutable
command list and `extras` dictionary were also shared between instances.

Allowed field access therefore raised `AttributeError`, selected mechanical
`REPAIR_CODE` feedback, and prevented candidates from reaching privilege checks.
The three archived candidates below demonstrate this defect; this does not imply
that their mechanisms deserve privilege admission.

Only `src/aea/families.py` changes in production: **8 added / 9 removed lines**.
`_SmokeInner` now constructs the actual `AlfworldEnvState` dataclass, preserving
the existing synthetic room, commands and fixed post-step count of 1. Other
fields and independent mutable containers derive from the canonical class.
`get_env_state` returns that concrete type. The three hook calls, observation and
transition fixture remain unchanged. The existing `identity_at_zero` function
already shares `_SmokeInner`, so it needs no compatibility edit.

This fixture checks field/API fidelity; it is not a world simulator. Unknown
attribute reads still raise `AttributeError`. Importing the canonical class does
not initialize optional ALFWorld/TextWorld/Gym/Torch dependencies.

## Permanent regressions

- `tests/unit/test_validator_contract.py`: 16 cases, 214 lines. Extracts fields
  from the actual designer paragraph, compares them with the real dataclass and
  bridge schema, and proves an inserted unsupported future declaration fails.
  Checks every canonical type/default, per-instance containers, `goal_text`,
  `done`, effectiveness True/False, d=0 identity, nonexistent-field rejection,
  exact historical hashes and active nonempty-goal/ineffective-action branches.
  Also checks import without optional simulator packages.
- `tests/unit/test_historical_validator_gates.py`: 5 cases, 105 lines. Uses exact
  historical sources with the real structural, identity and lexical functions;
  controlled consistent semantic FAIL/UNCERTAIN results test adapter routing.
  Those controlled results are explicitly not historical semantic scores.
  Proposal, certification and measurement callbacks are forbidden.
- Existing adapter tests use controlled FAIL/UNCERTAIN results to verify stops
  before solvability/policy, plus an actual offline PASS path into CONTROL.
  Real task110 integration verifies actual FAIL; the historical replay below
  separately verifies actual UNCERTAIN on the two lexical-pass sources.

## Exact historical candidate replay

| Candidate | Previous structural outcome | Corrected structural / d=0 | Actual lexical | Actual semantic in bounded replay | Solvability / policy |
| --- | --- | --- | --- | --- | --- |
| 126 D2 | Missing `last_action_was_effective` | PASS / PASS | PASS | UNCERTAIN | Not reached |
| 129 C1 | Missing `goal_text` | PASS / PASS | FAIL: embedded `go to countertop 2` | Not reached | Not reached |
| 129 I2 | Missing `goal_text` | PASS / PASS | PASS | UNCERTAIN | Not reached |

Exact archived source SHA-256 values, also asserted permanently in tests:

| Candidate | SHA-256 |
| --- | --- |
| 126 D2 | `ee62c351c25cdb805f849447db5ac28dfad0678ef2e60aa460133a5c9fe220d8` |
| 129 C1 | `58529c8cffb9de778977d1984e0ee4a49dd4353512f38b49fe7be88004fc6008` |
| 129 I2 | `d1caa3b5014b7c637fd72f44a28cfe198878acfb8fb89fea42af38d2fd4f2466` |

The two lexical-pass sources used the unchanged `probe_template` and
`screen_semantic_privilege`: 3 original episodes × 6 states (reset plus the first
5 recorded actions) × all 17 reachable doses = **306 probes each**, no probe
errors. Original resets were captured independently from unwrapped local
ALFWorld; they matched the reference's pre-action reset. Each replayed action,
raw observation, info, reward and ending flag matched its frozen identity trace.
Later privileged-reference observations were never admitted as public evidence.

Task 126 D2 leaves the initial observation unchanged. Its step-4 ineffective
action activates the reminder; the frozen grammar returns UNCERTAIN for the
unsupported text, first at dose 0.1875. Task 129 I2 is already UNCERTAIN at reset
(dose 0.0625) because its command preference lacks goal/current-episode
grounding. No admission bypass was observed. This does not claim the bounded
grammar identifies every individual relation in its text.

The actual semantic input hashes are:

- 126 D2: `8c3c5b14f5261047e76552f42f082cbc45286ad1a5b41f5537c5d0583b4e5a70`
- 129 I2: `4b620ba7f93533e4ec31ed77f0875abd6c6df53d0985e5081a33a2aea1d93504`

Local detailed replay inputs, result witnesses and provenance are retained at
`/tmp/validator_fidelity_downstream_audit/`; the standalone reproduction script
is `/tmp/validator_fidelity_downstream_audit.py`. These bounded diagnostics do
not certify later trajectory steps, unseen episodes or efficacy.

## Gate and method preservation

Admission remains structural/schema/API → identity/lexical privilege → semantic
privilege → solvability → policy. The lexical FAIL above reaches neither the
semantic callback nor later checks. Semantic FAIL/UNCERTAIN routing regressions
and existing integration tests block certification and measurement. No gate was
weakened to admit a historical candidate.

All 49 other baseline production files are byte-identical. In particular:

| Protected file | Unchanged SHA-256 |
| --- | --- |
| `src/aea/designer.py` | `9fa96689f9909d690963e44854ca530b1bcc36aec2300195f07a8f362e3e21c5` |
| `src/aea/low_optimizer.py` | `7c23cffc2d3cff5dc64a6dcf1aa8d4f0ca622de4309367e0aff03091a842b749` |
| `src/aea/semantic_low.py` | `53c0a9886b3adba1101a9144239bf6dc5a8f68cfaae8907df5151fae90b8b088` |
| `src/aea/semantic_privilege.py` | `ab0ba2aceffd53f408191105a4cfedb2dacc6136bd16defd03d553fad5b5dccd` |
| `src/aea/privilege_surfaces.py` | `c637d9519ed3db273262a123c075f830121a6c75932fbd030ae7e2744dcacee0` |
| `src/aea/controller.py` | `a89093dddf8be0c38f9576dc0fee73c9fcb46b531080303cdd8d4639cf312a3e` |
| `src/aea/config.py` | `7c47b36d3f2f3ee05983c758013ea42c5b3dce7238700e72ffdad2c1163c0afc` |
| `src/aea/evaluate.py` | `c16ed353e610d2e4a730ca4de7d072b79c2d60388f528f3999d7701c074e1a07` |
| `src/aea/witness.py` | `f287954433d79a6d6087d31e76473b3a18f6de7f7f4724321d18057bf236b5ae` |

Designer prompts, 2-call cap, feedback taxonomy, lineage, D/I isolation,
solvability, 4→8 evaluation, `assist_bracket`, freeze boundary, budgets and
acceptance remain unchanged. Correcting false structural feedback is the
intended implementation effect; **method-level behavior changed? NO**.

Historical preservation checks cover all 2,473 baseline tracked source/test/
script/doc/experiment files (only `families.py` changes) and all 105 files under
the two historical iterative-smoke run namespaces, including paid-call ledgers.
No historical artifact is overwritten or appended.

## Full offline validation and freeze

| Check | Result |
| --- | --- |
| Full unit suite | 319 passed, 11 integration tests deselected |
| Full integration suite, including real task110 | 10 passed, 1 existing optional RL-loader skip (Ray absent), 808.88s |
| Frozen semantic privilege benchmark | 14/14 matched: 3 PASS, 9 FAIL, 2 UNCERTAIN; task110 FAIL |
| Ruff | Passed |
| Ruff format --check | Passed; 179 files already formatted |
| Strict mypy | Passed; 95 source files |
| pre-commit --all-files | Passed |

Commands run from the research worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -m integration tests/integration
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/semantic_privilege_benchmark.py --output /tmp/validator_fidelity_semantic_benchmark.json
.venv/bin/ruff check --no-cache .
.venv/bin/ruff format --check --no-cache .
.venv/bin/mypy --cache-dir /tmp/validator_fidelity_mypy
UV_NO_SYNC=1 UV_OFFLINE=1 .venv/bin/pre-commit run --all-files
```

The commit containing this audit is the single focused correctness patch:
one production file, two new test files (21 cases / 319 lines), and two design
documents. No method version or preregistration is changed.

Final verdict: **VALIDATOR_FIDELITY_FIXED**. Structural validation now matches
the declared ALFWorld Rules state surface for the tested contract. This provides
no LOW efficacy claim. Stop here; no subsequent smoke or experiment is started.
