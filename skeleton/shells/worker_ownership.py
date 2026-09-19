"""Generation-safe ownership epochs for worker-controlled resources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable

from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry


@dataclass(frozen=True)
class OwnershipEpoch:
    resource_id:str
    worker:WorkerIdentity
    epoch:int
    token:str
    acquired_at:float
    expires_at:float

    def __post_init__(self)->None:
        if not self.resource_id or len(self.resource_id)>256:raise ValueError("invalid resource_id")
        if self.epoch<=0:raise ValueError("epoch must be positive")
        if self.expires_at<=self.acquired_at:raise ValueError("ownership expiry must follow acquisition")


class OwnershipConflict(RuntimeError):pass


class WorkerOwnership:
    """One current owner per resource with monotonic epochs."""

    def __init__(
        self,
        workers:WorkerRegistry,
        *,
        clock:Callable[[],float]=time.monotonic,
        max_resources:int=10000,
    )->None:
        self.workers=workers
        self._clock=clock
        self.max_resources=max_resources
        self._items:dict[str,OwnershipEpoch]={}
        self._epochs:dict[str,int]={}
        self._lock=threading.RLock()

    def _prune(self)->None:
        now=self._clock()
        for key in [key for key,value in self._items.items() if value.expires_at<=now]:
            del self._items[key]

    def acquire(
        self,
        resource_id:str,
        worker:WorkerIdentity,
        *,
        ttl_seconds:float=30.0,
    )->OwnershipEpoch:
        if ttl_seconds<=0:raise ValueError("ttl_seconds must be positive")
        self.workers.require_current(worker)
        with self._lock:
            self._prune()
            if resource_id in self._items:raise OwnershipConflict("resource already owned")
            if len(self._items)>=self.max_resources:raise OwnershipConflict("ownership capacity exhausted")
            epoch=self._epochs.get(resource_id,0)+1
            self._epochs[resource_id]=epoch
            now=self._clock()
            token=hashlib.sha256(f"{resource_id}:{worker.key}:{epoch}:{now}".encode()).hexdigest()[:32]
            record=OwnershipEpoch(resource_id,worker,epoch,token,now,now+ttl_seconds)
            self._items[resource_id]=record
            return record

    def renew(self,ownership:OwnershipEpoch,*,ttl_seconds:float=30.0)->OwnershipEpoch:
        if ttl_seconds<=0:raise ValueError("ttl_seconds must be positive")
        self.workers.require_current(ownership.worker)
        with self._lock:
            self._prune()
            current=self._items.get(ownership.resource_id)
            if current!=ownership:raise OwnershipConflict("ownership token is stale")
            now=self._clock()
            renewed=OwnershipEpoch(
                current.resource_id,current.worker,current.epoch,current.token,
                current.acquired_at,now+ttl_seconds,
            )
            self._items[current.resource_id]=renewed
            return renewed

    def release(self,ownership:OwnershipEpoch)->bool:
        with self._lock:
            current=self._items.get(ownership.resource_id)
            if current!=ownership:return False
            del self._items[ownership.resource_id]
            return True

    def require(self,ownership:OwnershipEpoch)->OwnershipEpoch:
        self.workers.require_current(ownership.worker)
        with self._lock:
            self._prune()
            current=self._items.get(ownership.resource_id)
            if current!=ownership:raise OwnershipConflict("ownership token is stale or expired")
            return current

    def current(self,resource_id:str)->OwnershipEpoch|None:
        with self._lock:
            self._prune()
            return self._items.get(resource_id)

    def snapshot(self)->tuple[OwnershipEpoch,...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._items.values(),key=lambda item:item.resource_id))
