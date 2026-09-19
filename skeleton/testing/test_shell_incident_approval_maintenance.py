"""Incident, approval, and maintenance regressions."""

from __future__ import annotations

import pytest

from skeleton.shells.approvals import ApprovalError, ApprovalRegistry
from skeleton.shells.incident import (
    IncidentRegistry,
    IncidentSeverity,
    IncidentState,
)
from skeleton.shells.maintenance import ShellMaintenance, ShellMaintenanceWindow


def test_incident_open():
    registry = IncidentRegistry()
    item = registry.open(
        IncidentSeverity.ERROR,
        "execution failed",
        correlation_id="c1",
        command="python",
        evidence={"receipt_id": "r1"},
    )
    assert item.state is IncidentState.OPEN
    assert item.severity is IncidentSeverity.ERROR


def test_incident_acknowledge():
    registry = IncidentRegistry()
    item = registry.open(IncidentSeverity.WARNING, "x")
    item = registry.acknowledge(item.incident_id, "alice")
    assert item.state is IncidentState.ACKNOWLEDGED
    assert item.acknowledged_by == "alice"


def test_incident_acknowledge_twice_rejected():
    registry = IncidentRegistry()
    item = registry.open(IncidentSeverity.WARNING, "x")
    registry.acknowledge(item.incident_id, "alice")
    with pytest.raises(RuntimeError):
        registry.acknowledge(item.incident_id, "bob")


def test_incident_mitigate_from_open():
    registry = IncidentRegistry()
    item = registry.open(IncidentSeverity.WARNING, "x")
    item = registry.mitigate(item.incident_id)
    assert item.state is IncidentState.MITIGATED


def test_incident_close_requires_ack_or_mitigated():
    registry = IncidentRegistry()
    item = registry.open(IncidentSeverity.WARNING, "x")
    with pytest.raises(RuntimeError):
        registry.close(item.incident_id)


def test_incident_close_after_ack():
    registry = IncidentRegistry()
    item = registry.open(IncidentSeverity.WARNING, "x")
    registry.acknowledge(item.incident_id, "alice")
    closed = registry.close(item.incident_id)
    assert closed.state is IncidentState.CLOSED
    assert closed.closed_at is not None


def test_incident_open_incidents_excludes_closed():
    registry = IncidentRegistry()
    a = registry.open(IncidentSeverity.WARNING, "a")
    b = registry.open(IncidentSeverity.ERROR, "b")
    registry.acknowledge(a.incident_id, "alice")
    registry.close(a.incident_id)
    assert [item.incident_id for item in registry.open_incidents()] == [b.incident_id]


def test_incident_capacity():
    registry = IncidentRegistry(max_incidents=1)
    registry.open(IncidentSeverity.WARNING, "a")
    with pytest.raises(RuntimeError):
        registry.open(IncidentSeverity.WARNING, "b")


def test_approval_create_and_require():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="f",
        approved_by="alice",
    )
    assert registry.require(
        approval,
        principal="p",
        command="python",
        fingerprint="f",
    ) == approval


def test_approval_mismatch_rejected():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="f",
        approved_by="alice",
    )
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="q",
            command="python",
            fingerprint="f",
        )


def test_approval_consume_invalidates_live_lookup():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="f",
        approved_by="alice",
    )
    consumed = registry.consume(
        approval,
        principal="p",
        command="python",
        fingerprint="f",
    )
    assert consumed.consumed
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="p",
            command="python",
            fingerprint="f",
        )


def test_approval_expiry():
    now = [0.0]
    registry = ApprovalRegistry(clock=lambda: now[0])
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="f",
        approved_by="alice",
        ttl_seconds=5,
    )
    now[0] = 5
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="p",
            command="python",
            fingerprint="f",
        )


def test_approval_capacity():
    registry = ApprovalRegistry(max_approvals=1)
    registry.approve(
        principal="p",
        command="python",
        fingerprint="f1",
        approved_by="alice",
    )
    with pytest.raises(ApprovalError):
        registry.approve(
            principal="p",
            command="python",
            fingerprint="f2",
            approved_by="alice",
        )


def test_maintenance_window_active_boundary():
    window = ShellMaintenanceWindow("w", 5, 10)
    assert not window.active_at(4.999)
    assert window.active_at(5)
    assert window.active_at(9.999)
    assert not window.active_at(10)


def test_maintenance_window_matches_prefix():
    window = ShellMaintenanceWindow("w", 0, 10, command_prefix="build.")
    assert window.matches(command="build.compile", principal="p")
    assert not window.matches(command="test.pytest", principal="p")


def test_maintenance_window_matches_principal():
    window = ShellMaintenanceWindow("w", 0, 10, principal="p")
    assert window.matches(command="python", principal="p")
    assert not window.matches(command="python", principal="q")


def test_maintenance_schedule_and_admit():
    now = [0.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.schedule(
        "w",
        delay_seconds=5,
        duration_seconds=10,
        command_prefix="python",
        principal="p",
    )
    assert maintenance.admit(command="python", principal="p")
    now[0] = 5
    assert not maintenance.admit(command="python", principal="p")
    assert maintenance.admit(command="git", principal="p")
    assert maintenance.admit(command="python", principal="q")


def test_maintenance_non_deny_window_does_not_block():
    now = [0.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(ShellMaintenanceWindow("w", 0, 10, deny_new=False))
    assert maintenance.admit(command="python", principal="p")


def test_maintenance_prune():
    now = [0.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(ShellMaintenanceWindow("a", 0, 1))
    maintenance.add(ShellMaintenanceWindow("b", 0, 10))
    now[0] = 2
    assert maintenance.prune() == 1
    assert [item.window_id for item in maintenance.snapshot()] == ["b"]
