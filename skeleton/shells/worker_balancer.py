"""Pure worker balancing recommendations; never migrates work automatically."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping,Sequence

from skeleton.shells.worker_capacity import CapacityView


class BalanceAction(str,Enum):
    KEEP="keep"
    DRAIN="drain"
    ADD_CAPACITY="add_capacity"
    REDUCE_CAPACITY="reduce_capacity"


@dataclass(frozen=True)
class BalancePolicy:
    target_utilization:float=0.70
    high_utilization:float=0.90
    low_utilization:float=0.20
    min_healthy_workers:int=1

    def __post_init__(self)->None:
        if not 0<self.low_utilization<self.target_utilization<self.high_utilization<=1:
            raise ValueError("invalid utilization thresholds")
        if self.min_healthy_workers<=0:
            raise ValueError("min_healthy_workers must be positive")


@dataclass(frozen=True)
class WorkerBalanceRecommendation:
    worker_id:str
    action:BalanceAction
    utilization:float
    reason:str

    def to_dict(self)->dict[str,object]:
        return {
            "worker_id":self.worker_id,
            "action":self.action.value,
            "utilization":self.utilization,
            "reason":self.reason,
        }


@dataclass(frozen=True)
class FleetBalanceReport:
    recommendations:tuple[WorkerBalanceRecommendation,...]
    aggregate_utilization:float
    healthy_workers:int
    total_inflight:int
    total_capacity:int

    def to_dict(self)->dict[str,object]:
        return {
            "aggregate_utilization":self.aggregate_utilization,
            "healthy_workers":self.healthy_workers,
            "total_inflight":self.total_inflight,
            "total_capacity":self.total_capacity,
            "recommendations":[item.to_dict() for item in self.recommendations],
        }


class WorkerBalancer:
    def __init__(self,policy:BalancePolicy|None=None)->None:
        self.policy=policy or BalancePolicy()

    @staticmethod
    def _utilization(view:CapacityView)->float:
        capacity=max(1,view.capacity.usable_inflight)
        return min(1.0,view.inflight/capacity)

    def analyze(self,views:Sequence[CapacityView])->FleetBalanceReport:
        healthy=[view for view in views if view.liveness.value=="healthy"]
        total_capacity=sum(view.capacity.usable_inflight for view in healthy)
        total_inflight=sum(view.inflight for view in healthy)
        aggregate=0.0 if total_capacity==0 else total_inflight/total_capacity
        recommendations:list[WorkerBalanceRecommendation]=[]

        for view in sorted(healthy,key=lambda item:item.worker_id):
            utilization=self._utilization(view)
            if utilization>=self.policy.high_utilization:
                action=BalanceAction.ADD_CAPACITY
                reason="worker exceeds high utilization threshold"
            elif (
                utilization<=self.policy.low_utilization
                and len(healthy)>self.policy.min_healthy_workers
                and aggregate<self.policy.target_utilization
            ):
                action=BalanceAction.DRAIN
                reason="worker is underutilized and fleet has spare capacity"
            else:
                action=BalanceAction.KEEP
                reason="worker is within balancing thresholds"
            recommendations.append(WorkerBalanceRecommendation(view.worker_id,action,utilization,reason))

        if not healthy:
            recommendations.append(
                WorkerBalanceRecommendation("",BalanceAction.ADD_CAPACITY,0.0,"no healthy workers available")
            )

        return FleetBalanceReport(
            tuple(recommendations),
            aggregate,
            len(healthy),
            total_inflight,
            total_capacity,
        )
