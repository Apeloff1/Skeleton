"""Gap between a published window and an inbox watermark.

Reports missing versions. Does not accept and does not advance a fence.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_store import SQLiteOperationStore


class SpineGapError(RuntimeError):
    """Gap read rejected its inputs. Not a maturity signal."""


class SpineGap:
    """Compare published versions for one operation with the inbox watermark."""

    def __init__(self, operations: SQLiteOperationStore, inbox: SQLiteInboxLedger, *, consumer_id: str = "spine") -> None:
        if not isinstance(operations, SQLiteOperationStore):
            raise SpineGapError("operations must be a SQLiteOperationStore")
        if not isinstance(inbox, SQLiteInboxLedger):
            raise SpineGapError("inbox must be a SQLiteInboxLedger")
        self.operations = operations
        self.inbox = inbox
        self.consumer_id = consumer_id

    def read(self, *, operation_id: str) -> dict[str, Any]:
        published = self.operations.published_outbox(operation_id=operation_id, limit=1000)
        versions = sorted(event.operation_version for event in published)
        applied = 0
        if hasattr(self.inbox, "watermark"):
            applied = int(self.inbox.watermark(self.consumer_id, operation_id))
        missing = [version for version in versions if version > applied]
        return {
            "kind": "spine_gap",
            "hit": len(missing) == 0,
            "law": "published-versus-watermark",
            "citation": "VOL-134",
            "operation_id": operation_id,
            "published_versions": versions,
            "applied_through": applied,
            "missing": missing,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
