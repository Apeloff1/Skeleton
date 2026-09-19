"""Low-cardinality trace spans for shell orchestration."""

from __future__ import annotations

from dataclasses import dataclass,field
import hashlib
import threading
import time
from types import MappingProxyType
from typing import Callable,Mapping

@dataclass(frozen=True)
class ShellSpan:
    span_id:str
    trace_id:str
    parent_span_id:str
    name:str
    started_at:float
    finished_at:float|None=None
    attributes:Mapping[str,str]=field(default_factory=dict)
    error_type:str=""

    def __post_init__(self)->None:
        if not self.span_id or not self.trace_id:
            raise ValueError("span_id and trace_id are required")
        if not self.name or len(self.name)>128:
            raise ValueError("invalid span name")
        attrs=dict(self.attributes)
        if len(attrs)>64:
            raise ValueError("too many span attributes")
        if any(not isinstance(k,str) or not isinstance(v,str) or len(k)>128 or len(v)>512 for k,v in attrs.items()):
            raise ValueError("invalid span attribute")
        object.__setattr__(self,"attributes",MappingProxyType(attrs))

    @property
    def finished(self)->bool:
        return self.finished_at is not None

    @property
    def duration_seconds(self)->float|None:
        if self.finished_at is None:
            return None
        return max(0.0,self.finished_at-self.started_at)

    def to_dict(self)->dict[str,object]:
        return {
            "span_id":self.span_id,
            "trace_id":self.trace_id,
            "parent_span_id":self.parent_span_id,
            "name":self.name,
            "started_at":self.started_at,
            "finished_at":self.finished_at,
            "duration_seconds":self.duration_seconds,
            "attributes":dict(self.attributes),
            "error_type":self.error_type,
        }

class ShellTracer:
    def __init__(self,*,max_spans:int=10000,clock:Callable[[],float]=time.monotonic)->None:
        if max_spans<=0:
            raise ValueError("max_spans must be positive")
        self.max_spans=max_spans
        self._clock=clock
        self._spans:dict[str,ShellSpan]={}
        self._order:list[str]=[]
        self._serial=0
        self._lock=threading.RLock()

    def start(
        self,
        name:str,
        *,
        trace_id:str,
        parent_span_id:str="",
        attributes:Mapping[str,str]|None=None,
    )->ShellSpan:
        with self._lock:
            self._serial+=1
            raw=f"{trace_id}:{name}:{self._serial}:{self._clock()}"
            span_id=hashlib.sha256(raw.encode()).hexdigest()[:24]
            span=ShellSpan(
                span_id,trace_id,parent_span_id,name,self._clock(),
                attributes=attributes or {},
            )
            self._spans[span_id]=span
            self._order.append(span_id)
            if len(self._order)>self.max_spans:
                evicted=self._order.pop(0)
                self._spans.pop(evicted,None)
            return span

    def finish(self,span:ShellSpan,*,error_type:str="")->ShellSpan:
        with self._lock:
            current=self._spans.get(span.span_id)
            if current!=span:
                raise RuntimeError("span is stale or unknown")
            if current.finished:
                raise RuntimeError("span already finished")
            finished=ShellSpan(
                current.span_id,current.trace_id,current.parent_span_id,current.name,
                current.started_at,self._clock(),current.attributes,error_type,
            )
            self._spans[span.span_id]=finished
            return finished

    def trace(self,trace_id:str)->tuple[ShellSpan,...]:
        with self._lock:
            return tuple(
                self._spans[span_id] for span_id in self._order
                if self._spans[span_id].trace_id==trace_id
            )

    def snapshot(self)->tuple[ShellSpan,...]:
        with self._lock:
            return tuple(self._spans[span_id] for span_id in self._order)
