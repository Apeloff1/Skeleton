"""
Enterprise SLA Tracker. Latency percentiles, success rate, and clipped-G compliance.
"""
from typing import Dict, List
import statistics

class EnterpriseSLA:
    def __init__(self):
        self.latencies: List[float] = []
        self.successes = 0
        self.failures = 0

    def record(self, latency_ms: float, success: bool) -> None:
        self.latencies.append(latency_ms)
        if success:
            self.successes += 1
        else:
            self.failures += 1

    def report(self) -> Dict:
        total = self.successes + self.failures
        p99 = sorted(self.latencies)[int(0.99 * len(self.latencies))] if self.latencies else 0
        return {
            "p99_ms": p99,
            "success_rate": self.successes / total if total else 1.0,
            "samples": len(self.latencies),
            "sla_met": p99 < 500 and (self.successes / total if total else 1.0) > 0.99
        }
