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


def test_higher_priority_squad_task_does_not_starve_legacy_queue() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-0"))
    store.add_items(
        [
            PlanItem(
                id="squad-task",
                title="Squad task",
                description="Must stay reserved for four-agent execution.",
                priority=100,
                target_team="night",
                metadata={"squad_size": 4},
            ),
            PlanItem(
                id="legacy-task",
                title="Legacy task",
                description="Must remain reachable by the legacy queue.",
                priority=50,
                target_team="night",
            ),
        ]
    )

    claimed = PlanQueueAPI(store).claim_next("night-0")
    assert claimed is not None
    assert claimed["id"] == "legacy-task"

    by_id = {item.id: item for item in store.snapshot_items()}
    assert by_id["squad-task"].status == "queued"
    assert by_id["squad-task"].owner is None
    assert by_id["legacy-task"].status == "assigned"
    assert by_id["legacy-task"].owner == "night-0"


def test_malformed_squad_stamp_fails_closed_for_legacy_queue() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-0"))
    store.add_items(
        [
            PlanItem(
                id="malformed-squad-task",
                title="Malformed squad task",
                description="Invalid squad metadata must not fall through to legacy dispatch.",
                priority=100,
                target_team="night",
                metadata={"squad_size": "four"},
            ),
            PlanItem(
                id="legacy-task",
                title="Legacy task",
                description="Safe fallback legacy work.",
                priority=50,
                target_team="night",
            ),
        ]
    )

    claimed = PlanQueueAPI(store).claim_next("night-0")
    assert claimed is not None
    assert claimed["id"] == "legacy-task"

    by_id = {item.id: item for item in store.snapshot_items()}
    assert by_id["malformed-squad-task"].status == "queued"
    assert by_id["malformed-squad-task"].owner is None
