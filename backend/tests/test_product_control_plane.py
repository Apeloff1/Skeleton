import pytest

from core.charter_policy import Rule
from core.product_control_plane import ProductControlPlane
from core.product_operations import OperationRejected


def test_control_plane_persists_policy_and_admits_after_restart(tmp_path):
    plane = ProductControlPlane(tmp_path)
    plane.ratify("builds", [Rule("submit", "build.submit", min_weight=2)])
    admitted = plane.admit(
        capability_id="studio",
        domain="builds",
        action="build.submit",
        principal="creator",
        actor_weight=2,
        payload={"title": "persistent"},
        idempotency_key="req-1",
    )

    restored = ProductControlPlane(tmp_path)
    decision = restored.policy.decide("builds", "build.submit", 2)
    assert decision.permitted is True
    replay = restored.admit(
        capability_id="studio",
        domain="builds",
        action="build.submit",
        principal="creator",
        actor_weight=2,
        payload={"title": "ignored-on-idempotent-retry"},
        idempotency_key="req-1",
    )
    assert replay == admitted
    assert restored.operations.outbox.pending_count == 1


def test_unpersisted_domain_fails_closed(tmp_path):
    plane = ProductControlPlane(tmp_path)
    with pytest.raises(OperationRejected, match="no charter"):
        plane.admit(
            capability_id="studio",
            domain="builds",
            action="build.submit",
            principal="creator",
            actor_weight=100,
            payload={},
        )


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
    assert restored.policy.snapshot().edicts[0].in_force is True


def test_status_exposes_kernel_governance_and_operation_health(tmp_path):
    plane = ProductControlPlane(tmp_path, outbox_cap=2)
    plane.ratify("builds", [Rule("submit", "build.submit")])
    status = plane.status()
    assert "studio" in {cap["id"] for cap in status["kernel"]["capabilities"]}
    assert status["governance"]["charters"][0]["domain"] == "builds"
    assert status["operations"]["outbox_capacity_remaining"] == 2
