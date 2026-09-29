"""Bounded resilience primitives adapted from the GameForge infrastructure model.

Source lineage: Apeloff1/gameforge-rs, README.md (v0.3.0), adapted into a
provider-neutral Python policy layer. The implementation is intentionally
small and deterministic so higher layers can compose it without a framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class DegradationLevel(IntEnum):
    NORMAL = 0
    REDUCED_CACHING = 1
    SHED_BACKGROUND = 2
    STALE_READS = 3
    READ_ONLY = 4


@dataclass(frozen=True, slots=True)
class ResilienceDecision:
    level: DegradationLevel
    allow_write: bool
    allow_background: bool
    allow_stale_reads: bool


class ResilienceController:
    """Deterministic monotonic degradation policy with explicit recovery."""

    def __init__(self, level: DegradationLevel = DegradationLevel.NORMAL) -> None:
        self._level = DegradationLevel(level)

    @property
    def level(self) -> DegradationLevel:
        return self._level

    def degrade(self, steps: int = 1) -> DegradationLevel:
        if steps < 1:
            raise ValueError("steps must be positive")
        self._level = DegradationLevel(min(int(DegradationLevel.READ_ONLY), int(self._level) + steps))
        return self._level

    def recover(self, steps: int = 1) -> DegradationLevel:
        if steps < 1:
            raise ValueError("steps must be positive")
        self._level = DegradationLevel(max(int(DegradationLevel.NORMAL), int(self._level) - steps))
        return self._level

    def decide(self) -> ResilienceDecision:
        level = self._level
        return ResilienceDecision(
            level=level,
            allow_write=level < DegradationLevel.READ_ONLY,
            allow_background=level < DegradationLevel.SHED_BACKGROUND,
            allow_stale_reads=level >= DegradationLevel.STALE_READS,
        )
