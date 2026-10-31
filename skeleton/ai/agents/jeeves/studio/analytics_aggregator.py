"""Analytics aggregator.
Rolls up telemetry and summaries into session metrics for distillation.
"""
from __future__ import annotations
from typing import Any, Dict, List

class AnalyticsAggregator:
    def __init__(self):
        self.sessions: List[Dict[str, Any]] = []
    def add(self, summary: Dict[str, Any], telemetry: Dict[str, Any]) -> None:
        self.sessions.append({"summary": summary, "telemetry_count": telemetry.get("count", 0)})
    def aggregate(self) -> Dict[str, Any]:
        if not self.sessions:
            return {"runs": 0}
        avg_optical = sum(s["summary"].get("optical", 0) for s in self.sessions) / len(self.sessions)
        avg_salvage = sum(s["summary"].get("salvage", 0) for s in self.sessions) / len(self.sessions)
        return {
            "runs": len(self.sessions),
            "avg_optical": round(avg_optical, 3),
            "avg_salvage": round(avg_salvage, 1),
            "total_events": sum(s["telemetry_count"] for s in self.sessions),
        }
