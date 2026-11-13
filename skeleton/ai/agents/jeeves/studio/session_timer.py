"""Session timer.
Tracks elapsed time and enforces optional time limits for daily challenges.
"""
from __future__ import annotations
from typing import Any, Dict
import time

class SessionTimer:
    def __init__(self, limit_seconds: int = 0):
        self.start = time.time()
        self.limit = limit_seconds
    def elapsed(self) -> float:
        return time.time() - self.start
    def remaining(self) -> float:
        if self.limit <= 0:
            return float("inf")
        return max(0.0, self.limit - self.elapsed())
    def expired(self) -> bool:
        return self.limit > 0 and self.remaining() <= 0
    def status(self) -> Dict[str, Any]:
        return {"elapsed": round(self.elapsed(), 1), "remaining": self.remaining(), "expired": self.expired()}
