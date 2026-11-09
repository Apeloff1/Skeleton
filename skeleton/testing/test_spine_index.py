from __future__ import annotations

from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.mongo_inbox import MongoInboxLedger
from skeleton.persistence.spine_index import SpineIndexPlan


def test_index_plan_skips_memory_driver() -> None:
    plan = SpineIndexPlan(MongoInboxLedger(None), MongoConsistencyFence())
    assert len(plan.plan()) == 3
    card = plan.apply()
    assert card["created"] == 0
    assert card["skipped"] == 3
    assert card["completion_checkbox"] is False
