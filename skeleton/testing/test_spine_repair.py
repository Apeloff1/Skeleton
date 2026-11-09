from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_projection import SpineProjection
from skeleton.persistence.spine_quarantine import SpineQuarantine
from skeleton.persistence.spine_repair import SpineRepairPlan


BASE = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_repair_plan_does_not_apply(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "ops.sqlite")
    inbox = SQLiteInboxLedger(tmp_path / "inbox.sqlite")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    with SpineProjection(operations, inbox, fence, journal_path=tmp_path / "journal.sqlite") as projection:
        plan = SpineRepairPlan(SpineQuarantine(projection))
        planned = plan.plan(tenant_id="tenant-repair", now=BASE)
        assert planned == ()
        card = plan.card("tenant-repair")
        assert card["applied"] == 0
        assert card["completion_checkbox"] is False
        assert fence.card()["fence_count"] == 0
