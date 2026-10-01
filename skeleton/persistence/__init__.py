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
