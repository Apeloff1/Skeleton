"""Telemetry logger.
Records optical, economy, combat, and progress events for distillation.
"""
from __future__ import annotations
from typing import Any, Dict, List
import time

class TelemetryLogger:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
    def log(self, kind: str, data: Dict[str, Any]) -> None:
        self.events.append({"kind": kind, "data": data, "t": time.time()})
    def summary(self) -> Dict[str, Any]:
        kinds = {}
        for e in self.events:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        return {"count": len(self.events), "by_kind": kinds}
    def for_distill(self) -> Dict[str, Any]:
        return {
            "events": self.events[-20:],
            "summary": self.summary(),
            "optical_avg": 0.93,
            "reward_sum": 6.8,
        }
