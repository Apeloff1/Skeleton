"""Submission controller and managed worker integration tests."""

from __future__ import annotations

from dataclasses import dataclass
import pytest

from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker import QueueWorker
from skeleton.shells.worker_backpressure import BackpressureDecision,BackpressureState
from skeleton.shells.worker_controller import WorkerController,WorkerSubmission
from skeleton.shells.worker_events import WorkerEvents
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRole
from skeleton.shells.worker_managed import ManagedQueueWorker
from skeleton.shells.worker_quota import WorkerQuota,WorkerQuotaLedger
from skeleton.shells.worker_runtime import WorkerRuntime


@dataclass(frozen=True)
class Outcome:
    ok:bool


class Executor:
    def __init__(self,ok=True):self.ok=ok
    def execute(self,*args,**kwargs):return Outcome(self.ok)


def ready_runtime():
    runtime=WorkerRuntime()
    worker=WorkerIdentity("builder",1,role=WorkerRole.BUILDER)
    runtime.register(worker)
    runtime.heartbeat(worker,sequence=1)
    return runtime,worker


@pytest.mark.parametrize("field,value", [
    ("submission_id",""),
    ("submission_id","   "),
    ("principal",""),
    ("principal","bad\x00principal"),
    ("work_class",""),
    ("work_class","bad\x00class"),
])
def test_worker_submission_rejects_invalid_identity_fields(field,value):
    kwargs={
        "submission_id":"s1",
        "principal":"p",
        "work_class":"build",
        "command":ShellCommand("python"),
    }
    kwargs[field]=value
    with pytest.raises(ValueError):
        WorkerSubmission(**kwargs)


@pytest.mark.parametrize("priority", [True, 1.5, "1"])
def test_worker_submission_rejects_invalid_priority(priority):
    with pytest.raises(ValueError):
        WorkerSubmission("s1","p","build",ShellCommand("python"),priority=priority)


@pytest.mark.parametrize("created_at", [-1, True, float("nan"), float("inf")])
def test_worker_submission_rejects_invalid_timestamp(created_at):
    with pytest.raises(ValueError):
        WorkerSubmission("s1","p","build",ShellCommand("python"),created_at=created_at)


def test_controller_new_submission_stable_shape():
    runtime,_=ready_runtime()
    controller=WorkerController(runtime)
    submission=controller.new_submission(
        principal="team:a",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    assert submission.submission_id=="s1"
    assert submission.principal=="team:a"
    assert submission.work_class=="build"


def test_controller_submit_queues_admitted_work():
    runtime,_=ready_runtime()
    controller=WorkerController(runtime)
    submission=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    decision=controller.submit(submission)
    assert decision.accepted
    assert decision.queue_item.item_id=="s1"
    assert runtime.queue.counts()["queued"]==1


def test_controller_submit_can_schedule():
    runtime,_=ready_runtime()
    now=[0.0]
    # Runtime can use its own clock; only schedule release needs the controller clock.
    controller=WorkerController(runtime,clock=lambda:now[0])
    submission=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    decision=controller.submit(submission,delay_seconds=5)
    assert decision.accepted
    assert decision.scheduled.schedule_id=="s1"
    assert runtime.queue.counts()["queued"]==0
    now[0]=5
    released=controller.release_ready()
    assert [item.item_id for item in released]==["s1"]


@pytest.mark.parametrize("delay", [-1, True, float("nan"), float("inf"), "1"])
def test_controller_rejects_invalid_delay_before_admission(delay):
    runtime,_=ready_runtime()
    controller=WorkerController(runtime)
    submission=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    with pytest.raises(ValueError):
        controller.submit(submission,delay_seconds=delay)
    assert runtime.queue.counts()["queued"]==0


def test_controller_denies_paused_backpressure():
    runtime,_=ready_runtime()
    controller=WorkerController(runtime)
    submission=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    pressure=BackpressureDecision(BackpressureState.PAUSED,0,"paused",0,0,0,False,0)
    decision=controller.submit(submission,backpressure=pressure)
    assert not decision.accepted
    assert runtime.queue.counts()["queued"]==0


def test_controller_wrong_role_denied():
    runtime=WorkerRuntime()
    tester=WorkerIdentity("tester",1,role=WorkerRole.TESTER)
    runtime.register(tester);runtime.heartbeat(tester,sequence=1)
    controller=WorkerController(runtime)
    submission=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    assert not controller.submit(submission).accepted


def test_controller_emits_queue_event():
    runtime,_=ready_runtime()
    events=WorkerEvents()
    controller=WorkerController(runtime,events=events)
    submission=controller.new_submission(
        principal="p",work_class="build",command=ShellCommand("python"),submission_id="s1"
    )
    controller.submit(submission)
    assert [event.kind for event in events.events()]==["worker.submission.queued"]


def test_managed_worker_records_success():
    runtime,_=ready_runtime()
    runtime.queue.enqueue(ShellCommand("python"),item_id="x")
    base=QueueWorker("w",runtime.queue,Executor(True))
    managed=ManagedQueueWorker(base)
    result=managed.run_once()
    assert result.ok
    assert managed.metrics.get("w").successes==1
    assert len(managed.journal)==2
    assert [event.kind for event in managed.events.events()]==[
        "worker.execution.started","worker.execution.completed"
    ]


def test_managed_worker_records_failed_outcome():
    runtime,_=ready_runtime()
    runtime.queue.enqueue(ShellCommand("python"),item_id="x")
    base=QueueWorker("w",runtime.queue,Executor(False))
    managed=ManagedQueueWorker(base)
    result=managed.run_once()
    assert not result.ok
    assert managed.metrics.get("w").failures==1


class RaisingExecutor:
    def execute(self,*args,**kwargs):raise RuntimeError("boom")


def test_managed_worker_records_exception_and_reraises():
    runtime,_=ready_runtime()
    runtime.queue.enqueue(ShellCommand("python"),item_id="x")
    managed=ManagedQueueWorker(QueueWorker("w",runtime.queue,RaisingExecutor()))
    with pytest.raises(RuntimeError):
        managed.run_once()
    assert managed.metrics.get("w").failures==1
    assert any(event.kind=="worker.execution.error" for event in managed.events.events())


def test_managed_worker_quota_blocks_execution():
    runtime,_=ready_runtime()
    runtime.queue.enqueue(ShellCommand("python"),item_id="x")
    quota=WorkerQuotaLedger(WorkerQuota(max_inflight=0,max_starts_per_window=0))
    managed=ManagedQueueWorker(QueueWorker("w",runtime.queue,Executor()),quotas=quota)
    with pytest.raises(RuntimeError):
        managed.run_once()
    assert runtime.queue.counts()["queued"]==1


def test_managed_worker_drain_is_bounded():
    runtime,_=ready_runtime()
    for i in range(5):runtime.queue.enqueue(ShellCommand("python"),item_id=str(i))
    managed=ManagedQueueWorker(QueueWorker("w",runtime.queue,Executor()))
    results=managed.drain(max_items=2)
    assert len(results)==2
    assert runtime.queue.counts()["queued"]==3
