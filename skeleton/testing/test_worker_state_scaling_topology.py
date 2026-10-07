"""Worker state store, compatibility, scaling, topology, and service tests."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_compatibility import CompatibilityRequirement,WorkerCompatibility
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistration,WorkerRole
from skeleton.shells.worker_scaling import ScalingAction,ScalingPolicy,WorkerScaler
from skeleton.shells.worker_service import WorkerService
from skeleton.shells.worker_state_store import StateConflict,WorkerStateStore
from skeleton.shells.worker_topology import SpreadConstraint,WorkerTopology


def test_state_store_create_and_update():
    store=WorkerStateStore()
    first=store.put("w",1,{"x":1})
    second=store.put("w",1,{"x":2},expected_revision=1)
    assert first.revision==1
    assert second.revision==2
    assert second.values["x"]==2
    assert second.valid


def test_state_store_revision_conflict():
    store=WorkerStateStore()
    store.put("w",1,{"x":1})
    with pytest.raises(StateConflict):
        store.put("w",1,{"x":2},expected_revision=0)


def test_state_store_generation_rollback_rejected():
    store=WorkerStateStore()
    store.put("w",2,{"x":1})
    with pytest.raises(StateConflict):
        store.put("w",1,{"x":2})


def test_state_store_new_generation_resets_revision():
    store=WorkerStateStore()
    store.put("w",1,{"x":1})
    item=store.put("w",2,{"x":2})
    assert item.revision==1
    assert item.generation==2


def test_state_store_cas():
    store=WorkerStateStore()
    first=store.put("w",1,{"x":1})
    second=store.compare_and_swap("w",1,first.revision,{"x":2})
    assert second.revision==2


def test_state_store_delete_guards_generation_revision():
    store=WorkerStateStore()
    record=store.put("w",1,{"x":1})
    assert not store.delete("w",generation=2)
    assert not store.delete("w",revision=2)
    assert store.delete("w",generation=1,revision=record.revision)


def test_state_store_payload_must_be_json():
    store=WorkerStateStore()
    with pytest.raises(ValueError):
        store.put("w",1,{"x":object()})


def test_compatibility_happy_path():
    identity=WorkerIdentity("w",1,features=frozenset({"python","git"}))
    requirement=CompatibilityRequirement(required_features=frozenset({"python"}))
    result=WorkerCompatibility().check(
        identity,requirement,controller_features={"python","docker"},controller_protocol_version=1
    )
    assert result.compatible
    assert result.negotiated_protocol==1
    assert result.common_features==frozenset({"python"})


def test_compatibility_missing_required_feature():
    identity=WorkerIdentity("w",1,features=frozenset({"python"}))
    result=WorkerCompatibility().check(
        identity,CompatibilityRequirement(required_features=frozenset({"git"}))
    )
    assert not result.compatible
    assert any("missing" in reason for reason in result.reasons)


def test_compatibility_forbidden_feature():
    identity=WorkerIdentity("w",1,features=frozenset({"unsafe"}))
    result=WorkerCompatibility().check(
        identity,CompatibilityRequirement(forbidden_features=frozenset({"unsafe"}))
    )
    assert not result.compatible


def test_compatibility_protocol_mismatch():
    identity=WorkerIdentity("w",1,protocol_version=2)
    requirement=CompatibilityRequirement(min_protocol_version=1,max_protocol_version=3)
    result=WorkerCompatibility().check(identity,requirement,controller_protocol_version=1)
    assert not result.compatible


def test_scaler_scale_out():
    scaler=WorkerScaler(ScalingPolicy(target_queue_per_worker=10,scale_out_queue_per_worker=20,max_step=5,max_workers=100))
    decision=scaler.recommend(healthy_workers=2,queued=100)
    assert decision.action is ScalingAction.SCALE_OUT
    assert decision.desired_workers>2
    assert decision.delta>0


def test_scaler_scale_in():
    scaler=WorkerScaler(ScalingPolicy(min_workers=1,max_step=2,scale_in_queue_per_worker=2,target_queue_per_worker=10,scale_out_queue_per_worker=20))
    decision=scaler.recommend(healthy_workers=5,queued=0)
    assert decision.action is ScalingAction.SCALE_IN
    assert decision.desired_workers==3


def test_scaler_holds_at_min_workers():
    scaler=WorkerScaler(ScalingPolicy(min_workers=2))
    decision=scaler.recommend(healthy_workers=2,queued=0)
    assert decision.action is ScalingAction.HOLD


def test_scaler_respects_max_workers():
    scaler=WorkerScaler(ScalingPolicy(max_workers=3,max_step=10,target_queue_per_worker=1,scale_out_queue_per_worker=2))
    decision=scaler.recommend(healthy_workers=2,queued=100)
    assert decision.desired_workers<=3


def registration(worker,zone):
    identity=WorkerIdentity(worker,1,labels={"zone":zone})
    return WorkerRegistration(identity,worker,0.0,0.0)


def test_topology_allows_balanced_domain():
    candidates=[registration("a","x"),registration("b","y")]
    decision=WorkerTopology().filter(
        candidates,active_assignments={"x":1,"y":0},
        constraint=SpreadConstraint("zone",max_skew=1,min_domains=2),
    )
    assert [item.identity.worker_id for item in decision.allowed]==["b"]


def test_topology_rejects_missing_label():
    identity=WorkerIdentity("w",1)
    reg=WorkerRegistration(identity,"w",0.0,0.0)
    decision=WorkerTopology().filter(
        [reg],active_assignments={"x":0},
        constraint=SpreadConstraint("zone",min_domains=1),
    )
    assert decision.allowed==()
    assert "w" in decision.rejected


def test_topology_requires_min_domains():
    candidates=[registration("a","x")]
    decision=WorkerTopology().filter(
        candidates,active_assignments={"x":0},
        constraint=SpreadConstraint("zone",min_domains=2),
    )
    assert not decision.allowed


def test_worker_service_register_heartbeat_status():
    service=WorkerService()
    worker=WorkerIdentity("w",1,role=WorkerRole.BUILDER)
    service.register(worker)
    service.heartbeat(worker,sequence=1)
    status=service.status()
    assert status.runtime["workers"]==1
    assert status.runtime["healthy"]==1
    assert status.health["ok"] is True
    assert status.snapshot_digest


def test_worker_service_snapshot_digest_changes():
    service=WorkerService()
    first=service.snapshot().digest
    worker=WorkerIdentity("w",1)
    service.register(worker)
    second=service.snapshot().digest
    assert first!=second
