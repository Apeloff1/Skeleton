"""Cooldown tracker. Ability timers."""
from typing import Any, Dict
class CooldownTracker:
    def __init__(self):
        self.cds: Dict[str, float] = {}
    def start(self, name: str, duration: float) -> None:
        self.cds[name] = duration
    def tick(self, dt: float) -> None:
        for k in list(self.cds):
            self.cds[k] -= dt
            if self.cds[k] <= 0: del self.cds[k]
    def ready(self, name: str) -> bool:
        return name not in self.cds
