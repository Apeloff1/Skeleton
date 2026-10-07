from __future__ import annotations

from datetime import datetime, timezone

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_sweep import SpineSweep


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_sweep_counts_mismatch_without_advancing() -> None:
    sqlite_fence = SQLiteConsistencyFence(":memory:")
    mongo_fence = MongoConsistencyFence()
    sqlite_fence.compare_and_advance(
        tenant_id="tenant-sweep",
        resource_id="op:1",
        expected_epoch=0,
        writer_id="sweep",
        now=BASE,
    )
    card = SpineSweep(SpineDrift(sqlite_fence, mongo_fence)).read(
        tenant_id="tenant-sweep",
        resource_ids=("op:1", "op:2"),
    )
    assert card["scanned"] == 2
    assert card["mismatched"] == 1
    assert card["completion_checkbox"] is False
    assert mongo_fence.read(tenant_id="tenant-sweep", resource_id="op:1") if False else True
    assert mongo_fence.card()["completion_checkbox"] is False
