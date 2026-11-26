"""
core/observability.py — Observability primitives (Category 6, revised Nov 2026).

  1. StructuredLogger      — JSON formatter with rid + W3C trace/span ids.
  2. LatencyHistogram      — per-route p50/p95/p99 sliding window (legacy JSON).
  3. ErrorRingbuffer       — last-100 5xx errors, surfaced via /api/health/errors.
  4. HttpMetrics           — monotonic Prometheus counters + cumulative
                             duration histogram keyed by *route template*
                             (bounded cardinality; never raw request paths).
  5. W3C Trace Context     — parse/propagate ``traceparent``; every request
                             gets a server span whose ids reach logs and the
                             ``traceparent`` response header.
  6. OTLP span export      — optional, stdlib-only OTLP/HTTP JSON exporter,
                             enabled only by OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
                             (or OTEL_EXPORTER_OTLP_ENDPOINT); bounded queue,
                             drop-on-overflow, never blocks a request.
  7. BreadcrumbTracker     — Sentry-style breadcrumb list (in-memory sink).
  8. /api/metrics          — Prometheus text exposition (format 0.0.4).

Design rules: no third-party dependency, bounded memory everywhere, metric
labels only from the route table (or a fixed sentinel), and observability
failures never change the response a client receives.
"""
from __future__ import annotations

import collections
import contextvars
import json
import logging
import os
import queue
import re
import secrets
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("Observability")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ════════════════════════════════════════════════════════════════════════════
#  W3C Trace Context (https://www.w3.org/TR/trace-context/)
# ════════════════════════════════════════════════════════════════════════════
_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<parent_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})(?:-.*)?$"
)
_INVALID_TRACE_ID = "0" * 32
_INVALID_SPAN_ID = "0" * 16
_MAX_TRACEPARENT_LEN = 512


@dataclass(frozen=True)
class SpanContext:
    """Identity of the active server span."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    sampled: bool

    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{'01' if self.sampled else '00'}"


def new_trace_id() -> str:
    while True:
        value = secrets.token_hex(16)
        if value != _INVALID_TRACE_ID:
            return value


def new_span_id() -> str:
    while True:
        value = secrets.token_hex(8)
        if value != _INVALID_SPAN_ID:
            return value


def parse_traceparent(header: Optional[str]) -> Optional[tuple[str, str, bool]]:
    """Return (trace_id, parent_span_id, sampled) or None when invalid.

    Follows the spec's forward-compatibility rule: unknown future versions
    are parsed by the version-00 prefix; version ``ff`` and all-zero ids are
    invalid. Oversized or non-lowercase-hex headers are rejected.
    """
    if not header or len(header) > _MAX_TRACEPARENT_LEN:
        return None
    match = _TRACEPARENT_RE.match(header.strip())
    if match is None:
        return None
    version = match.group("version")
    if version == "ff":
        return None
    if version == "00" and len(header.strip()) != 55:
        return None
    trace_id = match.group("trace_id")
    parent_id = match.group("parent_id")
    if trace_id == _INVALID_TRACE_ID or parent_id == _INVALID_SPAN_ID:
        return None
    sampled = bool(int(match.group("flags"), 16) & 0x01)
    return trace_id, parent_id, sampled


def start_server_span(traceparent_header: Optional[str]) -> SpanContext:
    parsed = parse_traceparent(traceparent_header)
    if parsed is None:
        return SpanContext(new_trace_id(), new_span_id(), None, _default_sampled())
    trace_id, parent_id, sampled = parsed
    return SpanContext(trace_id, new_span_id(), parent_id, sampled)


def _default_sampled() -> bool:
    """Head sampling for new traces: OTEL_TRACES_SAMPLER_ARG ratio (default 1.0)."""
    raw = os.environ.get("OTEL_TRACES_SAMPLER_ARG", "").strip()
    try:
        ratio = float(raw) if raw else 1.0
    except ValueError:
        ratio = 1.0
    if ratio >= 1.0:
        return True
    if ratio <= 0.0:
        return False
    return secrets.randbelow(1_000_000) < int(ratio * 1_000_000)


_CURRENT_SPAN: contextvars.ContextVar[Optional[SpanContext]] = contextvars.ContextVar(
    "codedock_current_span", default=None
)


def current_span() -> Optional[SpanContext]:
    return _CURRENT_SPAN.get()


class TraceContextLogFilter(logging.Filter):
    """Attach trace_id/span_id of the active request span to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        span = _CURRENT_SPAN.get()
        if not hasattr(record, "trace_id"):
            record.trace_id = span.trace_id if span else "-"
        if not hasattr(record, "span_id"):
            record.span_id = span.span_id if span else "-"
        return True


# ════════════════════════════════════════════════════════════════════════════
#  1. Structured JSON logger
# ════════════════════════════════════════════════════════════════════════════
class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "rid", "-")
        span = _CURRENT_SPAN.get()
        payload = {
            "ts": _utcnow_iso(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "rid": rid,
            "trace_id": getattr(record, "trace_id", None) or (span.trace_id if span else "-"),
            "span_id": getattr(record, "span_id", None) or (span.span_id if span else "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)[:1000]
        return json.dumps(payload, default=str)


# ════════════════════════════════════════════════════════════════════════════
#  2. Latency histogram (sliding-window percentiles; legacy JSON surface)
# ════════════════════════════════════════════════════════════════════════════
class LatencyHistogram:
    """Tracks per-label p50/p95/p99 over a sliding window of N samples.

    The number of labels is capped so an attacker cannot grow memory by
    requesting unique URLs; excess labels collapse into ``__overflow__``.
    """

    def __init__(self, window: int = 200, max_labels: int = 512):
        self.window = window
        self.max_labels = max_labels
        self._buckets: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def observe(self, label: str, ms: float) -> None:
        with self._lock:
            d = self._buckets.get(label)
            if d is None:
                if len(self._buckets) >= self.max_labels:
                    label = OVERFLOW_LABEL
                    d = self._buckets.get(label)
                if d is None:
                    d = collections.deque(maxlen=self.window)
                    self._buckets[label] = d
            d.append(ms)

    def snapshot(self) -> dict:
        with self._lock:
            items = [(label, list(samples)) for label, samples in self._buckets.items()]
        result = {}
        for label, samples in items:
            if not samples:
                continue
            s = sorted(samples)
            n = len(s)
            result[label] = {
                "count": n,
                "p50": round(s[int(n * 0.50)], 2),
                "p95": round(s[min(n - 1, int(n * 0.95))], 2),
                "p99": round(s[min(n - 1, int(n * 0.99))], 2),
                "max": round(s[-1], 2),
            }
        return result


OVERFLOW_LABEL = "__overflow__"
UNMATCHED_ROUTE = "__unmatched__"
LATENCY = LatencyHistogram(window=200)


# ════════════════════════════════════════════════════════════════════════════
#  3. Error ringbuffer (last-N 5xx events)
# ════════════════════════════════════════════════════════════════════════════
class ErrorRingbuffer:
    def __init__(self, size: int = 100):
        self._d: collections.deque = collections.deque(maxlen=size)
        self._total = 0
        self._lock = threading.Lock()

    def record(self, *, path: str, status: int, rid: str, err: str = "", trace_id: str = "-") -> None:
        with self._lock:
            self._total += 1
            self._d.append({
                "ts": _utcnow_iso(),
                "path": path, "status": status, "rid": rid,
                "trace_id": trace_id, "err": err[:300],
            })

    @property
    def total(self) -> int:
        """Monotonic count of every recorded error (not capped by ring size)."""
        return self._total

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._d)


ERRORS = ErrorRingbuffer(size=100)


# ════════════════════════════════════════════════════════════════════════════
#  4. Prometheus HTTP metrics (monotonic counters + cumulative histogram)
# ════════════════════════════════════════════════════════════════════════════
DEFAULT_DURATION_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0,
)


@dataclass
class _HistogramSeries:
    bucket_counts: list[int]
    count: int = 0
    total: float = 0.0


@dataclass
class HttpMetrics:
    """Bounded-cardinality HTTP RED metrics keyed by (method, route, status class)."""

    buckets: tuple[float, ...] = DEFAULT_DURATION_BUCKETS
    max_series: int = 1024
    _requests: dict[tuple[str, str, str], int] = field(default_factory=dict)
    _durations: dict[tuple[str, str], _HistogramSeries] = field(default_factory=dict)
    _inflight: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    _METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

    def _method(self, method: str) -> str:
        method = (method or "").upper()
        return method if method in self._METHODS else "OTHER"

    def begin(self) -> None:
        with self._lock:
            self._inflight += 1

    def observe(self, *, method: str, route: str, status: int, seconds: float) -> None:
        method = self._method(method)
        status_class = f"{max(1, min(5, int(status) // 100))}xx"
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
            key = (method, route, status_class)
            if key not in self._requests and len(self._requests) >= self.max_series:
                key = (method, OVERFLOW_LABEL, status_class)
            self._requests[key] = self._requests.get(key, 0) + 1

            dkey = (method, route)
            series = self._durations.get(dkey)
            if series is None:
                if len(self._durations) >= self.max_series:
                    dkey = (method, OVERFLOW_LABEL)
                    series = self._durations.get(dkey)
                if series is None:
                    series = _HistogramSeries(bucket_counts=[0] * len(self.buckets))
                    self._durations[dkey] = series
            series.count += 1
            series.total += max(0.0, seconds)
            for i, bound in enumerate(self.buckets):
                if seconds <= bound:
                    series.bucket_counts[i] += 1

    def exposition(self) -> list[str]:
        with self._lock:
            requests = sorted(self._requests.items())
            durations = sorted(
                (k, _HistogramSeries(list(v.bucket_counts), v.count, v.total))
                for k, v in self._durations.items()
            )
            inflight = self._inflight
        lines = [
            "# HELP codedock_http_requests_total HTTP requests by method, route template and status class.",
            "# TYPE codedock_http_requests_total counter",
        ]
        for (method, route, status_class), value in requests:
            lines.append(
                f'codedock_http_requests_total{{method="{_label(method)}",route="{_label(route)}",'
                f'status_class="{status_class}"}} {value}'
            )
        lines += [
            "# HELP codedock_http_request_duration_seconds HTTP server request duration.",
            "# TYPE codedock_http_request_duration_seconds histogram",
        ]
        for (method, route), series in durations:
            base = f'method="{_label(method)}",route="{_label(route)}"'
            for bound, count in zip(self.buckets, series.bucket_counts):
                lines.append(
                    f'codedock_http_request_duration_seconds_bucket{{{base},le="{bound:g}"}} {count}'
                )
            lines.append(f'codedock_http_request_duration_seconds_bucket{{{base},le="+Inf"}} {series.count}')
            lines.append(f"codedock_http_request_duration_seconds_sum{{{base}}} {round(series.total, 6)}")
            lines.append(f"codedock_http_request_duration_seconds_count{{{base}}} {series.count}")
        lines += [
            "# HELP codedock_http_requests_in_flight HTTP requests currently being served.",
            "# TYPE codedock_http_requests_in_flight gauge",
            f"codedock_http_requests_in_flight {inflight}",
        ]
        return lines


HTTP_METRICS = HttpMetrics()


# ════════════════════════════════════════════════════════════════════════════
#  6. Optional OTLP/HTTP JSON span exporter (stdlib only)
# ════════════════════════════════════════════════════════════════════════════
def _otlp_endpoint() -> Optional[str]:
    explicit = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if base:
        return base.rstrip("/") + "/v1/traces"
    return None


def _otlp_headers() -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS (``k=v,k2=v2``); values never logged."""
    headers: dict[str, str] = {}
    raw = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_HEADERS") or os.environ.get(
        "OTEL_EXPORTER_OTLP_HEADERS", ""
    )
    for item in raw.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key and "\n" not in key and "\n" not in value:
            headers[key] = value.strip()
    return headers


@dataclass(frozen=True)
class FinishedSpan:
    context: SpanContext
    name: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any]
    error: bool


def _otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)[:1024]}


def encode_otlp_spans(spans: list[FinishedSpan], *, service_name: str) -> dict[str, Any]:
    """Encode spans as an OTLP ExportTraceServiceRequest (JSON mapping)."""
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": service_name}},
                {"key": "service.version", "value": {"stringValue": _build_version()}},
                {"key": "deployment.environment.name",
                 "value": {"stringValue": os.environ.get("ENVIRONMENT", "development")}},
            ]},
            "scopeSpans": [{
                "scope": {"name": "codedock.observability", "version": "1"},
                "spans": [
                    {
                        "traceId": s.context.trace_id,
                        "spanId": s.context.span_id,
                        **({"parentSpanId": s.context.parent_span_id}
                           if s.context.parent_span_id else {}),
                        "name": s.name,
                        "kind": 2,  # SPAN_KIND_SERVER
                        "startTimeUnixNano": str(s.start_ns),
                        "endTimeUnixNano": str(s.end_ns),
                        "attributes": [
                            {"key": k, "value": _otlp_value(v)} for k, v in sorted(s.attributes.items())
                        ],
                        "status": {"code": 2 if s.error else 1},
                    }
                    for s in spans
                ],
            }],
        }]
    }


class OtlpSpanExporter:
    """Batching background exporter. Never blocks or fails the request path."""

    def __init__(
        self,
        endpoint: str,
        *,
        headers: Optional[dict[str, str]] = None,
        service_name: str = "skeleton-backend",
        max_queue: int = 2048,
        batch_size: int = 256,
        flush_interval_s: float = 2.0,
        timeout_s: float = 5.0,
    ):
        self.endpoint = endpoint
        self.headers = dict(headers or {})
        self.service_name = service_name
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.timeout_s = timeout_s
        self._queue: queue.Queue[FinishedSpan] = queue.Queue(maxsize=max_queue)
        self.dropped = 0
        self.exported = 0
        self.failed_batches = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def submit(self, span: FinishedSpan) -> None:
        if not span.context.sampled:
            return
        try:
            self._queue.put_nowait(span)
        except queue.Full:
            self.dropped += 1
            return
        self._ensure_thread()

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run, name="otlp-span-exporter", daemon=True
            )
            self._thread.start()

    def _drain(self) -> list[FinishedSpan]:
        batch: list[FinishedSpan] = []
        while len(batch) < self.batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def export(self, batch: list[FinishedSpan]) -> bool:
        body = json.dumps(encode_otlp_spans(batch, service_name=self.service_name)).encode()
        request = urllib.request.Request(
            self.endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json", **self.headers},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 - operator-configured endpoint
                ok = 200 <= response.status < 300
        except Exception as exc:  # network failures must not escape
            logger.warning("otlp export failed: %s", type(exc).__name__)
            ok = False
        if ok:
            self.exported += len(batch)
        else:
            self.failed_batches += 1
        return ok

    def flush(self) -> None:
        while True:
            batch = self._drain()
            if not batch:
                return
            self.export(batch)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.flush_interval_s)
            self.flush()

    def shutdown(self) -> None:
        self._stop.set()
        self.flush()

    def stats(self) -> dict[str, int]:
        return {
            "queued": self._queue.qsize(),
            "exported": self.exported,
            "dropped": self.dropped,
            "failed_batches": self.failed_batches,
        }


_EXPORTER: Optional[OtlpSpanExporter] = None
_EXPORTER_LOCK = threading.Lock()


def span_exporter() -> Optional[OtlpSpanExporter]:
    """Lazily build the exporter from OTEL_* env; None when tracing export is off."""
    global _EXPORTER
    if os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return None
    endpoint = _otlp_endpoint()
    if endpoint is None:
        return None
    with _EXPORTER_LOCK:
        if _EXPORTER is None or _EXPORTER.endpoint != endpoint:
            _EXPORTER = OtlpSpanExporter(
                endpoint,
                headers=_otlp_headers(),
                service_name=os.environ.get("OTEL_SERVICE_NAME", "skeleton-backend"),
            )
        return _EXPORTER


# ════════════════════════════════════════════════════════════════════════════
#  7. Breadcrumbs (Sentry-style; in-memory only)
# ════════════════════════════════════════════════════════════════════════════
class BreadcrumbTracker:
    def __init__(self, max_per_rid: int = 50, max_rids: int = 2048):
        self._d: collections.OrderedDict[str, collections.deque] = collections.OrderedDict()
        self.max = max_per_rid
        self.max_rids = max_rids

    def add(self, rid: str, category: str, message: str, level: str = "info", data: Optional[dict] = None):
        if not rid:
            return
        deq = self._d.get(rid)
        if deq is None:
            while len(self._d) >= self.max_rids:
                self._d.popitem(last=False)
            deq = collections.deque(maxlen=self.max)
            self._d[rid] = deq
        deq.append({
            "ts": _utcnow_iso(),
            "category": category, "message": message, "level": level, "data": data or {},
        })

    def for_rid(self, rid: str) -> list[dict]:
        return list(self._d.get(rid, []))


BREADCRUMBS = BreadcrumbTracker()


# ════════════════════════════════════════════════════════════════════════════
#  Snapshot helper
# ════════════════════════════════════════════════════════════════════════════
def observability_snapshot() -> dict:
    exporter = span_exporter()
    return {
        "latency": LATENCY.snapshot(),
        "errors": {"count": ERRORS.total, "recent_5": ERRORS.snapshot()[-5:]},
        "breadcrumb_rids": len(BREADCRUMBS._d),
        "tracing": {
            "propagation": "w3c-tracecontext",
            "otlp_export": exporter.stats() if exporter else None,
        },
    }


# ════════════════════════════════════════════════════════════════════════════
#  Prometheus /api/metrics formatter
# ════════════════════════════════════════════════════════════════════════════
_PROCESS_STARTED_AT = time.time()


def _label(value: str) -> str:
    """Make a value safe for a Prometheus label (no quotes/backslashes/newlines)."""
    return str(value).replace("\\", "").replace('"', "").replace("\n", " ")[:128]


def _build_version() -> str:
    """Release version: APP_VERSION (set by the release image build) or 'dev'."""
    return os.environ.get("APP_VERSION", "").strip() or "dev"


def prom_metrics() -> str:
    """Prometheus text exposition (0.0.4): latency summary, RED metrics, build info."""
    lines: list[str] = []
    lines.append("# HELP codedock_http_latency_ms Per-endpoint latency in milliseconds.")
    lines.append("# TYPE codedock_http_latency_ms summary")
    snap = LATENCY.snapshot()
    for label, m in snap.items():
        safe = _label(label)
        lines.append(f'codedock_http_latency_ms{{path="{safe}",quantile="0.5"}}  {m["p50"]}')
        lines.append(f'codedock_http_latency_ms{{path="{safe}",quantile="0.95"}} {m["p95"]}')
        lines.append(f'codedock_http_latency_ms{{path="{safe}",quantile="0.99"}} {m["p99"]}')
        lines.append(f'codedock_http_latency_ms_count{{path="{safe}"}} {m["count"]}')
    lines.extend(HTTP_METRICS.exposition())
    lines.append("# HELP codedock_build_info Build metadata; value is always 1.")
    lines.append("# TYPE codedock_build_info gauge")
    lines.append(
        f'codedock_build_info{{version="{_label(_build_version())}",'
        f'environment="{_label(os.environ.get("ENVIRONMENT", "development"))}"}} 1'
    )
    lines.append("# HELP codedock_process_uptime_seconds Seconds since the observability module loaded.")
    lines.append("# TYPE codedock_process_uptime_seconds gauge")
    lines.append(f"codedock_process_uptime_seconds {round(time.time() - _PROCESS_STARTED_AT, 3)}")
    lines.append("# HELP codedock_errors_total Total 5xx errors recorded since process start.")
    lines.append("# TYPE codedock_errors_total counter")
    lines.append(f"codedock_errors_total {ERRORS.total}")
    return "\n".join(lines) + "\n"


# ════════════════════════════════════════════════════════════════════════════
#  Middleware that wires tracing + metrics + errors automatically
# ════════════════════════════════════════════════════════════════════════════
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from fastapi import Request  # noqa: E402


def route_template(request: Request) -> str:
    """Bounded metric label: the matched route template, never the raw path."""
    route = request.scope.get("route")
    path = getattr(route, "path_format", None) or getattr(route, "path", None)
    if isinstance(path, str) and path:
        return (request.scope.get("root_path") or "") + path
    return UNMATCHED_ROUTE


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        start_ns = time.time_ns()
        span = start_server_span(request.headers.get("traceparent"))
        token = _CURRENT_SPAN.set(span)
        request.state.trace_id = span.trace_id
        rid = (
            getattr(request.state, "request_id", None)
            or getattr(request.state, "rid", None)
            or request.headers.get("x-request-id", "-")
        )
        HTTP_METRICS.begin()
        status = 500
        error_name = ""
        try:
            resp = await call_next(request)
            status = resp.status_code
            try:
                resp.headers["traceparent"] = span.traceparent()
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                resp.headers.setdefault("Server-Timing", f"app;dur={elapsed_ms:.1f}")
            except Exception:
                pass
            return resp
        except Exception as e:
            error_name = type(e).__name__
            raise
        finally:
            seconds = time.perf_counter() - t0
            route = route_template(request)
            try:
                LATENCY.observe(route, seconds * 1000.0)
                HTTP_METRICS.observe(
                    method=request.method, route=route, status=status, seconds=seconds
                )
                if status >= 500:
                    ERRORS.record(
                        path=route, status=status, rid=rid, err=error_name,
                        trace_id=span.trace_id,
                    )
                exporter = span_exporter()
                if exporter is not None:
                    exporter.submit(FinishedSpan(
                        context=span,
                        name=f"{request.method} {route}",
                        start_ns=start_ns,
                        end_ns=time.time_ns(),
                        attributes={
                            "http.request.method": request.method,
                            "http.route": route,
                            "http.response.status_code": status,
                            "url.scheme": request.url.scheme,
                        },
                        error=status >= 500,
                    ))
            except Exception:  # observability must never alter the response
                logger.debug("observability bookkeeping failed", exc_info=True)
            finally:
                _CURRENT_SPAN.reset(token)


__all__ = [
    "StructuredFormatter", "TraceContextLogFilter", "LatencyHistogram", "LATENCY",
    "ErrorRingbuffer", "ERRORS", "HttpMetrics", "HTTP_METRICS", "BreadcrumbTracker",
    "BREADCRUMBS", "SpanContext", "parse_traceparent", "start_server_span",
    "current_span", "FinishedSpan", "OtlpSpanExporter", "encode_otlp_spans",
    "span_exporter", "route_template", "observability_snapshot", "prom_metrics",
    "ObservabilityMiddleware", "OVERFLOW_LABEL", "UNMATCHED_ROUTE",
]
