"""Topology-aware spread constraints for worker placement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping,Sequence

from skeleton.shells.worker_identity import WorkerRegistration


@dataclass(frozen=True)
class SpreadConstraint:
    label_key:str
    max_skew:int=1
    min_domains:int=1

    def __post_init__(self)->None:
        if not self.label_key or len(self.label_key)>64:raise ValueError("invalid topology label")
        if self.max_skew<0 or self.min_domains<=0:raise ValueError("invalid spread bounds")


@dataclass(frozen=True)
class TopologyDecision:
    allowed:tuple[WorkerRegistration,...]
    domain_counts:dict[str,int]
    rejected:dict[str,str]


class WorkerTopology:
    def filter(
        self,
        candidates:Sequence[WorkerRegistration],
        *,
        active_assignments:Mapping[str,int],
        constraint:SpreadConstraint,
    )->TopologyDecision:
        domains:dict[str,int]={}
        for registration in candidates:
            domain=registration.identity.labels.get(constraint.label_key,"")
            if domain:
                domains.setdefault(domain,0)
        for domain,count in active_assignments.items():
            if count<0:raise ValueError("assignment counts may not be negative")
            domains[domain]=count

        if len(domains)<constraint.min_domains:
            return TopologyDecision((),dict(domains),{
                item.identity.worker_id:"insufficient topology domains" for item in candidates
            })

        minimum=min(domains.values(),default=0)
        allowed=[]
        rejected={}
        for registration in candidates:
            domain=registration.identity.labels.get(constraint.label_key,"")
            if not domain:
                rejected[registration.identity.worker_id]="worker lacks topology label"
                continue
            projected=domains.get(domain,0)+1
            if projected-minimum>constraint.max_skew:
                rejected[registration.identity.worker_id]="placement would exceed topology skew"
                continue
            allowed.append(registration)
        return TopologyDecision(tuple(allowed),dict(domains),rejected)
