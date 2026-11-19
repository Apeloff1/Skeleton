"""Immutable, digest-verified snapshots for deterministic replay boundaries."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .digest import freeze_state, state_digest


@dataclass(frozen=True)
class Snapshot:
    sequence: int
    state: Mapping[str, Any]
    digest: str

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        frozen = freeze_state(self.state)
        if type(self.digest) is not str or state_digest(frozen) != self.digest:
            raise ValueError("snapshot digest mismatch")
        object.__setattr__(self, "state", frozen)

    @classmethod
    def capture(cls, sequence: int, state: Mapping[str, Any]) -> "Snapshot":
        frozen = freeze_state(state)
        return cls(sequence, frozen, state_digest(frozen))
