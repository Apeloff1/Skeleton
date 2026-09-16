from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_api import SquadPlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore


def _worker(worker_id: str) -> WorkerState:
    return WorkerState(
        worker_id=worker_id,
        team="night",
        status="idle",
    )


def _squad_task(task_id: str) -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description=f"work {task_id}",
        priority=100,
        target_team="night",
        metadata={
            "squad_size": 4,
            "relevant_paths": ["skeleton/recovery/module.py"],
        },
    )


def test_invalid_lease_recovery_does_not_clobber_worker_reassigned_elsewhere() -> None:
    store = InMemoryPlanStore()
    for index in range(4):
        store.upsert_worker(_worker(f"night-{index}"))
    store.add_items([_squad_task("task-a")])

    api = SquadPlanQueueAPI(store)
    lease = api.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    moved_worker_id = next(iter(lease["members"].values()))
    moved_worker = next(
        worker for worker in store.snapshot_workers() if worker.worker_id == moved_worker_id
    )
    # Simulate a partially persisted handoff: the canonical task pointer already
    # moved, while stale squad metadata from the old lease is still present.
    moved_worker.current_task_id = "task-b"
    moved_worker.status = "working"
    store.upsert_worker(moved_worker)

    item = store.snapshot_items()[0]
    corrupted = dict(item.metadata["squad_lease"])
    corrupted["expires_at"] = "not-a-timestamp"
    item.metadata["squad_lease"] = corrupted
    store.update_item(item)

    assert api.recover_invalid_leases() == ["task-a"]

    recovered_workers = {worker.worker_id: worker for worker in store.snapshot_workers()}
    moved_after = recovered_workers[moved_worker_id]
    assert moved_after.current_task_id == "task-b"
    assert moved_after.status == "working"

    released = [
        worker
        for worker_id, worker in recovered_workers.items()
        if worker_id != moved_worker_id
    ]
    assert all(worker.current_task_id is None for worker in released)
    assert all(worker.status == "idle" for worker in released)
