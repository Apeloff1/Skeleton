from __future__ import annotations

from datetime import datetime, timezone

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_repair import RepairIntent


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_drift_reports_mismatch_without_advancing() -> None:
    sqlite_fence = SQLiteConsistencyFence(":memory:")
    mongo_fence = MongoConsistencyFence()
    sqlite_fence.compare_and_advance(
        tenant_id="tenant-drift",
        resource_id="op:1",
        expected_epoch=0,
        writer_id="drift",
        now=BASE,
    )
    card = SpineDrift(sqlite_fence, mongo_fence).read(tenant_id="tenant-drift", resource_id="op:1")
    assert card["sqlite_epoch"] == 1
    assert card["mongo_epoch"] == 0
    assert card["hit"] is False
    assert card["completion_checkbox"] is False
    assert mongo_fence.card()["completion_checkbox"] is False


def test_apply_gate_refuses_and_applies_nothing() -> None:
    gate = SpineApplyGate()
    intent = RepairIntent("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "tenant-drift", "InboxConflict", BASE)
    refusal = gate.consider(intent, now=BASE)
    assert refusal.as_dict()["applied"] == 0
    assert gate.card()["applied"] == 0
    assert gate.card()["refused"] == 1
