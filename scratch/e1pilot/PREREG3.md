# E1-pilot pre-registration — frozen 2026-09-0X (inputs: E-obs @ 8ee43da, E-obs-F @ 1ea37ee)

Setting: ALFWorld train seeds 0-29 (same games as E-obs); policy/consumer = Qwen3-8B via DashScope compatible mode,
non-thinking (enable_thinking=false), temperature 0.5, released policy prompt; designer/extractor = DeepSeek V4 Pro
(P3 only). Regime bins on p̂: zero = 0; edge-low (0, 0.2); band [0.2, 0.8]; edge-high (0.8, 1); saturated = 1.
Hardening band = App. G [0.4, 0.6]; at K = 8 it is p̂_8 ∈ {0.375, 0.5, 0.625}.

K1 (regime map, P1): both-sides if zero + edge-low ≥ 0.15 AND saturated + edge-high ≥ 0.15 (task-level bootstrap,
point estimates); one-sided otherwise (the side with ≥ 0.15 is kept; the pilot's P2 runs only if saturated +
edge-high ≥ 0.15, else the Pro fallback). Parse-failure stop: > 10% of policy steps unparseable in the smoke → stop.

K2 (controller, P2): share of target tasks reaching IN-BAND with total rollouts ≤ 16 is ≥ 0.60 → the structural
controller is alive; 0.30-0.60 → alive but the operator library needs a third family before E1; < 0.30 → dead for
this policy. K2' (expressivity ceiling): share of target tasks still NOEFFECT at the maximum feasible dose of both
families ≥ 0.40 → structural hardening cannot move this policy either; report as a ceiling. Also reported: median
rollouts-to-hit, uncertified/infeasible dose counts, certificate source counts, dose-response curves (subset).

K3 (downstream, P3): held-out success (mean over 3 replicates) of skills-from-controlled-envs minus
skills-from-original-env ≥ -0.02 on the in-distribution split → SL line alive; report OOD and no-skill alongside;
< -0.02 → SL line at risk; the RL Study becomes the primary downstream evidence.

Budget: hard USD 30, soft 20; P1 ≤ 10, P2 ≤ 10 (12 with fallback), P3 ≤ 10. Seeds: destination order 20260910,
fallback task sample 20260911, curve subset = first 5 hits in task-id order.
