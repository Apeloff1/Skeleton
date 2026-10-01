"""Skeleton persistence package.

Core durable repositories import eagerly. Snapshot compatibility helpers are
loaded lazily because snapshot restoration reaches Jeeves/orchestration
surfaces and therefore belongs to the higher architecture layer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from skeleton.persistence.conversation_repository import (
    ConversationAuthorizationError,
    ConversationConflict,
    ConversationNotFound,
    ConversationRepositoryCorruption,
    ConversationRepositoryError,
    SQLiteConversationRepository,
)
from skeleton.persistence.execution_repository import (
    ExecutionOutboxEvent,
    ExecutionRepositoryConflict,
    ExecutionRepositoryCorruption,
    ExecutionRepositoryError,
    SQLiteExecutionRepository,
)
from skeleton.persistence.memory_repository import (
    MemoryConflict,
    MemoryNotFound,
    MemoryProjectionEvent,
    MemoryRepositoryError,
    MemoryRevision,
    MongoMemoryRepository,
    SQLiteMemoryRepository,
)
from skeleton.persistence.operation_store import (
    OperationOutboxEvent,
    OperationStoreConflict,
    OperationStoreCorruptionError,
    OperationStoreError,
    SQLiteOperationStore,
    StoredOperation,
)
from skeleton.persistence.operation_runtime import (
    DurableOperationRuntime,
    OutboxDispatchReport,
)
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.spine_projection import SpineProjection, SpineProjectionReport
from skeleton.persistence.spine_land import SpineLand, SpineLandReport
from skeleton.persistence.mongo_inbox import MongoInboxLedger
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.spine_quarantine import SpineQuarantine
from skeleton.persistence.spine_status import SpineStatus
from skeleton.persistence.mongo_projection import MongoSpineProjection, MongoProjectionReport
from skeleton.persistence.spine_repair import SpineRepairPlan
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_catalog import SpineCatalog
from skeleton.persistence.mongo_catalog import MongoCatalog
from skeleton.persistence.spine_batch import SpineBatch, SpineBatchReport
from skeleton.persistence.spine_witness import SpineWitness
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_cutover import SpineCutover
from skeleton.persistence.spine_window import SpineWindow
from skeleton.persistence.spine_seal import SpineSeal
from skeleton.persistence.spine_digest import SpineDigest
from skeleton.persistence.spine_gap import SpineGap

_SNAPSHOT_EXPORTS = {
    "SnapshotStore",
    "restore_genesis_state",
    "restore_graph",
    "restore_mag",
    "restore_matrices",
    "restore_vector_store",
    "serialize_graph",
    "serialize_mag",
    "serialize_matrices",
    "serialize_vector_store",
    "snapshot_genesis_state",
}


def __getattr__(name: str) -> Any:
    if name not in _SNAPSHOT_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module("skeleton.persistence.snapshots")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | _SNAPSHOT_EXPORTS)


__all__ = [
    "ExecutionOutboxEvent",
    "ExecutionRepositoryConflict",
    "ExecutionRepositoryCorruption",
    "ExecutionRepositoryError",
    "SQLiteExecutionRepository",
    "ConversationAuthorizationError",
    "ConversationConflict",
    "ConversationNotFound",
    "ConversationRepositoryCorruption",
    "ConversationRepositoryError",
    "SQLiteConversationRepository",
    "MemoryConflict",
    "MemoryNotFound",
    "MemoryProjectionEvent",
    "MemoryRepositoryError",
    "MemoryRevision",
    "MongoMemoryRepository",
    "SQLiteMemoryRepository",
    "OperationOutboxEvent",
    "OperationStoreConflict",
    "OperationStoreCorruptionError",
    "OperationStoreError",
    "SQLiteOperationStore",
    "StoredOperation",
    "DurableOperationRuntime",
    "OutboxDispatchReport",
    "SQLiteInboxLedger",
    "SQLiteConsistencyFence",
    "SpineProjection",
    "SpineProjectionReport",
    "SpineLand",
    "SpineLandReport",
    "MongoInboxLedger",
    "MongoConsistencyFence",
    "SpineQuarantine",
    "SpineStatus",
    "MongoSpineProjection",
    "MongoProjectionReport",
    "SpineRepairPlan",
    "SpineLag",
    "SpineCatalog",
    "MongoCatalog",
    "SpineBatch",
    "SpineBatchReport",
    "SpineWitness",
    "SpineDrift",
    "SpineApplyGate",
    "SpineDigest",
    "SpineCutover",
    "SpineWindow",
    "SpineSeal",
    "SpineGap",
    "SnapshotStore",
    "snapshot_genesis_state",
    "restore_genesis_state",
    "serialize_vector_store",
    "restore_vector_store",
    "serialize_mag",
    "restore_mag",
    "serialize_graph",
    "restore_graph",
    "serialize_matrices",
    "restore_matrices",
]
