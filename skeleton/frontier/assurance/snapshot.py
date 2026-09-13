"""Immutable snapshots suitable for deterministic replay boundaries."""
from dataclasses import dataclass
from typing import Any, Mapping

from .digest import state_digest


@dataclass(frozen=True)
class Snapshot:
    sequence: int
    state: Mapping[str, Any]
    digest: str

    @classmethod
    def capture(cls, sequence: int, state: Mapping[str, Any]) -> "Snapshot":
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        frozen = dict(state)
        return cls(sequence, frozen, state_digest(frozen))
