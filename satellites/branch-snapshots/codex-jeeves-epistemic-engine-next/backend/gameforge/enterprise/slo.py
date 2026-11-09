from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class SLO:
    name: str
    objective: float
    window_hint: str
    indicator: str


class SLORegistry:
    def __init__(self):
        self.slos = [
            SLO("work_success_rate", 0.99, "1h", "work_completed / work_total"),
            SLO("queue_ack_rate", 0.995, "1h", "queue_acked / (acked+nacked)"),
            SLO("api_availability", 0.999, "1h", "process up + non-5xx"),
        ]
        self._counters: Dict[str, float] = {}

    def observe(self, key: str, n: float = 1.0):
        self._counters[key] = self._counters.get(key, 0.0) + n

    def evaluate(self) -> List[Dict[str, Any]]:
        completed = self._counters.get("work_completed_total", 0.0)
        failed = self._counters.get("work_failed_total", 0.0)
        total = completed + failed
        success_rate = (completed / total) if total else 1.0
        acked = self._counters.get("queue_acked_total", 0.0)
        nacked = self._counters.get("queue_nacked_total", 0.0)
        qtotal = acked + nacked
        ack_rate = (acked / qtotal) if qtotal else 1.0
        values = {
            "work_success_rate": success_rate,
            "queue_ack_rate": ack_rate,
            "api_availability": 1.0,
        }
        out = []
        for slo in self.slos:
            current = values.get(slo.name, 1.0)
            out.append(
                {
                    "name": slo.name,
                    "objective": slo.objective,
                    "current": current,
                    "window": slo.window_hint,
                    "burn": max(0.0, slo.objective - current),
                    "breaching": current < slo.objective,
                    "indicator": slo.indicator,
                }
            )
        return out


SLOS = SLORegistry()
