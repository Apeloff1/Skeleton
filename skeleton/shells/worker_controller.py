"""Submission/control facade for the worker plane; never spawns processes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from typing import Callable

from skeleton.shells.queue import QueueItem,ShellWorkQueue
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker_admission import WorkerAdmissionDecision
from skeleton.shells.worker_affinity import JobRequirements
from skeleton.shells.worker_backpressure import BackpressureDecision
from skeleton.shells.worker_capacity import CapacityDemand
from skeleton.shells.worker_events import WorkerEvents
from skeleton.shells.worker_routing import WorkerRoutes
from skeleton.shells.worker_runtime import WorkerRuntime
from skeleton.shells.worker_schedule import ScheduledWork,WorkerSchedule


@dataclass(frozen=True)
class WorkerSubmission:
    submission_id:str
    principal:str
    work_class:str
    command:ShellCommand
    priority:int=100
    demand:CapacityDemand=CapacityDemand()
    created_at:float=0.0

    def __post_init__(self)->None:
        if not self.submission_id or len(self.submission_id)>256:raise ValueError("invalid submission_id")
        if not self.principal or len(self.principal)>256:raise ValueError("invalid principal")
        if not self.work_class or len(self.work_class)>128:raise ValueError("invalid work_class")


@dataclass(frozen=True)
class SubmissionDecision:
    accepted:bool
    admission:WorkerAdmissionDecision
    queue_item:QueueItem|None=None
    scheduled:ScheduledWork|None=None

    def to_dict(self)->dict[str,object]:
        return {
            "accepted":self.accepted,
            "admission":self.admission.to_dict(),
            "queue_item_id":None if self.queue_item is None else self.queue_item.item_id,
            "schedule_id":None if self.scheduled is None else self.scheduled.schedule_id,
        }


class WorkerController:
    def __init__(
        self,
        runtime:WorkerRuntime,
        *,
        routes:WorkerRoutes|None=None,
        schedule:WorkerSchedule|None=None,
        events:WorkerEvents|None=None,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.runtime=runtime
        self.routes=routes or WorkerRoutes.defaults()
        self.schedule=schedule or WorkerSchedule(clock=clock)
        self.events=events or WorkerEvents(clock=clock)
        self._clock=clock

    def new_submission(
        self,
        *,
        principal:str,
        work_class:str,
        command:ShellCommand,
        priority:int=100,
        demand:CapacityDemand|None=None,
        submission_id:str|None=None,
    )->WorkerSubmission:
        now=self._clock()
        identifier=submission_id
        if identifier is None:
            raw=f"{principal}:{work_class}:{command.command}:{now}"
            identifier=hashlib.sha256(raw.encode()).hexdigest()[:32]
        return WorkerSubmission(
            identifier,principal,work_class,command,priority,demand or CapacityDemand(),now
        )

    def inspect(
        self,
        submission:WorkerSubmission,
        *,
        backpressure:BackpressureDecision|None=None,
    )->WorkerAdmissionDecision:
        requirements=self.routes.resolve(submission.work_class,principal=submission.principal)
        return self.runtime.inspect_admission(
            principal=submission.principal,
            requirements=requirements,
            demand=submission.demand,
            backpressure=backpressure,
        )

    def submit(
        self,
        submission:WorkerSubmission,
        *,
        backpressure:BackpressureDecision|None=None,
        delay_seconds:float=0.0,
    )->SubmissionDecision:
        admission=self.inspect(submission,backpressure=backpressure)
        if not admission.allowed:
            self.events.emit("worker.submission.denied",data={
                "submission_id":submission.submission_id,
                "principal":submission.principal,
                "reason":admission.reason,
            })
            return SubmissionDecision(False,admission)

        if delay_seconds>0:
            scheduled=self.schedule.schedule(
                submission.submission_id,
                submission.command,
                delay_seconds=delay_seconds,
                priority=submission.priority,
                principal=submission.principal,
            )
            self.events.emit("worker.submission.scheduled",data={
                "submission_id":submission.submission_id,
                "worker_id":admission.worker.identity.worker_id if admission.worker else "",
            })
            return SubmissionDecision(True,admission,scheduled=scheduled)

        item=self.runtime.queue.enqueue(
            submission.command,
            priority=submission.priority,
            item_id=submission.submission_id,
        )
        self.events.emit("worker.submission.queued",data={
            "submission_id":submission.submission_id,
            "worker_id":admission.worker.identity.worker_id if admission.worker else "",
        })
        return SubmissionDecision(True,admission,queue_item=item)

    def release_ready(self,*,limit:int=100)->tuple[QueueItem,...]:
        ready=self.schedule.pop_ready(limit=limit)
        queued=[]
        for scheduled in ready:
            item=self.runtime.queue.enqueue(
                scheduled.command,
                priority=scheduled.priority,
                item_id=scheduled.schedule_id,
            )
            queued.append(item)
            self.events.emit("worker.schedule.released",data={"submission_id":scheduled.schedule_id})
        return tuple(queued)
