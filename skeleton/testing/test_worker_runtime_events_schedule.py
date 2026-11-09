"""Worker runtime, events, schedule, metrics, and health tests."""

from __future__ import annotations

import pytest

from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker_events import WorkerEvents
from skeleton.shells.worker_heartbeat import HeartbeatPolicy,WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRole
from skeleton.shells.worker_metrics import WorkerMetrics
from skeleton.shells.worker_runtime import WorkerRuntime
from skeleton.shells.worker_schedule import WorkerSchedule


def test_events_emit_and_filter():
    now=[0.0]
    events=WorkerEvents(clock=lambda:now[0])
    first=events.emit("a",worker_id="w",generation=1)
    now[0]=1
    second=events.emit("b",worker_id="w",generation=1)
    assert first.sequence==1
    assert second.sequence==2
    assert events.events(kind="a")== (first,)
    assert events.events(after_sequence=1)==(second,)


def test_events_sink_failure_is_isolated():
    events=WorkerEvents()
    seen=[]
    events.subscribe(lambda event:seen.append(event.kind))
    events.subscribe(lambda event:(_ for _ in ()).throw(RuntimeError("boom")))
    events.emit("x")
    assert seen==["x"]


def test_events_ring_buffer_is_bounded():
    events=WorkerEvents(max_events=2)
    events.emit("1");events.emit("2");events.emit("3")
    assert [event.kind for event in events.tail(10)]==["2","3"]


def test_events_unsubscribe():
    events=WorkerEvents()
    sink=lambda event:None
    events.subscribe(sink)
    assert events.unsubscribe(sink)
    assert not events.unsubscribe(sink)


def test_schedule_delays_until_ready():
    now=[0.0]
    schedule=WorkerSchedule(clock=lambda:now[0])
    schedule.schedule("x",ShellCommand("python"),delay_seconds=5)
    assert schedule.pop_ready()==()
    now[0]=5
    assert [item.schedule_id for item in schedule.pop_ready()]==["x"]


def test_schedule_ready_order_is_time_priority_sequence():
    now=[0.0]
    schedule=WorkerSchedule(clock=lambda:now[0])
    schedule.schedule("a",ShellCommand("python"),priority=20)
    schedule.schedule("b",ShellCommand("python"),priority=10)
    schedule.schedule("c",ShellCommand("python"),priority=10)
    assert [item.schedule_id for item in schedule.pop_ready()]==["b","c","a"]


def test_schedule_cancel_lazily_removes_heap_entry():
    schedule=WorkerSchedule()
    schedule.schedule("x",ShellCommand("python"))
    assert schedule.cancel("x")
    assert not schedule.cancel("x")
    assert schedule.pop_ready()==()


def test_schedule_duplicate_id_rejected():
    schedule=WorkerSchedule()
    schedule.schedule("x",ShellCommand("python"))
    with pytest.raises(RuntimeError):
        schedule.schedule("x",ShellCommand("python"))


def test_metrics_started_completed_retry_recovered():
    metrics=WorkerMetrics()
    metrics.started("w")
    metrics.completed("w",ok=True,duration_ms=10,output_bytes=5)
    metrics.retried("w",2)
    metrics.recovered("w",3)
    item=metrics.get("w")
    assert item.starts==1
    assert item.successes==1
    assert item.retries==2
    assert item.recovered_claims==3
    assert item.average_duration_ms==10


def test_metrics_failure_ratio_and_snapshot_totals():
    metrics=WorkerMetrics()
    metrics.completed("a",ok=False,duration_ms=2,output_bytes=3)
    metrics.completed("b",ok=True,duration_ms=1,output_bytes=4)
    snap=metrics.snapshot()
    assert snap.total_failures==1
    assert snap.total_output_bytes==7


def test_metrics_cardinality_bound():
    metrics=WorkerMetrics(max_workers=1)
    metrics.started("a")
    with pytest.raises(RuntimeError):
        metrics.started("b")


def test_runtime_register_heartbeat_snapshot():
    now=[0.0]
    runtime=WorkerRuntime(clock=lambda:now[0])
    worker=WorkerIdentity("w",1,role=WorkerRole.BUILDER)
    runtime.register(worker)
    runtime.heartbeat(worker,sequence=1)
    snap=runtime.snapshot()
    assert snap.workers==1
    assert snap.enabled==1
    assert snap.healthy==1
    assert snap.journal_events==2


def test_runtime_checkpoint_is_chained():
    runtime=WorkerRuntime()
    worker=WorkerIdentity("w",1)
    runtime.register(worker)
    first=runtime.checkpoint(worker)
    second=runtime.checkpoint(worker)
    assert second.previous_digest==first.digest


def test_runtime_replace_resets_generation_checkpoint_chain():
    runtime=WorkerRuntime()
    first=WorkerIdentity("w",1)
    runtime.register(first)
    runtime.checkpoint(first)
    second=WorkerIdentity("w",2)
    runtime.replace(second)
    checkpoint=runtime.checkpoint(second)
    assert checkpoint.sequence==1
    assert checkpoint.generation==2


def test_runtime_admission_requires_heartbeat():
    runtime=WorkerRuntime()
    worker=WorkerIdentity("w",1)
    runtime.register(worker)
    decision=runtime.inspect_admission(principal="p")
    assert not decision.allowed
    runtime.heartbeat(worker,sequence=1)
    assert runtime.inspect_admission(principal="p").allowed


def test_runtime_health_reports_unknown_heartbeat():
    runtime=WorkerRuntime()
    runtime.register(WorkerIdentity("w",1))
    report=runtime.health_report()
    assert not report.ok
    assert any(item.code=="no_healthy_workers" for item in report.findings)
