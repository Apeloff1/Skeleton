"""Lag between pending and published outbox rows.

This is a read. It does not dispatch and it does not sign work off.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.operation_store import SQLiteOperationStore


class SpineLagError(RuntimeError):
    """Lag read rejected its inputs. Not a maturity signal."""


class SpineLag:
    """Count pending and published outbox rows for one store."""

    def __init__(self, operations: SQLiteOperationStore) -> None:
        if not isinstance(operations, SQLiteOperationStore):
            raise SpineLagError("operations must be a SQLiteOperationStore")
        self.operations = operations

    def read(self, *, operation_id: str | None = None) -> dict[str, Any]:
        pending = self.operations.pending_outbox_count(operation_id=operation_id)
        published = len(self.operations.published_outbox(operation_id=operation_id, limit=10000))
        return {
            "kind": "spine_lag",
            "hit": pending == 0,
            "law": "pending-versus-published",
            "citation": "VOL-134",
            "pending": pending,
            "published": published,
            "operation_id": operation_id,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
