# E-obs — observation study of EnvRigger on ALFWorld (pre-M0, temporary)

Everything under `scratch/eobs/` is a temporary pre-M0 study; archived to `docs/eobs/` at tag `m0`.
This is an OBSERVATION study: EnvRigger (google-research/envharness @ fab7d574, `third_party/envharness`,
unmodified) runs as released on ALFWorld train tasks with DeepSeek V4 Pro as policy and designer; we
record what it proposes/validates/decides and add LLM-free probes (expert-plan witnesses, replay
certificates, recoverability). Pre-registration: `PREREG.md` (committed before the first Phase-1 rollout).

Layout: see the E-obs brief §5. Phase gates: STOP after Phase 0 and after Phase 2 for owner review.

Runtime: `~/eobs_venv` (Python 3.12; envharness -e, alfworld[full], textworld 1.7.0), game data in
`~/eh_alfworld_data`. Secrets via pydantic-settings from `EnvJudge/.env` (never read or logged).
