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


# --- Live (archetype / sparse-set) world runtime ---------------------------
# Extend-only additions for the dense runtime world, scheduler, scripting
# sandbox and forge adapter.  They reuse the existing hierarchy so callers can
# keep catching ``ECSError`` / ``ValidationError`` / ``BoundsError``.


class EntityHandleError(EntityError):
    """A packed runtime entity handle is malformed, stale or not alive."""

    code = "SIM.ECS.ENTITY_HANDLE"


class ComponentTypeError(ComponentError):
    """A component type is unknown, duplicated or used with the wrong storage."""

    code = "SIM.ECS.COMPONENT_TYPE"


class StructuralChangeError(ECSError):
    """A structural world change was attempted while iteration was active."""

    code = "SIM.ECS.STRUCTURAL_CHANGE"


class AccessViolationError(ScheduleError):
    """A system touched a component or resource it did not declare."""

    code = "SIM.ECS.ACCESS_VIOLATION"


class ScriptError(ECSError):
    """Root failure for sandboxed game-logic scripts."""

    code = "SIM.ECS.SCRIPT"


class ScriptValidationError(ScriptError, ValidationError):
    """Script source failed static (AST) policy validation.

    ``context["violations"]`` carries ``[{"line", "col", "rule", "detail"}]``
    in source order so editors can underline every rejected construct.
    """

    code = "SIM.ECS.SCRIPT_VALIDATION"


class ScriptRuntimeError(ScriptError):
    """A script raised an ordinary error while running inside the sandbox."""

    code = "SIM.ECS.SCRIPT_RUNTIME"


class ScriptLimitError(ScriptError, BoundsError):
    """A script exceeded one of its execution budgets."""

    code = "SIM.ECS.SCRIPT_LIMIT"


class ScriptStepLimitError(ScriptLimitError):
    code = "SIM.ECS.SCRIPT_STEP_LIMIT"


class ScriptMemoryLimitError(ScriptLimitError):
    code = "SIM.ECS.SCRIPT_MEMORY_LIMIT"


class ScriptDepthLimitError(ScriptLimitError):
    code = "SIM.ECS.SCRIPT_DEPTH_LIMIT"


class ScriptTimeLimitError(ScriptLimitError):
    code = "SIM.ECS.SCRIPT_TIME_LIMIT"


class ForgeAdapterError(ValidationError):
    """A forge blueprint / component graph could not be instantiated."""

    code = "SIM.ECS.FORGE_ADAPTER"
