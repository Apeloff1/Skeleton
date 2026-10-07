"""Surface material contracts used by contact generation and solving."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .errors import PhysicsValidationError


class CombineRule(str, Enum):
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    MULTIPLY = "multiply"


def _coefficient(value: float, *, name: str, maximum: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= maximum:
        raise PhysicsValidationError(f"{name} must be in [0, {maximum}]")
    return value


def combine_scalar(left: float, right: float, rule: CombineRule) -> float:
    if rule is CombineRule.AVERAGE:
        return (left + right) * 0.5
    if rule is CombineRule.MINIMUM:
        return min(left, right)
    if rule is CombineRule.MAXIMUM:
        return max(left, right)
    if rule is CombineRule.MULTIPLY:
        return left * right
    raise PhysicsValidationError("unsupported material combine rule")


@dataclass(frozen=True, slots=True)
class PhysicsMaterial:
    friction: float = 0.6
    restitution: float = 0.0
    rolling_friction: float = 0.0
    friction_rule: CombineRule = CombineRule.AVERAGE
    restitution_rule: CombineRule = CombineRule.MAXIMUM

    def __post_init__(self) -> None:
        object.__setattr__(self, "friction", _coefficient(self.friction, name="friction", maximum=4.0))
        object.__setattr__(
            self,
            "restitution",
            _coefficient(self.restitution, name="restitution"),
        )
        object.__setattr__(
            self,
            "rolling_friction",
            _coefficient(self.rolling_friction, name="rolling_friction", maximum=4.0),
        )
        if not isinstance(self.friction_rule, CombineRule):
            raise PhysicsValidationError("friction_rule must be CombineRule")
        if not isinstance(self.restitution_rule, CombineRule):
            raise PhysicsValidationError("restitution_rule must be CombineRule")


@dataclass(frozen=True, slots=True)
class ContactMaterial:
    friction: float
    restitution: float
    rolling_friction: float


def combine_materials(left: PhysicsMaterial, right: PhysicsMaterial) -> ContactMaterial:
    # Deterministic rule precedence: the lexicographically larger enum value is
    # intentionally *not* used.  More conservative rules win explicitly.
    friction_rule = (
        left.friction_rule
        if left.friction_rule is right.friction_rule
        else CombineRule.MINIMUM
    )
    restitution_rule = (
        left.restitution_rule
        if left.restitution_rule is right.restitution_rule
        else CombineRule.MAXIMUM
    )
    return ContactMaterial(
        friction=combine_scalar(left.friction, right.friction, friction_rule),
        restitution=combine_scalar(left.restitution, right.restitution, restitution_rule),
        rolling_friction=min(left.rolling_friction, right.rolling_friction),
    )
