"""Explicit capability policy for frontier agents.

Capabilities are data, not implicit authority. The runtime can require one or
more named capabilities before dispatching promoted implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CapabilityPolicy:
    allowed: frozenset[str]

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "CapabilityPolicy":
        normalized = frozenset(name.strip() for name in names if name.strip())
        return cls(normalized)

    def permits(self, required: Iterable[str]) -> bool:
        return set(required).issubset(self.allowed)

    def require(self, required: Iterable[str]) -> None:
        missing = sorted(set(required) - self.allowed)
        if missing:
            raise PermissionError(f"missing capabilities: {', '.join(missing)}")
