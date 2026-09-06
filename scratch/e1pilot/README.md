# E1-pilot — Qwen3-8B policy switch, regime map, structural-hardening dose pilot (pre-M0, temporary)

Inputs: E-obs @ 8ee43da, E-obs-F @ 1ea37ee. Pre-registration: `PREREG3.md` (committed before the first P1 rollout).
Gates: STOP after P1 (regime map) and after P2 (dose pilot); P3 only with owner approval.
Runtime: `~/eobs_venv`, `~/eh_alfworld_data`, envharness submodule unchanged; reuses `scratch/eobs/eobs` (ledger client
extended backward-compatibly for a second provider, `eobs.replay` for certificates).
