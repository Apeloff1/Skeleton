"""Worker capacity models and deterministic placement headroom calculations."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from skeleton.shells.worker_heartbeat import LivenessView, WorkerLiveness
from skeleton.shells.worker_identity import WorkerRegistration


@dataclass(frozen=True)
class WorkerCapacity:
    max_inflight: int = 1
    max_weight: int = 1
    reserved_inflight: int = 0
    reserved_weight: int = 0

    def __post_init__(self) -> None:
        values=(self.max_inflight,self.max_weight,self.reserved_inflight,self.reserved_weight)
        if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in values):
            raise ValueError("worker capacity values must be non-negative integers")
        if self.max_inflight<=0 or self.max_weight<=0:
            raise ValueError("worker capacity maxima must be positive")
        if self.reserved_inflight>self.max_inflight or self.reserved_weight>self.max_weight:
            raise ValueError("reserved capacity exceeds maximum")

    @property
    def usable_inflight(self)->int:
        return self.max_inflight-self.reserved_inflight

    @property
    def usable_weight(self)->int:
        return self.max_weight-self.reserved_weight

    def to_dict(self)->dict[str,int]:
        return {
            "max_inflight":self.max_inflight,
            "max_weight":self.max_weight,
            "reserved_inflight":self.reserved_inflight,
            "reserved_weight":self.reserved_weight,
            "usable_inflight":self.usable_inflight,
            "usable_weight":self.usable_weight,
        }


@dataclass(frozen=True)
class CapacityDemand:
    inflight: int = 1
    weight: int = 1

    def __post_init__(self)->None:
        if isinstance(self.inflight,bool) or not isinstance(self.inflight,int) or self.inflight<=0:
            raise ValueError("demand inflight must be positive")
        if isinstance(self.weight,bool) or not isinstance(self.weight,int) or self.weight<=0:
            raise ValueError("demand weight must be positive")


@dataclass(frozen=True)
class CapacityView:
    worker_id:str
    generation:int
    capacity:WorkerCapacity
    inflight:int
    active_weight:int
    liveness:WorkerLiveness

    @property
    def free_inflight(self)->int:
        return max(0,self.capacity.usable_inflight-self.inflight)

    @property
    def free_weight(self)->int:
        return max(0,self.capacity.usable_weight-self.active_weight)

    def can_fit(self,demand:CapacityDemand)->bool:
        return (
            self.liveness is WorkerLiveness.HEALTHY
            and self.free_inflight>=demand.inflight
            and self.free_weight>=demand.weight
        )

    def to_dict(self)->dict[str,object]:
        return {
            "worker_id":self.worker_id,
            "generation":self.generation,
            "capacity":self.capacity.to_dict(),
            "inflight":self.inflight,
            "active_weight":self.active_weight,
            "liveness":self.liveness.value,
            "free_inflight":self.free_inflight,
            "free_weight":self.free_weight,
        }


@dataclass(frozen=True)
class FleetCapacity:
    workers:tuple[CapacityView,...]

    @property
    def total_free_inflight(self)->int:
        return sum(view.free_inflight for view in self.workers if view.liveness is WorkerLiveness.HEALTHY)

    @property
    def total_free_weight(self)->int:
        return sum(view.free_weight for view in self.workers if view.liveness is WorkerLiveness.HEALTHY)

    @property
    def healthy_workers(self)->int:
        return sum(view.liveness is WorkerLiveness.HEALTHY for view in self.workers)

    def fit_count(self,demand:CapacityDemand)->int:
        return sum(view.can_fit(demand) for view in self.workers)

    def to_dict(self)->dict[str,object]:
        return {
            "total_free_inflight":self.total_free_inflight,
            "total_free_weight":self.total_free_weight,
            "healthy_workers":self.healthy_workers,
            "workers":[view.to_dict() for view in self.workers],
        }


class WorkerCapacityCatalog:
    """Capacity declarations keyed by worker ID and protected by generation checks at read time."""

    def __init__(self,default:WorkerCapacity|None=None)->None:
        self.default=default or WorkerCapacity()
        self._items:dict[str,WorkerCapacity]={}

    def set(self,worker_id:str,capacity:WorkerCapacity)->None:
        if not worker_id or len(worker_id)>128:
            raise ValueError("invalid worker_id")
        if not isinstance(capacity,WorkerCapacity):
            raise TypeError("capacity must be WorkerCapacity")
        self._items[worker_id]=capacity

    def get(self,worker_id:str)->WorkerCapacity:
        return self._items.get(worker_id,self.default)

    def remove(self,worker_id:str)->bool:
        return self._items.pop(worker_id,None) is not None

    def snapshot(self)->Mapping[str,WorkerCapacity]:
        return MappingProxyType(dict(self._items))

    def fleet(
        self,
        registrations:Sequence[WorkerRegistration],
        liveness:Mapping[str,LivenessView],
        active_weight:Mapping[str,int]|None=None,
    )->FleetCapacity:
        weights=active_weight or {}
        views=[]
        for registration in registrations:
            identity=registration.identity
            live=liveness.get(identity.worker_id)
            if live is None:
                live=LivenessView(identity.worker_id,identity.generation,WorkerLiveness.UNKNOWN,None,None,False,0)
            views.append(CapacityView(
                worker_id=identity.worker_id,
                generation=identity.generation,
                capacity=self.get(identity.worker_id),
                inflight=live.inflight,
                active_weight=max(0,int(weights.get(identity.worker_id,0))),
                liveness=live.liveness,
            ))
        return FleetCapacity(tuple(sorted(views,key=lambda item:item.worker_id)))
