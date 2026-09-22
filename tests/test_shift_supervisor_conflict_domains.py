from __future__ import annotations

from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI, PlanReadAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore


def _worker(worker_id: str) -> WorkerState:
    return WorkerState(worker_id=worker_id, team="night", status="idle")


def _item(item_id: str, priority: int, domain: str) -> PlanItem:
    return PlanItem(
        id=item_id,
        title=f"Task {item_id}",
        description="conflict-domain regression fixture",
        priority=priority,
        target_team="night",
        metadata={
            "conflict_domain": domain,
            "relevant_paths": ["core/shift_supervisor"],
        },
    )


def test_legacy_queue_serializes_matching_conflict_domains() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("worker-1"))
    store.upsert_worker(_worker("worker-2"))
    store.add_items(
        [
            _item("task-a", 100, "path:core/shift_supervisor"),
            _item("task-b", 90, "PATH:CORE/SHIFT_SUPERVISOR"),
        ]
    )
    queue = PlanQueueAPI(store)

    first = queue.claim_next("worker-1")
    assert first is not None
    assert first["id"] == "task-a"
    assert queue.claim_next("worker-2") is None

    store.finish_claim("worker-1", "task-a", outcome="done")
    second = queue.claim_next("worker-2")
    assert second is not None
    assert second["id"] == "task-b"


def test_wildcard_conflict_domain_blocks_independent_domain_until_release() -> None:
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("worker-1"))
    store.upsert_worker(_worker("worker-2"))
    store.add_items(
        [
            _item("global", 100, "*"),
            _item("local", 90, "api:plan-queue"),
        ]
    )
    queue = PlanQueueAPI(store)

    assert queue.claim_next("worker-1")["id"] == "global"
    assert queue.claim_next("worker-2") is None


def test_plan_read_payload_surfaces_conflict_context() -> None:
    store = InMemoryPlanStore()
    store.add_items([_item("task-a", 100, "api:plan-queue")])

    payload = PlanReadAPI(store).pending_for_team("night")[0]
    assert payload["conflict_domain"] == "api:plan-queue"
    assert payload["relevant_paths"] == ["core/shift_supervisor"]
