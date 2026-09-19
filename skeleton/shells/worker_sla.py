"""Queue-wait and execution service-level budgets for worker jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SLAClass(str,Enum):
    INTERACTIVE="interactive"
    STANDARD="standard"
    BATCH="batch"
    MAINTENANCE="maintenance"


@dataclass(frozen=True)
class SLABudget:
    max_queue_seconds:float
    max_runtime_seconds:float
    max_attempts:int
    priority:int

    def __post_init__(self)->None:
        if self.max_queue_seconds<=0 or self.max_runtime_seconds<=0:
            raise ValueError("SLA time budgets must be positive")
        if self.max_attempts<=0:raise ValueError("max_attempts must be positive")


@dataclass(frozen=True)
class SLAEvaluation:
    sla_class:SLAClass
    queue_age_seconds:float
    runtime_seconds:float
    attempts:int
    queue_breached:bool
    runtime_breached:bool
    attempts_breached:bool

    @property
    def breached(self)->bool:
        return self.queue_breached or self.runtime_breached or self.attempts_breached

    def to_dict(self)->dict[str,object]:
        return {
            "sla_class":self.sla_class.value,
            "queue_age_seconds":self.queue_age_seconds,
            "runtime_seconds":self.runtime_seconds,
            "attempts":self.attempts,
            "queue_breached":self.queue_breached,
            "runtime_breached":self.runtime_breached,
            "attempts_breached":self.attempts_breached,
            "breached":self.breached,
        }


class WorkerSLA:
    def __init__(self,budgets:dict[SLAClass,SLABudget]|None=None)->None:
        self.budgets=budgets or {
            SLAClass.INTERACTIVE:SLABudget(5,30,2,10),
            SLAClass.STANDARD:SLABudget(60,120,3,50),
            SLAClass.BATCH:SLABudget(3600,1800,3,100),
            SLAClass.MAINTENANCE:SLABudget(7200,3600,2,200),
        }
        missing=set(SLAClass)-set(self.budgets)
        if missing:raise ValueError("SLA budget map must define every class")

    def budget(self,sla_class:SLAClass)->SLABudget:
        return self.budgets[SLAClass(sla_class)]

    def evaluate(
        self,
        sla_class:SLAClass,
        *,
        queue_age_seconds:float,
        runtime_seconds:float=0.0,
        attempts:int=1,
    )->SLAEvaluation:
        if queue_age_seconds<0 or runtime_seconds<0 or attempts<=0:
            raise ValueError("invalid SLA observation")
        budget=self.budget(sla_class)
        return SLAEvaluation(
            SLAClass(sla_class),
            queue_age_seconds,
            runtime_seconds,
            attempts,
            queue_age_seconds>budget.max_queue_seconds,
            runtime_seconds>budget.max_runtime_seconds,
            attempts>budget.max_attempts,
        )
