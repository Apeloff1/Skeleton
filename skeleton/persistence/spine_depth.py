"""Poison replay bind for the open spine projection.

Importing this module attaches the recovery read. Replay returns marks and
does not advance the fence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from skeleton.persistence.spine_projection import PoisonMark, SpineProjection


def _poisons(self: SpineProjection) -> tuple[PoisonMark, ...]:
    with self._lock:
        rows = self._connection.execute(
            """
            SELECT outbox_id, operation_id, tenant_id, reason, recorded_at
            FROM projection_poison
            WHERE consumer_id = ?
            ORDER BY recorded_at ASC, outbox_id ASC
            """,
            (self.consumer_id,),
        ).fetchall()
    marks = []
    for row in rows:
        recorded = datetime.fromisoformat(row["recorded_at"])
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        marks.append(
            PoisonMark(
                outbox_id=row["outbox_id"],
                operation_id=row["operation_id"],
                tenant_id=row["tenant_id"],
                reason=row["reason"],
                recorded_at=recorded,
            )
        )
    return tuple(marks)


def _replay_poison(self: SpineProjection) -> tuple[PoisonMark, ...]:
    return _poisons(self)


if not hasattr(SpineProjection, "poisons"):
    SpineProjection.poisons = _poisons  # type: ignore[attr-defined]
if not hasattr(SpineProjection, "replay_poison"):
    SpineProjection.replay_poison = _replay_poison  # type: ignore[attr-defined]
