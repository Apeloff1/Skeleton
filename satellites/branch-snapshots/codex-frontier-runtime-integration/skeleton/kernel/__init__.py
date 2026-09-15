"""
Skeleton Kernel — Core primitives and foundational types

Provides:
- errors: SkeletonError, BlueprintError, MaterialisationError
- events: DomainEvent, EventBus
- ids: UserId, BlueprintId
- entropy: EntropyPool
- clocks: VectorClock
- invariants: Invariant, InvariantLattice
- registry: CapabilityRegistry
"""

from __future__ import annotations

from skeleton.kernel.primitives import (
    BlueprintError,
    BlueprintId,
    CapabilityRegistry,
    DomainEvent,
    EntropyPool,
    EventBus,
    Invariant,
    InvariantLattice,
    MaterialisationError,
    SkeletonError,
    UserId,
    VectorClock,
)

__all__ = [
    "SkeletonError",
    "BlueprintError",
    "MaterialisationError",
    "DomainEvent",
    "EventBus",
    "UserId",
    "BlueprintId",
    "EntropyPool",
    "VectorClock",
    "Invariant",
    "InvariantLattice",
    "CapabilityRegistry",
]
