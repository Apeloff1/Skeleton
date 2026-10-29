"""Performance profiler.
Tracks frame times and optical processing cost.
"""
from __future__ import annotations
from typing import Any, Dict, List

class PerformanceProfiler:
    def __init__(self):
        self.samples: List[float] = []
    def sample(self, ms: float) -> None:
        self.samples.append(ms)
    def summary(self) -> Dict[str, Any]:
        if not self.samples:
            return {"avg_ms": 0, "max_ms": 0, "count": 0}
        return {
            "avg_ms": round(sum(self.samples) / len(self.samples), 2),
            "max_ms": round(max(self.samples), 2),
            "count": len(self.samples),
        }
