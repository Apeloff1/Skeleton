from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI, SquadPlanQueueAPI
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


def test_active_lease_members_stay_reserved_when_worker_row_loses_assignment() -> None:
    store = InMemoryPlanStore()
    for index in range(7):
        store.upsert_worker(_worker(f"night-{index}"))

    first = _squad_task("task-a")
    second = _squad_task("task-b")
    second.metadata["relevant_paths"] = ["skeleton/independent/module.py"]
    store.add_items([first, second])

    api = SquadPlanQueueAPI(store)
    lease = api.claim_next("night", plan_generation="rev-1")
    assert lease is not None
    assert lease["task_id"] == "task-a"

    damaged_worker_id = next(iter(lease["members"].values()))
    damaged_worker = next(
        worker
        for worker in store.snapshot_workers()
        if worker.worker_id == damaged_worker_id
    )
    # Simulate a partial durable restore that lost the worker-row assignment
    # while the canonical task lease remains valid and authoritative.
    damaged_worker.current_task_id = None
    damaged_worker.status = "idle"
    damaged_worker.metadata = {}
    store.upsert_worker(damaged_worker)

    # Only three genuinely unreserved workers remain, so the damaged lease
    # member must not be counted or double-booked into the second squad.
    assert api.safe_capacity("night") == 0
    assert api.claim_next("night", plan_generation="rev-1") is None

    by_id = {item.id: item for item in store.snapshot_items()}
    assert by_id["task-a"].status == "assigned"
    assert by_id["task-b"].status == "queued"
    assert by_id["task-b"].owner is None


def test_legacy_queue_cannot_claim_worker_reserved_by_active_squad_lease() -> None:
    store = InMemoryPlanStore()
    for index in range(4):
        store.upsert_worker(_worker(f"night-{index}"))
    store.add_items([_squad_task("task-a")])

    squad_api = SquadPlanQueueAPI(store)
    lease = squad_api.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    damaged_worker_id = next(iter(lease["members"].values()))
    damaged_worker = next(
        worker
        for worker in store.snapshot_workers()
        if worker.worker_id == damaged_worker_id
    )
    damaged_worker.current_task_id = None
    damaged_worker.status = "idle"
    damaged_worker.metadata = {}
    store.upsert_worker(damaged_worker)

    legacy = PlanItem(
        id="legacy-task",
        title="legacy-task",
        description="single-worker fallback work",
        priority=50,
        target_team="night",
    )
    store.add_items([legacy])

    assert PlanQueueAPI(store).claim_next(damaged_worker_id) is None
    legacy_after = next(item for item in store.snapshot_items() if item.id == "legacy-task")
    assert legacy_after.status == "queued"
    assert legacy_after.owner is None
