from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.shift_manager import SMBShiftManager
from core.shift_supervisor.worker_api import WorkerControlAPI


class NoopModel:
    def call_json(self, **kwargs):
        return {"summary": "", "tasks": [], "delegation": []}


def test_worker_control_api_reports_clock_state():
    manager = SMBShiftManager(store=InMemoryPlanStore(), model=NoopModel())
    api = WorkerControlAPI(manager)

    state = api.clock_in("night-1", "night")
    assert state["worker_id"] == "night-1"
    assert state["team"] == "night"
    assert state["status"] == "idle"

    state = api.heartbeat("night-1", status="working", task_id="task-1")
    assert state["status"] == "working"
    assert state["current_task_id"] == "task-1"
