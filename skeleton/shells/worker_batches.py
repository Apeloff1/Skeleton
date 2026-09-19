"""Atomic-looking worker batch admission plans without hidden execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.shells.worker_admission import WorkerAdmission,WorkerAdmissionDecision
from skeleton.shells.worker_affinity import JobRequirements
from skeleton.shells.worker_capacity import CapacityDemand
from skeleton.shells.worker_heartbeat import LivenessView
from skeleton.shells.worker_identity import WorkerRegistration


@dataclass(frozen=True)
class WorkerBatchItem:
    item_id:str
    principal:str
    requirements:JobRequirements=JobRequirements()
    demand:CapacityDemand=CapacityDemand()

    def __post_init__(self)->None:
        if not self.item_id or len(self.item_id)>256:raise ValueError("invalid batch item_id")
        if not self.principal or len(self.principal)>256:raise ValueError("invalid batch principal")


@dataclass(frozen=True)
class WorkerBatchDecision:
    item:WorkerBatchItem
    admission:WorkerAdmissionDecision


@dataclass(frozen=True)
class WorkerBatchPlan:
    decisions:tuple[WorkerBatchDecision,...]

    @property
    def allowed(self)->bool:
        return all(item.admission.allowed for item in self.decisions)

    @property
    def accepted(self)->int:
        return sum(item.admission.allowed for item in self.decisions)

    @property
    def rejected(self)->int:
        return len(self.decisions)-self.accepted

    def to_dict(self)->dict[str,object]:
        return {
            "allowed":self.allowed,
            "accepted":self.accepted,
            "rejected":self.rejected,
            "decisions":[
                {"item_id":item.item.item_id,"admission":item.admission.to_dict()}
                for item in self.decisions
            ],
        }


class WorkerBatchPlanner:
    def __init__(self,admission:WorkerAdmission)->None:self.admission=admission

    def plan(
        self,
        items:Sequence[WorkerBatchItem],
        *,
        registrations:Sequence[WorkerRegistration],
        liveness:dict[str,LivenessView],
    )->WorkerBatchPlan:
        decisions=[]
        for item in items:
            decision=self.admission.inspect(
                principal=item.principal,
                registrations=registrations,
                liveness=liveness,
                requirements=item.requirements,
                demand=item.demand,
            )
            decisions.append(WorkerBatchDecision(item,decision))
        return WorkerBatchPlan(tuple(decisions))
