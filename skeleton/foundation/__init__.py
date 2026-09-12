"""
Skeleton Foundation — The Bedrock Package

The four primitives everything else stands on:

- MerkleDAG: content-addressed immutable store — every artifact
  hash-addressed, tamper-evident, provenance-linked
- EventJournal + ReplayEngine: append-only hash-chained event log with
  deterministic state reconstruction — time becomes a function of the log
- CapabilityKernel + Membrane + CapabilityGuard: object-capability
  security — unforgeable, attenuable, revocable authority; least
  authority as the system default
- TemporalLattice: LTL-lite invariants over the event timeline —
  safety, liveness, and response properties with violation traces

Usage:
    from skeleton.foundation import (
        MerkleDAG, DAGAdapter,
        EventJournal, ReplayEngine, JournaledBus,
        CapabilityKernel, Membrane, CapabilityGuard,
        TemporalLattice, TemporalInvariant,
    )
"""

from skeleton.foundation.merkle import DAGAdapter, MerkleDAG, Node
from skeleton.foundation.journal import (
    EventJournal,
    JournalEntry,
    JournaledBus,
    ReplayEngine,
)
from skeleton.foundation.ocap import (
    Capability,
    CapabilityGuard,
    CapabilityKernel,
    Membrane,
)
from skeleton.foundation.temporal import (
    TemporalEvaluator,
    TemporalInvariant,
    TemporalLattice,
    Trace,
)

__all__ = [
    "MerkleDAG",
    "DAGAdapter",
    "Node",
    "EventJournal",
    "JournalEntry",
    "JournaledBus",
    "ReplayEngine",
    "Capability",
    "CapabilityKernel",
    "CapabilityGuard",
    "Membrane",
    "TemporalInvariant",
    "TemporalLattice",
    "TemporalEvaluator",
    "Trace",
]
