"""Repair/evolution marker for the frontier consolidation pass."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairPlan:
    name: str
    priority: int
    reversible: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool) or self.priority < 0:
            raise ValueError("priority must be a non-negative integer")
        if not isinstance(self.reversible, bool):
            raise TypeError("reversible must be bool")

    @property
    def critical(self) -> bool:
        return self.priority >= 100
