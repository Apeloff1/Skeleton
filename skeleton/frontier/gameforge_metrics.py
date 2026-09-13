"""Tiny bounded counters for resilience contracts."""
from __future__ import annotations
from threading import Lock
class CounterSet:
    def __init__(self,names:tuple[str,...]):
        if len(set(names))!=len(names): raise ValueError("duplicate counter")
        self._values={n:0 for n in names}; self._lock=Lock()
    def inc(self,name:str,amount:int=1)->int:
        if amount<0: raise ValueError("amount must be non-negative")
        with self._lock:
            if name not in self._values: raise KeyError(name)
            self._values[name]+=amount; return self._values[name]
    def snapshot(self)->dict[str,int]:
        with self._lock: return dict(self._values)
