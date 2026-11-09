from __future__ import annotations

import sqlite3

import pytest

from skeleton.vault.data_governance import DataGovernanceDenied
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    GovernedDataRecord,
    LifecycleConflict,
    LifecycleError,
    LifecycleState,
)


def _record(
    record_id: str,
    *,
    tenant: str = "tenant-a",
    data_class: str = "internal",
    targets: tuple[str, ...] = ("memory", "artifact"),
    created_at: float = 10.0,
    retention_until: float | None = None,
    exportable: bool = True,
) -> GovernedDataRecord:
    return GovernedDataRecord(
        record_id=record_id,
        tenant_id=tenant,
        owner_plane="memory",
        source_ref=f"memory://{record_id}",
        data_class=data_class,
        purposes=("assistant-context",),
        deletion_targets=targets,
        created_at=created_at,
        retention_until=retention_until,
        exportable=exportable,
    )


def test_inventory_is_tenant_scoped_and_payload_free() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a"))
    registry.register(_record("b", tenant="tenant-b"))
    registry.register(_record("c", exportable=False))

    export = registry.export_inventory("tenant-a")

    assert export["tenant_id"] == "tenant-a"
    assert export["count"] == 1
    assert [row["record_id"] for row in export["records"]] == ["a"]
    rendered = str(export)
    assert "payload" not in rendered
    assert "secret content" not in rendered


def test_deletion_plan_fans_out_to_all_declared_targets() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", targets=("memory", "artifact", "retrieval")))

    plan = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)

    assert plan.plan_id.startswith("del-")
    assert [action.target for action in plan.actions] == [
        "artifact",
        "memory",
        "retrieval",
    ]
    assert registry.get("a")["state"] == "delete_pending"


def test_partial_deletion_acknowledgement_does_not_claim_completion() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", targets=("memory", "artifact")))
    plan = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)

    first = registry.acknowledge_deletion(
        plan.plan_id,
        "a",
        "memory",
        now=21.0,
    )

    assert first.state is LifecycleState.DELETE_PENDING
    assert registry.get("a")["state"] == "delete_pending"

    second = registry.acknowledge_deletion(
        plan.plan_id,
        "a",
        "artifact",
        now=22.0,
    )

    assert second.state is LifecycleState.DELETED
    assert registry.get("a")["state"] == "deleted"
    assert registry.inventory("tenant-a") == ()
    assert registry.inventory("tenant-a", include_deleted=True)[0]["state"] == "deleted"


def test_cross_tenant_deletion_is_denied() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", tenant="tenant-a"))

    with pytest.raises(
        DataGovernanceDenied,
        match="cross-tenant deletion request denied",
    ):
        registry.request_deletion(
            "tenant-b",
            record_ids=["a"],
            now=20.0,
        )

    assert registry.get("a")["state"] == "active"


def test_duplicate_acknowledgement_fails_closed() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", targets=("memory", "artifact")))
    plan = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)
    registry.acknowledge_deletion(plan.plan_id, "a", "memory", now=21.0)

    with pytest.raises(LifecycleConflict, match="already acknowledged"):
        registry.acknowledge_deletion(
            plan.plan_id,
            "a",
            "memory",
            now=22.0,
        )


def test_pending_deletion_request_is_idempotent() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a"))
    first = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)
    second = registry.request_deletion("tenant-a", record_ids=["a"], now=30.0)

    assert second.plan_id == first.plan_id
    assert second.actions == first.actions


def test_retention_expiry_creates_tenant_scoped_plans() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("expired-a", retention_until=15.0))
    registry.register(
        _record(
            "future-a",
            retention_until=25.0,
        )
    )
    registry.register(
        _record(
            "expired-b",
            tenant="tenant-b",
            retention_until=19.0,
        )
    )

    plans = registry.plan_retention_expiry(now=20.0)

    assert [plan.tenant_id for plan in plans] == ["tenant-a", "tenant-b"]
    assert {
        action.record_id
        for plan in plans
        for action in plan.actions
    } == {"expired-a", "expired-b"}
    assert registry.get("future-a")["state"] == "active"


def test_retention_deadline_cannot_precede_creation() -> None:
    with pytest.raises(LifecycleError, match="must not precede"):
        _record("a", created_at=20.0, retention_until=19.0)


def test_deletion_target_must_be_declared() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", targets=("memory",)))
    plan = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)

    with pytest.raises(LifecycleError, match="not declared"):
        registry.acknowledge_deletion(
            plan.plan_id,
            "a",
            "artifact",
            now=21.0,
        )


def test_receipts_are_tenant_scoped() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", targets=("memory",)))
    registry.register(_record("b", tenant="tenant-b", targets=("memory",)))

    plan_a = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)
    registry.acknowledge_deletion(plan_a.plan_id, "a", "memory", now=21.0)
    plan_b = registry.request_deletion("tenant-b", record_ids=["b"], now=20.0)
    registry.acknowledge_deletion(plan_b.plan_id, "b", "memory", now=21.0)

    receipts = registry.receipts(tenant_id="tenant-a")

    assert len(receipts) == 1
    assert receipts[0].record_id == "a"


def test_retry_of_pending_plan_returns_only_outstanding_targets() -> None:
    registry = DataLifecycleRegistry()
    registry.register(_record("a", targets=("memory", "artifact")))
    plan = registry.request_deletion("tenant-a", record_ids=["a"], now=20.0)
    registry.acknowledge_deletion(plan.plan_id, "a", "memory", now=21.0)

    retry = registry.request_deletion("tenant-a", record_ids=["a"], now=30.0)

    assert retry.plan_id == plan.plan_id
    assert [(action.record_id, action.target) for action in retry.actions] == [
        ("a", "artifact"),
    ]



def test_durable_registry_survives_restart_with_pending_plan(tmp_path) -> None:
    path = tmp_path / "governance-lifecycle.sqlite3"
    first = DataLifecycleRegistry(path)
    first.register(
        _record(
            "durable",
            targets=("memory", "retrieval"),
            retention_until=40.0,
        )
    )
    plan = first.request_deletion(
        "tenant-a",
        record_ids=("durable",),
        reason="tenant-request",
        now=20.0,
    )
    first.acknowledge_deletion(
        plan.plan_id,
        "durable",
        "memory",
        now=21.0,
    )
    first.close()

    restarted = DataLifecycleRegistry(path)
    row = restarted.get("durable")
    assert row["state"] == "delete_pending"
    assert row["retention_until"] == 40.0

    retry = restarted.request_deletion(
        "tenant-a",
        record_ids=("durable",),
        reason="tenant-request",
        now=30.0,
    )
    assert retry.plan_id == plan.plan_id
    assert [(action.record_id, action.target) for action in retry.actions] == [
        ("durable", "retrieval"),
    ]
    assert [receipt.target for receipt in restarted.receipts()] == ["memory"]

    final = restarted.acknowledge_deletion(
        retry.plan_id,
        "durable",
        "retrieval",
        now=31.0,
    )
    assert final.state is LifecycleState.DELETED
    restarted.close()

    again = DataLifecycleRegistry(path)
    assert again.get("durable")["state"] == "deleted"
    assert again.inventory("tenant-a") == ()
    assert len(again.receipts(tenant_id="tenant-a")) == 2
    again.close()


def test_pending_deletion_plan_is_tenant_fenced_and_receipt_aware() -> None:
    registry = DataLifecycleRegistry()
    registry.register(
        _record("linked", targets=("conversation", "artifact"))
    )
    plan = registry.request_deletion(
        "tenant-a",
        record_ids=("linked",),
        now=20.0,
    )
    registry.acknowledge_deletion(
        plan.plan_id,
        "linked",
        "artifact",
        now=21.0,
    )

    pending = registry.pending_deletion_plan(
        plan.plan_id,
        tenant_id="tenant-a",
    )

    assert pending.plan_id == plan.plan_id
    assert [
        (action.record_id, action.target)
        for action in pending.actions
    ] == [("linked", "conversation")]
    with pytest.raises(
        DataGovernanceDenied,
        match="cross-tenant deletion plan access denied",
    ):
        registry.pending_deletion_plan(
            plan.plan_id,
            tenant_id="tenant-b",
        )


def test_durable_registry_preserves_retention_plans_across_restart(tmp_path) -> None:
    path = tmp_path / "retention-lifecycle.sqlite3"
    first = DataLifecycleRegistry(path)
    first.register(
        _record(
            "expired",
            targets=("memory",),
            retention_until=15.0,
        )
    )
    plans = first.plan_retention_expiry(now=20.0)
    assert len(plans) == 1
    first.close()

    restarted = DataLifecycleRegistry(path)
    retry = restarted.request_deletion(
        "tenant-a",
        record_ids=("expired",),
        reason="retention-expired",
        now=99.0,
    )
    assert retry.plan_id == plans[0].plan_id
    assert retry.actions == plans[0].actions
    restarted.close()


def test_tenant_retention_plan_replays_only_outstanding_actions() -> None:
    registry = DataLifecycleRegistry()
    registry.register(
        _record(
            "retention-linked",
            targets=("memory", "conversation"),
            retention_until=15.0,
        )
    )

    first = registry.plan_retention_expiry_for_tenant(
        "tenant-a",
        now=20.0,
    )
    assert first is not None
    registry.acknowledge_deletion(
        first.plan_id,
        "retention-linked",
        "memory",
        now=21.0,
    )

    replay = registry.plan_retention_expiry_for_tenant(
        "tenant-a",
        now=30.0,
    )

    assert replay is not None
    assert replay.plan_id == first.plan_id
    assert [
        (action.record_id, action.target)
        for action in replay.actions
    ] == [("retention-linked", "conversation")]


def test_durable_registry_rejects_corrupt_snapshot(tmp_path) -> None:
    path = tmp_path / "corrupt-lifecycle.sqlite3"
    registry = DataLifecycleRegistry(path)
    registry.register(_record("safe", targets=("memory",)))
    registry.close()

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE data_lifecycle_snapshot SET payload_json = ? WHERE singleton = 1",
        ('{"schema_version":1,"entries":"not-a-list"}',),
    )
    connection.commit()
    connection.close()

    with pytest.raises((LifecycleError, TypeError)):
        DataLifecycleRegistry(path)
