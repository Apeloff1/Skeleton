"""Per-gate metrics and trace spans for the Pack F gate plane.

Built on Internal Systems' observability libraries — no new metrics or
tracing backend:

* :class:`skeleton.observability.metrics.MetricsCollector` for counters,
  gauges and histograms;
* :class:`skeleton.observability.tracing.Tracer` for spans (redaction of
  attributes/events is applied by the tracer itself).

:class:`GateTelemetry` exposes one adapter per gate:

=====================  ======================================================
gate                   hook
=====================  ======================================================
s2s auth               :meth:`GateTelemetry.s2s_hook` (``S2SAuthGate.add_hook``)
pipeline               :class:`TelemetryStage` (kind ``telemetry``)
circuit breakers       :meth:`GateTelemetry.breaker_listener`
backpressure           :meth:`GateTelemetry.backpressure_listener`
=====================  ======================================================

Label cardinality is bounded by design: labels carry route/policy *names*,
outcomes and status classes — never raw paths, tenant ids or token
material. Every hook swallows its own exceptions; telemetry can never
change a gate verdict.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Dict, Mapping, Optional, Tuple

from skeleton.gate_plane.pipeline.core import CallContext, Handler, PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.errors import PipelineError
from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.observability.metrics import MetricsCollector
from skeleton.observability.tracing import Span, Tracer

M_S2S_DECISIONS = "gate_plane.s2s.decisions"
M_S2S_TOKEN_ERRORS = "gate_plane.s2s.token_errors"
M_PIPE_REQUESTS = "gate_plane.pipeline.requests"
M_PIPE_ERRORS = "gate_plane.pipeline.errors"
M_PIPE_LATENCY_MS = "gate_plane.pipeline.latency_ms"
M_PIPE_ATTEMPTS = "gate_plane.pipeline.attempts"
M_PIPE_RETRIES = "gate_plane.pipeline.retries"
M_PIPE_IN_FLIGHT = "gate_plane.pipeline.in_flight"
M_BREAKER_TRANSITIONS = "gate_plane.breaker.transitions"
M_BREAKER_STATE = "gate_plane.breaker.state"
M_BP_DECISIONS = "gate_plane.backpressure.decisions"
M_BP_LOAD = "gate_plane.backpressure.load"

SPAN_PIPELINE = "gate_plane.pipeline"
SPAN_S2S = "gate_plane.s2s.decide"

BREAKER_STATE_VALUE = {"closed": 0.0, "half_open": 1.0, "open": 2.0}

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_LABEL_SAFE = re.compile(r"[^A-Za-z0-9_.:\-]")
MAX_LABEL_LEN = 64


def safe_label(value: Any) -> str:
    """Normalise a label value: bounded length, conservative charset."""
    text = "none" if value is None else str(value)
    text = _LABEL_SAFE.sub("_", text)[:MAX_LABEL_LEN]
    return text or "none"


def status_class(status: int) -> str:
    return f"{int(status) // 100}xx" if 100 <= int(status) <= 599 else "other"


def parse_traceparent(value: Optional[str]) -> Optional[Tuple[str, str]]:
    """Parse a W3C ``traceparent``; returns ``(trace_id, parent_span_id)`` or None."""
    if not value:
        return None
    m = _TRACEPARENT_RE.match(value.strip().lower())
    if not m:
        return None
    trace_id, span_id, _flags = m.groups()
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return trace_id, span_id


def format_traceparent(span: Span) -> str:
    trace = (span.trace_id or "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", trace):
        trace = (trace.encode("utf-8").hex() + "0" * 32)[:32]
    sid = (span.span_id or "")[:16].ljust(16, "0")
    return f"00-{trace}-{sid}-01"


class GateTelemetry:
    """Metrics + traces for every gate in the plane."""

    def __init__(
        self,
        *,
        metrics: Optional[MetricsCollector] = None,
        tracer: Optional[Tracer] = None,
        clock: Optional[Clock] = None,
        service_name: str = "gate_plane",
    ) -> None:
        self.metrics = metrics or MetricsCollector()
        self.tracer = tracer or Tracer(service_name)
        self.clock = clock or system_clock()
        self._in_flight: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._dropped = 0

    # -- guarded emit ---------------------------------------------------------------
    def _safe(self, fn, *args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - telemetry never changes a verdict
            with self._lock:
                self._dropped += 1

    def _inc(self, name: str, labels: Mapping[str, Any], value: float = 1.0) -> None:
        self._safe(self.metrics.increment, name, value, {k: safe_label(v) for k, v in labels.items()})

    def _gauge(self, name: str, value: float, labels: Mapping[str, Any]) -> None:
        self._safe(self.metrics.gauge, name, value, {k: safe_label(v) for k, v in labels.items()})

    def _hist(self, name: str, value: float, labels: Mapping[str, Any]) -> None:
        self._safe(self.metrics.histogram, name, value, {k: safe_label(v) for k, v in labels.items()})

    # -- s2s gate -------------------------------------------------------------------
    def s2s_hook(self, method: str, path: str, decision: Any) -> None:
        """``S2SAuthGate.add_hook(telemetry.s2s_hook)``. ``path`` is never a label."""
        try:
            outcome = getattr(getattr(decision, "outcome", None), "value", "unknown")
            policy = getattr(decision, "policy", None) or "none"
            principal = getattr(decision, "principal", None)
            service = getattr(principal, "service", None) if principal is not None else None
            if principal is not None and getattr(principal, "anonymous", False):
                service = "anonymous"
            labels = {"outcome": outcome, "policy": policy, "method": (method or "GET").upper()}
            self._inc(M_S2S_DECISIONS, labels)
            token_error = getattr(decision, "token_error", None)
            if token_error is not None:
                self._inc(M_S2S_TOKEN_ERRORS, {"code": getattr(token_error, "value", token_error)})
            span = self.tracer.start_span(
                SPAN_S2S,
                **{
                    "gate.outcome": outcome,
                    "gate.policy": policy,
                    "gate.method": labels["method"],
                    "s2s.service": service or "none",
                    "http.status": getattr(decision, "http_status", None),
                },
            )
            span.ended_at = span.started_at
            if outcome not in ("allow", "open_bypass"):
                span.status = "ERROR"
                span.set_attribute("gate.reason", getattr(decision, "reason", ""))
            self.tracer.exporter.export(span)
        except Exception:  # noqa: BLE001
            with self._lock:
                self._dropped += 1

    # -- breakers -------------------------------------------------------------------
    def breaker_listener(self, name: str, old: Any, new: Any) -> None:
        old_v = getattr(old, "value", str(old))
        new_v = getattr(new, "value", str(new))
        self._inc(M_BREAKER_TRANSITIONS, {"breaker": name, "from": old_v, "to": new_v})
        self._gauge(M_BREAKER_STATE, BREAKER_STATE_VALUE.get(new_v, -1.0), {"breaker": name})

    # -- backpressure ---------------------------------------------------------------
    def backpressure_listener(self, request: Any, decision: Any) -> None:
        action = getattr(getattr(decision, "action", None), "value", "unknown")
        source = getattr(decision, "source", None) or "none"
        self._inc(M_BP_DECISIONS, {"action": action, "reason": getattr(decision, "reason", "none"), "source": source})
        view = getattr(decision, "view", None)
        if view is not None:
            self._gauge(M_BP_LOAD, float(view.load), {"source": source})

    # -- pipeline -------------------------------------------------------------------
    def _track_in_flight(self, route: str, delta: int) -> None:
        with self._lock:
            n = self._in_flight.get(route, 0) + delta
            self._in_flight[route] = max(0, n)
            value = self._in_flight[route]
        self._gauge(M_PIPE_IN_FLIGHT, float(value), {"route": route})

    def stage(self, *, name: str = "telemetry") -> "TelemetryStage":
        return TelemetryStage(self, name=name)

    def stage_factory(self):
        """``PipelineRouter(stage_factories={"telemetry": telemetry.stage_factory()})``."""

        def factory(_route: Any) -> TelemetryStage:
            return TelemetryStage(self)

        return factory

    # -- wiring ---------------------------------------------------------------------
    def attach(
        self,
        *,
        s2s_gate: Any = None,
        breakers: Any = None,
        backpressure: Any = None,
    ) -> "GateTelemetry":
        """Register hooks on whichever gates are supplied. Returns self."""
        if s2s_gate is not None:
            s2s_gate.add_hook(self.s2s_hook)
        if breakers is not None:
            breakers.add_listener(self.breaker_listener)
        if backpressure is not None:
            backpressure.add_listener(self.backpressure_listener)
        return self

    def snapshot(self) -> Dict[str, Any]:
        snap = self.metrics.snapshot()
        with self._lock:
            snap = dict(snap)
            snap["telemetry_dropped"] = self._dropped
        return snap

    def counter(self, name: str, **labels: Any) -> float:
        key = MetricsCollector._key(name, {k: safe_label(v) for k, v in labels.items()} or None)
        return float(self.metrics.snapshot().get("counters", {}).get(key, 0.0))

    def spans(self, name: Optional[str] = None, limit: int = 100):
        return self.tracer.exporter.query(name=name, limit=limit)

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped


class TelemetryStage:
    """Outermost pipeline stage: one span + request/latency/attempt metrics per call.

    Continues an inbound W3C ``traceparent`` when present and publishes the
    outbound one as ``ctx.attrs['traceparent']`` for the handler to forward.
    Pipeline events (retries, breaker rejects, sheds) become span events.
    """

    kind = "telemetry"

    def __init__(self, telemetry: GateTelemetry, *, name: str = "telemetry") -> None:
        self.name = name
        self.telemetry = telemetry

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        t = self.telemetry
        route = safe_label(ctx.route)
        upstream = safe_label(ctx.upstream)
        inbound = None
        for k, v in request.headers.items():
            if str(k).lower() == "traceparent":
                inbound = parse_traceparent(str(v))
                break
        attrs: Dict[str, Any] = {
            "gate.route": route,
            "gate.upstream": upstream,
            "gate.method": request.verb,
            "gate.priority": request.priority,
        }
        if inbound is not None:
            attrs["trace_id"] = inbound[0]
            attrs["gate.parent_span"] = inbound[1]
        started = ctx.clock.monotonic()
        t._track_in_flight(route, +1)
        labels = {"route": route, "method": request.verb}
        try:
            with t.tracer(SPAN_PIPELINE, **attrs) as span:
                ctx.attrs["traceparent"] = format_traceparent(span)
                ctx.attrs["trace_id"] = span.trace_id
                try:
                    response = nxt(request, ctx)
                except Exception as exc:
                    reason = exc.reason if isinstance(exc, PipelineError) else type(exc).__name__
                    t._inc(M_PIPE_ERRORS, {**labels, "error": reason})
                    status = exc.status if isinstance(exc, PipelineError) else 500
                    t._inc(M_PIPE_REQUESTS, {**labels, "status_class": status_class(status)})
                    self._finish_span(span, ctx, status)
                    raise
                t._inc(M_PIPE_REQUESTS, {**labels, "status_class": status_class(response.status)})
                self._finish_span(span, ctx, response.status)
                if response.status >= 500:
                    span.status = "ERROR"
                return response
        finally:
            elapsed_ms = max(0.0, (ctx.clock.monotonic() - started) * 1000.0)
            t._hist(M_PIPE_LATENCY_MS, elapsed_ms, {"route": route})
            attempts = int(ctx.attrs.get("attempts", 1 if ctx.attempt else 0) or 0)
            t._hist(M_PIPE_ATTEMPTS, float(attempts), {"route": route})
            retries = sum(1 for e in ctx.events if e.get("event") == "retry")
            if retries:
                t._inc(M_PIPE_RETRIES, {"route": route}, float(retries))
            t._track_in_flight(route, -1)

    def _finish_span(self, span: Span, ctx: CallContext, status: int) -> None:
        try:
            span.set_attribute("http.status", int(status))
            span.set_attribute("gate.attempts", int(ctx.attrs.get("attempts", 1)))
            bp = ctx.attrs.get("backpressure")
            if isinstance(bp, dict):
                span.set_attribute("gate.backpressure", bp.get("action"))
            for ev in ctx.events[-32:]:
                data = {k: v for k, v in ev.items() if k not in ("event", "t")}
                span.add_event(str(ev.get("event", "event")), **data)
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "BREAKER_STATE_VALUE",
    "GateTelemetry",
    "M_BP_DECISIONS",
    "M_BP_LOAD",
    "M_BREAKER_STATE",
    "M_BREAKER_TRANSITIONS",
    "M_PIPE_ATTEMPTS",
    "M_PIPE_ERRORS",
    "M_PIPE_IN_FLIGHT",
    "M_PIPE_LATENCY_MS",
    "M_PIPE_REQUESTS",
    "M_PIPE_RETRIES",
    "M_S2S_DECISIONS",
    "M_S2S_TOKEN_ERRORS",
    "SPAN_PIPELINE",
    "SPAN_S2S",
    "TelemetryStage",
    "format_traceparent",
    "parse_traceparent",
    "safe_label",
    "status_class",
]
