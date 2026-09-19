"""Worker aggregate policy, snapshot, and diagnostics tests."""

from __future__ import annotations

import json
import pytest

from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker_diagnostics import DiagnosticSeverity,WorkerDiagnostics
from skeleton.shells.worker_heartbeat import HeartbeatPolicy,HeartbeatRegistry
from skeleton.shells.worker_health import WorkerHealthInspector
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry
from skeleton.shells.worker_metrics import WorkerMetrics
from skeleton.shells.worker_policy import WorkerPlanePolicy
from skeleton.shells.worker_quota import WorkerQuota
from skeleton.shells.worker_snapshot import FleetSnapshotter
from skeleton.shells.worker_supervisor import SupervisorPolicy,WorkerSupervisor


def test_worker_plane_policy_serializes_all_sections():
    payload=WorkerPlanePolicy().to_dict()
    assert "heartbeat" in payload
    assert "backpressure" in payload
    assert "quota" in payload
    assert "recovery" in payload
    assert "supervisor" in payload


def test_worker_plane_policy_can_narrow_capacity():
    parent=WorkerPlanePolicy(max_workers=100,max_queue_items=100)
    child=parent.narrow(max_workers=10,max_queue_items=50)
    assert child.no_wider_than(parent)


def test_worker_plane_policy_rejects_capacity_widening():
    parent=WorkerPlanePolicy(max_workers=10)
    with pytest.raises(ValueError):
        parent.narrow(max_workers=11)


def test_worker_plane_policy_quota_narrowing():
    parent=WorkerPlanePolicy(quota=WorkerQuota(max_inflight=10,max_starts_per_window=100,window_seconds=10))
    child=parent.narrow(quota=WorkerQuota(max_inflight=5,max_starts_per_window=50,window_seconds=20))
    assert child.no_wider_than(parent)


def test_worker_plane_policy_rejects_quota_window_widening():
    parent=WorkerPlanePolicy(quota=WorkerQuota(window_seconds=20))
    with pytest.raises(ValueError):
        parent.narrow(quota=WorkerQuota(window_seconds=10))


def setup_snapshot(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    beats=HeartbeatRegistry(workers=workers,clock=lambda:now[0])
    queue=ShellWorkQueue(clock=lambda:now[0])
    metrics=WorkerMetrics()
    supervisor=WorkerSupervisor(workers,clock=lambda:now[0])
    health=WorkerHealthInspector(workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor)
    snap=FleetSnapshotter(
        workers=workers,heartbeats=beats,queue=queue,metrics=metrics,
        health=health,supervisor=supervisor,clock=lambda:now[0],
    )
    return workers,beats,queue,metrics,supervisor,snap


def test_snapshot_is_canonical_and_digest_stable():
    now=[1.0]
    workers,beats,queue,metrics,supervisor,snapshotter=setup_snapshot(now)
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    supervisor.attach(worker)
    beats.beat(worker,sequence=1)
    first=snapshotter.capture()
    second=snapshotter.capture()
    assert first.dumps()==second.dumps()
    assert first.digest==second.digest


def test_snapshot_digest_changes_with_state():
    now=[1.0]
    workers,beats,queue,metrics,supervisor,snapshotter=setup_snapshot(now)
    first=snapshotter.capture()
    queue.enqueue(ShellCommand("python"),item_id="x")
    second=snapshotter.capture()
    assert first.digest!=second.digest


def test_snapshot_loads_validates_schema():
    now=[1.0]
    *_,snapshotter=setup_snapshot(now)
    snapshot=snapshotter.capture()
    payload=FleetSnapshotter.loads(snapshot.dumps())
    assert payload["schema_version"]==1
    bad=json.loads(snapshot.dumps());bad["schema_version"]=2
    with pytest.raises(ValueError):
        FleetSnapshotter.loads(json.dumps(bad))


def test_diagnostics_healthy_worker_clean():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    beats=HeartbeatRegistry(workers=workers,clock=lambda:now[0])
    beats.beat(worker,sequence=1)
    queue=ShellWorkQueue(clock=lambda:now[0])
    supervisor=WorkerSupervisor(workers,clock=lambda:now[0])
    supervisor.attach(worker)
    report=WorkerDiagnostics(workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor).inspect()
    assert report.ok


def test_diagnostics_enabled_stale_worker_error():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    beats=HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(late_after_seconds=1,stale_after_seconds=2),
        clock=lambda:now[0],
    )
    beats.beat(worker,sequence=1)
    queue=ShellWorkQueue(clock=lambda:now[0])
    now[0]=3
    report=WorkerDiagnostics(workers=workers,heartbeats=beats,queue=queue).inspect()
    assert not report.ok
    assert any(item.code=="enabled_stale_worker" for item in report.findings)


def test_diagnostics_unregistered_claim_owner_warns():
    queue=ShellWorkQueue()
    queue.enqueue(ShellCommand("python"),item_id="x")
    queue.claim("ghost")
    workers=WorkerRegistry()
    beats=HeartbeatRegistry(workers=workers)
    report=WorkerDiagnostics(workers=workers,heartbeats=beats,queue=queue).inspect()
    assert any(item.code=="claim_owner_unregistered" for item in report.findings)
    assert report.warnings>=1


def test_diagnostics_disabled_claim_owner_warns():
    workers=WorkerRegistry()
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    workers.set_enabled(worker,False)
    beats=HeartbeatRegistry(workers=workers)
    queue=ShellWorkQueue()
    queue.enqueue(ShellCommand("python"),item_id="x")
    queue.claim("w")
    report=WorkerDiagnostics(workers=workers,heartbeats=beats,queue=queue).inspect()
    assert any(item.code=="claim_owner_disabled" for item in report.findings)
