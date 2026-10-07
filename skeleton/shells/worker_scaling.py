"""Pure fleet scaling recommendations from capacity and backlog signals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ScalingAction(str,Enum):
    HOLD="hold"
    SCALE_OUT="scale_out"
    SCALE_IN="scale_in"


@dataclass(frozen=True)
class ScalingPolicy:
    target_queue_per_worker:float=10.0
    scale_out_queue_per_worker:float=25.0
    scale_in_queue_per_worker:float|None=None
    min_workers:int=1
    max_workers:int=256
    max_step:int=8

    def __post_init__(self)->None:
        scale_in=self.scale_in_queue_per_worker
        if scale_in is None:
            scale_in=min(2.0,self.target_queue_per_worker/2)
            object.__setattr__(self,"scale_in_queue_per_worker",scale_in)
        if not 0<=scale_in<self.target_queue_per_worker<self.scale_out_queue_per_worker:
            raise ValueError("invalid scaling thresholds")
        if self.min_workers<=0 or self.max_workers<self.min_workers:
            raise ValueError("invalid worker scale bounds")
        if self.max_step<=0:raise ValueError("max_step must be positive")


@dataclass(frozen=True)
class ScalingRecommendation:
    action:ScalingAction
    current_workers:int
    desired_workers:int
    queued:int
    queue_per_worker:float
    reason:str

    @property
    def delta(self)->int:return self.desired_workers-self.current_workers

    def to_dict(self)->dict[str,object]:
        return {
            "action":self.action.value,
            "current_workers":self.current_workers,
            "desired_workers":self.desired_workers,
            "delta":self.delta,
            "queued":self.queued,
            "queue_per_worker":self.queue_per_worker,
            "reason":self.reason,
        }


class WorkerScaler:
    def __init__(self,policy:ScalingPolicy|None=None)->None:self.policy=policy or ScalingPolicy()

    def recommend(self,*,healthy_workers:int,queued:int)->ScalingRecommendation:
        if healthy_workers<0 or queued<0:raise ValueError("scaling inputs may not be negative")
        effective=max(1,healthy_workers)
        ratio=queued/effective
        desired=max(self.policy.min_workers,healthy_workers)
        action=ScalingAction.HOLD
        reason="within scaling thresholds"
        if ratio>=self.policy.scale_out_queue_per_worker:
            raw=max(1,int((queued/self.policy.target_queue_per_worker)+0.999))
            desired=min(self.policy.max_workers,healthy_workers+self.policy.max_step,raw)
            desired=max(desired,self.policy.min_workers)
            action=ScalingAction.SCALE_OUT if desired>healthy_workers else ScalingAction.HOLD
            reason="queue pressure exceeds scale-out threshold"
        elif ratio<=self.policy.scale_in_queue_per_worker and healthy_workers>self.policy.min_workers:
            desired=max(self.policy.min_workers,healthy_workers-self.policy.max_step)
            action=ScalingAction.SCALE_IN if desired<healthy_workers else ScalingAction.HOLD
            reason="queue pressure below scale-in threshold"
        return ScalingRecommendation(action,healthy_workers,desired,queued,ratio,reason)
