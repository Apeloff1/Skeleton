from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_digest import SpineDigest
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_gap import SpineGap
from skeleton.persistence.spine_ledger import SpineLedger


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
OP = "17171717-1717-4717-8717-171717171717"


def test_ledger_appends_same_digest(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    digest = SpineDigest(
        SpineGap(operations, inbox),
        SpineDrift(SQLiteConsistencyFence(tmp_path / "fence.sqlite"), MongoConsistencyFence()),
    )
    ledger = SpineLedger(tmp_path / "ledger.sqlite", digest)
    first = ledger.record(tenant_id="tenant-ledger", operation_id=OP, now=BASE)
    second = ledger.record(tenant_id="tenant-ledger", operation_id=OP, now=BASE)
    assert first["digest"] == second["digest"]
    assert second["count"] == 2
    assert second["completion_checkbox"] is False
    ledger.close()
