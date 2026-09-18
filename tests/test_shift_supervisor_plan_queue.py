from concurrent.futures import ThreadPoolExecutor

from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore


def _worker(worker_id: str, team: str, *, overtime_minutes: int = 0) -> WorkerState:
    return WorkerState(
        worker_id=worker_id,
        team=team,  # type: ignore[arg-type]
        status="idle",
        overtime_minutes=overtime_minutes,
    )


def test_worker_pulls_highest_priority_eligible_plan_item_and_cannot_double_claim():
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-1", "night"))
    store.add_items(
        [
            PlanItem(id="low", title="Low", description="low", priority=20, target_team="night"),
            PlanItem(id="high", title="High", description="high", priority=90, target_team="night"),
            PlanItem(id="idle", title="Idle", description="idle", priority=100, target_team="idle"),
        ]
    )
    queue = PlanQueueAPI(store)

    claimed = queue.claim_next("night-1")

    assert claimed is not None
    assert claimed["id"] == "high"
    assert claimed["owner"] == "night-1"
    assert claimed["status"] == "assigned"
    assert queue.claim_next("night-1") is None


def test_dependency_blocks_claim_until_predecessor_is_done():
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-1", "night"))
    store.upsert_worker(_worker("night-2", "night"))
    store.add_items(
        [
            PlanItem(id="base", title="Base", description="base", priority=50, target_team="night"),
            PlanItem(
                id="follow",
                title="Follow",
                description="follow",
                priority=100,
                target_team="night",
                dependencies=["base"],
            ),
        ]
    )
    queue = PlanQueueAPI(store)

    first = queue.claim_next("night-1")
    assert first is not None and first["id"] == "base"
    assert queue.claim_next("night-2") is None

    queue.complete("night-1", "base")
    second = queue.claim_next("night-2")
    assert second is not None and second["id"] == "follow"


def test_team_and_overtime_guards_prevent_extra_work():
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-overtime", "night", overtime_minutes=120))
    store.upsert_worker(_worker("idle-1", "idle"))
    store.add_items(
        [
            PlanItem(id="night", title="Night", description="night", priority=90, target_team="night"),
        ]
    )
    queue = PlanQueueAPI(store, overtime_soft_limit_minutes=120)

    assert queue.claim_next("night-overtime") is None
    assert queue.claim_next("idle-1") is None
    assert store.snapshot_items()[0].owner is None


def test_release_returns_unfinished_work_to_plan_without_supervisor_contact():
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-1", "night"))
    store.upsert_worker(_worker("night-2", "night"))
    store.add_items(
        [
            PlanItem(id="task", title="Task", description="task", priority=90, target_team="night"),
        ]
    )
    queue = PlanQueueAPI(store)

    assert queue.claim_next("night-1")["id"] == "task"
    released = queue.release("night-1", "task")
    assert released["owner"] is None
    assert released["status"] == "queued"

    reclaimed = queue.claim_next("night-2")
    assert reclaimed is not None
    assert reclaimed["id"] == "task"
    assert reclaimed["owner"] == "night-2"


def test_concurrent_workers_cannot_double_claim_one_plan_item():
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-1", "night"))
    store.upsert_worker(_worker("night-2", "night"))
    store.add_items(
        [
            PlanItem(id="only", title="Only", description="only", priority=100, target_team="night"),
        ]
    )
    queue = PlanQueueAPI(store)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(queue.claim_next, ["night-1", "night-2"]))

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0]["id"] == "only"


def test_blocked_or_offline_worker_cannot_claim():
    store = InMemoryPlanStore()
    store.upsert_worker(WorkerState(worker_id="blocked", team="night", status="blocked"))
    store.upsert_worker(WorkerState(worker_id="offline", team="night", status="offline"))
    store.add_items(
        [
            PlanItem(id="task", title="Task", description="task", priority=100, target_team="night"),
        ]
    )
    queue = PlanQueueAPI(store)

    assert queue.claim_next("blocked") is None
    assert queue.claim_next("offline") is None


def test_working_worker_without_task_cannot_claim_new_work():
    store = InMemoryPlanStore()
    store.upsert_worker(WorkerState(worker_id="stale-working", team="night", status="working"))
    store.add_items(
        [
            PlanItem(id="task", title="Task", description="task", priority=100, target_team="night"),
        ]
    )
    queue = PlanQueueAPI(store)

    assert queue.claim_next("stale-working") is None
    assert store.claim_next_for_worker("stale-working") is None
    assert store.snapshot_items()[0].owner is None
