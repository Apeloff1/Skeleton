"""Explicit maintenance windows for worker admission and draining."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class MaintenanceWindow:
    worker_id:str
    starts_at:float
    ends_at:float
    reason:str=""
    drain:bool=True

    def __post_init__(self)->None:
        if not self.worker_id:raise ValueError("worker_id is required")
        if self.starts_at<0 or self.ends_at<=self.starts_at:
            raise ValueError("invalid maintenance interval")
        if len(self.reason)>512:raise ValueError("maintenance reason too long")

    def active_at(self,now:float)->bool:
        return self.starts_at<=now<self.ends_at


class WorkerMaintenance:
    def __init__(self,*,clock:Callable[[],float]=time.monotonic,max_windows:int=10000)->None:
        self._clock=clock
        self.max_windows=max_windows
        self._items:list[MaintenanceWindow]=[]
        self._lock=threading.RLock()

    def add(
        self,
        worker_id:str,
        *,
        delay_seconds:float=0.0,
        duration_seconds:float,
        reason:str="",
        drain:bool=True,
    )->MaintenanceWindow:
        if delay_seconds<0 or duration_seconds<=0:
            raise ValueError("invalid maintenance timing")
        with self._lock:
            if len(self._items)>=self.max_windows:
                raise RuntimeError("maintenance window capacity exhausted")
            now=self._clock()
            item=MaintenanceWindow(worker_id,now+delay_seconds,now+delay_seconds+duration_seconds,reason,drain)
            self._items.append(item)
            return item

    def active(self,worker_id:str,*,at:float|None=None)->tuple[MaintenanceWindow,...]:
        now=self._clock() if at is None else at
        with self._lock:
            return tuple(item for item in self._items if item.worker_id==worker_id and item.active_at(now))

    def available(self,worker_id:str)->bool:
        return not self.active(worker_id)

    def prune(self)->int:
        now=self._clock()
        with self._lock:
            before=len(self._items)
            self._items=[item for item in self._items if item.ends_at>now]
            return before-len(self._items)

    def snapshot(self)->tuple[MaintenanceWindow,...]:
        with self._lock:return tuple(sorted(self._items,key=lambda x:(x.starts_at,x.worker_id)))
