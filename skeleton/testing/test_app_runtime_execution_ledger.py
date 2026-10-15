"""Runtime ledger execution IDs must not collide under sustained load."""

from __future__ import annotations

from skeleton.app.runtime.execution_ledger import ExecutionLedger, ExecutionStatus


def test_execution_ids_remain_unique_after_retention_capacity_is_reached():
    ledger = ExecutionLedger(max_records=2)
    first = ledger.begin("app-start")
    second = ledger.begin("app-start")
    third = ledger.begin("app-start")
    fourth = ledger.begin("app-start")

    assert len({first.execution_id, second.execution_id, third.execution_id, fourth.execution_id}) == 4
    assert ledger.get(first.execution_id) is None
    assert ledger.get(second.execution_id) is None
    assert ledger.get(third.execution_id) is not None
    assert ledger.get(fourth.execution_id) is not None
    assert [item.execution_id for item in ledger.snapshot()] == [
        third.execution_id, fourth.execution_id,
    ]


def test_latest_execution_can_complete_after_ledger_trimming():
    ledger = ExecutionLedger(max_records=1)
    earlier = ledger.begin("repair")
    latest = ledger.begin("repair")
    completed = ledger.complete(latest.execution_id, success=True, evidence={"phase": "done"})

    assert earlier.execution_id != latest.execution_id
    assert ledger.get(earlier.execution_id) is None
    assert completed.status is ExecutionStatus.SUCCEEDED
    assert ledger.get(latest.execution_id) == completed
