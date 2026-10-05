from __future__ import annotations
"""
Zaibatsu-Level Observability Layer
Centralized, structured observability for the entire GameForge CNS.
Includes: Structured logging, metrics collection (ties into Latent Metrics Table), distributed tracing (lightweight), health checks, and alerting hooks.
Designed to be S20-friendly (lightweight, no heavy dependencies) while being enterprise-grade.
"""

import logging
import json
import time
from typing import Any, Dict, Optional
from datetime import datetime

# Try to use existing Latent Metrics Table
try:
    from gameforge.exocortex.agentic.latent_metrics_table import LatentMetricsTable
except ImportError:
    LatentMetricsTable = None

class ZaibatsuObservability:
    """
    Enterprise-grade observability for Zaibatsu-level CNS.
    - Structured JSON logging
    - Metrics collection (integrated with Latent Metrics Table)
    - Lightweight tracing
    - Health checks
    - Alerting hooks (can be extended to external systems)
    """

    def __init__(self, service_name: str = "gameforge-cns"):
        self.service_name = service_name
        self.logger = self._setup_logger()
        self.metrics_table = LatentMetricsTable() if LatentMetricsTable else None
        self.traces: Dict[str, Dict] = {}  # lightweight in-memory tracing

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.service_name)
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '{"time": "%(asctime)s", "level": "%(levelname)s", "service": "%(name)s", "message": "%(message)s"}'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def log(self, level: str, message: str, **kwargs):
        """Structured logging."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "level": level.upper(),
            "message": message,
            **kwargs
        }
        if level.upper() == "ERROR":
            self.logger.error(json.dumps(log_data))
        elif level.upper() == "WARNING":
            self.logger.warning(json.dumps(log_data))
        else:
            self.logger.info(json.dumps(log_data))

    def record_metric(self, category: str, name: str, value: float, metadata: Dict = None, room_id: str = "global"):
        """Record metric into the Latent Metrics Table (if available)."""
        if self.metrics_table:
            self.metrics_table.record_metric(category, name, value, metadata, room_id)
        else:
            self.log("INFO", f"Metric recorded (no table): {category}.{name} = {value}")

    def start_trace(self, trace_id: str, operation: str, metadata: Dict = None):
        """Start a lightweight trace span."""
        self.traces[trace_id] = {
            "operation": operation,
            "start_time": time.time(),
            "metadata": metadata or {},
            "events": []
        }
        self.log("INFO", f"Trace started: {operation}", trace_id=trace_id)

    def add_trace_event(self, trace_id: str, event: str, metadata: Dict = None):
        if trace_id in self.traces:
            self.traces[trace_id]["events"].append({
                "time": time.time(),
                "event": event,
                "metadata": metadata or {}
            })

    def end_trace(self, trace_id: str):
        if trace_id in self.traces:
            span = self.traces.pop(trace_id)
            duration = time.time() - span["start_time"]
            self.log("INFO", f"Trace completed: {span['operation']}", 
                     trace_id=trace_id, duration_ms=round(duration * 1000, 2))
            return {"duration_ms": duration * 1000, **span}
        return None

    def health_check(self) -> Dict[str, Any]:
        """Basic health check for the observability layer and core components."""
        health = {
            "service": self.service_name,
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics_table_available": self.metrics_table is not None,
            "active_traces": len(self.traces)
        }
        return health

    def alert(self, severity: str, message: str, metadata: Dict = None):
        """Hook for alerting (can be connected to external systems later)."""
        self.log("WARNING" if severity.lower() == "warning" else "ERROR", 
                 f"ALERT [{severity}]: {message}", **(metadata or {}))

# Global instance for easy access across the CNS
observability = ZaibatsuObservability("gameforge-cns")