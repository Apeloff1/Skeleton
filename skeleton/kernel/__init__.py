"""
Skeleton Kernel — Core primitives and foundational types

Provides:
- errors: SkeletonError, BlueprintError, MaterialisationError
- events: DomainEvent, EventBus
- causality: CausalGraph, CausalNode, CausalPath
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
from skeleton.kernel.causality import CausalGraph, CausalGraphError, CausalNode, CausalPath
from skeleton.kernel.work_queue import SubmitterCapError

__all__ = [
    "SkeletonError",
    "BlueprintError",
    "MaterialisationError",
    "DomainEvent",
    "EventBus",
    "CausalGraph",
    "CausalGraphError",
    "CausalNode",
    "CausalPath",
    "UserId",
    "BlueprintId",
    "EntropyPool",
    "VectorClock",
    "Invariant",
    "InvariantLattice",
    "CapabilityRegistry",
    "SubmitterCapError",
]
