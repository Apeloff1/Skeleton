from datetime import datetime, timedelta, timezone

import pytest

from core.shift_supervisor.models import PlanItem, PlanRevision, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI, SquadPlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.squads import SQUAD_ROLES, SQUAD_SIZE, SquadCoordinator, safe_squad_capacity


def _worker(worker_id: str, team: str = "night", *, preferred: str | None = None) -> WorkerState:
    metadata = {}
    if preferred:
        metadata["preferred_squad_roles"] = [preferred]
    return WorkerState(worker_id=worker_id, team=team, status="idle", metadata=metadata)  # type: ignore[arg-type]


def _task(task_id: str, priority: int, domain: str, *, deps: list[str] | None = None) -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description=f"work {task_id}",
        priority=priority,
        target_team="night",
        dependencies=list(deps or []),
        metadata={
            "squad_size": 4,
            "conflict_domain": domain,
            "relevant_paths": [f"skeleton/{domain}/module.py"],
        },
    )


def _seed_workers(store: InMemoryPlanStore, count: int) -> None:
    roles = list(SQUAD_ROLES)
    for index in range(count):
        preferred = roles[index] if index < len(roles) else None
        store.upsert_worker(_worker(f"night-{index}", preferred=preferred))


def _completion_evidence() -> dict[str, bool]:
    return {
        "research_complete": True,
        "implementation_complete": True,
        "reviewer_approved": True,
        "verifier_approved": True,
    }


def _revision(revision_id: str) -> PlanRevision:
    return PlanRevision(
        revision_id=revision_id,
        actor="test-supervisor",
        created_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
    )


def test_capacity_is_four_workers_per_squad_and_spares_do_not_swarm() -> None:
    workers = [_worker(f"night-{index}") for index in range(9)]
    assert SQUAD_SIZE == 4
    assert safe_squad_capacity(workers, "night") == 2


def test_claim_reserves_exactly_four_distinct_roles_and_blocks_legacy_single_worker_claim() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 5)
    store.add_items([_task("task-a", 100, "gameplay")])

    legacy = PlanQueueAPI(store)
    assert legacy.claim_next("night-4") is None
    assert store.snapshot_items()[0].status == "queued"
    assert store.snapshot_items()[0].owner is None

    squad = SquadPlanQueueAPI(store).claim_next("night", plan_generation="rev-1")
    assert squad is not None
    assert set(squad["members"]) == set(SQUAD_ROLES)
    assert len(set(squad["members"].values())) == 4
    assert squad["conflict_domain"] == "skeleton/gameplay"
    item = store.snapshot_items()[0]
    assert item.owner == squad["squad_id"]
    assert item.status == "assigned"


def test_conflict_domain_prevents_two_squads_from_piling_into_same_subsystem() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 12)
    store.add_items(
        [
            _task("same-high", 100, "engine"),
            _task("same-low", 90, "engine"),
            _task("other", 80, "networking"),
        ]
    )
    api = SquadPlanQueueAPI(store)

    first = api.claim_next("night", plan_generation="rev-1")
    second = api.claim_next("night", plan_generation="rev-1")

    assert first is not None and first["task_id"] == "same-high"
    assert second is not None and second["task_id"] == "other"
    queued = {item.id: item.status for item in store.snapshot_items()}
    assert queued["same-low"] == "queued"


def test_conflict_lock_uses_repository_paths_not_model_labels() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 8)
    first = _task("first", 100, "claimed-label")
    second = _task("second", 90, "different-label")
    first.metadata["relevant_paths"] = ["skeleton/shared/core.py"]
    second.metadata["relevant_paths"] = ["skeleton/shared/other.py"]
    store.add_items([first, second])
    api = SquadPlanQueueAPI(store)

    claimed = api.claim_next("night", plan_generation="rev-1")
    blocked = api.claim_next("night", plan_generation="rev-1")

    assert claimed is not None
    assert claimed["conflict_domain"] == "skeleton/shared"
    assert blocked is None


def test_dependencies_remain_authoritative_for_squad_claims() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 8)
    store.add_items([_task("base", 50, "base"), _task("follow", 100, "follow", deps=["base"])])
    coordinator = SquadCoordinator(store)

    first = coordinator.claim_next("night", plan_generation="rev-1")
    assert first is not None and first.task_id == "base"
    coordinator.finish(first.squad_id, first.task_id, outcome="done", evidence=_completion_evidence())
    second = coordinator.claim_next("night", plan_generation="rev-1")
    assert second is not None and second.task_id == "follow"


def test_current_plan_generation_is_required_when_revision_state_exists() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    store.append_revision(_revision("rev-current"))
    coordinator = SquadCoordinator(store)

    with pytest.raises(ValueError, match="stale plan_generation"):
        coordinator.claim_next("night", plan_generation="rev-old")

    lease = coordinator.claim_next("night", plan_generation="rev-current")
    assert lease is not None
    assert lease.plan_generation == "rev-current"


def test_completion_requires_independent_research_review_and_verification_evidence() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    coordinator = SquadCoordinator(store)
    lease = coordinator.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    with pytest.raises(ValueError, match="completion evidence missing"):
        coordinator.finish(
            lease.squad_id,
            lease.task_id,
            outcome="done",
            evidence={"implementation_complete": True},
        )

    finished = coordinator.finish(
        lease.squad_id,
        lease.task_id,
        outcome="done",
        evidence=_completion_evidence(),
    )
    assert finished.status == "done"
    assert all(worker.status == "idle" for worker in store.snapshot_workers())
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())


def test_expired_lease_cannot_finish_or_renew_and_reclaim_preserves_evidence() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    coordinator = SquadCoordinator(store, default_lease_minutes=5)
    start = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    lease = coordinator.claim_next("night", plan_generation="rev-7", now=start)
    assert lease is not None
    expired = start + timedelta(minutes=6)

    with pytest.raises(PermissionError, match="lease expired"):
        coordinator.renew(lease.squad_id, lease.task_id, now=expired)
    with pytest.raises(PermissionError, match="lease expired"):
        coordinator.finish(
            lease.squad_id,
            lease.task_id,
            outcome="done",
            evidence=_completion_evidence(),
            now=expired,
        )

    reclaimed = coordinator.reclaim_expired(now=expired)
    assert reclaimed == ["task-a"]
    item = store.snapshot_items()[0]
    assert item.status == "queued"
    assert item.owner is None
    assert item.metadata["lease_expiry_count"] == 1
    history = item.metadata["squad_lease_history"]
    assert history[-1]["outcome"] == "lease_expired"
    assert history[-1]["plan_generation"] == "rev-7"


def test_worker_role_preferences_are_used_without_reusing_worker() -> None:
    store = InMemoryPlanStore()
    for role in SQUAD_ROLES:
        store.upsert_worker(_worker(f"preferred-{role}", preferred=role))
    store.add_items([_task("task-a", 100, "gameplay")])
    lease = SquadCoordinator(store).claim_next("night", plan_generation="rev-1")
    assert lease is not None
    assert lease.members == {role: f"preferred-{role}" for role in SQUAD_ROLES}
