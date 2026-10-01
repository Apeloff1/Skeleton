"""Dispatch hook for the P2 spine.

This does not replace DurableOperationRuntime.dispatch_outbox. The caller
holds the runtime and asks the hook to publish, then project. A second call
on an already published row is a duplicate and does not advance the fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.operation_runtime import (
    DurableOperationRuntime,
    OutboxDispatchReport,
)
from skeleton.persistence.spine_cursor import SpineCursor, SpineCursorRead
from skeleton.persistence.spine_projection import SpineProjection, SpineProjectionReport


class SpineDispatchError(RuntimeError):
    """Hook rejected its inputs. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class SpineDispatchReport:
    dispatch: OutboxDispatchReport
    projection: SpineProjectionReport
    cursor: SpineCursor
    ran_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "spine_dispatch",
            "hit": self.projection.poisoned == 0 and self.dispatch.error_type is None,
            "law": "dispatch-project-cursor",
            "citation": "VOL-134",
            "published": self.dispatch.published,
            "remaining": self.dispatch.remaining,
            "applied": self.projection.applied,
            "duplicates": self.projection.duplicates,
            "poisoned": self.projection.poisoned,
            "fence_advances": self.projection.fence_advances,
            "applied_count": self.cursor.applied_count,
            "poison_count": self.cursor.poison_count,
            "fence_epoch": self.cursor.fence_epoch,
            "ran_at": self.ran_at.isoformat(),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


class SpineDispatchHook:
    """Publish pending outbox rows, project them, then read the cursor."""

    def __init__(
        self,
        runtime: DurableOperationRuntime,
        projection: SpineProjection,
        cursor: SpineCursorRead,
    ) -> None:
        if not isinstance(runtime, DurableOperationRuntime):
            raise SpineDispatchError("runtime must be a DurableOperationRuntime")
        if not isinstance(projection, SpineProjection):
            raise SpineDispatchError("projection must be a SpineProjection")
        if not isinstance(cursor, SpineCursorRead):
            raise SpineDispatchError("cursor must be a SpineCursorRead")
        self.runtime = runtime
        self.projection = projection
        self.cursor = cursor
        self.attempts = 0

    def run(
        self,
        *,
        operation_id: str | None = None,
        tenant_id: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
        now: datetime | None = None,
    ) -> SpineDispatchReport:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise SpineDispatchError("limit must be a positive integer")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineDispatchError("now must be timezone-aware")
        dispatch = self.runtime.dispatch_outbox(operation_id=operation_id, limit=limit)
        projection = self.projection.project(limit=limit, now=instant)
        cursor = self.cursor.read(tenant_id=tenant_id, resource_id=resource_id)
        self.attempts += 1
        return SpineDispatchReport(
            dispatch=dispatch,
            projection=projection,
            cursor=cursor,
            ran_at=instant,
        )

    def card(self, report: SpineDispatchReport) -> dict[str, Any]:
        payload = report.as_dict()
        payload["attempts"] = self.attempts
        return payload
