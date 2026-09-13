"""Bounded sliding-window counter."""
from collections import deque
class SlidingWindow:
    def __init__(self,capacity:int):
        if capacity<=0: raise ValueError("capacity must be positive")
        self._q=deque(maxlen=capacity); self._cap=capacity
    def add(self,value)->None: self._q.append(value)
    def values(self)->tuple: return tuple(self._q)
    def __len__(self): return len(self._q)
