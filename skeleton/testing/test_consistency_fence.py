from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.consistency_fence import (
    ConsistencyConflict,
    ConsistencyFenceError,
    SQLiteConsistencyFence,
)


BASE = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def test_open_and_cas_advances_epoch_for_one_tenant() -> None:
    with SQLiteConsistencyFence() as fence:
        opened = fence.open(
            tenant_id="tenant-a",
            resource_id="operation-stream",
            writer_id="writer-a",
            now=BASE,
        )
        assert opened.epoch == 1
        advanced = fence.compare_and_advance(
            tenant_id="tenant-a",
            resource_id="operation-stream",
            expected_epoch=1,
            writer_id="writer-b",
            now=BASE + timedelta(seconds=1),
        )
        assert advanced.epoch == 2
        assert advanced.writer_id == "writer-b"
        assert fence.read(tenant_id="tenant-a", resource_id="operation-stream").digest == advanced.digest
        card = fence.card()
        assert card["stored_prose"] == 0
        assert card["completion_checkbox"] is False
        assert card["citation"] == "VOL-132"
        assert card["fence_count"] == 1


def test_stale_epoch_and_foreign_tenant_fail_closed() -> None:
    with SQLiteConsistencyFence() as fence:
        fence.open(
            tenant_id="tenant-a",
            resource_id="ledger",
            writer_id="writer-a",
            now=BASE,
        )
        with pytest.raises(ConsistencyConflict, match="stale"):
            fence.compare_and_advance(
                tenant_id="tenant-a",
                resource_id="ledger",
                expected_epoch=0,
                writer_id="writer-b",
                now=BASE + timedelta(seconds=1),
            )
        with pytest.raises(ConsistencyFenceError, match="unknown fence"):
            fence.read(tenant_id="tenant-b", resource_id="ledger")
        isolated = fence.open(
            tenant_id="tenant-b",
            resource_id="ledger",
            writer_id="writer-b",
            now=BASE,
        )
        assert isolated.epoch == 1
        assert fence.read(tenant_id="tenant-a", resource_id="ledger").epoch == 1


def test_advance_cannot_predate_current_token() -> None:
    with SQLiteConsistencyFence() as fence:
        fence.open(
            tenant_id="tenant-a",
            resource_id="ledger",
            writer_id="writer-a",
            now=BASE + timedelta(seconds=5),
        )
        with pytest.raises(ConsistencyConflict, match="predate"):
            fence.compare_and_advance(
                tenant_id="tenant-a",
                resource_id="ledger",
                expected_epoch=1,
                writer_id="writer-b",
                now=BASE,
            )
