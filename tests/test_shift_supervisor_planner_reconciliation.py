import json
from datetime import datetime, timezone

from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.shift_manager import SMBShiftManager
from core.shift_supervisor.squads import SQUAD_SIZE, SquadCoordinator


class RecordingModel:
    def __init__(self) -> None:
        self.calls = []

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        return {"summary": "reconciled", "tasks": []}


def _store_with_squad() -> tuple[InMemoryPlanStore, PlanItem]:
    store = InMemoryPlanStore()
    for index in range(SQUAD_SIZE):
        store.upsert_worker(
            WorkerState(worker_id=f"night-{index}", team="night", status="idle")
        )
    item = PlanItem(
        id="squad-task",
        title="squad-task",
        description="four-agent work",
        priority=100,
        target_team="night",
        metadata={
            "squad_size": SQUAD_SIZE,
            "relevant_paths": ["core/shift_supervisor/shift_manager.py"],
        },
    )
    store.add_items([item])
    return store, item


def _planner_capacity(model: RecordingModel) -> int:
    payload = json.loads(model.calls[-1]["user_prompt"])
    return payload["staffing"]["teams"]["night"]["safe_squad_capacity"]


def test_manager_reclaims_expired_lease_before_reporting_planner_capacity() -> None:
    store, _ = _store_with_squad()
    lease = SquadCoordinator(store, default_lease_minutes=5).claim_next(
        "night",
        plan_generation="rev-1",
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert lease is not None
    model = RecordingModel()

    SMBShiftManager(store=store, model=model).refresh_plan(project_context={})

    assert _planner_capacity(model) == 1
    item = store.snapshot_items()[0]
    assert item.status == "queued"
    assert item.owner is None
    assert item.metadata["squad_lease_history"][-1]["outcome"] == "lease_expired"
    assert all(worker.status == "idle" for worker in store.snapshot_workers())
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())


def test_manager_recovers_malformed_lease_before_reporting_planner_capacity() -> None:
    store, _ = _store_with_squad()
    lease = SquadCoordinator(store).claim_next(
        "night",
        plan_generation="rev-1",
    )
    assert lease is not None
    item = store.snapshot_items()[0]
    broken_lease = dict(item.metadata["squad_lease"])
    broken_members = dict(broken_lease["members"])
    broken_members.pop("verifier")
    broken_lease["members"] = broken_members
    item.metadata = {**item.metadata, "squad_lease": broken_lease}
    store.update_item(item)
    model = RecordingModel()

    SMBShiftManager(store=store, model=model).refresh_plan(project_context={})

    assert _planner_capacity(model) == 1
    recovered = store.snapshot_items()[0]
    assert recovered.status == "queued"
    assert recovered.owner is None
    assert recovered.metadata["squad_lease_history"][-1]["outcome"] == "invalid_lease_recovered"
    assert all(worker.status == "idle" for worker in store.snapshot_workers())
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())
