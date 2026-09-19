from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from .models import PlanItem, PlanRevision, WorkerState


_IMMUTABLE_SCALARS = (str, int, float, bool, type(None))


class SupervisorStateTypeError(ValueError):
    """Raised when canonical supervisor state contains unsupported mutable data."""


def clone_state_value(value: Any, *, depth: int = 0, max_depth: int = 24) -> Any:
    """Clone JSON-like supervisor state without sharing caller-owned containers.

    The control plane deliberately owns every mutable object that crosses its
    storage boundary.  A shallow dataclass copy is not enough because metadata,
    evidence, dependency arrays and worker accounting contain nested lists and
    dictionaries.

    Only operationally expected state shapes are accepted.  This keeps snapshot
    cloning deterministic and avoids invoking arbitrary user-defined deepcopy
    hooks inside a privileged control plane.
    """
    if depth > max_depth:
        raise SupervisorStateTypeError("supervisor state nesting exceeds limit")
    if isinstance(value, _IMMUTABLE_SCALARS):
        return value
    if isinstance(value, datetime):
        return value
    if isinstance(value, list):
        return [
            clone_state_value(item, depth=depth + 1, max_depth=max_depth)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            clone_state_value(item, depth=depth + 1, max_depth=max_depth)
            for item in value
        )
    if isinstance(value, dict):
        cloned: dict[Any, Any] = {}
        for key, item in value.items():
            if not isinstance(key, (str, int, float, bool)):
                raise SupervisorStateTypeError(
                    f"unsupported supervisor state key type: {type(key).__name__}"
                )
            cloned[key] = clone_state_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
            )
        return cloned
    raise SupervisorStateTypeError(
        f"unsupported supervisor state value type: {type(value).__name__}"
    )


def clone_plan_item(item: PlanItem) -> PlanItem:
    return replace(
        item,
        dependencies=list(item.dependencies),
        research_refs=list(item.research_refs),
        validation=list(item.validation),
        metadata=clone_state_value(item.metadata),
    )


def clone_worker_state(worker: WorkerState) -> WorkerState:
    return replace(
        worker,
        overtime_task_ids=list(worker.overtime_task_ids),
        metadata=clone_state_value(worker.metadata),
    )


def clone_plan_revision(revision: PlanRevision) -> PlanRevision:
    return replace(
        revision,
        added_item_ids=list(revision.added_item_ids),
        updated_item_ids=list(revision.updated_item_ids),
    )


def require_exact_schema_version(value: Any, expected: int, *, field: str = "version") -> int:
    """Require an actual JSON integer, not Python's bool-as-int compatibility."""
    if type(value) is not int or value != expected:
        raise ValueError(f"unsupported {field}: {value!r}")
    return value


def strict_nonnegative_int(
    value: Any,
    *,
    field: str,
    maximum: int | None = None,
) -> int:
    """Parse a policy/accounting integer without bool or float coercion."""
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} exceeds maximum {maximum}")
    return value
