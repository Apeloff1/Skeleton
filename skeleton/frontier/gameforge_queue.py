"""Bounded FIFO queue with explicit backpressure."""
from collections import deque
class BoundedQueue:
 def __init__(self,capacity):
  if capacity<=0: raise ValueError("capacity must be positive")
  self.capacity=capacity; self._items=deque()
 def push(self,item):
  if len(self._items)>=self.capacity: return False
  self._items.append(item); return True
 def pop(self): return self._items.popleft() if self._items else None
 def __len__(self): return len(self._items)
