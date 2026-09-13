"""Explicit capability policy for frontier agents.

Capabilities are data, not implicit authority. The runtime can require one or
more named capabilities before dispatching promoted implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def capability_names(names: Iterable[str], *, drop_empty: bool = False) -> frozenset[str]:
    if isinstance(names, (str, bytes)):
        raise TypeError("capabilities must be a collection of names, not a string")
    normalized = set()
    for name in names:
        if not isinstance(name, str):
            raise TypeError("capability names must be strings")
        name = name.strip()
        if not name:
            if drop_empty:
                continue
            raise ValueError("capability names must not be empty")
        normalized.add(name)
    return frozenset(normalized)


@dataclass(frozen=True, slots=True)
class CapabilityPolicy:
    allowed: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed", capability_names(self.allowed))

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "CapabilityPolicy":
        return cls(capability_names(names, drop_empty=True))

    def permits(self, required: Iterable[str]) -> bool:
        return capability_names(required).issubset(self.allowed)

    def require(self, required: Iterable[str]) -> None:
        missing = sorted(capability_names(required) - self.allowed)
        if missing:
            raise PermissionError(f"missing capabilities: {', '.join(missing)}")
