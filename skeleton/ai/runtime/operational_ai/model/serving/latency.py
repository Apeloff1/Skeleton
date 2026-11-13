"""Explicit latency histogram with bounded sample memory."""
from __future__ import annotations
from collections import deque
from threading import Lock
from .contracts import ServingError

class Latency:
    def __init__(self,size:int=1024):
        if not 1<=size<=100000:raise ServingError('invalid latency window')
        self._items=deque(maxlen=size);self._lock=Lock()
    def record(self,ns:int)->None:
        if type(ns) is not int or not 0<=ns<=10**15:raise ServingError('invalid latency')
        with self._lock:self._items.append(ns)
    def percentile(self,percent:float)->int|None:
        if not 0<=percent<=100:raise ServingError('invalid percentile')
        with self._lock:vals=sorted(self._items)
        if not vals:return None
        return vals[max(0,min(len(vals)-1,int((len(vals)-1)*percent/100)))]
