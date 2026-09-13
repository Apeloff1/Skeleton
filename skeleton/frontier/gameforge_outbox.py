"""Bounded outbox contract for durable handoff without a persistence dependency."""
from __future__ import annotations
from collections import deque
from threading import Lock
from typing import Generic, TypeVar
T=TypeVar("T")
class BoundedOutbox(Generic[T]):
    def __init__(self, capacity:int=1024)->None:
        if capacity<=0: raise ValueError("capacity must be positive")
        self._q=deque(maxlen=capacity); self._cap=capacity; self._lock=Lock()
    def append(self,item:T)->bool:
        with self._lock:
            if len(self._q)>=self._cap: return False
            self._q.append(item); return True
    def pop(self)->T|None:
        with self._lock: return self._q.popleft() if self._q else None
    def __len__(self)->int:
        with self._lock: return len(self._q)
