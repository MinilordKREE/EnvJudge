"""Exact archived source routing; controlled semantic verdicts are not safety scores."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

import pytest

import aea.low_optimizer as low
from aea.designer import AssistFamily, Reference, serialize_low
from aea.semantic_low import ScreenedLowOptimizer, _UncertainAdmissionError
from aea.semantic_privilege import Decision, SemanticGateInput, screen_semantic_privilege
from tests.unit.test_validator_contract import ARCHIVE, HISTORICAL


@pytest.mark.parametrize(
    ("case", "verdict"), [(0, "FAIL"), (0, "UNCERTAIN"), (1, "FAIL"), (2, "FAIL"), (2, "UNCERTAIN")]
)
def test_exact_historical_sources_preserve_admission_order(
    monkeypatch: pytest.MonkeyPatch, case: int, verdict: Decision
) -> None:
    filename, expected_sha, goal = HISTORICAL[case]
    source = (ARCHIVE / filename).read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == expected_sha
    order: list[str] = []

    def instrument(name: str) -> None:
        original = getattr(low, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            order.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(low, name, call)

    for name in ("validate_rules_template", "identity_at_zero", "privilege_check"):
        instrument(name)

    # A minimal reference tests lexical routing without replaying historical world state.
    # Only 129 C1 contains this numbered action. Actual semantic outcomes are audited
    # independently using the frozen reference and trusted original-state replay.
    reference = Reference(True, "pass", ("go to countertop 2",))

    def screen(family: AssistFamily) -> Any:
        assert case != 1, "lexical rejection reached the semantic screen"
        order.append("semantic")
        assert family.template == source
        # Exercise the frozen adapter's two rejection paths with a consistent, bound
        # result. This intentionally controls the verdict rather than classifying source.
        result = screen_semantic_privilege(
            SemanticGateInput(source, reference, "", (), "historical-routing")
        )
        return replace(
            result,
            decision=verdict,
            findings=tuple(replace(finding, decision=verdict) for finding in result.findings),
        )

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("_validate must not propose, certify, or measure")

    optimizer = ScreenedLowOptimizer(
        serialize_low((), 0.0, 16, reference),
        (),
        reference,
        goal,
        task_id="historical-routing",
        propose=forbidden,
        certify=forbidden,
        measure=forbidden,
        remaining=lambda: 20,
        screen=screen,
    )
    arguments = {
        "families": [
            {
                "name": "historical",
                "axis": "O",
                "mechanism_summary": "Exact archived source for admission routing",
                "why": "Exercise validator fidelity without a new proposal",
                "rules_code": source,
                "direction": "easier_with_d",
            }
        ]
    }
    if case != 1 and verdict == "UNCERTAIN":
        with pytest.raises(_UncertainAdmissionError, match="semantic_privilege_uncertain"):
            optimizer._validate(arguments)
        assert len(optimizer.history) == 1
        record = optimizer.history[0]
        assert record.source_sha256 == expected_sha and not record.structural
        assert record.solvability is None and record.endpoint is None
    else:
        family, structural, privilege = optimizer._validate(arguments)
        assert family is None and structural == []
        if case == 1:
            assert any("reference action embedded: 'go to countertop 2'" in r for r in privilege)
            assert not any("semantic_privilege" in r for r in privilege)
        else:
            assert len(privilege) == 1 and privilege[0].startswith("semantic_privilege_fail:")
    assert order == ["validate_rules_template", "identity_at_zero", "privilege_check"] + (
        [] if case == 1 else ["semantic"]
    )
