"""Explicit delayed-work schedule without background timers."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import threading
import time
from typing import Callable

from skeleton.shells.runner import ShellCommand


@dataclass(frozen=True)
class ScheduledWork:
    schedule_id:str
    command:ShellCommand
    ready_at:float
    priority:int
    sequence:int
    principal:str="default"

    def __post_init__(self)->None:
        if (
            not isinstance(self.schedule_id,str)
            or not self.schedule_id.strip()
            or len(self.schedule_id)>256
            or "\x00" in self.schedule_id
        ):
            raise ValueError("invalid schedule_id")
        if not isinstance(self.command,ShellCommand):
            raise TypeError("command must be ShellCommand")
        if (
            isinstance(self.ready_at,bool)
            or not isinstance(self.ready_at,(int,float))
            or not math.isfinite(float(self.ready_at))
            or float(self.ready_at)<0.0
        ):
            raise ValueError("ready_at must be finite and non-negative")
        if isinstance(self.priority,bool) or not isinstance(self.priority,int):
            raise ValueError("priority must be an integer")
        if isinstance(self.sequence,bool) or not isinstance(self.sequence,int) or self.sequence<=0:
            raise ValueError("sequence must be a positive integer")
        if (
            not isinstance(self.principal,str)
            or not self.principal.strip()
            or len(self.principal)>256
            or "\x00" in self.principal
        ):
            raise ValueError("invalid schedule principal")


class WorkerSchedule:
    """Heap-backed schedule polled explicitly by the control plane."""

    def __init__(self,*,clock:Callable[[],float]=time.monotonic,max_items:int=10000)->None:
        if isinstance(max_items,bool) or not isinstance(max_items,int) or max_items<=0:
            raise ValueError("max_items must be a positive integer")
        self._clock=clock
        self.max_items=max_items
        self._heap:list[tuple[float,int,int,str]]=[]
        self._items:dict[str,ScheduledWork]={}
        self._sequence=0
        self._lock=threading.RLock()

    def schedule(
        self,
        schedule_id:str,
        command:ShellCommand,
        *,
        delay_seconds:float=0.0,
        priority:int=100,
        principal:str="default",
    )->ScheduledWork:
        if (
            isinstance(delay_seconds,bool)
            or not isinstance(delay_seconds,(int,float))
            or not math.isfinite(float(delay_seconds))
            or float(delay_seconds)<0.0
        ):
            raise ValueError("delay_seconds must be finite and non-negative")
        if isinstance(priority,bool) or not isinstance(priority,int):
            raise ValueError("priority must be an integer")
        with self._lock:
            if schedule_id in self._items:
                raise RuntimeError("schedule_id already exists")
            if len(self._items)>=self.max_items:
                raise RuntimeError("worker schedule capacity exhausted")
            self._sequence+=1
            item=ScheduledWork(
                schedule_id,command,self._clock()+delay_seconds,priority,self._sequence,principal
            )
            self._items[schedule_id]=item
            heapq.heappush(self._heap,(item.ready_at,item.priority,item.sequence,item.schedule_id))
            return item

    def cancel(self,schedule_id:str)->bool:
        with self._lock:
            return self._items.pop(schedule_id,None) is not None

    def pop_ready(self,*,limit:int=100)->tuple[ScheduledWork,...]:
        if isinstance(limit,bool) or not isinstance(limit,int) or limit<=0:
            raise ValueError("limit must be a positive integer")
        now=self._clock()
        result=[]
        with self._lock:
            while self._heap and len(result)<limit:
                ready_at,_,_,schedule_id=self._heap[0]
                if ready_at>now: break
                heapq.heappop(self._heap)
                item=self._items.pop(schedule_id,None)
                if item is None: continue
                result.append(item)
            return tuple(result)

    def next_ready_at(self)->float|None:
        with self._lock:
            while self._heap and self._heap[0][3] not in self._items:
                heapq.heappop(self._heap)
            return None if not self._heap else self._heap[0][0]

    def snapshot(self)->tuple[ScheduledWork,...]:
        with self._lock:
            return tuple(sorted(self._items.values(),key=lambda x:(x.ready_at,x.priority,x.sequence)))
