"""Immutable integer bounds primitive used by runtime policies."""
from dataclasses import dataclass

from .invariant import require


@dataclass(frozen=True)
class BoundedInt:
    value: int
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        require(all(type(x) is int for x in (self.value, self.minimum, self.maximum)), "integer bounds required")
        require(self.minimum <= self.maximum, "minimum must not exceed maximum")
        require(self.minimum <= self.value <= self.maximum, "value outside bounds")

    def clamp(self, value: int) -> "BoundedInt":
        require(type(value) is int, "integer value required")
        return BoundedInt(min(self.maximum, max(self.minimum, value)), self.minimum, self.maximum)
