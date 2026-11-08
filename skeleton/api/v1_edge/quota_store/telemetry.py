"""Quota metrics and audit events through the existing Pack F GateTelemetry.

No new metrics backend: counters/gauges go to ``GateTelemetry.metrics``
(Internal Systems' ``MetricsCollector``) with labels normalised by
``safe_label``. Labels are bounded: scope, quota class or route template,
outcome and store name — never tenant ids, keys or paths.

Audit events (denials, store outages, operator resets) go to registered
sinks as plain dicts carrying a *hashed* tenant reference. Like every gate
telemetry hook, nothing here can raise into the request path.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from skeleton.gate_plane.telemetry.gate_telemetry import GateTelemetry, safe_label

M_QUOTA_DECISIONS = "gate_plane.quota.decisions"
M_QUOTA_STORE_ERRORS = "gate_plane.quota.store_errors"
M_QUOTA_REMAINING = "gate_plane.quota.remaining_ratio"
M_QUOTA_STORE_LATENCY_MS = "gate_plane.quota.store_latency_ms"
M_QUOTA_AUDIT = "gate_plane.quota.audit_events"

AUDIT_DENIED = "quota.denied"
AUDIT_STORE_DOWN = "quota.store_unavailable"
AUDIT_RESET = "quota.reset"
AUDIT_EXEMPT = "quota.exempt"

AuditSink = Callable[[Dict[str, Any]], None]


class QuotaTelemetry:
    def __init__(self, telemetry: Optional[GateTelemetry] = None, *,
                 clock: Callable[[], float] = time.time, max_audit: int = 1000):
        self.telemetry = telemetry or GateTelemetry()
        self._clock = clock
        self._sinks: List[AuditSink] = []
        self._recent: List[Dict[str, Any]] = []
        self._max = max_audit
        self._lock = threading.Lock()
        self.dropped = 0

    def add_sink(self, sink: AuditSink) -> None:
        self._sinks.append(sink)

    def _guard(self, fn, *a, **kw) -> None:
        try:
            fn(*a, **kw)
        except Exception:  # noqa: BLE001 - telemetry never changes a verdict
            with self._lock:
                self.dropped += 1

    def _labels(self, **labels: Any) -> Dict[str, str]:
        return {k: safe_label(v) for k, v in labels.items()}

    def decision(self, scope: str, label: str, outcome: str, remaining: float, capacity: float,
                 store: str) -> None:
        m = self.telemetry.metrics
        self._guard(m.increment, M_QUOTA_DECISIONS, 1.0,
                    self._labels(scope=scope, name=label, outcome=outcome, store=store))
        if capacity > 0:
            self._guard(m.gauge, M_QUOTA_REMAINING, max(0.0, remaining) / capacity,
                        self._labels(scope=scope, name=label))

    def store_latency(self, store: str, ms: float) -> None:
        self._guard(self.telemetry.metrics.histogram, M_QUOTA_STORE_LATENCY_MS, ms,
                    self._labels(store=store))

    def store_error(self, store: str, op: str) -> None:
        self._guard(self.telemetry.metrics.increment, M_QUOTA_STORE_ERRORS, 1.0,
                    self._labels(store=store, op=op))

    def audit(self, event: str, **fields: Any) -> Dict[str, Any]:
        rec = {"event": event, "ts": self._clock(), **fields}
        with self._lock:
            self._recent.append(rec)
            if len(self._recent) > self._max:
                del self._recent[: len(self._recent) - self._max]
        self._guard(self.telemetry.metrics.increment, M_QUOTA_AUDIT, 1.0, self._labels(event=event))
        for sink in list(self._sinks):
            self._guard(sink, dict(rec))
        return rec

    def recent(self, event: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._recent if event is None or r["event"] == event]

    def count(self, scope: str, name: str, outcome: str, store: str) -> float:
        return self.telemetry.counter(M_QUOTA_DECISIONS, scope=scope, name=name,
                                      outcome=outcome, store=store)
