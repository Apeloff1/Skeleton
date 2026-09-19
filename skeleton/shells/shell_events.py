"""Bounded synchronous event stream for shell-plane control events."""

from __future__ import annotations

from dataclasses import dataclass,field
import threading
import time
from types import MappingProxyType
from typing import Callable,Mapping,Protocol


@dataclass(frozen=True)
class ShellEvent:
    sequence:int
    kind:str
    observed_at:float
    correlation_id:str=""
    command:str=""
    data:Mapping[str,object]=field(default_factory=dict)

    def __post_init__(self)->None:
        if self.sequence<=0:raise ValueError("event sequence must be positive")
        if not self.kind or len(self.kind)>128:raise ValueError("invalid shell event kind")
        if len(self.correlation_id)>160 or len(self.command)>128:raise ValueError("shell event identity too long")
        payload=dict(self.data)
        if len(payload)>64:raise ValueError("shell event data has too many fields")
        object.__setattr__(self,"data",MappingProxyType(payload))

    def to_dict(self)->dict[str,object]:
        return {
            "sequence":self.sequence,"kind":self.kind,"observed_at":self.observed_at,
            "correlation_id":self.correlation_id,"command":self.command,"data":dict(self.data),
        }


class ShellEventSink(Protocol):
    def __call__(self,event:ShellEvent)->None: ...


class ShellEvents:
    def __init__(self,*,max_events:int=10000,clock:Callable[[],float]=time.monotonic)->None:
        if max_events<=0:raise ValueError("max_events must be positive")
        self.max_events=max_events
        self._clock=clock
        self._sequence=0
        self._events:list[ShellEvent]=[]
        self._sinks:list[ShellEventSink]=[]
        self._lock=threading.RLock()

    def subscribe(self,sink:ShellEventSink)->None:
        with self._lock:
            if sink not in self._sinks:self._sinks.append(sink)

    def unsubscribe(self,sink:ShellEventSink)->bool:
        with self._lock:
            try:self._sinks.remove(sink)
            except ValueError:return False
            return True

    def emit(
        self,
        kind:str,
        *,
        correlation_id:str="",
        command:str="",
        data:Mapping[str,object]|None=None,
    )->ShellEvent:
        with self._lock:
            self._sequence+=1
            event=ShellEvent(self._sequence,kind,self._clock(),correlation_id,command,data or {})
            self._events.append(event)
            if len(self._events)>self.max_events:
                del self._events[:len(self._events)-self.max_events]
            sinks=tuple(self._sinks)
        for sink in sinks:
            try:sink(event)
            except Exception:continue
        return event

    def query(
        self,
        *,
        kind:str|None=None,
        correlation_id:str|None=None,
        command:str|None=None,
        after_sequence:int=0,
    )->tuple[ShellEvent,...]:
        with self._lock:
            return tuple(
                event for event in self._events
                if event.sequence>after_sequence
                and (kind is None or event.kind==kind)
                and (correlation_id is None or event.correlation_id==correlation_id)
                and (command is None or event.command==command)
            )

    def tail(self,count:int=100)->tuple[ShellEvent,...]:
        if count<=0:raise ValueError("count must be positive")
        with self._lock:return tuple(self._events[-count:])
