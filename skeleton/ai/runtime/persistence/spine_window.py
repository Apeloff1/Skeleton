"""Published window for one tenant.

Lists acknowledged outbox identities. Does not dispatch and does not accept.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.operation_store import SQLiteOperationStore


class SpineWindowError(RuntimeError):
    """Window read rejected its inputs. Not a maturity signal."""


class SpineWindow:
    """Published outbox identities whose stored envelope matches the tenant."""

    def __init__(self, operations: SQLiteOperationStore) -> None:
        if not isinstance(operations, SQLiteOperationStore):
            raise SpineWindowError("operations must be a SQLiteOperationStore")
        self.operations = operations

    def list(self, *, tenant_id: str, limit: int = 100) -> tuple[str, ...]:
        if not isinstance(tenant_id, str) or not tenant_id.strip() or tenant_id != tenant_id.strip():
            raise SpineWindowError("tenant_id must be canonical text")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise SpineWindowError("limit must be a positive integer")
        identities: list[str] = []
        for event in self.operations.published_outbox(limit=limit):
            stored = self.operations.get(event.operation_id)
            if stored.envelope.tenant_id == tenant_id:
                identities.append(event.outbox_id)
        return tuple(identities)

    def card(self, *, tenant_id: str, limit: int = 100) -> dict[str, Any]:
        identities = self.list(tenant_id=tenant_id, limit=limit)
        return {
            "kind": "spine_window",
            "hit": True,
            "law": "tenant-published-window",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "count": len(identities),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
