"""Small provider-neutral observability primitives."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Observation:
    name: str
    value: float
    unit: str = "count"

    def __post_init__(self):
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.unit:
            raise ValueError("unit must not be empty")
