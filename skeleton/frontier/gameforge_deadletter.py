"""Bounded dead-letter queue for fail-safe rejection handling."""
from collections import deque
class DeadLetterQueue:
    def __init__(self,capacity:int=256):
        if capacity<=0: raise ValueError("capacity must be positive")
        self._q=deque(maxlen=capacity); self._cap=capacity
    def push(self,item)->bool:
        if len(self._q)>=self._cap: return False
        self._q.append(item); return True
    def drain(self)->list: items=list(self._q); self._q.clear(); return items
    def __len__(self): return len(self._q)
