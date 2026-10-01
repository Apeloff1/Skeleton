"""Cursor read for the P2 spine projection journal.

The cursor is evidence of how far one consumer has applied published rows.
It is not a completion checkbox and it does not move the fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.consistency_fence import (
    ConsistencyFenceError,
    SQLiteConsistencyFence,
)
from skeleton.persistence.spine_projection import PoisonMark, SpineProjection


class SpineCursorError(RuntimeError):
    """Cursor input cannot be read. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class SpineCursor:
    consumer_id: str
    applied_count: int
    updated_at: datetime | None
    poison_count: int
    fence_epoch: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "spine_cursor",
            "hit": self.poison_count == 0,
            "law": "projection-cursor-read",
            "citation": "VOL-134",
            "consumer_id": self.consumer_id,
            "applied_count": self.applied_count,
            "updated_at": None if self.updated_at is None else self.updated_at.isoformat(),
            "poison_count": self.poison_count,
            "fence_epoch": self.fence_epoch,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class SpineCursorRead:
    """Read the projection cursor, poison count, and optional fence epoch."""

    def __init__(self, projection: SpineProjection, fence: SQLiteConsistencyFence | None = None) -> None:
        if not isinstance(projection, SpineProjection):
            raise SpineCursorError("projection must be a SpineProjection")
        if fence is not None and not isinstance(fence, SQLiteConsistencyFence):
            raise SpineCursorError("fence must be a SQLiteConsistencyFence")
        self.projection = projection
        self.fence = fence

    def read(
        self,
        *,
        tenant_id: str | None = None,
        resource_id: str | None = None,
    ) -> SpineCursor:
        if (tenant_id is None) != (resource_id is None):
            raise SpineCursorError("tenant_id and resource_id must be supplied together")
        with self.projection._lock:
            row = self.projection._connection.execute(
                """
                SELECT applied_count, updated_at
                FROM projection_cursor
                WHERE consumer_id = ?
                """,
                (self.projection.consumer_id,),
            ).fetchone()
            completion = self.projection._connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM projection_applied
                WHERE consumer_id = ?
                """,
                (self.projection.consumer_id,),
            ).fetchone()
            poison = self.projection._connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM projection_poison
                WHERE consumer_id = ?
                """,
                (self.projection.consumer_id,),
            ).fetchone()
        applied = 0
        updated = None
        if row is not None:
            applied_raw = row["applied_count"]
            if isinstance(applied_raw, bool) or not isinstance(applied_raw, int) or applied_raw < 0:
                raise SpineCursorError("applied_count must be a non-negative integer")
            applied = applied_raw
            updated = _aware(row["updated_at"])
        completion_count = int(completion["n"])
        if applied != completion_count:
            raise SpineCursorError(
                "projection cursor disagrees with completion journal"
            )
        epoch = None
        if self.fence is not None and tenant_id is not None and resource_id is not None:
            try:
                epoch = self.fence.read(tenant_id=tenant_id, resource_id=resource_id).epoch
            except ConsistencyFenceError:
                epoch = None
        return SpineCursor(
            consumer_id=self.projection.consumer_id,
            applied_count=applied,
            updated_at=updated,
            poison_count=int(poison["n"]),
            fence_epoch=epoch,
        )

    def poisons(self) -> tuple[PoisonMark, ...]:
        if hasattr(self.projection, "poisons"):
            return self.projection.poisons()
        return ()

    def card(self, cursor: SpineCursor) -> dict[str, Any]:
        return cursor.as_dict()
