from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.persistence.consistency_fence import ConsistencyConflict, ConsistencyFenceError
from skeleton.persistence.mongo_fence import MongoConsistencyFence


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_mongo_fence_opens_advances_and_hides_foreign_tenant() -> None:
    fence = MongoConsistencyFence()
    opened = fence.compare_and_advance(
        tenant_id="tenant-mongo",
        resource_id="op:1",
        expected_epoch=0,
        writer_id="writer",
        now=BASE,
    )
    assert opened.epoch == 1
    advanced = fence.compare_and_advance(
        tenant_id="tenant-mongo",
        resource_id="op:1",
        expected_epoch=1,
        writer_id="writer",
        now=BASE,
    )
    assert advanced.epoch == 2
    with pytest.raises(ConsistencyConflict):
        fence.compare_and_advance(
            tenant_id="tenant-mongo",
            resource_id="op:1",
            expected_epoch=1,
            writer_id="writer",
            now=BASE,
        )
    with pytest.raises(ConsistencyFenceError):
        fence.read(tenant_id="tenant-other", resource_id="op:1")
    assert fence.card()["completion_checkbox"] is False
