"""Deterministic simulation primitives for promoted GameForge behavior."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class SimulationTick:
    tick: int
    seed: int
    state: Mapping[str, int] = field(default_factory=dict)

    def next(self, *, delta: Mapping[str, int] | None = None) -> SimulationTick:
        if self.tick < 0:
            raise ValueError("tick must not be negative")
        updates = dict(self.state)
        for key, value in (delta or {}).items():
            if not key.strip():
                raise ValueError("state keys must not be empty")
            updates[key] = updates.get(key, 0) + value
        return SimulationTick(self.tick + 1, self.seed, updates)


def stable_seed(namespace: str, identity: str) -> int:
    """Derive a reproducible unsigned 64-bit seed from stable identifiers."""
    if not namespace.strip() or not identity.strip():
        raise ValueError("namespace and identity must not be empty")
    digest = sha256(f"{namespace.strip()}:{identity.strip()}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    kind: str
    prompt: str
    seed: int
    parameters: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.prompt.strip():
            raise ValueError("kind and prompt must not be empty")
