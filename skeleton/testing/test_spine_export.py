from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_export import SpineExport
from skeleton.persistence.spine_projection import SpineProjection
from skeleton.persistence.spine_quarantine import SpineQuarantine


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_export_writes_unsigned_card(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        projection.project(now=BASE + timedelta(seconds=1))
        target = tmp_path / "card.json"
        card = SpineExport(SpineQuarantine(projection)).write(target, tenant_id="tenant-export")
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["count"] == 0
        assert loaded["completion_checkbox"] is False
        assert card["exported"] is True
        assert fence.card()["fence_count"] == 0
