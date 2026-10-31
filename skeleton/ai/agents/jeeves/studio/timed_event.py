"""Timed event. Triggers after delay."""
from typing import Any, Dict
class TimedEvent:
    def __init__(self, delay: float, kind: str):
        self.delay = delay
        self.kind = kind
        self.elapsed = 0.0
    def tick(self, dt: float) -> bool:
        self.elapsed += dt
        return self.elapsed >= self.delay
