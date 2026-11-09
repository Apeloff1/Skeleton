"""Weighted concurrency permits for shell execution admission."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class ConcurrencyPermit:
    permit_id:int
    weight:int
    owner:str
    acquired_at:float


@dataclass(frozen=True)
class ConcurrencySnapshot:
    capacity:int
    used:int
    permits:int

    @property
    def available(self)->int:return max(0,self.capacity-self.used)

    def to_dict(self)->dict[str,int]:
        return {"capacity":self.capacity,"used":self.used,"available":self.available,"permits":self.permits}


class ConcurrencyLimit(RuntimeError):pass


class WeightedConcurrency:
    """Thread-safe explicit weighted semaphore with nonblocking admission."""

    def __init__(
        self,
        capacity:int,
        *,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        if isinstance(capacity,bool) or not isinstance(capacity,int) or capacity<=0:
            raise ValueError("capacity must be a positive integer")
        self.capacity=capacity
        self._clock=clock
        self._used=0
        self._serial=0
        self._permits:dict[int,ConcurrencyPermit]={}
        self._condition=threading.Condition(threading.RLock())

    def try_acquire(self,weight:int=1,*,owner:str="anonymous")->ConcurrencyPermit|None:
        if isinstance(weight,bool) or not isinstance(weight,int) or weight<=0:
            raise ValueError("weight must be a positive integer")
        if weight>self.capacity:raise ConcurrencyLimit("requested weight exceeds total capacity")
        if not owner or len(owner)>256:raise ValueError("invalid concurrency owner")
        with self._condition:
            if self._used+weight>self.capacity:return None
            self._serial+=1
            permit=ConcurrencyPermit(self._serial,weight,owner,self._clock())
            self._permits[permit.permit_id]=permit
            self._used+=weight
            return permit

    def acquire(
        self,
        weight:int=1,
        *,
        owner:str="anonymous",
        timeout:float|None=None,
    )->ConcurrencyPermit:
        if timeout is not None and timeout<0:raise ValueError("timeout may not be negative")
        deadline=None if timeout is None else self._clock()+timeout
        with self._condition:
            while True:
                permit=self.try_acquire(weight,owner=owner)
                if permit is not None:return permit
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining=deadline-self._clock()
                if remaining<=0:raise ConcurrencyLimit("concurrency acquisition timed out")
                self._condition.wait(remaining)

    def release(self,permit:ConcurrencyPermit)->bool:
        with self._condition:
            current=self._permits.get(permit.permit_id)
            if current!=permit:return False
            del self._permits[permit.permit_id]
            self._used-=permit.weight
            self._condition.notify_all()
            return True

    def require(self,permit:ConcurrencyPermit)->ConcurrencyPermit:
        with self._condition:
            current=self._permits.get(permit.permit_id)
            if current!=permit:raise ConcurrencyLimit("concurrency permit is stale")
            return current

    def by_owner(self,owner:str)->tuple[ConcurrencyPermit,...]:
        with self._condition:
            return tuple(sorted((item for item in self._permits.values() if item.owner==owner),key=lambda x:x.permit_id))

    def snapshot(self)->ConcurrencySnapshot:
        with self._condition:return ConcurrencySnapshot(self.capacity,self._used,len(self._permits))
