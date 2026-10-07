"""Bounded synchronous event stream for worker-plane state changes."""

from __future__ import annotations

from dataclasses import dataclass,field
import threading
import time
from types import MappingProxyType
from typing import Callable,Mapping,Protocol


@dataclass(frozen=True)
class WorkerEvent:
    sequence:int
    kind:str
    worker_id:str
    generation:int
    observed_at:float
    data:Mapping[str,object]=field(default_factory=dict)

    def __post_init__(self)->None:
        if self.sequence<=0:
            raise ValueError("event sequence must be positive")
        if not self.kind or len(self.kind)>128:
            raise ValueError("invalid event kind")
        if len(self.worker_id)>128:
            raise ValueError("worker_id too long")
        if self.generation<0:
            raise ValueError("generation may not be negative")
        payload=dict(self.data)
        if len(payload)>64:
            raise ValueError("worker event data has too many fields")
        object.__setattr__(self,"data",MappingProxyType(payload))

    def to_dict(self)->dict[str,object]:
        return {
            "sequence":self.sequence,
            "kind":self.kind,
            "worker_id":self.worker_id,
            "generation":self.generation,
            "observed_at":self.observed_at,
            "data":dict(self.data),
        }


class WorkerEventSink(Protocol):
    def __call__(self,event:WorkerEvent)->None: ...


class WorkerEvents:
    def __init__(self,*,max_events:int=10000,clock:Callable[[],float]=time.monotonic)->None:
        if max_events<=0:
            raise ValueError("max_events must be positive")
        self.max_events=max_events
        self._clock=clock
        self._events:list[WorkerEvent]=[]
        self._sinks:list[WorkerEventSink]=[]
        self._sequence=0
        self._lock=threading.RLock()

    def subscribe(self,sink:WorkerEventSink)->None:
        with self._lock:
            if sink in self._sinks:
                return
            self._sinks.append(sink)

    def unsubscribe(self,sink:WorkerEventSink)->bool:
        with self._lock:
            try:self._sinks.remove(sink)
            except ValueError:return False
            return True

    def emit(
        self,
        kind:str,
        *,
        worker_id:str="",
        generation:int=0,
        data:Mapping[str,object]|None=None,
    )->WorkerEvent:
        with self._lock:
            self._sequence+=1
            event=WorkerEvent(self._sequence,kind,worker_id,generation,self._clock(),data or {})
            self._events.append(event)
            if len(self._events)>self.max_events:
                del self._events[:len(self._events)-self.max_events]
            sinks=tuple(self._sinks)
        for sink in sinks:
            try:sink(event)
            except Exception:
                # Event observers cannot break worker execution.
                continue
        return event

    def events(
        self,
        *,
        kind:str|None=None,
        worker_id:str|None=None,
        after_sequence:int=0,
    )->tuple[WorkerEvent,...]:
        with self._lock:
            return tuple(
                event for event in self._events
                if event.sequence>after_sequence
                and (kind is None or event.kind==kind)
                and (worker_id is None or event.worker_id==worker_id)
            )

    def tail(self,count:int=100)->tuple[WorkerEvent,...]:
        if count<=0: raise ValueError("count must be positive")
        with self._lock:return tuple(self._events[-count:])
