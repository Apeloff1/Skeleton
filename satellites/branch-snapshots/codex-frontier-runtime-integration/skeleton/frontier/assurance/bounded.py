"""Small immutable bounds primitive used by runtime policies."""

from dataclasses import dataclass

from .invariant import require


@dataclass(frozen=True)
class BoundedInt:
    value: int
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        require(self.minimum <= self.maximum, "minimum must not exceed maximum")
        require(self.minimum <= self.value <= self.maximum, "value outside bounds")

    def clamp(self, value: int) -> "BoundedInt":
        return BoundedInt(min(self.maximum, max(self.minimum, value)), self.minimum, self.maximum)
