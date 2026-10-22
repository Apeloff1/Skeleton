"""
Operational Rate Limiter. Token-bucket style bound by clipped-G and CAS.
Fills the rate control gap. Fail-closed.
"""
from typing import Dict
import time

class RateLimiter:
    def __init__(self, capacity: int = 60):
        self.capacity = capacity
        self.tokens = capacity
        self.last = time.time()

    def allow(self, cas: str) -> Dict:
        now = time.time()
        elapsed = now - self.last
        self.tokens = min(self.capacity, self.tokens + elapsed)
        self.last = now
        if self.tokens >= 1 and len(cas) >= 16:
            self.tokens -= 1
            return {"allowed": True, "remaining": int(self.tokens)}
        return {"allowed": False, "remaining": int(self.tokens)}
