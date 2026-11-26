"""Tests for skeleton.telemetry.planes (#121 per-plane tracing + metrics)."""

from __future__ import annotations

import pytest

from skeleton.observability.correlation import correlation_scope
from skeleton.telemetry import planes
from skeleton.telemetry.planes import PlaneTelemetry


def test_span_records_calls_latency_and_trace():
    t = PlaneTelemetry()
    with t.span("kernel", "dispatch", task="x") as span:
        assert span.name == "kernel.dispatch"
    s = t.summary("kernel", "dispatch")
    assert s["calls"] == 1.0
    assert s["errors"] == 0.0
    assert s["latency_ms"]["count"] == 1
    exported = t.exporter.query(name="kernel.dispatch")
    assert exported and exported[0].attributes["plane"] == "kernel"


def test_error_counted_and_span_failed():
    t = PlaneTelemetry()
    with pytest.raises(RuntimeError):
        with t.span("agents", "act"):
            raise RuntimeError("boom")
    assert t.summary("agents", "act")["errors"] == 1.0
    assert t.exporter.query(name="agents.act")[0].status == "ERROR"


def test_correlation_follows_api_agent_kernel():
    t = PlaneTelemetry()
    with correlation_scope("req-121") as cid:
        with t.span("api", "request"):
            with t.span("agents", "plan"):
                with t.span("kernel", "dispatch"):
                    pass
    spans = t.traces(cid)
    assert [s["name"] for s in spans] == ["kernel.dispatch", "agents.plan", "api.request"]
    assert len({s["trace_id"] for s in spans}) == 1
    assert spans[0]["parent_id"] == spans[1]["span_id"]


def test_no_correlation_attribute_when_unset():
    t = PlaneTelemetry()
    with t.span("api", "health") as span:
        pass
    assert "correlation_id" not in span.attributes


def test_unknown_plane_rejected():
    with pytest.raises(ValueError):
        PlaneTelemetry().tracer("gpu")


def test_default_helpers_share_one_instance():
    planes.reset_default_plane_telemetry()
    try:
        with planes.kernel_span("tick"):
            pass
        with planes.agent_span("tick"):
            pass
        with planes.api_span("tick"):
            pass
        t = planes.default_plane_telemetry()
        for plane in planes.PLANES:
            assert t.summary(plane, "tick")["calls"] == 1.0
    finally:
        planes.reset_default_plane_telemetry()
