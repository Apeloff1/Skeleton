"""Engine-neutral networking contracts for Skeleton.

This package holds replication and rollback primitives that later transport,
session, and engine adapters can consume. It does not open sockets.
"""

from skeleton.network.replication import (
    SCHEMA_VERSION,
    Ack,
    Authority,
    DeliveryOutcome,
    HistoryExhaustedError,
    IngestResult,
    OfflineChannel,
    Patch,
    PatchOp,
    ReconciliationEvidence,
    Replica,
    ReplicationError,
    RollbackEvidence,
    SchemaCompatibilityError,
    SequenceError,
    SerializationError,
    canonical_dumps,
    frame_digest,
    state_digest,
)

__all__ = [
    "SCHEMA_VERSION",
    "Ack",
    "Authority",
    "DeliveryOutcome",
    "HistoryExhaustedError",
    "IngestResult",
    "OfflineChannel",
    "Patch",
    "PatchOp",
    "ReconciliationEvidence",
    "Replica",
    "ReplicationError",
    "RollbackEvidence",
    "SchemaCompatibilityError",
    "SequenceError",
    "SerializationError",
    "canonical_dumps",
    "frame_digest",
    "state_digest",
]
