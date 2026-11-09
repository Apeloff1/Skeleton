"""Short-lived execution admission leases before process dispatch."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable

@dataclass(frozen=True)
class AdmissionLease:
    lease_id:str
    key:str
    principal:str
    command:str
    acquired_at:float
    expires_at:float
    revision:int=1

class AdmissionLeaseConflict(RuntimeError):
    pass

class AdmissionLeases:
    """One current lease per admission key with TTL and revision protection."""

    def __init__(self,*,max_leases:int=10000,clock:Callable[[],float]=time.monotonic)->None:
        if max_leases<=0:
            raise ValueError("max_leases must be positive")
        self.max_leases=max_leases
        self._clock=clock
        self._items:dict[str,AdmissionLease]={}
        self._serial=0
        self._lock=threading.RLock()

    def _prune(self)->None:
        now=self._clock()
        for key in [key for key,value in self._items.items() if value.expires_at<=now]:
            del self._items[key]

    def acquire(self,key:str,*,principal:str,command:str,ttl_seconds:float=30.0)->AdmissionLease:
        if not key or len(key)>256:
            raise ValueError("invalid admission lease key")
        if not principal or len(principal)>256:
            raise ValueError("invalid principal")
        if not command or len(command)>128:
            raise ValueError("invalid command")
        if ttl_seconds<=0:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._prune()
            if key in self._items:
                raise AdmissionLeaseConflict("admission lease already held")
            if len(self._items)>=self.max_leases:
                raise AdmissionLeaseConflict("admission lease capacity exhausted")
            self._serial+=1
            now=self._clock()
            token=hashlib.sha256(f"{key}:{principal}:{command}:{self._serial}:{now}".encode()).hexdigest()[:32]
            lease=AdmissionLease(token,key,principal,command,now,now+ttl_seconds)
            self._items[key]=lease
            return lease

    def renew(self,lease:AdmissionLease,*,ttl_seconds:float=30.0)->AdmissionLease:
        if ttl_seconds<=0:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._prune()
            current=self._items.get(lease.key)
            if current!=lease:
                raise AdmissionLeaseConflict("admission lease is stale")
            now=self._clock()
            renewed=AdmissionLease(
                current.lease_id,current.key,current.principal,current.command,
                current.acquired_at,now+ttl_seconds,current.revision+1,
            )
            self._items[current.key]=renewed
            return renewed

    def release(self,lease:AdmissionLease)->bool:
        with self._lock:
            current=self._items.get(lease.key)
            if current!=lease:
                return False
            del self._items[lease.key]
            return True

    def require(self,lease:AdmissionLease)->AdmissionLease:
        with self._lock:
            self._prune()
            current=self._items.get(lease.key)
            if current!=lease:
                raise AdmissionLeaseConflict("admission lease is stale or expired")
            return current

    def snapshot(self)->tuple[AdmissionLease,...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._items.values(),key=lambda item:item.key))
