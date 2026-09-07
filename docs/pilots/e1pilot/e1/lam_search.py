"""PREREG3b F_O sequential λ search: start 0.75, step 0.125; NOEFFECT → λ + step, ZERO/OVERSHOOT → λ − step, then halve the
step; ≤ 4 evaluations; stop at IN-BAND (or NEAR? no: only IN-BAND stops). Pure logic; unit-tested."""

from __future__ import annotations


def next_lambda(history: list[tuple[float, str]], start: float = 0.75, step0: float = 0.125, max_evals: int = 4) -> float | None:
    """history = [(λ, class)], classes from controller.classify*. Returns the next λ or None when done."""
    if not history:
        return start
    if len(history) >= max_evals or history[-1][1] == "IN-BAND":
        return None
    lam, step = start, step0
    for i, (l, cls) in enumerate(history):
        if i > 0:
            step = step / 2
        if cls == "NOEFFECT" or cls == "NEAR" and l < 0.5:
            lam = l + step
        elif cls in ("ZERO", "OVERSHOOT") or cls == "NEAR":
            lam = l - step
        else:
            lam = l
    lam = round(min(max(lam, 0.0), 1.0), 4)
    if any(abs(lam - l) < 1e-9 for l, _ in history):
        return None
    return lam


def monotonicity_violations(history: list[tuple[float, str]]) -> int:
    """Count pairs (λ_a < λ_b) with class NOEFFECT at λ_b and ZERO at λ_a (a NOEFFECT above a ZERO)."""
    v = 0
    for la, ca in history:
        for lb, cb in history:
            if la < lb and ca == "ZERO" and cb == "NOEFFECT":
                v += 1
    return v
