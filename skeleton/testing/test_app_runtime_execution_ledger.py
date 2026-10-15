"""Runtime ledger execution IDs must not collide under sustained load."""

from __future__ import annotations

from skeleton.app.runtime.execution_ledger import ExecutionLedger, ExecutionStatus


def test_execution_ids_remain_unique_after_retention_capacity_is_reached():
    ledger = ExecutionLedger(max_records=2)
    first = ledger.begin("app-start")
    ledger.complete(first.execution_id, success=True)
    second = ledger.begin("app-start")
    ledger.complete(second.execution_id, success=True)
    third = ledger.begin("app-start")
    ledger.complete(third.execution_id, success=True)
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
    ledger.complete(earlier.execution_id, success=False)
    latest = ledger.begin("repair")
    completed = ledger.complete(latest.execution_id, success=True, evidence={"phase": "done"})

    assert earlier.execution_id != latest.execution_id
    assert ledger.get(earlier.execution_id) is None
    assert completed.status is ExecutionStatus.SUCCEEDED
    assert ledger.get(latest.execution_id) == completed


def test_ledger_refuses_new_work_instead_of_eviction_of_active_execution():
    import pytest

    ledger = ExecutionLedger(max_records=1)
    active = ledger.begin("repair")

    with pytest.raises(OverflowError, match="full of active work"):
        ledger.begin("another-command")

    assert ledger.get(active.execution_id) == active
    finished = ledger.complete(active.execution_id, success=True)
    assert finished.status is ExecutionStatus.SUCCEEDED
    later = ledger.begin("another-command")
    assert later.execution_id != active.execution_id
