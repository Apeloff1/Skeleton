"""skeleton.kernel.omnifabric — Ω-fabric hex port (gameforge-rs OmniFabric).

Extend-only forge-path surface. Prefer this package over
``backend.zaibatsu.fabric`` when working inside skeleton hex.

Public entrypoints:
- :class:`OmniFabric` — core hash-chained spine
- :class:`OmniFabricService` — cohesive facade (catalog/projections/routes)
- :class:`FabricEvent` / :class:`FabricOutbox`
"""
from __future__ import annotations

from skeleton.kernel.omnifabric.codecs import GENESIS_HASH, sha256_hex, stable_json
from skeleton.kernel.omnifabric.core import DEFAULT_HOT_CAP, OmniFabric
from skeleton.kernel.omnifabric.errors import (
    CapacityError,
    ChainBroken,
    LedgerUnknown,
    OmniFabricError,
    OutboxFull,
    OutboxJournalError,
    ProjectionStale,
    QueryBoundsError,
    ReplayConflict,
    SegmentCorrupt,
)
from skeleton.kernel.omnifabric.events import FabricEvent, event_from_mapping, event_to_mapping
from skeleton.kernel.omnifabric.ledgers import LedgerCatalog, LedgerInfo
from skeleton.kernel.omnifabric.outbox import COLLECTION_DEFAULT, FabricOutbox, OutboxEntry
from skeleton.kernel.omnifabric.projections import (
    CallableProjection,
    KindCounterProjection,
    LastValueProjection,
    Projection,
    ProjectionHub,
    QuorumAttestationProjection,
)
from skeleton.kernel.omnifabric.service import OmniFabricService
from skeleton.kernel.omnifabric.verify import ChainReport, evidence_bundle, verify_events

__all__ = [
    "GENESIS_HASH",
    "DEFAULT_HOT_CAP",
    "COLLECTION_DEFAULT",
    "sha256_hex",
    "stable_json",
    "OmniFabric",
    "OmniFabricService",
    "OmniFabricError",
    "OutboxFull",
    "OutboxJournalError",
    "ChainBroken",
    "LedgerUnknown",
    "ProjectionStale",
    "SegmentCorrupt",
    "ReplayConflict",
    "CapacityError",
    "QueryBoundsError",
    "FabricEvent",
    "event_from_mapping",
    "event_to_mapping",
    "FabricOutbox",
    "OutboxEntry",
    "LedgerCatalog",
    "LedgerInfo",
    "Projection",
    "ProjectionHub",
    "CallableProjection",
    "KindCounterProjection",
    "LastValueProjection",
    "QuorumAttestationProjection",
    "ChainReport",
    "verify_events",
    "evidence_bundle",
]
