from __future__ import annotations

from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_digest import SpineDigest
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_gap import SpineGap
from skeleton.persistence.spine_ledger import SpineLedger
from skeleton.persistence.spine_pair import SpinePair
from skeleton.persistence.spine_tracker import SpineTracker


def test_tracker_and_pair(tmp_path: Path) -> None:
    card = SpineTracker().card()
    assert card["read_project_percent"] == 84
    assert card["apply_percent"] == 0
    assert card["merge_percent"] == 0
    assert card["completion_checkbox"] is False
    digest = SpineDigest(
        SpineGap(SQLiteOperationStore(tmp_path / "ops.sqlite"), SQLiteInboxLedger(tmp_path / "inbox.sqlite")),
        SpineDrift(SQLiteConsistencyFence(tmp_path / "fence.sqlite"), MongoConsistencyFence()),
    )
    ledger = SpineLedger(tmp_path / "ledger.sqlite", digest)
    pair = SpinePair(ledger).read(
        tenant_id="tenant-pair",
        operation_id="18181818-1818-4818-8818-181818181818",
    )
    assert pair["equal"] is True
    assert pair["count"] == 0
    ledger.close()
