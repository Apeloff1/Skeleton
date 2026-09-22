from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

from skeleton.agents.swarm_load_shed import SharedLoadShedPolicy
from skeleton.intelligence.capacity_planner import CapacityPlanner
from skeleton.intelligence.shared_pressure import (
    SharedPressureConflict,
    SharedPressureExceeded,
    SharedPressurePolicy,
    SqliteSharedPressureLedger,
)


def _ledger(path: Path) -> SqliteSharedPressureLedger:
    ledger = SqliteSharedPressureLedger(path)
    ledger.configure(
        SharedPressurePolicy(
            scope="ai-work",
            max_concurrency=2,
            max_queue_depth=4,
            max_tenant_concurrency=1,
            max_tenant_queue_depth=2,
            soft_shed_fraction=0.75,
            protect_priority_at_or_below=10,
            default_lease_seconds=5.0,
        )
    )
    return ledger


def test_two_processes_cannot_overbook_shared_concurrency(tmp_path: Path) -> None:
    path = tmp_path / "pressure.sqlite3"
    _ledger(path)
    left = SqliteSharedPressureLedger(path)
    right = SqliteSharedPressureLedger(path)
    barrier = threading.Barrier(2)

    def acquire(ledger: SqliteSharedPressureLedger, tenant: str, op: str, owner: str):
        barrier.wait(timeout=5)
        try:
            lease = ledger.acquire(
                "ai-work",
                tenant,
                op,
                owner,
                priority=5,
                now=10.0,
            )
            return ("ok", lease.operation_id)
        except SharedPressureExceeded as exc:
            return ("denied", str(exc))

    # Each tenant may consume one slot, but never more than global capacity.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: acquire(*args),
                [
                    (left, "tenant-a", "op-a", "worker-a"),
                    (right, "tenant-b", "op-b", "worker-b"),
                ],
            )
        )

    assert [item[0] for item in results].count("ok") == 2
    snap = SqliteSharedPressureLedger(path).snapshot("ai-work", now=10.1)
    assert snap.active == 2

    with pytest.raises(SharedPressureExceeded, match="shared_concurrency_saturated"):
        left.acquire(
            "ai-work",
            "tenant-c",
            "op-c",
            "worker-c",
            priority=5,
            now=10.2,
        )


def test_noisy_neighbor_cannot_consume_all_concurrency(tmp_path: Path) -> None:
    path = tmp_path / "pressure.sqlite3"
    ledger = _ledger(path)
    ledger.acquire("ai-work", "tenant-a", "op-a", "worker-a", priority=5, now=10.0)

    with pytest.raises(SharedPressureExceeded, match="tenant_concurrency_saturated"):
        ledger.acquire(
            "ai-work",
            "tenant-a",
            "op-a2",
            "worker-a2",
            priority=5,
            now=10.1,
        )

    other = ledger.acquire(
        "ai-work",
        "tenant-b",
        "op-b",
        "worker-b",
        priority=5,
        now=10.2,
    )
    assert other.tenant_id == "tenant-b"


def test_queue_and_tenant_queue_caps_are_shared_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "pressure.sqlite3"
    _ledger(path)
    first = SqliteSharedPressureLedger(path)
    second = SqliteSharedPressureLedger(path)

    first.enqueue("ai-work", "tenant-a", "task-a1", priority=5, now=1.0)
    second.enqueue("ai-work", "tenant-a", "task-a2", priority=5, now=1.1)

    with pytest.raises(SharedPressureExceeded, match="tenant_queue_saturated"):
        first.enqueue("ai-work", "tenant-a", "task-a3", priority=5, now=1.2)

    second.enqueue("ai-work", "tenant-b", "task-b1", priority=5, now=1.3)
    second.enqueue("ai-work", "tenant-b", "task-b2", priority=5, now=1.4)

    with pytest.raises(SharedPressureExceeded, match="shared_queue_saturated"):
        first.enqueue("ai-work", "tenant-c", "task-c1", priority=5, now=1.5)


def test_expired_lease_is_reclaimed_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "pressure.sqlite3"
    ledger = _ledger(path)
    lease = ledger.acquire(
        "ai-work",
        "tenant-a",
        "op-a",
        "worker-a",
        priority=5,
        lease_seconds=1.0,
        now=10.0,
    )

    restarted = SqliteSharedPressureLedger(path)
    assert restarted.snapshot("ai-work", now=10.5).active == 1
    assert restarted.snapshot("ai-work", now=11.0).active == 0

    replacement = restarted.acquire(
        "ai-work",
        "tenant-a",
        "op-new",
        "worker-b",
        priority=5,
        now=11.1,
    )
    assert replacement.lease_id != lease.lease_id


def test_owner_fencing_blocks_foreign_release_and_renew(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "pressure.sqlite3")
    lease = ledger.acquire(
        "ai-work",
        "tenant-a",
        "op-a",
        "worker-a",
        priority=5,
        now=10.0,
    )

    with pytest.raises(SharedPressureConflict, match="owner mismatch"):
        ledger.renew(lease.lease_id, "worker-b", now=10.1)
    with pytest.raises(SharedPressureConflict, match="owner mismatch"):
        ledger.release(lease.lease_id, "worker-b")

    assert ledger.snapshot("ai-work", now=10.2).active == 1


def test_soft_shedding_protects_priority_but_drops_normal_work(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "pressure.sqlite3")
    ledger.enqueue("ai-work", "tenant-a", "task-a", priority=5, now=1.0)
    ledger.enqueue("ai-work", "tenant-b", "task-b", priority=5, now=1.1)
    ledger.enqueue("ai-work", "tenant-c", "task-c", priority=5, now=1.2)

    normal = ledger.decide(
        "ai-work",
        "tenant-d",
        priority=100,
        for_queue=False,
        now=1.3,
    )
    protected = ledger.decide(
        "ai-work",
        "tenant-d",
        priority=5,
        for_queue=False,
        now=1.3,
    )

    assert normal.admitted is False
    assert normal.reason == "soft_pressure_shed"
    assert protected.admitted is True


def test_queue_promotion_is_atomic(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "pressure.sqlite3")
    ticket = ledger.enqueue(
        "ai-work",
        "tenant-a",
        "task-a",
        priority=5,
        now=1.0,
    )

    lease = ledger.promote(ticket.ticket_id, "worker-a", now=2.0)

    snap = ledger.snapshot("ai-work", tenant_id="tenant-a", now=2.1)
    assert lease.operation_id == "task-a"
    assert snap.active == 1
    assert snap.queued == 0


def test_capacity_planner_ingests_shared_pressure(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "pressure.sqlite3")
    ledger.acquire("ai-work", "tenant-a", "op-a", "worker-a", priority=5, now=1.0)
    ledger.enqueue("ai-work", "tenant-b", "task-b", priority=5, now=1.1)

    snapshot = ledger.snapshot("ai-work", now=1.2)
    planner = CapacityPlanner()
    utilization = planner.record_shared_pressure(snapshot)

    assert utilization["shared.ai-work.concurrency"] == 0.5
    assert utilization["shared.ai-work.queue"] == 0.25


def test_swarm_load_shed_adapter_uses_durable_pressure(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "pressure.sqlite3")
    ledger.enqueue("ai-work", "tenant-a", "task-a", priority=5, now=1.0)
    ledger.enqueue("ai-work", "tenant-b", "task-b", priority=5, now=1.1)
    ledger.enqueue("ai-work", "tenant-c", "task-c", priority=5, now=1.2)

    policy = SharedLoadShedPolicy(ledger, "ai-work")
    normal = policy.evaluate("tenant-d", priority=100, now=1.3)
    protected = policy.evaluate("tenant-d", priority=5, now=1.3)

    assert normal.admit is False
    assert normal.reason == "soft_pressure_shed"
    assert protected.admit is True
