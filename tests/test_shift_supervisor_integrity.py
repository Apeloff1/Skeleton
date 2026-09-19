from datetime import datetime, timedelta, timezone

import pytest

from core.shift_supervisor.integrity import (
    SupervisorIntegrityError,
    audit_store,
    require_no_critical_integrity,
)
from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.squads import SquadCoordinator


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _worker(worker_id: str, *, status: str = "idle") -> WorkerState:
    return WorkerState(
        worker_id=worker_id,
        team="night",
        status=status,  # type: ignore[arg-type]
        last_heartbeat_at=NOW,
    )


def _task(task_id: str, *, status: str = "queued", owner: str | None = None) -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description="work",
        priority=50,
        target_team="night",
        status=status,  # type: ignore[arg-type]
        owner=owner,
    )


def test_clean_idle_store_is_healthy():
    store = InMemoryPlanStore()
    store.upsert_worker(_worker("night-1"))
    store.add_items([_task("task")])
    report = audit_store(store, now=NOW)
    assert report.healthy is True
    assert report.findings == ()
    assert len(report.digest) == 64


def test_queued_owner_is_critical_and_fails_guard():
    store = InMemoryPlanStore()
    item = _task("task")
    store.add_items([item])
    item = store.snapshot_items()[0]
    item.owner = "night-1"
    store.update_item(item)

    report = audit_store(store, now=NOW)
    assert any(f.code == "queued-item-owned" for f in report.findings)
    with pytest.raises(SupervisorIntegrityError):
        require_no_critical_integrity(report)


def test_worker_cannot_point_at_missing_task():
    store = InMemoryPlanStore()
    worker = _worker("night-1", status="working")
    worker.current_task_id = "missing"
    store.upsert_worker(worker)

    report = audit_store(store, now=NOW)
    assert any(f.code == "worker-task-missing" for f in report.findings)
    assert report.critical_count >= 1


def test_dependency_cycle_is_critical():
    store = InMemoryPlanStore()
    store.add_items([
        PlanItem(id="a", title="a", description="a", priority=1, target_team="night", dependencies=["b"]),
        PlanItem(id="b", title="b", description="b", priority=1, target_team="night", dependencies=["a"]),
    ])
    report = audit_store(store, now=NOW)
    assert any(f.code == "dependency-cycle" for f in report.findings)


def test_stale_active_worker_is_error_not_silent_capacity():
    store = InMemoryPlanStore()
    worker = _worker("night-1")
    worker.last_heartbeat_at = NOW - timedelta(hours=2)
    store.upsert_worker(worker)

    report = audit_store(store, now=NOW, heartbeat_stale_after=timedelta(minutes=20))
    finding = next(f for f in report.findings if f.code == "active-worker-heartbeat-stale")
    assert finding.severity.value == "error"


def test_valid_squad_is_integrity_clean():
    store = InMemoryPlanStore()
    for index, role in enumerate(("researcher", "lead", "reviewer", "verifier")):
        worker = _worker(f"night-{index}")
        worker.metadata["preferred_squad_roles"] = [role]
        store.upsert_worker(worker)
    store.add_items([
        PlanItem(
            id="task",
            title="task",
            description="work",
            priority=100,
            target_team="night",
            metadata={
                "squad_size": 4,
                "conflict_domain": "core/shift_supervisor",
                "relevant_paths": ["core/shift_supervisor/runtime.py"],
            },
        )
    ])
    lease = SquadCoordinator(store, default_lease_minutes=30).claim_next(
        "night",
        plan_generation="rev-1",
        now=NOW,
    )
    assert lease is not None
    report = audit_store(store, now=NOW + timedelta(minutes=1))
    assert report.critical_count == 0
    assert report.error_count == 0


def test_squad_worker_role_tamper_is_detected():
    store = InMemoryPlanStore()
    for index in range(4):
        store.upsert_worker(_worker(f"night-{index}"))
    store.add_items([
        PlanItem(
            id="task",
            title="task",
            description="work",
            priority=100,
            target_team="night",
            metadata={"squad_size": 4, "conflict_domain": "core"},
        )
    ])
    lease = SquadCoordinator(store).claim_next("night", plan_generation="rev-1", now=NOW)
    assert lease is not None
    worker_id = lease.members["researcher"]
    worker = next(w for w in store.snapshot_workers() if w.worker_id == worker_id)
    worker.metadata["current_squad_role"] = "verifier"
    store.upsert_worker(worker)

    report = audit_store(store, now=NOW)
    assert any(f.code == "squad-worker-role-mismatch" for f in report.findings)
