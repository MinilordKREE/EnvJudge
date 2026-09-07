PREREG3b — P2b refined dose pilot (frozen before any rollout; K2 in PREREG3 stays "dead" on record; P2b tests a refined controller, not a re-run)
Targets: the 11 Qwen-saturated tasks (+ the 3 edge-high tasks as a secondary set).
Families and doses:
  F_O footer masking, sequential search on λ ∈ (0.5, 1.0): start 0.75; NOEFFECT → λ + 0.125, ZERO/OVERSHOOT → λ − 0.125,
    then halve the step; ≤ 4 λ evaluations per task; report monotonicity violations (a NOEFFECT above a ZERO). Certificate R_pol.
  F_H horizon squeeze (T-axis: terminate with failure at step m via modify_transition): m ∈ {L_exp + 6, L_exp + 3, L_exp}
    where L_exp = shortest certified expert plan length from reset (3 attempts); certified by construction when L_exp ≤ m.
  F_S0′ displacement with the expert as difficulty oracle: among feasible destinations choose the one maximizing the certified
    expert plan length from the staged state (3 attempts each; LLM-free); doses = the top-2 destinations by plan length.
Uncertified doses (all families): run 4 provisional policy rollouts; any success certifies post hoc (witness = that rollout);
  0/4 stays uncertified and is reported, no further rollouts.
Controller: per task, family order F_O → F_H → F_S0′, stop at first IN-BAND (p̂₈ ∈ {0.375, 0.5, 0.625}); 4→8 rollouts per dose as before.
K2b: share of the 11 tasks reaching IN-BAND within ≤ 24 total rollouts ≥ 0.60 → controller alive; 0.30–0.60 → alive, library needs work; < 0.30 → dead.
Also report per-family leverage (share of tasks the family moves out of NOEFFECT at any dose), rollouts-to-hit, uncertified/infeasible counts, and the λ dose–response curve for the 11 tasks.
Budget: P2b ≤ USD 30 (worst case ~800 rollouts, typical ~350). Order: P3a first (two arms), then P2b, then P3b if P2b yields ≥ 5 in-band envs.
