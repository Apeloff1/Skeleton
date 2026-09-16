from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI, SquadPlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore


def _worker(worker_id: str) -> WorkerState:
    return WorkerState(worker_id=worker_id, team="night", status="idle")


def test_unstamped_legacy_task_is_not_claimed_by_squad_runtime() -> None:
    store = InMemoryPlanStore()
    for index in range(4):
        store.upsert_worker(_worker(f"night-{index}"))
    store.add_items(
        [
            PlanItem(
                id="legacy-task",
                title="Legacy task",
                description="Explicitly retains single-worker semantics.",
                priority=100,
                target_team="night",
            )
        ]
    )

    assert (
        SquadPlanQueueAPI(store).claim_next(
            "night",
            plan_generation="rev-1",
        )
        is None
    )
    item = store.snapshot_items()[0]
    assert item.status == "queued"
    assert item.owner is None


def test_unstamped_legacy_task_remains_available_to_single_worker_queue() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-0"))
    store.add_items(
        [
            PlanItem(
                id="legacy-task",
                title="Legacy task",
                description="Explicitly retains single-worker semantics.",
                priority=100,
                target_team="night",
            )
        ]
    )

    claimed = PlanQueueAPI(store).claim_next("night-0")
    assert claimed is not None
    assert claimed["id"] == "legacy-task"
    assert claimed["status"] == "assigned"
