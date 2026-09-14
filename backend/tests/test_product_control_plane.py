import pytest

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY, POLICY_VERSION
from core.charter_policy import Rule
from core.product_control_plane import ProductControlPlane
from core.product_operations import OperationRejected


def test_control_plane_persists_policy_and_admits_after_restart(tmp_path):
    plane = ProductControlPlane(tmp_path)
    plane.ratify("builds", [Rule("submit", "build.submit", min_weight=2)])
    admitted = plane.admit(capability_id="studio", domain="builds", action="build.submit",
                           principal="creator", actor_weight=2, payload={"title": "persistent"},
                           idempotency_key="req-1")
    restored = ProductControlPlane(tmp_path)
    decision = restored.policy.decide("builds", "build.submit", 2)
    assert decision.permitted is True
    replay = restored.admit(capability_id="studio", domain="builds", action="build.submit",
                            principal="creator", actor_weight=2,
                            payload={"title": "ignored-on-idempotent-retry"}, idempotency_key="req-1")
    assert replay == admitted
    assert restored.operations.outbox.pending_count == 1


def test_canonical_policy_bootstraps_only_explicit_product_actions(tmp_path):
    plane = ProductControlPlane(tmp_path)
    domains = {charter.domain for charter in plane.policy.snapshot().charters}
    assert domains == {item.domain for item in CANONICAL_PRODUCT_POLICY}
    for item in CANONICAL_PRODUCT_POLICY:
        for action in item.actions:
            assert plane.policy.decide(item.domain, action, 0).permitted is True
        assert plane.policy.decide(item.domain, "wildcard.execute", 999).permitted is False


def test_bootstrap_can_be_disabled_for_strict_empty_installation(tmp_path):
    plane = ProductControlPlane(tmp_path, bootstrap_policy=False)
    assert plane.policy.snapshot().charters == []
    with pytest.raises(OperationRejected, match="no charter"):
        plane.admit(capability_id="studio", domain="studio", action="build.submit",
                    principal="creator", actor_weight=100, payload={})


def test_unpersisted_noncanonical_domain_fails_closed(tmp_path):
    plane = ProductControlPlane(tmp_path)
    with pytest.raises(OperationRejected, match="no charter"):
        plane.admit(capability_id="studio", domain="builds", action="build.submit",
                    principal="creator", actor_weight=100, payload={})


def test_edict_mutations_persist_immediately(tmp_path):
    plane = ProductControlPlane(tmp_path)
    plane.ratify("runtime", [Rule("deploy-old", "runtime.deploy", min_weight=9)])
    edict = plane.propose_edict("runtime", Rule("deploy-new", "runtime.deploy", min_weight=3), "court")
    assert edict is not None
    assert plane.enforce_edict(edict.id) is True
    restored = ProductControlPlane(tmp_path)
    decision = restored.policy.decide("runtime", "runtime.deploy", 3)
    assert decision.permitted is True
    assert decision.cited_rule == "deploy-new"
    assert any(item.in_force and item.id == edict.id for item in restored.policy.snapshot().edicts)


def test_canonical_admission_is_visible_in_pending_projection(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(capability_id="world-forge", domain="world-forge", action="world.create",
                           principal="product-user", actor_weight=0,
                           payload={"prompt": "archipelago"}, idempotency_key="world-1")
    pending = plane.pending()
    assert pending == [{
        "operation_id": admitted.id,
        "capability_id": "world-forge",
        "pillar": "create",
        "domain": "world-forge",
        "action": "world.create",
        "principal": "product-user",
        "outbox_seq": admitted.outbox_seq,
        "admitted_at": admitted.admitted_at,
        "idempotency_key": "world-1",
        "executor_bound": True,
    }]


def test_status_exposes_kernel_governance_executor_and_operation_health(tmp_path):
    plane = ProductControlPlane(tmp_path, outbox_cap=2)
    plane.ratify("builds", [Rule("submit", "build.submit")])
    status = plane.status()
    assert status["policy_version"] == POLICY_VERSION
    assert status["policy_bootstrap_enabled"] is True
    assert "studio" in {cap["id"] for cap in status["kernel"]["capabilities"]}
    domains = {charter["domain"] for charter in status["governance"]["charters"]}
    assert "studio" in domains
    assert "builds" in domains
    assert status["operations"]["outbox_capacity_remaining"] == 2
    assert status["executors"]["coverage"]["bound_actions"] == 8
    assert status["receipts"]["version"] == 2
