# E-obs addendum H — hardening arm (paper App. G configuration), frozen before any Phase-2b rollout
Config: corpus_eobs.yaml minus agent.extra_instructions (generic HarnessAgent prompt only), objective.target_band = [0.4, 0.6]
(App. G), all else unchanged (K=5, max_k=5, temperature 0.5, N tasks = same seeds 0..N-1). Run name eobs_alfworld_H_001.
Statistics O4H, O5H, O7H = the O4, O5, O7 definitions and thresholds of PREREG.md applied to this arm only;
O8H descriptive. Branch decisions for contribution 2 (certification layer, per-axis certificates, harden branch)
are read from O4H/O5H/O7H; the released-config arm reports O4/O5/O7 as observed but they are uninformative
by construction (scaffold-only prompt). S1 in PREREG.md is unchanged and evaluated on the released arm as frozen.
Budget: within the study's hard cap USD 120 / soft gate 80. Phase-3 certificates and R_hint cap (60 candidates ×
3 attempts) are shared across both arms, SR_c=0 candidates first.
