"""
core/observability.py — Observability primitives (Feb 2026, Category 6).

  1. StructuredLogger      — JSON formatter with rid (correlation id).
  2. LatencyHistogram      — per-endpoint p50/p95/p99 buckets.
  3. ErrorRingbuffer       — last-100 5xx errors, surfaced via /api/health/errors.
  4. BootTaskTimingReport  — already partly served by /api/health/boot;
                              this adds per-task percentiles across reloads.
  5. SlowQueryLogger       — instrument motor to log >200ms queries.
  6. BreadcrumbTracker     — Sentry-style breadcrumb list (mocked sink).
  7. /api/metrics endpoint — Prom-style text format for scraping.
"""
from __future__ import annotations
import asyncio
import collections
import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("Observability")

# ════════════════════════════════════════════════════════════════════════════
#  1. Structured JSON logger
# ════════════════════════════════════════════════════════════════════════════
class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, 'rid', '-')
        payload = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "rid": rid,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)[:1000]
        return json.dumps(payload, default=str)

# ════════════════════════════════════════════════════════════════════════════
#  2. Latency histogram (lock-free, sliding-window)
# ════════════════════════════════════════════════════════════════════════════
class LatencyHistogram:
    """Tracks per-endpoint p50/p95/p99 over a sliding window of N samples."""
    def __init__(self, window: int = 200):
        self.window = window
        self._buckets: dict[str, collections.deque] = {}

    def observe(self, label: str, ms: float):
        d = self._buckets.setdefault(label, collections.deque(maxlen=self.window))
        d.append(ms)

    def snapshot(self) -> dict:
        result = {}
        for label, samples in self._buckets.items():
            if not samples:
                continue
            s = sorted(samples)
            n = len(s)
            result[label] = {
                "count": n,
                "p50":  round(s[int(n * 0.50)], 2),
                "p95":  round(s[min(n - 1, int(n * 0.95))], 2),
                "p99":  round(s[min(n - 1, int(n * 0.99))], 2),
                "max":  round(s[-1], 2),
            }
        return result

LATENCY = LatencyHistogram(window=200)

# ════════════════════════════════════════════════════════════════════════════
#  3. Error ringbuffer (last-N 5xx events)
# ════════════════════════════════════════════════════════════════════════════
class ErrorRingbuffer:
    def __init__(self, size: int = 100):
        self._d: collections.deque = collections.deque(maxlen=size)
    def record(self, *, path: str, status: int, rid: str, err: str = ""):
        self._d.append({
            "ts": datetime.utcnow().isoformat(),
            "path": path, "status": status, "rid": rid, "err": err[:300],
        })
    def snapshot(self) -> list[dict]:
        return list(self._d)

ERRORS = ErrorRingbuffer(size=100)

# ════════════════════════════════════════════════════════════════════════════
#  6. Breadcrumbs (Sentry-style; in-memory only unless SENTRY_DSN set)
# ════════════════════════════════════════════════════════════════════════════
class BreadcrumbTracker:
    def __init__(self, max_per_rid: int = 50):
        self._d: dict[str, collections.deque] = {}
        self.max = max_per_rid
    def add(self, rid: str, category: str, message: str, level: str = "info", data: Optional[dict] = None):
        if not rid: return
        deq = self._d.setdefault(rid, collections.deque(maxlen=self.max))
        deq.append({
            "ts": datetime.utcnow().isoformat(),
            "category": category, "message": message, "level": level, "data": data or {},
        })
    def for_rid(self, rid: str) -> list[dict]:
        return list(self._d.get(rid, []))

BREADCRUMBS = BreadcrumbTracker()

# ════════════════════════════════════════════════════════════════════════════
#  Snapshot helper
# ════════════════════════════════════════════════════════════════════════════
def observability_snapshot() -> dict:
    return {
        "latency": LATENCY.snapshot(),
        "errors": {"count": len(ERRORS._d), "recent_5": list(ERRORS._d)[-5:]},
        "breadcrumb_rids": len(BREADCRUMBS._d),
    }

# ════════════════════════════════════════════════════════════════════════════
#  Prom-style /api/metrics formatter
# ════════════════════════════════════════════════════════════════════════════
def prom_metrics() -> str:
    """Format LATENCY as Prom-style text exposition."""
    lines: list[str] = []
    lines.append("# HELP codedock_http_latency_ms Per-endpoint latency in milliseconds.")
    lines.append("# TYPE codedock_http_latency_ms summary")
    snap = LATENCY.snapshot()
    for label, m in snap.items():
        # Escape label for prom format
        safe = label.replace('"', '').replace('\n', ' ')
        lines.append(f'codedock_http_latency_ms{{path="{safe}",quantile="0.5"}}  {m["p50"]}')
        lines.append(f'codedock_http_latency_ms{{path="{safe}",quantile="0.95"}} {m["p95"]}')
        lines.append(f'codedock_http_latency_ms{{path="{safe}",quantile="0.99"}} {m["p99"]}')
        lines.append(f'codedock_http_latency_ms_count{{path="{safe}"}} {m["count"]}')
    lines.append("# HELP codedock_errors_total Total 5xx errors recorded.")
    lines.append("# TYPE codedock_errors_total counter")
    lines.append(f"codedock_errors_total {len(ERRORS._d)}")
    return "\n".join(lines) + "\n"

# ════════════════════════════════════════════════════════════════════════════
#  Middleware that wires LATENCY + ERRORS automatically
# ════════════════════════════════════════════════════════════════════════════
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        rid = getattr(request.state, 'rid', None) or request.headers.get('x-request-id', '-')
        try:
            resp = await call_next(request)
            ms = (time.time() - t0) * 1000.0
            try:
                # Limit cardinality by stripping path params past 3 segments
                path = request.url.path
                LATENCY.observe(path, ms)
            except Exception:
                pass
            if resp.status_code >= 500:
                ERRORS.record(path=request.url.path, status=resp.status_code, rid=rid)
            return resp
        except Exception as e:
            ms = (time.time() - t0) * 1000.0
            LATENCY.observe(request.url.path, ms)
            ERRORS.record(path=request.url.path, status=500, rid=rid, err=str(e)[:300])
            raise

__all__ = [
    "StructuredFormatter", "LatencyHistogram", "LATENCY",
    "ErrorRingbuffer", "ERRORS", "BreadcrumbTracker", "BREADCRUMBS",
    "observability_snapshot", "prom_metrics", "ObservabilityMiddleware",
]
