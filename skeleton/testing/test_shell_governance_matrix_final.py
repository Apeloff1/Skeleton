"""Final shell-plane stale-state and governance regression matrix."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.approvals import ApprovalError, ApprovalRegistry
from skeleton.shells.attestations import HMACAttestor
from skeleton.shells.cancellation import CancellationReason, CancellationRegistry
from skeleton.shells.change_control import ChangeControl, ChangeState
from skeleton.shells.feature_gates import FeatureGate, FeatureGateRegistry
from skeleton.shells.incident import IncidentRegistry, IncidentSeverity
from skeleton.shells.maintenance import ShellMaintenance, ShellMaintenanceWindow
from skeleton.shells.namespace import NamespaceRegistry, ShellNamespace
from skeleton.shells.output_policy import OutputClass, OutputClassifier, OutputRetentionPolicy
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.replay import EvidenceReplay, ReplayStatus
from skeleton.shells.retention import OutputRetentionStore


def receipt(correlation="c"):
    return ExecutionReceipt(
        command="python",
        correlation_id=correlation,
        fingerprint="fp",
        started_at="s",
        finished_at="f",
        duration_ms=1,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
    )


def test_approval_wrong_fingerprint_fails():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="alice",
    )
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="p",
            command="python",
            fingerprint="b",
        )


def test_approval_wrong_command_fails():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="alice",
    )
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="p",
            command="git",
            fingerprint="a",
        )


def test_approval_wrong_principal_fails():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="alice",
    )
    with pytest.raises(ApprovalError):
        registry.require(
            approval,
            principal="q",
            command="python",
            fingerprint="a",
        )


def test_approval_consumed_is_pruned_from_snapshot():
    registry = ApprovalRegistry()
    approval = registry.approve(
        principal="p",
        command="python",
        fingerprint="a",
        approved_by="alice",
    )
    registry.consume(
        approval,
        principal="p",
        command="python",
        fingerprint="a",
    )
    assert registry.snapshot() == ()


def test_namespace_prefixes_are_or_logic():
    namespace = ShellNamespace(
        "n",
        command_prefixes=frozenset({"build.", "test."}),
    )
    assert namespace.allows_command("build.compile")
    assert namespace.allows_command("test.unit")
    assert not namespace.allows_command("deploy.prod")


def test_namespace_empty_principals_means_all():
    namespace = ShellNamespace("n", principals=frozenset())
    assert namespace.allows_principal("a")
    assert namespace.allows_principal("b")


def test_namespace_disabled_registry_authorization_fails():
    registry = NamespaceRegistry()
    registry.set(ShellNamespace("n", enabled=False))
    with pytest.raises(PermissionError):
        registry.authorize("n", principal="p", command="python")


def test_namespace_snapshot_sorted():
    registry = NamespaceRegistry()
    registry.set(ShellNamespace("z"))
    registry.set(ShellNamespace("a"))
    registry.set(ShellNamespace("m"))
    assert [item.name for item in registry.snapshot()] == ["a", "m", "z"]


def test_maintenance_nonmatching_window_does_not_block():
    now = [5.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(
        ShellMaintenanceWindow(
            "w",
            0,
            10,
            command_prefix="git",
            principal="p",
        )
    )
    assert maintenance.admit(command="python", principal="p")
    assert maintenance.admit(command="git.status", principal="q")


def test_maintenance_matching_window_blocks():
    now = [5.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(
        ShellMaintenanceWindow(
            "w",
            0,
            10,
            command_prefix="git",
            principal="p",
        )
    )
    assert not maintenance.admit(command="git.status", principal="p")


def test_maintenance_expired_window_not_active():
    now = [11.0]
    maintenance = ShellMaintenance(clock=lambda: now[0])
    maintenance.add(ShellMaintenanceWindow("w", 0, 10))
    assert maintenance.active(command="python", principal="p") == ()


def test_feature_deny_has_priority_over_allow():
    gate = FeatureGate(
        "x",
        enabled=True,
        rollout_percent=100,
        allow_principals=frozenset({"p"}),
        deny_principals=frozenset({"q"}),
    )
    assert gate.evaluate("p")
    assert not gate.evaluate("q")


def test_feature_registry_remove_disables_lookup():
    registry = FeatureGateRegistry()
    registry.set(FeatureGate("x", enabled=True, rollout_percent=100))
    assert registry.enabled("x", "p")
    registry.remove("x")
    assert not registry.enabled("x", "p")


def test_change_control_reject_after_approval_allowed():
    control = ChangeControl(required_approvals=1)
    change = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    control.approve(change.change_id, "bob")
    rejected = control.reject(change.change_id)
    assert rejected.state is ChangeState.REJECTED


def test_incident_snapshot_order_follows_open_time():
    now = [0.0]
    registry = IncidentRegistry(clock=lambda: now[0])
    first = registry.open(IncidentSeverity.WARNING, "a")
    now[0] = 1
    second = registry.open(IncidentSeverity.WARNING, "b")
    assert registry.snapshot() == (first, second)


def test_output_classifier_secret_wins_when_both_patterns_match():
    classifier = OutputClassifier(
        secret_patterns=("credential",),
        sensitive_patterns=("credential",),
    )
    assert classifier.classify(b"credential") is OutputClass.SECRET


def test_secret_retention_store_keeps_digest_only():
    policy = OutputRetentionPolicy()
    classified = policy.apply(b"credential", OutputClass.SECRET)
    store = OutputRetentionStore()
    retained = store.put("x", classified, retention_seconds=1)
    assert retained.payload == b""
    assert retained.digest


def test_receipt_chain_two_items_verify():
    chain = ReceiptChain()
    chain.append(receipt("a"))
    chain.append(receipt("b"))
    assert chain.verify()


def test_receipt_chain_second_previous_hash_tamper_fails():
    chain = ReceiptChain()
    chain.append(receipt("a"))
    chain.append(receipt("b"))
    item = chain._items[1]
    chain._items[1] = replace(item, previous_hash="0" * 64)
    assert not chain.verify()


def test_attested_replay_two_receipts():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    a = receipt("a")
    b = receipt("b")
    attestations = {
        a.receipt_id: attestor.sign_receipt(a),
        b.receipt_id: attestor.sign_receipt(b),
    }
    report = EvidenceReplay().verify_attested((a, b), attestations, attestor)
    assert report.valid
    assert [item.status for item in report.items] == [
        ReplayStatus.VERIFIED,
        ReplayStatus.VERIFIED,
    ]


def test_attested_replay_one_tampered_signature():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    a = receipt("a")
    b = receipt("b")
    good = attestor.sign_receipt(a)
    bad = replace(attestor.sign_receipt(b), signature="0" * 64)
    report = EvidenceReplay().verify_attested(
        (a, b),
        {
            a.receipt_id: good,
            b.receipt_id: bad,
        },
        attestor,
    )
    assert not report.valid
    assert report.items[1].status is ReplayStatus.INVALID_ATTESTATION


def test_cancellation_registry_retains_reason_until_removed():
    registry = CancellationRegistry()
    registry.create("x")
    registry.cancel("x", CancellationReason.POLICY, detail="revoked")
    assert registry.require("x").snapshot().detail == "revoked"
    registry.remove("x")
    assert registry.get("x") is None


def test_cancellation_remove_missing_is_false():
    assert not CancellationRegistry().remove("missing")
