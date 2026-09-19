"""Worker identity and heartbeat adversarial tests."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_heartbeat import (
    HeartbeatError,
    HeartbeatPolicy,
    HeartbeatRegistry,
    WorkerLiveness,
)
from skeleton.shells.worker_identity import (
    WorkerIdentity,
    WorkerIdentityError,
    WorkerRegistry,
    WorkerRole,
)


def identity(worker_id="w1",generation=1,**kwargs):
    return WorkerIdentity(worker_id,generation,**kwargs)


@pytest.mark.parametrize("value",[""," space","a/b","*bad","x"*129])
def test_identity_rejects_bad_worker_id(value):
    with pytest.raises(WorkerIdentityError):
        identity(value)


@pytest.mark.parametrize("value",[0,-1,True,1.5])
def test_identity_rejects_bad_generation(value):
    with pytest.raises(WorkerIdentityError):
        identity(generation=value)


def test_identity_freezes_labels_and_features():
    labels={"zone":"a"}
    features={"python"}
    item=identity(labels=labels,features=features)
    labels["zone"]="b"
    features.add("git")
    assert item.labels["zone"]=="a"
    assert item.features==frozenset({"python"})


def test_identity_key_and_fingerprint_are_stable():
    first=identity(labels={"zone":"a"},features={"python","git"})
    second=identity(labels={"zone":"a"},features={"git","python"})
    assert first.key=="w1#1"
    assert first.fingerprint==second.fingerprint


def test_registry_register_and_find():
    registry=WorkerRegistry()
    item=identity()
    registration=registry.register(item)
    assert registry.find("w1")==registration
    assert registry.current(item)
    assert len(registry)==1


def test_registry_rejects_duplicate_without_replace():
    registry=WorkerRegistry()
    registry.register(identity())
    with pytest.raises(WorkerIdentityError):
        registry.register(identity())


def test_registry_replace_requires_higher_generation():
    registry=WorkerRegistry()
    registry.register(identity(generation=2))
    with pytest.raises(WorkerIdentityError):
        registry.replace(identity(generation=2))
    with pytest.raises(WorkerIdentityError):
        registry.replace(identity(generation=1))
    assert registry.replace(identity(generation=3)).identity.generation==3


def test_registry_old_generation_cannot_unregister_new():
    registry=WorkerRegistry()
    old=identity(generation=1)
    registry.register(old)
    new=identity(generation=2)
    current=registry.replace(new)
    assert registry.unregister(old) is False
    assert registry.unregister(new,registration_id="wrong") is False
    assert registry.unregister(new,registration_id=current.registration_id) is True


def test_registry_enable_is_generation_safe():
    registry=WorkerRegistry()
    old=identity()
    registry.register(old)
    new=identity(generation=2)
    registry.replace(new)
    with pytest.raises(WorkerIdentityError):
        registry.set_enabled(old,False)
    assert registry.set_enabled(new,False).enabled is False


def test_registry_matching_role_labels_features():
    registry=WorkerRegistry()
    registry.register(identity("a",role=WorkerRole.BUILDER,labels={"zone":"x"},features={"git"}))
    registry.register(identity("b",role=WorkerRole.TESTER,labels={"zone":"x"},features={"pytest"}))
    matches=registry.matching(role=WorkerRole.BUILDER,labels={"zone":"x"},features={"git"})
    assert [item.identity.worker_id for item in matches]==["a"]


def test_registry_matching_skips_disabled_by_default():
    registry=WorkerRegistry()
    item=identity("a")
    registry.register(item)
    registry.set_enabled(item,False)
    assert registry.matching()==()
    assert len(registry.matching(enabled_only=False))==1


def test_registry_capacity_bound():
    registry=WorkerRegistry(max_workers=1)
    registry.register(identity("a"))
    with pytest.raises(WorkerIdentityError):
        registry.register(identity("b"))


def test_registry_snapshot_counts_roles():
    registry=WorkerRegistry()
    registry.register(identity("a",role=WorkerRole.BUILDER))
    registry.register(identity("b",role=WorkerRole.BUILDER))
    registry.register(identity("c",role=WorkerRole.TESTER))
    snap=registry.snapshot()
    assert snap.enabled==3
    assert snap.by_role()["builder"]==2
    assert snap.by_role()["tester"]==1


@pytest.mark.parametrize(
    "late,stale",
    [(0,10),(10,10),(11,10),(-1,10)],
)
def test_heartbeat_policy_rejects_invalid_thresholds(late,stale):
    with pytest.raises(ValueError):
        HeartbeatPolicy(late_after_seconds=late,stale_after_seconds=stale)


def test_heartbeat_requires_registered_current_generation():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    beats=HeartbeatRegistry(workers=workers,clock=lambda:now[0])
    item=identity()
    with pytest.raises(WorkerIdentityError):
        beats.beat(item,sequence=1)
    workers.register(item)
    beats.beat(item,sequence=1)
    newer=identity(generation=2)
    workers.replace(newer)
    with pytest.raises(WorkerIdentityError):
        beats.beat(item,sequence=2)


def test_heartbeat_sequence_must_increase():
    item=identity()
    workers=WorkerRegistry()
    workers.register(item)
    beats=HeartbeatRegistry(workers=workers)
    beats.beat(item,sequence=2)
    with pytest.raises(HeartbeatError):
        beats.beat(item,sequence=2)
    with pytest.raises(HeartbeatError):
        beats.beat(item,sequence=1)


def test_heartbeat_sequence_gap_is_bounded():
    item=identity()
    workers=WorkerRegistry()
    workers.register(item)
    beats=HeartbeatRegistry(workers=workers,policy=HeartbeatPolicy(max_sequence_gap=2))
    beats.beat(item,sequence=1)
    with pytest.raises(HeartbeatError):
        beats.beat(item,sequence=10)


def test_heartbeat_new_generation_can_restart_sequence():
    workers=WorkerRegistry()
    first=identity(generation=1)
    workers.register(first)
    beats=HeartbeatRegistry(workers=workers)
    beats.beat(first,sequence=50)
    second=identity(generation=2)
    workers.replace(second)
    beat=beats.beat(second,sequence=1)
    assert beat.sequence==1


@pytest.mark.parametrize("metrics",[
    {"x":"not-number"},
    {"x":float("inf")},
    {"x":float("-inf")},
    {"x":float("nan")},
])
def test_heartbeat_rejects_bad_metrics(metrics):
    item=identity()
    workers=WorkerRegistry()
    workers.register(item)
    beats=HeartbeatRegistry(workers=workers)
    with pytest.raises(HeartbeatError):
        beats.beat(item,sequence=1,metrics=metrics)


def test_liveness_unknown_before_first_beat():
    item=identity()
    workers=WorkerRegistry()
    workers.register(item)
    beats=HeartbeatRegistry(workers=workers)
    assert beats.liveness(item).liveness is WorkerLiveness.UNKNOWN


def test_liveness_transitions_healthy_late_stale():
    now=[0.0]
    item=identity()
    workers=WorkerRegistry(clock=lambda:now[0])
    workers.register(item)
    beats=HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(late_after_seconds=5,stale_after_seconds=10),
        clock=lambda:now[0],
    )
    beats.beat(item,sequence=1,busy=True,inflight=2)
    assert beats.liveness(item).liveness is WorkerLiveness.HEALTHY
    now[0]=5
    assert beats.liveness(item).liveness is WorkerLiveness.LATE
    now[0]=10
    assert beats.liveness(item).liveness is WorkerLiveness.STALE


def test_heartbeat_forget_is_generation_safe():
    workers=WorkerRegistry()
    first=identity()
    workers.register(first)
    beats=HeartbeatRegistry(workers=workers)
    beats.beat(first,sequence=1)
    second=identity(generation=2)
    workers.replace(second)
    beats.beat(second,sequence=1)
    assert beats.forget(first) is False
    assert beats.latest("w1").identity==second
    assert beats.forget(second) is True


def test_prune_stale_removes_only_stale():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    a=identity("a")
    b=identity("b")
    workers.register(a);workers.register(b)
    beats=HeartbeatRegistry(workers=workers,policy=HeartbeatPolicy(late_after_seconds=2,stale_after_seconds=4),clock=lambda:now[0])
    beats.beat(a,sequence=1)
    now[0]=3
    beats.beat(b,sequence=1)
    now[0]=5
    stale=beats.prune_stale()
    assert [item.identity.worker_id for item in stale]==["a"]
    assert beats.latest("a") is None
    assert beats.latest("b") is not None


def test_heartbeat_snapshot_counts_states():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    ids=[identity("a"),identity("b"),identity("c")]
    for item in ids:workers.register(item)
    beats=HeartbeatRegistry(workers=workers,policy=HeartbeatPolicy(late_after_seconds=2,stale_after_seconds=4),clock=lambda:now[0])
    beats.beat(ids[0],sequence=1)
    beats.beat(ids[1],sequence=1)
    beats.beat(ids[2],sequence=1)
    now[0]=3
    beats.beat(ids[0],sequence=2)
    now[0]=5
    snap=beats.snapshot()
    assert snap.healthy==0
    assert snap.late==1
    assert snap.stale==2
