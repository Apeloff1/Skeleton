from datetime import datetime, timedelta, timezone

from core.shift_supervisor.health import snapshot_health
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.shift_manager import SMBShiftManager


class NoopModel:
    def call_json(self, **kwargs):
        return {"summary": "", "tasks": [], "delegation": []}


def test_health_reports_active_and_overtime_workers():
    store = InMemoryPlanStore()
    manager = SMBShiftManager(store=store, model=NoopModel(), normal_shift_minutes=60)
    start = datetime(2026, 9, 16, tzinfo=timezone.utc)
    manager.clock_in("night-1", "night", at=start)
    manager.heartbeat("night-1", status="working", task_id="x", at=start + timedelta(minutes=61))

    health = snapshot_health(store)

    assert health.clocked_in == 1
    assert health.working == 1
    assert health.overtime_workers == 1
