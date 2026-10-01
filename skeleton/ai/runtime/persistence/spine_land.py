"""One-call land seam for the P2 runtime spine.

This binds already-landed pieces. It does not replace DurableOperationRuntime
and it does not sign work off. Dispatch remains the publisher. Projection
consumes only acknowledged outbox rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_runtime import (
    DurableOperationRuntime,
    OutboxDispatchReport,
)
from skeleton.persistence.spine_projection import (
    SpineProjection,
    SpineProjectionReport,
)


class SpineLandError(RuntimeError):
    """Land seam rejected its inputs. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class SpineLandReport:
    dispatch: OutboxDispatchReport
    projection: SpineProjectionReport

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "spine_land",
            "hit": self.projection.poisoned == 0 and self.dispatch.error_type is None,
            "law": "dispatch-then-project",
            "citation": "VOL-134",
            "published": self.dispatch.published,
            "remaining": self.dispatch.remaining,
            "applied": self.projection.applied,
            "duplicates": self.projection.duplicates,
            "poisoned": self.projection.poisoned,
            "fence_advances": self.projection.fence_advances,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


class SpineLand:
    """Dispatch the outbox, then project published rows into inbox and fence."""

    def __init__(
        self,
        runtime: DurableOperationRuntime,
        inbox: SQLiteInboxLedger,
        fence: SQLiteConsistencyFence,
        projection: SpineProjection,
    ) -> None:
        if not isinstance(runtime, DurableOperationRuntime):
            raise SpineLandError("runtime must be a DurableOperationRuntime")
        if not isinstance(inbox, SQLiteInboxLedger):
            raise SpineLandError("inbox must be a SQLiteInboxLedger")
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineLandError("fence must be a SQLiteConsistencyFence")
        if not isinstance(projection, SpineProjection):
            raise SpineLandError("projection must be a SpineProjection")
        self.runtime = runtime
        self.inbox = inbox
        self.fence = fence
        self.projection = projection

    def project_published(
        self,
        *,
        operation_id: str | None = None,
        limit: int = 100,
    ) -> SpineLandReport:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise SpineLandError("limit must be a positive integer")
        dispatch = self.runtime.dispatch_outbox(operation_id=operation_id, limit=limit)
        projection = self.projection.project(limit=limit)
        return SpineLandReport(dispatch=dispatch, projection=projection)

    def card(self, report: SpineLandReport) -> dict[str, Any]:
        return report.as_dict()
