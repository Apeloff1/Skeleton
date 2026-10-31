"""Threat meter. Tracks player threat for AI decisions."""
from typing import Any, Dict
class ThreatMeter:
    def __init__(self):
        self.threat = 0.0
    def add(self, amount: float) -> None:
        self.threat = min(100.0, self.threat + amount)
    def decay(self, dt: float) -> None:
        self.threat = max(0.0, self.threat - 5.0 * dt)
