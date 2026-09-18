"""Deterministic active/standby failover groups for shell workers."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable,Sequence

from skeleton.shells.worker_heartbeat import HeartbeatRegistry,WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry


@dataclass(frozen=True)
class FailoverGroup:
    group_id:str
    members:tuple[str,...]
    active_worker_id:str
    revision:int=1

    def __post_init__(self)->None:
        if not self.group_id or len(self.group_id)>128:
            raise ValueError("invalid failover group_id")
        if not self.members:
            raise ValueError("failover group requires members")
        if len(set(self.members))!=len(self.members):
            raise ValueError("failover members must be unique")
        if self.active_worker_id not in self.members:
            raise ValueError("active worker must be a group member")

    def to_dict(self)->dict[str,object]:
        return {
            "group_id":self.group_id,
            "members":list(self.members),
            "active_worker_id":self.active_worker_id,
            "revision":self.revision,
        }


@dataclass(frozen=True)
class FailoverDecision:
    changed:bool
    previous_worker_id:str
    active_worker_id:str
    reason:str
    revision:int

    def to_dict(self)->dict[str,object]:
        return {
            "changed":self.changed,
            "previous_worker_id":self.previous_worker_id,
            "active_worker_id":self.active_worker_id,
            "reason":self.reason,
            "revision":self.revision,
        }


class WorkerFailover:
    def __init__(
        self,
        workers:WorkerRegistry,
        heartbeats:HeartbeatRegistry,
        *,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.workers=workers
        self.heartbeats=heartbeats
        self._clock=clock
        self._groups:dict[str,FailoverGroup]={}
        self._lock=threading.RLock()

    def create(self,group_id:str,members:Sequence[WorkerIdentity],*,active_worker_id:str|None=None)->FailoverGroup:
        if not members:
            raise ValueError("members are required")
        for identity in members:
            self.workers.require_current(identity)
        ids=tuple(identity.worker_id for identity in members)
        active=active_worker_id or ids[0]
        group=FailoverGroup(group_id,ids,active)
        with self._lock:
            if group_id in self._groups:
                raise RuntimeError("failover group already exists")
            self._groups[group_id]=group
            return group

    def evaluate(self,group_id:str)->FailoverDecision:
        with self._lock:
            group=self._groups[group_id]
            active_registration=self.workers.find(group.active_worker_id)
            active_healthy=False
            if active_registration is not None and active_registration.enabled:
                active_healthy=self.heartbeats.liveness(active_registration.identity).liveness is WorkerLiveness.HEALTHY
            if active_healthy:
                return FailoverDecision(False,group.active_worker_id,group.active_worker_id,"active worker is healthy",group.revision)

            replacement=None
            for worker_id in group.members:
                if worker_id==group.active_worker_id:
                    continue
                registration=self.workers.find(worker_id)
                if registration is None or not registration.enabled:
                    continue
                if self.heartbeats.liveness(registration.identity).liveness is WorkerLiveness.HEALTHY:
                    replacement=worker_id
                    break
            if replacement is None:
                return FailoverDecision(False,group.active_worker_id,group.active_worker_id,"no healthy standby",group.revision)

            updated=FailoverGroup(
                group.group_id,
                group.members,
                replacement,
                revision=group.revision+1,
            )
            self._groups[group_id]=updated
            return FailoverDecision(True,group.active_worker_id,replacement,"promoted healthy standby",updated.revision)

    def get(self,group_id:str)->FailoverGroup:
        with self._lock:
            return self._groups[group_id]

    def snapshot(self)->tuple[FailoverGroup,...]:
        with self._lock:
            return tuple(sorted(self._groups.values(),key=lambda item:item.group_id))
