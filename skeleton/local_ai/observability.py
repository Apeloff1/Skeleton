"""
Observability hooks for local AI. Metrics, traces, and clipped-G stamps.
"""
from typing import Dict

class Observability:
    def __init__(self):
        self.metrics: Dict[str, float] = {}

    def record(self, name: str, value: float) -> None:
        self.metrics[name] = value

    def stamp(self) -> Dict:
        return {"metrics": self.metrics.copy(), "obs": "local"}
