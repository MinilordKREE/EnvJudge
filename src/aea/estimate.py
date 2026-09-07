"""Sequential Beta regime estimation (spec section 2).

Posterior Beta(1+s, 1+f); first batch 4, then batches of 2; stop when the posterior mass of any
regime interval — zero ``p < lo``, band ``lo <= p <= hi``, saturated ``p > hi`` with (lo, hi) = B_L
—
reaches ``confidence`` or ``n = k_max``. Extreme tasks stop at n = 10 by this rule alone
(P(p > 0.8 | 10/10) = 1 - 0.8^11 ≈ 0.914). The regime is the interval with the largest posterior
mass. Environment errors (``Trace.error``) are retried once and never counted.

Reference: the K-rollout dispatch mirrors ``orchestrator.py:986-1046`` (one spec per rollout, same
``reset_seed``); see docs/reuse/estimate.md. No reference source copied.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from envharness.core.types import Trace

from aea.config import AEAConfig
from aea.errors import InfraError

type Regime = Literal["zero", "band", "saturated"]

type RolloutFn = Callable[[int], Trace]
"""Run rollout number ``i`` (0-based within the estimate) and return its Trace."""


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Lentz; Numerical Recipes 6.4)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (tiny if abs(d) < tiny else d)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (tiny if abs(d) < tiny else d)
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (tiny if abs(d) < tiny else d)
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b) for a, b > 0 and 0 <= x <= 1."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_bt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def regime_probabilities(
    successes: int, failures: int, band: tuple[float, float]
) -> dict[Regime, float]:
    """Posterior mass of the three regimes under Beta(1+s, 1+f)."""
    a, b = 1.0 + successes, 1.0 + failures
    lo, hi = band
    below = betainc(a, b, lo)
    upto = betainc(a, b, hi)
    return {"zero": below, "band": upto - below, "saturated": 1.0 - upto}


@dataclass
class EstimateResult:
    regime: Regime
    p_hat: float
    n: int
    successes: int
    probabilities: dict[Regime, float]
    stop_reason: str
    traces: list[Trace] = field(default_factory=list)
    errors_retried: int = 0


def estimate(rollout: RolloutFn, config: AEAConfig) -> EstimateResult:
    """Run the sequential test; ``rollout(i)`` returns a Trace; one retry per errored rollout."""
    traces: list[Trace] = []
    successes = 0
    retried = 0
    band = config.band_l
    n_next = config.batch_first
    index = 0
    while True:
        for _ in range(n_next):
            trace = rollout(index)
            index += 1
            if trace.error:
                retried += 1
                trace = rollout(index)
                index += 1
                if trace.error:
                    raise InfraError(
                        f"rollout failed twice: {trace.error}", kind="rollout_error", attempts=2
                    )
            traces.append(trace)
            successes += int(bool(trace.success))
        n = len(traces)
        probs = regime_probabilities(successes, n - successes, band)
        best = max(probs, key=lambda r: probs[r])
        if probs[best] >= config.confidence:
            return EstimateResult(
                best, successes / n, n, successes, probs, "confidence", traces, retried
            )
        if n >= config.k_max:
            return EstimateResult(
                best, successes / n, n, successes, probs, "k_max", traces, retried
            )
        n_next = min(config.batch_next, config.k_max - n)
