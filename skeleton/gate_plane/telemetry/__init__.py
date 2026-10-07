"""Pack F gate-plane telemetry: per-gate metrics and trace spans.

Thin adapters over Internal Systems' ``skeleton.observability`` metrics and
tracing libraries. No host side effects; no ``api/server.py`` changes.
"""

from __future__ import annotations

from skeleton.gate_plane.telemetry.gate_telemetry import (
    BREAKER_STATE_VALUE,
    M_BP_DECISIONS,
    M_BP_LOAD,
    M_BREAKER_STATE,
    M_BREAKER_TRANSITIONS,
    M_PIPE_ATTEMPTS,
    M_PIPE_ERRORS,
    M_PIPE_IN_FLIGHT,
    M_PIPE_LATENCY_MS,
    M_PIPE_REQUESTS,
    M_PIPE_RETRIES,
    M_S2S_DECISIONS,
    M_S2S_TOKEN_ERRORS,
    SPAN_PIPELINE,
    SPAN_S2S,
    GateTelemetry,
    TelemetryStage,
    format_traceparent,
    parse_traceparent,
    safe_label,
    status_class,
)

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
