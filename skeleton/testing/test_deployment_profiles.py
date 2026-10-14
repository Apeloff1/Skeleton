import pytest

from skeleton.ai.runtime.deferred.deployment_profiles import (
    AirGapProfile, Connectivity, DeferredOperation, DeferredSyncLedger,
    EdgeNode, EdgeProfile, EnterpriseProfile, EnterpriseTopology,
    OfflineProfile, SyncState, TransferBundle, admit_transfer,
)

D = "a" * 64


def test_offline_profile_cannot_claim_remote_capabilities():
    with pytest.raises(ValueError, match="remote capabilities"):
        OfflineProfile("offline", Connectivity.OFFLINE, ("local:model",), ("remote:web",), "data@1", "t")


def test_offline_profile_exposes_freshness_revision():
    profile = OfflineProfile("offline", Connectivity.OFFLINE, ("local:model",), (), "data@1", "2026-10-06T00:00Z")
    assert profile.data_revision == "data@1"
    assert profile.freshness_observed_at


def test_deferred_sync_is_idempotent():
    ledger = DeferredSyncLedger()
    op = DeferredOperation("op1", D, "idem1", "authority:receipt")
    first = ledger.reconcile(op, remote_revision="r2")
    second = ledger.reconcile(op, remote_revision="r3")
    assert first == second
    assert first.state is SyncState.APPLIED
    assert first.remote_revision == "r2"


def test_deferred_sync_rejects_idempotency_collision():
    ledger = DeferredSyncLedger()
    ledger.reconcile(DeferredOperation("op1", D, "same", "auth"), remote_revision="r1")
    with pytest.raises(ValueError, match="collision"):
        ledger.reconcile(DeferredOperation("op2", D, "same", "auth"), remote_revision="r2")


def test_conflict_is_explicit_not_silently_applied():
    receipt = DeferredSyncLedger().reconcile(DeferredOperation("op", D, "id", "auth"), remote_revision="r", conflict=True)
    assert receipt.state is SyncState.CONFLICT
    assert receipt.remote_revision is None


def test_air_gap_disables_egress_and_connectors_by_construction():
    with pytest.raises(ValueError, match="disable"):
        AirGapProfile("secure", False, True, ("release",))
    with pytest.raises(ValueError, match="disable"):
        AirGapProfile("secure", True, False, ("release",))


def test_air_gap_import_requires_trusted_signer():
    profile = AirGapProfile("secure", False, False, ("release",))
    good = TransferBundle("b1", D, D, "release", D)
    bad = TransferBundle("b2", D, D, "unknown", D)
    assert admit_transfer(profile, good)
    assert not admit_transfer(profile, bad)


def test_air_gap_requires_at_least_one_trusted_signer():
    with pytest.raises(ValueError, match="trusted"):
        AirGapProfile("secure", False, False, ())


def test_edge_profile_rejects_model_larger_than_measured_memory():
    with pytest.raises(ValueError, match="cannot exceed"):
        EdgeProfile("tiny", 2, 1024, 4096, 2048, "strict", Connectivity.INTERMITTENT)


def test_edge_node_binds_runtime_and_persisted_state():
    profile = EdgeProfile("edge", 4, 8192, 16384, 4096, "strict", Connectivity.INTERMITTENT)
    node = EdgeNode("node1", profile, "runtime@abc", D)
    assert node.persisted_state_digest == D
    assert node.profile.security_profile == "strict"


def test_enterprise_admin_and_model_authority_must_be_separate():
    with pytest.raises(ValueError, match="separate"):
        EnterpriseProfile("org", EnterpriseTopology.HA, ("alice",), ("alice",), "policy@1")


def test_enterprise_identity_is_deterministic_and_policy_bound():
    profile = EnterpriseProfile("org", EnterpriseTopology.HA, ("admin",), ("model-approver",), "policy@1")
    same = EnterpriseProfile("org", EnterpriseTopology.HA, ("admin",), ("model-approver",), "policy@1")
    changed = EnterpriseProfile("org", EnterpriseTopology.HA, ("admin",), ("model-approver",), "policy@2")
    assert profile.identity == same.identity
    assert profile.identity != changed.identity
