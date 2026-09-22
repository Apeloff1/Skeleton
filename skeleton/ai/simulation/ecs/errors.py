"""Typed failures for the deterministic ECS/simulation core.

The ECS package is intentionally engine-neutral and provider-neutral.  Errors
are stable machine-readable classes so callers can distinguish malformed
schemas, invalid entity state, scheduling cycles, replay corruption and hard
resource bounds without string matching.
"""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.kernel.errors import KernelError


class ECSError(KernelError):
    """Root failure for the deterministic simulation plane."""

    code = "SIM.ECS"

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, context=dict(context or {}))


class ValidationError(ECSError):
    code = "SIM.ECS.VALIDATION"


class BoundsError(ECSError):
    code = "SIM.ECS.BOUNDS"


class IdentifierError(ValidationError):
    code = "SIM.ECS.IDENTIFIER"


class SchemaError(ValidationError):
    code = "SIM.ECS.SCHEMA"


class SchemaConflictError(SchemaError):
    code = "SIM.ECS.SCHEMA_CONFLICT"


class SchemaNotFoundError(SchemaError):
    code = "SIM.ECS.SCHEMA_NOT_FOUND"


class SchemaVersionError(SchemaError):
    code = "SIM.ECS.SCHEMA_VERSION"


class EntityError(ECSError):
    code = "SIM.ECS.ENTITY"


class EntityNotFoundError(EntityError):
    code = "SIM.ECS.ENTITY_NOT_FOUND"


class EntityExistsError(EntityError):
    code = "SIM.ECS.ENTITY_EXISTS"


class EntityTombstonedError(EntityError):
    code = "SIM.ECS.ENTITY_TOMBSTONED"


class ComponentError(ECSError):
    code = "SIM.ECS.COMPONENT"


class ComponentNotFoundError(ComponentError):
    code = "SIM.ECS.COMPONENT_NOT_FOUND"


class ComponentExistsError(ComponentError):
    code = "SIM.ECS.COMPONENT_EXISTS"


class ResourceError(ECSError):
    code = "SIM.ECS.RESOURCE"


class ResourceNotFoundError(ResourceError):
    code = "SIM.ECS.RESOURCE_NOT_FOUND"


class QueryError(ECSError):
    code = "SIM.ECS.QUERY"


class ScheduleError(ECSError):
    code = "SIM.ECS.SCHEDULE"


class ScheduleCycleError(ScheduleError):
    code = "SIM.ECS.SCHEDULE_CYCLE"


class SystemNotFoundError(ScheduleError):
    code = "SIM.ECS.SYSTEM_NOT_FOUND"


class SystemConflictError(ScheduleError):
    code = "SIM.ECS.SYSTEM_CONFLICT"


class EventError(ECSError):
    code = "SIM.ECS.EVENT"


class EventOverflowError(BoundsError):
    code = "SIM.ECS.EVENT_OVERFLOW"


class CommandError(ECSError):
    code = "SIM.ECS.COMMAND"


class CommandOverflowError(BoundsError):
    code = "SIM.ECS.COMMAND_OVERFLOW"


class SnapshotError(ECSError):
    code = "SIM.ECS.SNAPSHOT"


class SnapshotVersionError(SnapshotError):
    code = "SIM.ECS.SNAPSHOT_VERSION"


class SnapshotDigestError(SnapshotError):
    code = "SIM.ECS.SNAPSHOT_DIGEST"


class DeltaError(SnapshotError):
    code = "SIM.ECS.DELTA"


class ReplayError(ECSError):
    code = "SIM.ECS.REPLAY"


class ReplayDivergenceError(ReplayError):
    code = "SIM.ECS.REPLAY_DIVERGENCE"


class ClockError(ECSError):
    code = "SIM.ECS.CLOCK"


class TransactionError(ECSError):
    code = "SIM.ECS.TRANSACTION"
