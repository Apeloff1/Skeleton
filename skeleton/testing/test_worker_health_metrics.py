"""Worker health and metric edge-case tests."""

from __future__ import annotations

from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker_health import WorkerHealthInspector,WorkerHealthSeverity
from skeleton.shells.worker_heartbeat import HeartbeatPolicy,HeartbeatRegistry
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry
from skeleton.shells.worker_metrics import WorkerMetrics
from skeleton.shells.worker_supervisor import SupervisorPolicy,WorkerSupervisor


def setup(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    beats=HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(late_after_seconds=2,stale_after_seconds=4),
        clock=lambda:now[0],
    )
    queue=ShellWorkQueue(clock=lambda:now[0])
    supervisor=WorkerSupervisor(workers,clock=lambda:now[0])
    return workers,beats,queue,supervisor


def test_health_empty_fleet_is_not_critical_by_itself():
    now=[0.0]
    workers,beats,queue,supervisor=setup(now)
    report=WorkerHealthInspector(workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor).inspect()
    assert report.registered==0
    assert report.critical==0


def test_health_unknown_heartbeat_warns_and_no_healthy_is_critical():
    now=[0.0]
    workers,beats,queue,supervisor=setup(now)
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    supervisor.attach(worker)
    report=WorkerHealthInspector(workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor).inspect()
    assert any(item.code=="heartbeat_unknown" for item in report.findings)
    assert any(item.code=="no_healthy_workers" for item in report.findings)
    assert not report.ok


def test_health_late_and_stale_counts():
    now=[0.0]
    workers,beats,queue,supervisor=setup(now)
    a=WorkerIdentity("a",1);b=WorkerIdentity("b",1)
    workers.register(a);workers.register(b)
    supervisor.attach(a);supervisor.attach(b)
    beats.beat(a,sequence=1);beats.beat(b,sequence=1)
    now[0]=3
    beats.beat(a,sequence=2)
    now[0]=5
    report=WorkerHealthInspector(workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor).inspect()
    assert report.late==1
    assert report.stale==1


def test_health_queue_warning_and_critical():
    now=[0.0]
    workers,beats,queue,supervisor=setup(now)
    inspector=WorkerHealthInspector(
        workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor,
        queue_warning=1,queue_critical=2,
    )
    queue.enqueue(ShellCommand("python"),item_id="a")
    assert any(item.code=="queue_high" for item in inspector.inspect().findings)
    queue.enqueue(ShellCommand("python"),item_id="b")
    assert any(item.code=="queue_critical" for item in inspector.inspect().findings)


def test_health_quarantine_is_critical():
    now=[0.0]
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    beats=HeartbeatRegistry(workers=workers,clock=lambda:now[0])
    beats.beat(worker,sequence=1)
    queue=ShellWorkQueue(clock=lambda:now[0])
    supervisor=WorkerSupervisor(workers,policy=SupervisorPolicy(max_faults=1),clock=lambda:now[0])
    supervisor.attach(worker)
    supervisor.fault(worker,"x")
    report=WorkerHealthInspector(workers=workers,heartbeats=beats,queue=queue,supervisor=supervisor).inspect()
    quarantine=[item for item in report.findings if item.code=="worker_quarantined"]
    assert quarantine
    assert quarantine[0].severity is WorkerHealthSeverity.CRITICAL


def test_metrics_unknown_worker_is_zero_without_cardinality_side_effect():
    metrics=WorkerMetrics(max_workers=1)
    assert metrics.get("missing").starts==0
    metrics.started("real")
    assert metrics.get("real").starts==1


def test_metrics_reset_one_worker():
    metrics=WorkerMetrics()
    metrics.started("a");metrics.started("b")
    metrics.reset("a")
    assert metrics.get("a").starts==0
    assert metrics.get("b").starts==1


def test_metrics_reset_all():
    metrics=WorkerMetrics()
    metrics.started("a");metrics.started("b")
    metrics.reset()
    assert metrics.snapshot().workers=={}


def test_metrics_success_ratio():
    metrics=WorkerMetrics()
    metrics.completed("a",ok=True,duration_ms=1,output_bytes=0)
    metrics.completed("a",ok=False,duration_ms=1,output_bytes=0)
    assert metrics.get("a").success_ratio==0.5
