"""Dependency-aware execution of immutable shell plans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from typing import Callable

from skeleton.shells.cancellation import CancellationToken
from skeleton.shells.deadlines import Deadline
from skeleton.shells.dispatch import DispatchResult,ShellDispatcher
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan,PlanStep
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.session import ShellSession

class StepState(str,Enum):
    PENDING="pending"
    SUCCEEDED="succeeded"
    FAILED="failed"
    SKIPPED="skipped"
    CANCELLED="cancelled"

@dataclass(frozen=True)
class StepExecution:
    step_id:str
    state:StepState
    dispatch:DispatchResult|None
    reason:str=""
    started_at:float=0.0
    finished_at:float=0.0

    @property
    def ok(self)->bool:
        return self.state is StepState.SUCCEEDED

    def to_dict(self)->dict[str,object]:
        return {
            "step_id":self.step_id,
            "state":self.state.value,
            "ok":self.ok,
            "reason":self.reason,
            "duration_seconds":max(0.0,self.finished_at-self.started_at),
            "dispatch":None if self.dispatch is None else {
                "ok":self.dispatch.ok,
                "permit_id":self.dispatch.permit_id,
                "lease_id":self.dispatch.lease_id,
                "duration_ms":self.dispatch.duration_ms,
            },
        }

@dataclass(frozen=True)
class PlanExecutionReport:
    plan_id:str
    fingerprint:str
    steps:tuple[StepExecution,...]
    started_at:float
    finished_at:float

    @property
    def succeeded(self)->int:
        return sum(step.state is StepState.SUCCEEDED for step in self.steps)

    @property
    def failed(self)->int:
        return sum(step.state is StepState.FAILED for step in self.steps)

    @property
    def skipped(self)->int:
        return sum(step.state is StepState.SKIPPED for step in self.steps)

    @property
    def ok(self)->bool:
        return self.failed==0 and all(step.state is not StepState.CANCELLED for step in self.steps)

    def to_dict(self)->dict[str,object]:
        return {
            "plan_id":self.plan_id,
            "fingerprint":self.fingerprint,
            "ok":self.ok,
            "succeeded":self.succeeded,
            "failed":self.failed,
            "skipped":self.skipped,
            "duration_seconds":max(0.0,self.finished_at-self.started_at),
            "steps":[step.to_dict() for step in self.steps],
        }

class ShellPlanExecutor:
    """Execute plan steps in deterministic topological order."""

    def __init__(
        self,
        dispatcher:ShellDispatcher,
        *,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.dispatcher=dispatcher
        self._clock=clock

    def execute(
        self,
        plan:ExecutionPlan,
        *,
        context:ExecutionContext,
        cancellation:CancellationToken|None=None,
        deadline:Deadline|None=None,
        retry:RetryPolicy|None=None,
        session:ShellSession|None=None,
    )->PlanExecutionReport:
        started=self._clock()
        results:dict[str,StepExecution]={}
        ordered=plan.topological_order()

        for step in ordered:
            step_started=self._clock()
            if cancellation is not None and cancellation.cancelled:
                results[step.step_id]=StepExecution(
                    step.step_id,StepState.CANCELLED,None,
                    "plan cancellation requested",step_started,self._clock(),
                )
                continue

            blocked=[]
            for dependency in step.depends_on:
                result=results[dependency]
                if not result.ok:
                    blocked.append(dependency)
            if blocked and not step.continue_on_failure:
                results[step.step_id]=StepExecution(
                    step.step_id,StepState.SKIPPED,None,
                    f"dependency failed: {sorted(blocked)[0]}",
                    step_started,self._clock(),
                )
                continue

            child=context.child(
                f"{context.correlation_id}:{step.step_id}",
                attributes={**dict(context.attributes),"plan_id":plan.plan_id,"step_id":step.step_id},
            )
            try:
                dispatch=self.dispatcher.dispatch(
                    step.command,
                    context=child,
                    cancellation=cancellation,
                    deadline=deadline,
                    retry=retry,
                    session=session,
                    lease_key=f"{plan.plan_id}:{step.step_id}",
                )
                state=StepState.SUCCEEDED if dispatch.ok else StepState.FAILED
                reason="" if dispatch.ok else "command returned unsuccessful outcome"
                results[step.step_id]=StepExecution(
                    step.step_id,state,dispatch,reason,step_started,self._clock()
                )
            except BaseException as exc:
                results[step.step_id]=StepExecution(
                    step.step_id,StepState.FAILED,None,type(exc).__name__,
                    step_started,self._clock(),
                )
                if not step.continue_on_failure:
                    continue

        return PlanExecutionReport(
            plan.plan_id,
            plan.fingerprint,
            tuple(results[step.step_id] for step in ordered),
            started,
            self._clock(),
        )
