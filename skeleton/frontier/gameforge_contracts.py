"""Stable names for composed frontier contracts."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ContractVersion:
    name: str
    major: int = 1
    minor: int = 0

    def compatible_with(self, other: "ContractVersion") -> bool:
        return self.name == other.name and self.major == other.major
