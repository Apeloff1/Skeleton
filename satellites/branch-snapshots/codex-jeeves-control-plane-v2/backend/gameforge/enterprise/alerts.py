from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Alert:
    name: str
    severity: str  # info|warn|critical
    message: str
    value: float | None = None


class MetricsRegistry:
    def __init__(self):
        self.counters: Dict[str, float] = {}
        self.histograms: Dict[str, Dict[str, float]] = {}

    def inc(self, name: str, n: float = 1.0, **labels):
        key = name if not labels else f"{name}|" + ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        self.counters[key] = self.counters.get(key, 0.0) + n

    def observe(self, name: str, value: float, **labels):
        key = name if not labels else f"{name}|" + ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        h = self.histograms.setdefault(key, {"count": 0.0, "sum": 0.0, "avg": 0.0})
        h["count"] += 1
        h["sum"] += value
        h["avg"] = h["sum"] / h["count"]

    def snapshot(self) -> Dict[str, Any]:
        return {"counters": dict(self.counters), "histograms": dict(self.histograms)}


METRICS = MetricsRegistry()


class AlertEvaluator:
    def evaluate(self) -> List[Alert]:
        snap = METRICS.snapshot()
        counters = snap.get("counters") or {}
        hist = snap.get("histograms") or {}
        alerts: List[Alert] = []

        nacked = sum(v for k, v in counters.items() if k.startswith("queue_nacked_total"))
        if nacked > 20:
            alerts.append(Alert("queue_nacks_high", "warn", f"Queue nacks={nacked}", nacked))

        errors = sum(v for k, v in counters.items() if "worker_messages_total" in k and "status=error" in k)
        if errors > 10:
            alerts.append(Alert("worker_errors_high", "critical", f"Worker errors={errors}", errors))

        blocked = sum(v for k, v in counters.items() if k.startswith("quota_blocked_total"))
        if blocked > 50:
            alerts.append(Alert("quota_blocks_high", "warn", f"Quota blocks={blocked}", blocked))

        for k, data in hist.items():
            if "work_latency_seconds" in k and data.get("avg", 0) > 30:
                alerts.append(
                    Alert(
                        "work_latency_high",
                        "warn",
                        f"High avg latency on {k}: {data.get('avg'):.2f}s",
                        data.get("avg"),
                    )
                )

        try:
            from gameforge.enterprise.slo import SLOS

            for row in SLOS.evaluate():
                if not row.get("breaching"):
                    continue
                severity = "critical" if row["current"] < (row["objective"] - 0.02) else "warn"
                alerts.append(
                    Alert(
                        name=f"slo_burn_{row['name']}",
                        severity=severity,
                        message=(
                            f"SLO {row['name']} breaching: current={row['current']:.4f} "
                            f"objective={row['objective']:.4f}"
                        ),
                        value=row["current"],
                    )
                )
        except Exception:
            pass
        return alerts


ALERTS = AlertEvaluator()
