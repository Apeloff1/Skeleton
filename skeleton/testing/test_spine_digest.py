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


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_digest_is_stable_and_unsigned(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    sqlite_fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    mongo_fence = MongoConsistencyFence()
    digest = SpineDigest(SpineGap(operations, inbox), SpineDrift(sqlite_fence, mongo_fence))
    first = digest.read(tenant_id="tenant-digest", operation_id="16161616-1616-4616-8616-161616161616")
    second = digest.read(tenant_id="tenant-digest", operation_id="16161616-1616-4616-8616-161616161616")
    assert first["digest"] == second["digest"]
    assert len(first["digest"]) == 64
    assert first["completion_checkbox"] is False
    assert first["sqlite_epoch"] == 0
    assert first["mongo_epoch"] == 0
