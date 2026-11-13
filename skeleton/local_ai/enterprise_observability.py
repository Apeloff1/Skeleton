"""
Enterprise Observability. Metrics, traces, clipped-G stamps, and audit correlation.
"""
from typing import Dict
from .metrics_collector import MetricsCollector
from .audit_log import AuditLog
from .clipped_g_observer import ClippedGObserver

class EnterpriseObservability:
    def __init__(self):
        self.metrics = MetricsCollector()
        self.audit = AuditLog("chronicle/enterprise_obs.jsonl")
        self.observer = ClippedGObserver()

    def record_request(self, latency_ms: float, tokens: int, g: float) -> None:
        self.metrics.inc("requests")
        self.metrics.set("last_latency_ms", latency_ms)
        self.metrics.set("last_tokens", tokens)
        self.metrics.set("last_g", g)
        self.observer.observe({"delta": 0.05, "mass": 1.02})
        self.audit.log({"event": "obs", "latency": latency_ms, "tokens": tokens, "g": g})

    def snapshot(self) -> Dict:
        return {
            "metrics": self.metrics.snapshot(),
            "g": self.observer.stamp(),
            "enterprise": True
        }
