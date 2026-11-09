"""Additional governance edge cases for feature, approval, change, and rollout state."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.approvals import ApprovalError, ApprovalRegistry
from skeleton.shells.change_control import ChangeControl, ChangeState
from skeleton.shells.feature_gates import FeatureGate, FeatureGateRegistry
from skeleton.shells.incident import IncidentRegistry, IncidentSeverity, IncidentState
from skeleton.shells.maintenance import ShellMaintenance, ShellMaintenanceWindow
from skeleton.shells.namespace import NamespaceRegistry, ShellNamespace
from skeleton.shells.policy_rollout import PolicyRolloutManager, RolloutPhase
from skeleton.shells.policy_store import PolicyStore
from skeleton.shells.runner import ShellPolicy


def policy(tmp_path, timeout=10):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    return ShellPolicy(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        default_timeout=5,
        max_timeout=timeout,
        max_output_bytes=1024,
        max_input_bytes=1024,
        max_env_bytes=1024,
        max_args=16,
        max_arg_bytes=1024,
    )


def test_feature_gate_metadata_is_copied():
    metadata = {"owner": "a"}
    gate = FeatureGate("x", metadata=metadata)
    metadata["owner"] = "b"
    assert gate.metadata["owner"] == "a"


def test_feature_gate_invalid_metadata_size():
    with pytest.raises(ValueError):
        FeatureGate("x", metadata={str(i): "v" for i in range(65)})


def test_feature_registry_unknown_get_raises():
    with pytest.raises(KeyError):
        FeatureGateRegistry().get("missing")


@pytest.mark.parametrize("principal", ["", "x" * 257])
def test_feature_gate_rejects_bad_principal(principal):
    with pytest.raises(ValueError):
        FeatureGate("x").evaluate(principal)


def test_namespace_metadata_is_copied():
    metadata = {"owner": "a"}
    namespace = ShellNamespace("n", metadata=metadata)
    metadata["owner"] = "b"
    assert namespace.metadata["owner"] == "a"


def test_namespace_registry_replace_same_name():
    registry = NamespaceRegistry(max_namespaces=1)
    registry.set(ShellNamespace("n", enabled=False))
    registry.set(ShellNamespace("n", enabled=True))
    assert registry.get("n").enabled


def test_namespace_registry_remove():
    registry = NamespaceRegistry()
    registry.set(ShellNamespace("n"))
    assert registry.remove("n")
    assert not registry.remove("n")


def test_approval_snapshot_prunes_expired():
    now = [0.0]
    registry = ApprovalRegistry(clock=lambda: now[0])
    registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="x",
        ttl_seconds=1,
    )
    registry.approve(
        principal="p",
        command="python",
        fingerprint="b",
        approved_by="x",
        ttl_seconds=10,
    )
    now[0] = 2
    items = registry.snapshot()
    assert len(items) == 1
    assert items[0].fingerprint == "b"


def test_approval_old_object_invalid_after_consume():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="x",
    )
    registry.consume(
        approval,
        principal="p",
        command="python",
        fingerprint="a",
    )
    with pytest.raises(ApprovalError):
        registry.consume(
            approval,
            principal="p",
            command="python",
            fingerprint="a",
        )


def test_change_control_rejected_cannot_apply():
    control = ChangeControl()
    change = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="a",
    )
    control.reject(change.change_id)
    with pytest.raises(RuntimeError):
        control.applied(change.change_id)


def test_change_control_applied_cannot_reject():
    control = ChangeControl()
    change = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="a",
    )
    control.approve(change.change_id, "b")
    control.applied(change.change_id)
    with pytest.raises(RuntimeError):
        control.reject(change.change_id)


def test_change_control_snapshot_sorted_by_id():
    control = ChangeControl()
    a = control.propose(
        kind="policy",
        target="a",
        summary="a",
        payload={"a": 1},
        proposed_by="a",
    )
    b = control.propose(
        kind="policy",
        target="b",
        summary="b",
        payload={"b": 1},
        proposed_by="a",
    )
    ids = [item.change_id for item in control.snapshot()]
    assert ids == sorted((a.change_id, b.change_id))


def test_incident_evidence_is_copied():
    evidence = {"x": 1}
    registry = IncidentRegistry()
    incident = registry.open(IncidentSeverity.ERROR, "x", evidence=evidence)
    evidence["x"] = 2
    assert incident.evidence["x"] == 1


def test_incident_mitigated_can_close():
    registry = IncidentRegistry()
    incident = registry.open(IncidentSeverity.ERROR, "x")
    registry.mitigate(incident.incident_id)
    assert registry.close(incident.incident_id).state is IncidentState.CLOSED


def test_incident_closed_cannot_mitigate():
    registry = IncidentRegistry()
    incident = registry.open(IncidentSeverity.ERROR, "x")
    registry.acknowledge(incident.incident_id, "a")
    registry.close(incident.incident_id)
    with pytest.raises(RuntimeError):
        registry.mitigate(incident.incident_id)


def test_maintenance_overlapping_windows_any_deny_blocks():
    now = [0.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(ShellMaintenanceWindow("observe", 0, 10, deny_new=False))
    maintenance.add(ShellMaintenanceWindow("deny", 0, 10, deny_new=True))
    assert not maintenance.admit(command="python", principal="p")


def test_maintenance_active_sorted_by_start():
    now = [5.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(ShellMaintenanceWindow("b", 2, 10))
    maintenance.add(ShellMaintenanceWindow("a", 1, 10))
    assert [item.window_id for item in maintenance.active(command="python", principal="p")] == ["a", "b"]


@pytest.mark.parametrize("percent", [-1, 101])
def test_rollout_rejects_invalid_canary(tmp_path, percent):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    with pytest.raises(ValueError):
        manager.prepare("r", policy(tmp_path, timeout=9), canary_percent=percent)


def test_rollout_canary_zero_selects_nobody(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r", policy(tmp_path, timeout=9), canary_percent=0)
    manager.advance("r")
    assert not manager.selected("r", "p")


def test_rollout_canary_hundred_selects_everyone(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r", policy(tmp_path, timeout=9), canary_percent=100)
    manager.advance("r")
    assert manager.selected("r", "p")
    assert manager.selected("r", "q")


def test_rollout_rollback_cannot_advance(tmp_path):
    store = PolicyStore(policy(tmp_path))
    manager = PolicyRolloutManager(store)
    manager.prepare("r", policy(tmp_path, timeout=9))
    manager.rollback("r")
    with pytest.raises(RuntimeError):
        manager.advance("r")
