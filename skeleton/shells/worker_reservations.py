"""Capacity reservations for worker admission-to-execution handoff."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.worker_capacity import CapacityDemand,WorkerCapacityCatalog
from skeleton.shells.worker_heartbeat import HeartbeatRegistry,WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry


@dataclass(frozen=True)
class CapacityReservation:
    reservation_id:str
    worker:WorkerIdentity
    demand:CapacityDemand
    created_at:float
    expires_at:float


class ReservationConflict(RuntimeError):pass


class WorkerReservations:
    def __init__(
        self,
        workers:WorkerRegistry,
        heartbeats:HeartbeatRegistry,
        capacities:WorkerCapacityCatalog,
        *,
        clock:Callable[[],float]=time.monotonic,
        max_reservations:int=10000,
    )->None:
        self.workers=workers
        self.heartbeats=heartbeats
        self.capacities=capacities
        self._clock=clock
        self.max_reservations=max_reservations
        self._items:dict[str,CapacityReservation]={}
        self._serial=0
        self._lock=threading.RLock()

    def _prune(self)->None:
        now=self._clock()
        for key in [key for key,value in self._items.items() if value.expires_at<=now]:
            del self._items[key]

    def _used(self,worker_id:str)->CapacityDemand:
        inflight=weight=0
        for reservation in self._items.values():
            if reservation.worker.worker_id==worker_id:
                inflight+=reservation.demand.inflight
                weight+=reservation.demand.weight
        return CapacityDemand(max(1,inflight),max(1,weight)) if inflight or weight else CapacityDemand(1,1)

    def reserve(
        self,
        worker:WorkerIdentity,
        demand:CapacityDemand|None=None,
        *,
        ttl_seconds:float=30.0,
    )->CapacityReservation:
        demand=demand or CapacityDemand()
        if ttl_seconds<=0:raise ValueError("ttl_seconds must be positive")
        self.workers.require_current(worker)
        if self.heartbeats.liveness(worker).liveness is not WorkerLiveness.HEALTHY:
            raise ReservationConflict("worker is not healthy")
        with self._lock:
            self._prune()
            if len(self._items)>=self.max_reservations:
                raise ReservationConflict("reservation capacity exhausted")
            capacity=self.capacities.get(worker.worker_id)
            current_inflight=sum(
                item.demand.inflight for item in self._items.values() if item.worker.worker_id==worker.worker_id
            )
            current_weight=sum(
                item.demand.weight for item in self._items.values() if item.worker.worker_id==worker.worker_id
            )
            if current_inflight+demand.inflight>capacity.usable_inflight:
                raise ReservationConflict("worker inflight capacity exhausted")
            if current_weight+demand.weight>capacity.usable_weight:
                raise ReservationConflict("worker weight capacity exhausted")
            self._serial+=1
            now=self._clock()
            token=hashlib.sha256(f"{worker.key}:{self._serial}:{now}".encode()).hexdigest()[:32]
            reservation=CapacityReservation(token,worker,demand,now,now+ttl_seconds)
            self._items[token]=reservation
            return reservation

    def release(self,reservation:CapacityReservation)->bool:
        with self._lock:
            current=self._items.get(reservation.reservation_id)
            if current!=reservation:return False
            del self._items[reservation.reservation_id]
            return True

    def require(self,reservation:CapacityReservation)->CapacityReservation:
        self.workers.require_current(reservation.worker)
        with self._lock:
            self._prune()
            current=self._items.get(reservation.reservation_id)
            if current!=reservation:raise ReservationConflict("reservation is stale or expired")
            return current

    def snapshot(self)->tuple[CapacityReservation,...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._items.values(),key=lambda x:x.reservation_id))
