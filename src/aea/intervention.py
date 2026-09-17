"""Explicit family and nominal-control declarations for designer/controller AEA v3.

These types do not change the schemas or defaults of any historical selector. A declaration
proposes an order; neither numeric values nor level names prove intervention strength.
"""

from __future__ import annotations

import hashlib
import json
import math
from itertools import pairwise
from typing import Any, Literal, Self

from envharness.core.types import Candidate
from pydantic import Field, field_validator, model_validator

from aea.core.config import StrictModel

type Direction = Literal["easier", "harder"]
type ControlKind = Literal["BINARY", "SCALAR", "DISCRETE"]
type DesignOperation = Literal["CREATE", "REPAIR_CODE", "REPLACE_MECHANISM", "REFINE_CONTROL"]
type FeedbackReason = Literal[
    "ACCEPTED",
    "NO_LEVERAGE",
    "OVERPOWERED_BINARY",
    "INSUFFICIENT_ATTENUATION",
    "INSUFFICIENT_RESOLUTION",
    "NON_MONOTONE_CONTROL_SURFACE",
    "CONTROL_EXHAUSTED",
    "SOLVABILITY_FAILURE",
    "PRIVILEGE_REJECTION",
    "MECHANICAL_FAILURE",
]
type HookName = Literal["filter_action", "modify_transition", "filter_observation"]

DEFAULT_SCALAR_GRID = tuple(i / 16 for i in range(17))


def canonical_hash(value: Any) -> str:
    """Hash exact JSON values, refusing non-finite numbers and lossy string conversion."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


class NominalSetting(StrictModel):
    value: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    name: str | None = Field(default=None, min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def _numeric(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("setting value must be a number, not a label or boolean")
        return value

    def as_record(self) -> dict[str, Any]:
        """Allowlisted numeric/hash metadata; a designer's free-form name stays private."""
        return {
            "value": self.value,
            "name_sha256": canonical_hash(self.name) if self.name else None,
        }


def _validate_grid(values: tuple[float, ...]) -> None:
    if not 2 <= len(values) <= 33:
        raise ValueError("control needs 2..33 bounded nominal settings")
    if values[0] != 0.0 or values[-1] != 1.0:
        raise ValueError("control must include OFF=0 and the declared maximum=1")
    if any(not math.isfinite(v) or not 0.0 <= v <= 1.0 for v in values):
        raise ValueError("nominal settings must be finite numbers in [0, 1]")
    if any(a >= b for a, b in pairwise(values)):
        raise ValueError("nominal values must be distinct and in increasing proposed order")


class ControlDeclaration(StrictModel):
    kind: ControlKind = "SCALAR"
    settings: tuple[NominalSetting, ...] = ()

    @model_validator(mode="after")
    def _settings(self) -> Self:
        if self.kind == "DISCRETE" and not self.settings:
            raise ValueError("DISCRETE control requires an explicit ordered setting list")
        if self.settings:
            values = tuple(s.value for s in self.settings)
            _validate_grid(values)
            if self.kind == "BINARY" and values != (0.0, 1.0):
                raise ValueError("BINARY exposes only OFF=0 and ON=1")
            names = [s.name for s in self.settings if s.name is not None]
            if len(set(names)) != len(names):
                raise ValueError("named nominal settings must have distinct names")
        return self

    def nominal_settings(
        self, scalar_grid: tuple[float, ...] = DEFAULT_SCALAR_GRID
    ) -> tuple[NominalSetting, ...]:
        if self.settings:
            return self.settings
        if self.kind == "BINARY":
            return (NominalSetting(value=0.0, name="OFF"), NominalSetting(value=1.0, name="ON"))
        _validate_grid(scalar_grid)
        return tuple(NominalSetting(value=value) for value in scalar_grid)

    @property
    def sha256(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class V3Config(StrictModel):
    """New search envelope only; probe/accept remain explicit fields of AEAConfig."""

    max_design_rounds: int = Field(default=3, ge=1, strict=True)
    max_control_probes: int = Field(default=5, ge=1, strict=True)
    scalar_grid: tuple[float, ...] = DEFAULT_SCALAR_GRID

    @field_validator("scalar_grid")
    @classmethod
    def _grid(cls, grid: tuple[float, ...]) -> tuple[float, ...]:
        _validate_grid(grid)
        return grid


class InterventionFamily(StrictModel):
    """Host-bound family identity plus the Designer's proposed semantic intervention.

    The session, not the model, assigns IDs, round, operation and parent/semantic lineage.
    REFINE_CONTROL may change source and control while preserving semantic_mechanism_id;
    that promise is audited by the design/session protocol, not inferred from source syntax.
    """

    family_id: str = Field(min_length=1)
    direction: Direction
    mechanism_summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    axis: Literal["O", "T", "A"]
    hooks: tuple[HookName, ...] = ("filter_observation",)
    control: ControlDeclaration = ControlDeclaration()
    expected_effect: str = Field(min_length=1)
    parent_family_id: str | None = None
    design_round: int = Field(default=1, ge=1, strict=True)
    operation: DesignOperation = "CREATE"
    semantic_mechanism_id: str = Field(min_length=1)

    @field_validator("hooks")
    @classmethod
    def _hooks(cls, hooks: tuple[HookName, ...]) -> tuple[HookName, ...]:
        if not hooks or len(set(hooks)) != len(hooks):
            raise ValueError("hooks must be nonempty and distinct")
        return hooks

    @property
    def template(self) -> str:
        return self.source

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.source.encode()).hexdigest()

    @property
    def control_sha256(self) -> str:
        return self.control.sha256

    def render(self, setting: NominalSetting | float, task_id: str) -> Candidate:
        value = (
            setting.value
            if isinstance(setting, NominalSetting)
            else NominalSetting(value=setting).value
        )
        source = self.source.replace("__DOSE__", repr(float(value))).replace(
            "__TASK_ID__", repr(str(task_id))
        )
        return Candidate(rules_code=source, rationale=f"{self.family_id} setting={value}")
