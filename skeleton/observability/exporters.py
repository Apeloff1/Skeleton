"""Observability exporters — OTLP-ish wire encoders for metrics and spans.

In-memory registries are useful during dev; production ships metrics+traces
to a collector. Exporters serialize registries into compact JSON payloads
callers can POST to any OTLP-compatible endpoint you wire via the sender.

- :class:`MetricsExporter` — encode a MetricsRegistry snapshot
- :class:`TraceExporter` — encode a list of spans
- both expose ``push()`` that accepts a sender callable
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.trace import Span, SpanStatus


class ExporterError:
    pass


class MetricsExporter:
    """Encode registry snapshot into a wire-friendly JSON payload."""

    def __init__(self, sink: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self._sink = sink

    def encode(self, registry: Any) -> Dict[str, Any]:
        snapshot = registry.snapshot() if hasattr(registry, "snapshot") else {}
        return {
            "kind": "metrics",
            "payload": snapshot,
        }

    def push(self, registry: Any) -> None:
        if self._sink is None:
            return
        self._sink(self.encode(registry))


class TraceExporter:
    """Encode spans into compact OTLP-ish records."""

    def __init__(self, sink: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self._sink = sink

    def encode_many(self, spans: List[Span]) -> Dict[str, Any]:
        return {
            "kind": "traces",
            "payload": [
                {
                    "name": span.name,
                    "trace_id": span.context.trace_id,
                    "span_id": span.context.span_id,
                    "parent_span_id": span.context.parent_span_id,
                    "status": span.status.value,
                    "duration_ms": round(
                        ((span.finished_at or 0.0) - span.started_at) * 1000.0,
                        3,
                    ),
                    "attributes": span.attributes,
                }
                for span in spans
            ],
        }

    def push(self, spans: List[Span]) -> None:
        if self._sink is None:
            return
        self._sink(self.encode_many(spans))
