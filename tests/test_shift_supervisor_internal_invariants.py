from datetime import datetime, timezone

from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI, SquadPlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.squads import SquadCoordinator


def _worker(worker_id: str, *, overtime: int = 0) -> WorkerState:
    return WorkerState(
        worker_id=worker_id,
        team="night",
        status="idle",
        overtime_minutes=overtime,
    )


def _legacy_task(task_id: str = "legacy-task", priority: int = 50) -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description="legacy work",
        priority=priority,
        target_team="night",
    )


def _squad_task(task_id: str = "squad-task", priority: int = 100) -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description="four-agent work",
        priority=priority,
        target_team="night",
        metadata={
            "squad_size": 4,
            "relevant_paths": ["core/shift_supervisor/plan_api.py"],
        },
    )


def test_legacy_zero_overtime_limit_allows_zero_overtime_worker() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-0", overtime=0))
    store.add_items([_legacy_task()])

    claimed = PlanQueueAPI(store, overtime_soft_limit_minutes=0).claim_next("night-0")

    assert claimed is not None
    assert claimed["id"] == "legacy-task"


def test_explicit_unsupported_squad_size_never_falls_through_to_legacy_queue() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-0"))
    unsupported = _squad_task("unsupported-squad", priority=100)
    unsupported.metadata["squad_size"] = 5
    store.add_items([unsupported, _legacy_task(priority=50)])

    claimed = PlanQueueAPI(store).claim_next("night-0")

    assert claimed is not None
    assert claimed["id"] == "legacy-task"
    by_id = {item.id: item for item in store.snapshot_items()}
    assert by_id["unsupported-squad"].status == "queued"
    assert by_id["unsupported-squad"].owner is None


def test_safe_capacity_reclaims_expired_leases_before_planning() -> None:
    store = InMemoryPlanStore()
    for index in range(4):
        store.upsert_worker(_worker(f"night-{index}"))
    store.add_items([_squad_task()])

    lease = SquadCoordinator(store, default_lease_minutes=5).claim_next(
        "night",
        plan_generation="rev-1",
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert lease is not None
    assert all(worker.status == "working" for worker in store.snapshot_workers())

    capacity = SquadPlanQueueAPI(store).safe_capacity("night")

    assert capacity == 1
    item = store.snapshot_items()[0]
    assert item.status == "queued"
    assert item.owner is None
    assert item.metadata["squad_lease_history"][-1]["outcome"] == "lease_expired"
    assert all(worker.status == "idle" for worker in store.snapshot_workers())
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())
