"""Durable state primitives for resumable Skeleton execution.

FROZEN (issue #4122): ``skeleton.state`` is frozen in place. New code must
import only ``skeleton.persistence``; migration into the canonical package is
tracked in issue #4122. Docstring-only notice: no behaviour change, no warning.

Deprecated: use skeleton.persistence.state
(planned target; the move is tracked in the #4122 storage/state follow-up issue).
"""
__deprecated__ = "skeleton.persistence"  # issue #4122: docstring-only deprecation, no warning

from .migrations import (
    CheckpointMigrator,
    MigrationError,
    MigrationPathError,
    MigrationResult,
    MigrationValidationError,
)
from .run_store import (
    SCHEMA_VERSION,
    CheckpointRecord,
    InvalidTransition,
    PayloadTooLarge,
    ResumeState,
    RunNotFound,
    RunRecord,
    RunStatus,
    RunStoreError,
    SQLiteRunStore,
    SchemaVersionError,
    StateConflict,
    StepRecord,
    StepStatus,
)

__all__ = [
    "SCHEMA_VERSION",
    "CheckpointMigrator",
    "CheckpointRecord",
    "InvalidTransition",
    "MigrationError",
    "MigrationPathError",
    "MigrationResult",
    "MigrationValidationError",
    "PayloadTooLarge",
    "ResumeState",
    "RunNotFound",
    "RunRecord",
    "RunStatus",
    "RunStoreError",
    "SQLiteRunStore",
    "SchemaVersionError",
    "StateConflict",
    "StepRecord",
    "StepStatus",
]
