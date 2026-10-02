from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_projection import SpineProjection
from skeleton.persistence.spine_quarantine import SpineQuarantine
from skeleton.persistence.spine_status import SpineStatus


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_status_and_quarantine_stay_unsigned(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        projection.project(now=BASE + timedelta(seconds=1))
        status = SpineStatus(projection, inbox, fence)
        card = status.card(tenant_id="tenant-status", resource_id="op:missing")
        assert card["fence_epoch"] is None
        assert card["poison_count"] == 0
        assert card["completion_checkbox"] is False
        quarantine = SpineQuarantine(projection)
        assert quarantine.card("tenant-status")["count"] == 0
