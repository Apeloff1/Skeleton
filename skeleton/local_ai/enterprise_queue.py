"""
Enterprise Request Queue. Priority queue, backpressure, and clipped-G aware scheduling.
"""
from typing import Dict, List
from collections import deque
from .clipped_g_observer import ClippedGObserver

class EnterpriseQueue:
    def __init__(self, max_size: int = 100):
        self.queue = deque()
        self.max_size = max_size
        self.observer = ClippedGObserver()

    def enqueue(self, item: Dict, priority: int = 0) -> bool:
        if len(self.queue) >= self.max_size:
            return False
        self.queue.append((priority, item))
        self.queue = deque(sorted(self.queue, key=lambda x: -x[0]))
        return True

    def dequeue(self) -> Dict:
        if not self.queue:
            return {}
        _, item = self.queue.popleft()
        self.observer.observe({"delta": 0.01, "mass": 1.01})
        return item

    def size(self) -> int:
        return len(self.queue)
