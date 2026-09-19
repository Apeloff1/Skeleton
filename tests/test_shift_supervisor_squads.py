from datetime import datetime, timedelta, timezone

import pytest

from core.shift_supervisor.models import PlanItem, PlanRevision, WorkerState
from core.shift_supervisor.plan_api import PlanQueueAPI, SquadPlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.squads import (
    SQUAD_ROLES,
    SQUAD_SIZE,
    SquadCoordinator,
    safe_squad_capacity,
)


def _worker(
    worker_id: str,
    team: str = "night",
    *,
    preferred: str | None = None,
    overtime: int = 0,
) -> WorkerState:
    metadata = {}
    if preferred:
        metadata["preferred_squad_roles"] = [preferred]
    return WorkerState(
        worker_id=worker_id,
        team=team,  # type: ignore[arg-type]
        status="idle",
        overtime_minutes=overtime,
        metadata=metadata,
    )


def _task(
    task_id: str,
    priority: int,
    domain: str,
    *,
    deps: list[str] | None = None,
    team: str = "night",
) -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description=f"work {task_id}",
        priority=priority,
        target_team=team,  # type: ignore[arg-type]
        dependencies=list(deps or []),
        metadata={
            "squad_size": 4,
            "conflict_domain": domain,
            "relevant_paths": [f"skeleton/{domain}/module.py"],
        },
    )


def _seed_workers(store: InMemoryPlanStore, count: int, team: str = "night") -> None:
    roles = list(SQUAD_ROLES)
    for index in range(count):
        preferred = roles[index] if index < len(roles) else None
        store.upsert_worker(_worker(f"{team}-{index}", team, preferred=preferred))


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


def test_zero_overtime_limit_still_allows_workers_with_zero_overtime() -> None:
    workers = [_worker(f"night-{index}") for index in range(4)]
    workers.append(_worker("night-overtime", overtime=1))
    assert safe_squad_capacity(
        workers,
        "night",
        overtime_soft_limit_minutes=0,
    ) == 1


def test_claim_reserves_exactly_four_distinct_roles_and_blocks_legacy_claim() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 5)
    store.add_items([_task("task-a", 100, "gameplay")])

    legacy = PlanQueueAPI(store)
    assert legacy.claim_next("night-4") is None
    item = store.snapshot_items()[0]
    assert item.status == "queued"
    assert item.owner is None

    squad = SquadPlanQueueAPI(store).claim_next("night", plan_generation="rev-1")
    assert squad is not None
    assert set(squad["members"]) == set(SQUAD_ROLES)
    assert len(set(squad["members"].values())) == 4
    assert squad["conflict_domain"] == "skeleton/gameplay"


def test_conflict_domain_uses_repository_paths_not_model_labels() -> None:
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


def test_independent_conflict_domains_can_run_in_parallel() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 8)
    store.add_items(
        [
            _task("gameplay", 100, "gameplay"),
            _task("network", 90, "networking"),
        ]
    )
    api = SquadPlanQueueAPI(store)
    first = api.claim_next("night", plan_generation="rev-1")
    second = api.claim_next("night", plan_generation="rev-1")
    assert first is not None
    assert second is not None
    assert first["conflict_domain"] != second["conflict_domain"]


def test_dependencies_remain_authoritative_for_squad_claims() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 8)
    store.add_items(
        [
            _task("base", 50, "base"),
            _task("follow", 100, "follow", deps=["base"]),
        ]
    )
    coordinator = SquadCoordinator(store)

    first = coordinator.claim_next("night", plan_generation="rev-1")
    assert first is not None and first.task_id == "base"
    coordinator.finish(
        first.squad_id,
        first.task_id,
        outcome="done",
        evidence=_completion_evidence(),
    )
    second = coordinator.claim_next("night", plan_generation="rev-1")
    assert second is not None and second.task_id == "follow"


def test_new_claim_requires_current_plan_generation() -> None:
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


def test_active_lease_survives_later_plan_revision() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    store.append_revision(_revision("rev-1"))
    start = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    coordinator = SquadCoordinator(store, default_lease_minutes=30)
    lease = coordinator.claim_next(
        "night",
        plan_generation="rev-1",
        now=start,
    )
    assert lease is not None

    store.append_revision(_revision("rev-2"))
    renewed = coordinator.renew(
        lease.squad_id,
        lease.task_id,
        minutes=30,
        now=start + timedelta(minutes=5),
    )
    assert renewed.plan_generation == "rev-1"
    finished = coordinator.finish(
        lease.squad_id,
        lease.task_id,
        outcome="done",
        evidence=_completion_evidence(),
        now=start + timedelta(minutes=10),
    )
    assert finished.status == "done"


def test_completion_requires_all_four_evidence_dimensions() -> None:
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


def test_expired_lease_cannot_mutate_and_reclaim_preserves_history() -> None:
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

    assert coordinator.reclaim_expired(now=expired) == ["task-a"]
    item = store.snapshot_items()[0]
    assert item.status == "queued"
    assert item.owner is None
    assert item.metadata["lease_expiry_count"] == 1
    assert item.metadata["squad_lease_history"][-1]["outcome"] == "lease_expired"
    assert item.metadata["squad_lease_history"][-1]["plan_generation"] == "rev-7"


def test_revoked_lease_cannot_renew_or_finish() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    coordinator = SquadCoordinator(store)
    lease = coordinator.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    item = store.snapshot_items()[0]
    item.metadata["lease_revoked"] = True
    store.update_item(item)

    with pytest.raises(PermissionError, match="revoked"):
        coordinator.renew(lease.squad_id, lease.task_id)
    with pytest.raises(PermissionError, match="revoked"):
        coordinator.finish(
            lease.squad_id,
            lease.task_id,
            outcome="done",
            evidence=_completion_evidence(),
        )


def test_api_revoke_immediately_releases_capacity_and_allows_fresh_lease() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    api = SquadPlanQueueAPI(store)
    lease = api.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    revoked = api.revoke(
        lease["squad_id"],
        lease["task_id"],
        reason="control-plane conflict detected",
    )
    assert revoked["status"] == "queued"
    assert revoked["owner"] is None
    assert revoked["metadata"]["lease_revocation_count"] == 1
    history = revoked["metadata"]["squad_lease_history"][-1]
    assert history["outcome"] == "lease_revoked"
    assert history["reason"] == "control-plane conflict detected"
    assert all(worker.status == "idle" for worker in store.snapshot_workers())
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())

    replacement = api.claim_next("night", plan_generation="rev-1")
    assert replacement is not None
    assert replacement["task_id"] == "task-a"
    assert replacement["lease_generation"] == lease["lease_generation"] + 1


def test_malformed_durable_lease_is_recovered_without_stranding_workers() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    api = SquadPlanQueueAPI(store)
    lease = api.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    item = store.snapshot_items()[0]
    corrupted = dict(item.metadata["squad_lease"])
    corrupted["expires_at"] = "not-a-timestamp"
    item.metadata["squad_lease"] = corrupted
    store.update_item(item)

    assert api.recover_invalid_leases() == ["task-a"]
    recovered = store.snapshot_items()[0]
    assert recovered.status == "queued"
    assert recovered.owner is None
    assert recovered.metadata["invalid_lease_recovery_count"] == 1
    history = recovered.metadata["squad_lease_history"][-1]
    assert history["outcome"] == "invalid_lease_recovered"
    assert "malformed squad lease" in history["error"]
    assert all(worker.status == "idle" for worker in store.snapshot_workers())
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())

    replacement = api.claim_next("night", plan_generation="rev-1")
    assert replacement is not None
    assert replacement["task_id"] == "task-a"
    assert replacement["lease_generation"] == lease["lease_generation"] + 1


def test_worker_role_preferences_are_used_without_worker_reuse() -> None:
    store = InMemoryPlanStore()
    for role in SQUAD_ROLES:
        store.upsert_worker(_worker(f"preferred-{role}", preferred=role))
    store.add_items([_task("task-a", 100, "gameplay")])
    lease = SquadCoordinator(store).claim_next("night", plan_generation="rev-1")
    assert lease is not None
    assert lease.members == {role: f"preferred-{role}" for role in SQUAD_ROLES}


def test_allowed_worker_pool_is_enforced_atomically() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 8)
    store.add_items([_task("task-a", 100, "gameplay")])
    allowed = {f"night-{index}" for index in range(4)}
    lease = SquadCoordinator(store).claim_next(
        "night",
        plan_generation="rev-1",
        worker_ids=sorted(allowed),
    )
    assert lease is not None
    assert set(lease.members.values()) == allowed


def test_inflight_squad_survives_durable_store_round_trip() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    store.append_revision(_revision("rev-1"))
    start = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    lease = SquadCoordinator(store, default_lease_minutes=30).claim_next(
        "night",
        plan_generation="rev-1",
        now=start,
    )
    assert lease is not None

    restored = InMemoryPlanStore()
    restored.restore_state(store.export_state(max_items=8, max_workers=8, max_revisions=8))
    restored_coordinator = SquadCoordinator(restored, default_lease_minutes=30)
    finished = restored_coordinator.finish(
        lease.squad_id,
        lease.task_id,
        outcome="done",
        evidence=_completion_evidence(),
        now=start + timedelta(minutes=5),
    )
    assert finished.status == "done"
    assert finished.metadata["squad_lease_history"][-1]["outcome"] == "done"


def test_lease_envelope_is_versioned_and_content_addressed() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    lease = SquadCoordinator(store).claim_next("night", plan_generation="rev-1")
    assert lease is not None

    envelope = store.snapshot_items()[0].metadata["squad_lease"]
    assert envelope["schema_version"] == 1
    assert len(envelope["fingerprint"]) == 64
    assert envelope["fingerprint"] == lease.fingerprint


def test_tampered_lease_fingerprint_is_recovered_fail_closed() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    api = SquadPlanQueueAPI(store)
    lease = api.claim_next("night", plan_generation="rev-1")
    assert lease is not None

    item = store.snapshot_items()[0]
    envelope = dict(item.metadata["squad_lease"])
    envelope["conflict_domain"] = "tampered-domain"
    item.metadata["squad_lease"] = envelope
    store.update_item(item)

    assert api.recover_invalid_leases() == ["task-a"]
    recovered = store.snapshot_items()[0]
    assert recovered.status == "queued"
    assert recovered.owner is None
    assert "fingerprint mismatch" in recovered.metadata["squad_lease_history"][-1]["error"]
    assert all(worker.current_task_id is None for worker in store.snapshot_workers())


def test_lease_schema_bool_does_not_alias_integer_version() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    api = SquadPlanQueueAPI(store)
    assert api.claim_next("night", plan_generation="rev-1") is not None

    item = store.snapshot_items()[0]
    envelope = dict(item.metadata["squad_lease"])
    envelope["schema_version"] = True
    item.metadata["squad_lease"] = envelope
    store.update_item(item)

    assert api.recover_invalid_leases() == ["task-a"]
    assert "schema version" in store.snapshot_items()[0].metadata["squad_lease_history"][-1]["error"]


def test_naive_lease_timestamp_is_recovered_fail_closed() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    api = SquadPlanQueueAPI(store)
    assert api.claim_next("night", plan_generation="rev-1") is not None

    item = store.snapshot_items()[0]
    envelope = dict(item.metadata["squad_lease"])
    envelope["started_at"] = "2026-09-19T12:00:00"
    item.metadata["squad_lease"] = envelope
    store.update_item(item)

    assert api.recover_invalid_leases() == ["task-a"]
    assert "timezone-aware" in store.snapshot_items()[0].metadata["squad_lease_history"][-1]["error"]


@pytest.mark.parametrize("value", [True, False, 30.5, "30"])
def test_lease_duration_policy_requires_real_integer(value) -> None:
    store = InMemoryPlanStore()
    with pytest.raises(ValueError, match="integer"):
        SquadCoordinator(store, default_lease_minutes=value)  # type: ignore[arg-type]


def test_malformed_queued_lease_generation_cannot_silently_reset() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    task = _task("task-a", 100, "gameplay")
    task.metadata["lease_generation"] = True
    store.add_items([task])

    with pytest.raises(ValueError, match="lease generation"):
        SquadCoordinator(store).claim_next("night", plan_generation="rev-1")


def test_durable_lease_round_trip_preserves_fingerprint() -> None:
    store = InMemoryPlanStore()
    _seed_workers(store, 4)
    store.add_items([_task("task-a", 100, "gameplay")])
    store.append_revision(_revision("rev-1"))
    start = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    lease = SquadCoordinator(store).claim_next(
        "night",
        plan_generation="rev-1",
        now=start,
    )
    assert lease is not None

    restored = InMemoryPlanStore()
    restored.restore_state(store.export_state(max_items=8, max_workers=8, max_revisions=8))
    envelope = restored.snapshot_items()[0].metadata["squad_lease"]
    assert envelope["fingerprint"] == lease.fingerprint
    parsed = SquadCoordinator(restored)._lease_from_item(restored.snapshot_items()[0])
    assert parsed.fingerprint == lease.fingerprint
