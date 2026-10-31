"""
Operational Metrics Collector. Aggregates G, mass, token counts, latency proxies, and seam usage.
Fills the metrics gap.
"""
from typing import Dict
from collections import defaultdict

class MetricsCollector:
    def __init__(self):
        self.counters = defaultdict(int)
        self.gauges = {}

    def inc(self, name: str, n: int = 1):
        self.counters[name] += n

    def set(self, name: str, value: float):
        self.gauges[name] = value

    def snapshot(self) -> Dict:
        return {"counters": dict(self.counters), "gauges": self.gauges.copy()}
