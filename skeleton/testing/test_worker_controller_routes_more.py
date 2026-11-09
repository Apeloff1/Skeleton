"""More controller, routing, scaling, and state safety tests."""

from __future__ import annotations

import pytest

from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker_controller import WorkerController
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRole
from skeleton.shells.worker_runtime import WorkerRuntime
from skeleton.shells.worker_schedule import WorkerSchedule
from skeleton.shells.worker_scaling import ScalingPolicy,WorkerScaler
from skeleton.shells.worker_state_store import WorkerStateStore


def runtime_with(role):
    runtime=WorkerRuntime()
    worker=WorkerIdentity("w",1,role=role)
    runtime.register(worker)
    runtime.heartbeat(worker,sequence=1)
    return runtime


@pytest.mark.parametrize(
    "work_class,role",
    [
        ("build",WorkerRole.BUILDER),
        ("test",WorkerRole.TESTER),
        ("analysis",WorkerRole.ANALYZER),
        ("maintenance",WorkerRole.MAINTENANCE),
    ],
)
def test_default_routes_accept_matching_roles(work_class,role):
    runtime=runtime_with(role)
    controller=WorkerController(runtime)
    submission=controller.new_submission(
        principal="p",work_class=work_class,command=ShellCommand("python"),submission_id="x"
    )
    assert controller.inspect(submission).allowed


def test_controller_duplicate_submission_id_fails_queue_insert():
    runtime=runtime_with(WorkerRole.BUILDER)
    controller=WorkerController(runtime)
    first=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="same"
    )
    controller.submit(first)
    second=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="same"
    )
    with pytest.raises(ValueError):
        controller.submit(second)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_schedule_rejects_invalid_capacity(value):
    with pytest.raises(ValueError):
        WorkerSchedule(max_items=value)


@pytest.mark.parametrize("delay", [-1, True, float("nan"), float("inf"), "1"])
def test_schedule_rejects_invalid_delay(delay):
    schedule=WorkerSchedule()
    with pytest.raises(ValueError):
        schedule.schedule("x",ShellCommand("python"),delay_seconds=delay)


@pytest.mark.parametrize("priority", [True, 1.5, "1"])
def test_schedule_rejects_invalid_priority(priority):
    schedule=WorkerSchedule()
    with pytest.raises(ValueError):
        schedule.schedule("x",ShellCommand("python"),priority=priority)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_schedule_rejects_invalid_release_limit(limit):
    schedule=WorkerSchedule()
    with pytest.raises(ValueError):
        schedule.pop_ready(limit=limit)


def test_schedule_limit_on_release():
    now=[0.0]
    schedule=WorkerSchedule(clock=lambda:now[0])
    for i in range(3):
        schedule.schedule(str(i),ShellCommand("python"))
    assert len(schedule.pop_ready(limit=2))==2
    assert len(schedule.snapshot())==1


def test_state_snapshot_sorted():
    store=WorkerStateStore()
    store.put("b",1,{})
    store.put("a",1,{})
    assert [item.worker_id for item in store.snapshot()]==["a","b"]


def test_scaling_policy_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        ScalingPolicy(scale_in_queue_per_worker=10,target_queue_per_worker=5)


def test_scaler_rejects_negative_inputs():
    scaler=WorkerScaler()
    with pytest.raises(ValueError):
        scaler.recommend(healthy_workers=-1,queued=0)
    with pytest.raises(ValueError):
        scaler.recommend(healthy_workers=1,queued=-1)
