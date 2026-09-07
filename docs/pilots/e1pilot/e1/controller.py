"""P2 controller: fixed dose order F_S0 k=1,2,3 then F_O λ=0.5,1.0; certificate ladder before any rollout; sequential band
control (4 rollouts → 4/4 NOEFFECT / 0/4 ZERO / else run to 8). Pure stopping/classification logic lives here (unit-tested);
the env/LLM plumbing is in p2_run.py."""

from __future__ import annotations

DOSES = [("F_S0", 1), ("F_S0", 2), ("F_S0", 3), ("F_O", 0.5), ("F_O", 1.0)]
BAND8 = {3 / 8, 4 / 8, 5 / 8}
NEAR8 = {2 / 8, 6 / 8}


def classify_after4(successes: int) -> str | None:
    """After 4 rollouts: 'NOEFFECT' (4/4), 'ZERO' (0/4), or None (continue to 8)."""
    if successes == 4:
        return "NOEFFECT"
    if successes == 0:
        return "ZERO"
    return None


def classify8(successes: int) -> str:
    p = successes / 8
    if p in BAND8:
        return "IN-BAND"
    if p in NEAR8:
        return "NEAR"
    return "NOEFFECT" if p > 6 / 8 else "OVERSHOOT"


def rollouts_needed(successes_after4: int) -> int:
    return 4 if classify_after4(successes_after4) else 8


def next_dose(index: int) -> tuple[str, float] | None:
    return DOSES[index + 1] if index + 1 < len(DOSES) else None
