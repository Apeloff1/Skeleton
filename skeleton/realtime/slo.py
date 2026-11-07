"""Realtime transport SLO metrics.

Bridges into the existing observability emit layer: any sink exposing the
``MetricsCollector`` shape (``increment`` / ``gauge`` / ``histogram``, e.g.
``ServerState.metrics`` served at ``/api/v1/metrics``) receives every sample
under the ``realtime.*`` namespace. A bounded local window also computes the
p50/p95 delivery latency and evaluates the SLO targets for ``/realtime/slo``.
Sink failures are swallowed: metrics must never break delivery.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Dict, Optional

# ADR-realtime-transport §5 (PR #4101). Measured server-side.
SLO_TARGETS: Dict[str, float] = {
    "connect_success_rate_min": 0.995,
    "delivery_latency_p95_ms_max": 500.0,
    "delivery_latency_p99_ms_max": 2000.0,
    "resume_success_rate_min": 0.99,
    "heartbeat_miss_rate_max": 0.005,
    "lagged_drop_rate_max": 0.001,
}

COUNTERS = (
    "connect_attempts",
    "connect_successes",
    "connect_failures",
    "reconnects",
    "disconnects",
    "events_published",
    "events_delivered",
    "events_dropped",
    "events_resumed",
    "resume_attempts",
    "resume_successes",
    "stream_resets",
    "stream_lagged",
    "heartbeats_sent",
    "heartbeat_misses",
    "presence_timeouts",
    "payload_redactions",
    "publish_rejected",
)


def _percentile(sorted_values: list, p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return float(sorted_values[idx])


class RealtimeSLO:
    """Thread-safe counters + latency window with an optional metrics sink."""

    def __init__(self, sink: Optional[Any] = None, *, window: int = 4096, prefix: str = "realtime") -> None:
        self._sink = sink
        self._prefix = prefix
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = {name: 0.0 for name in COUNTERS}
        self._latency: Deque[float] = deque(maxlen=max(16, int(window)))
        self._gauges: Dict[str, float] = {"active_connections": 0.0}

    # -- sink bridge -------------------------------------------------------
    def bind_sink(self, sink: Optional[Any]) -> None:
        self._sink = sink

    def _emit(self, kind: str, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        sink = self._sink
        if sink is None:
            return
        try:
            getattr(sink, kind)(f"{self._prefix}.{name}", value, labels)
        except Exception:
            pass

    def _inc(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + value
        self._emit("increment", name, value, labels)

    # -- recorders ---------------------------------------------------------
    def record_connect(self, ok: bool, *, transport: str = "sse") -> None:
        self._inc("connect_attempts", labels={"transport": transport})
        self._inc("connect_successes" if ok else "connect_failures", labels={"transport": transport})

    def record_reconnect(self) -> None:
        self._inc("reconnects")

    def record_disconnect(self, reason: str = "closed") -> None:
        self._inc("disconnects", labels={"reason": reason})

    def record_published(self, channel: str) -> None:
        self._inc("events_published", labels={"channel": channel})

    def record_delivered(self, channel: str, latency_ms: float) -> None:
        latency_ms = max(0.0, float(latency_ms))
        with self._lock:
            self._latency.append(latency_ms)
        self._inc("events_delivered", labels={"channel": channel})
        self._emit("histogram", "delivery_latency_ms", latency_ms, {"channel": channel})

    def record_dropped(self, count: int = 1, *, reason: str = "backpressure") -> None:
        if count > 0:
            self._inc("events_dropped", float(count), labels={"reason": reason})

    def record_resumed(self, count: int = 1) -> None:
        if count > 0:
            self._inc("events_resumed", float(count))

    def record_resume(self, ok: bool) -> None:
        self._inc("resume_attempts")
        if ok:
            self._inc("resume_successes")
        else:
            self._inc("stream_resets")

    def record_lagged(self, dropped: int) -> None:
        self._inc("stream_lagged")
        self.record_dropped(dropped, reason="lagged")

    def record_heartbeat_sent(self) -> None:
        self._inc("heartbeats_sent")

    def record_heartbeat_miss(self, count: int = 1) -> None:
        if count > 0:
            self._inc("heartbeat_misses", float(count))

    def record_presence_timeout(self) -> None:
        self._inc("presence_timeouts")

    def record_redactions(self, count: int) -> None:
        if count > 0:
            self._inc("payload_redactions", float(count))

    def record_publish_rejected(self, reason: str) -> None:
        self._inc("publish_rejected", labels={"reason": reason})

    def set_active_connections(self, value: int) -> None:
        with self._lock:
            self._gauges["active_connections"] = float(value)
        self._emit("gauge", "active_connections", float(value))

    # -- read side ---------------------------------------------------------
    def counter(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            latencies = sorted(self._latency)
        attempts = counters["connect_attempts"]
        published = counters["events_published"]
        heartbeats = counters["heartbeats_sent"] + counters["heartbeat_misses"]
        connect_rate = counters["connect_successes"] / attempts if attempts else 1.0
        drop_rate = counters["events_dropped"] / published if published else 0.0
        miss_rate = counters["heartbeat_misses"] / heartbeats if heartbeats else 0.0
        resumes = counters["resume_attempts"]
        resume_rate = counters["resume_successes"] / resumes if resumes else 1.0
        p50 = _percentile(latencies, 0.50)
        p95 = _percentile(latencies, 0.95)
        p99 = _percentile(latencies, 0.99)
        actual = {
            "connect_success_rate": round(connect_rate, 6),
            "delivery_latency_p50_ms": round(p50, 3),
            "delivery_latency_p95_ms": round(p95, 3),
            "delivery_latency_p99_ms": round(p99, 3),
            "resume_success_rate": round(resume_rate, 6),
            "heartbeat_miss_rate": round(miss_rate, 6),
            "lagged_drop_rate": round(drop_rate, 6),
        }
        slo = {
            "connect_success_rate": connect_rate >= SLO_TARGETS["connect_success_rate_min"],
            "delivery_latency_p95_ms": p95 < SLO_TARGETS["delivery_latency_p95_ms_max"],
            "delivery_latency_p99_ms": p99 < SLO_TARGETS["delivery_latency_p99_ms_max"],
            "resume_success_rate": resume_rate >= SLO_TARGETS["resume_success_rate_min"],
            "heartbeat_miss_rate": miss_rate < SLO_TARGETS["heartbeat_miss_rate_max"],
            "lagged_drop_rate": drop_rate < SLO_TARGETS["lagged_drop_rate_max"],
        }
        return {
            "kind": "realtime-slo",
            "counters": counters,
            "gauges": gauges,
            "latency_samples": len(latencies),
            "actual": actual,
            "targets": dict(SLO_TARGETS),
            "slo_met": slo,
            "healthy": all(slo.values()),
        }


__all__ = ["COUNTERS", "RealtimeSLO", "SLO_TARGETS"]
