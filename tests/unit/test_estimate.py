from __future__ import annotations

import random
from collections import Counter

import pytest
from envharness.core.types import Candidate, Trace

from aea.config import AEAConfig
from aea.errors import InfraError
from aea.estimate import betainc, estimate, regime_probabilities


def _trace(success: bool, error: str | None = None) -> Trace:
    return Trace(
        episode_id="e",
        iteration_id="i",
        task_id="t",
        candidate=Candidate(),
        success=success,
        error=error,
    )


def test_betainc_closed_forms() -> None:
    # I_x(1, b) = 1 - (1-x)^b ; I_x(a, 1) = x^a ; symmetry
    assert abs(betainc(1, 3, 0.4) - (1 - 0.6**3)) < 1e-12
    assert abs(betainc(4, 1, 0.7) - 0.7**4) < 1e-12
    assert abs(betainc(2.5, 3.5, 0.3) - (1 - betainc(3.5, 2.5, 0.7))) < 1e-12
    assert betainc(2, 2, 0) == 0 and betainc(2, 2, 1) == 1


def test_regime_probabilities_extremes() -> None:
    probs = regime_probabilities(10, 0, (0.2, 0.8))
    assert abs(probs["saturated"] - (1 - 0.8**11)) < 1e-12 and probs["saturated"] > 0.9
    probs = regime_probabilities(0, 10, (0.2, 0.8))
    assert probs["zero"] > 0.9
    probs = regime_probabilities(4, 4, (0.2, 0.8))
    assert max(probs, key=lambda r: probs[r]) == "band"


def test_extreme_task_stops_at_ten() -> None:
    result = estimate(lambda i: _trace(True), AEAConfig())
    assert result.n == 10 and result.regime == "saturated" and result.stop_reason == "confidence"
    result = estimate(lambda i: _trace(False), AEAConfig())
    assert result.n == 10 and result.regime == "zero" and result.p_hat == 0.0


def test_error_retried_once_and_not_counted() -> None:
    calls = {"n": 0}

    def rollout(i: int) -> Trace:
        calls["n"] += 1
        return _trace(True, error="subprocess timeout") if i == 0 else _trace(True)

    result = estimate(rollout, AEAConfig())
    assert result.errors_retried == 1 and result.n == 10 and calls["n"] == 11
    with pytest.raises(InfraError):
        estimate(lambda i: _trace(False, error="boom"), AEAConfig())


@pytest.mark.parametrize("p", [0.0, 0.1, 0.5, 0.9, 1.0])
def test_simulated_stopping_and_misclassification(p: float) -> None:
    rng = random.Random(20260907)
    cfg = AEAConfig()
    stops: Counter[int] = Counter()
    regimes: Counter[str] = Counter()
    for _ in range(200):
        result = estimate(lambda i: _trace(rng.random() < p), cfg)
        stops[result.n] += 1
        regimes[result.regime] += 1
        assert result.n <= cfg.k and result.n >= cfg.impl.batch_first and (result.n - 4) % 2 == 0
    if p in (0.0, 1.0):
        assert stops == {10: 200}
    if p == 0.5:
        assert regimes["saturated"] / 200 < 0.05  # band -> saturated misclassification
        assert regimes["zero"] / 200 < 0.05
    if p == 1.0:
        assert regimes == {"saturated": 200}
    if p == 0.0:
        assert regimes == {"zero": 200}
