"""Contract tests for canonical observability helpers."""

import json

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.observability import (
    EventMetricsBridge,
    HealthRegistry,
    MetricsRegistry,
    StructuredLogger,
    Tracer,
    probe,
    redact_payload,
)


def test_health_liveness_and_readiness_redact_probe_failures() -> None:
    health = HealthRegistry()

    @probe("ok")
    def ok():
        return {"ok": True, "detail": "fine"}

    @probe("boom")
    def boom():
        raise RuntimeError("token=super-secret")

    health.add_liveness(ok)
    health.add_readiness(ok)
    health.add_readiness(boom)

    assert health.liveness()["status"] == "up"
    readiness = health.readiness()
    assert readiness["status"] == "down"
    assert readiness["probes"][1]["detail"] == "RuntimeError"
    assert "super-secret" not in str(readiness)


def test_metrics_registry_counter_and_rollup() -> None:
    registry = MetricsRegistry()
    registry.counter("http.requests")
    registry.counter("http.requests", value=2)

    assert registry.get_counter("http.requests") == 3
    assert registry.rollup()["counters"]["http.requests"] == 3


def test_event_bus_emit_preserves_and_infers_correlation_id() -> None:
    bus = EventBus()
    events: list[DomainEvent] = []
    bus.subscribe("runtime.*", events.append)

    bus.emit(
        "runtime.run.started",
        {"run_id": "run-1"},
        correlation_id="request-123",
    )
    bus.emit("runtime.agent.assigned", {"task_id": "task-9"})

    assert len(events) == 2
    assert events[0].correlation_id == "request-123"
    assert events[0].payload == {"run_id": "run-1"}
    assert events[1].correlation_id == "task-9"


def test_event_metrics_bridge_redacts_and_collects_baseline_metrics() -> None:
    bus = EventBus()
    bridge = EventMetricsBridge(max_events=4)
    bridge.attach(bus)
    source = {
        "status": 500,
        "duration_ms": 20,
        "queue_depth": 3,
        "memory_bytes": 1024,
        "authorization": "Bearer abc.def",
        "error": "provider failed api-key=very-secret",
    }

    bus.emit("api.request.failed", source, correlation_id="req-1")
    bus.emit(
        "runtime.tool.retry",
        {"retrying": True, "duration_ms": 10},
        correlation_id="req-1",
    )
    bus.emit("api.rate_limit.rejected", {"status": 429}, correlation_id="req-2")

    snapshot = bridge.snapshot()
    first = snapshot["events"][0]
    assert first["correlation_id"] == "req-1"
    assert first["payload"]["authorization"] == "[REDACTED]"
    assert first["payload"]["error"] == "provider failed api-key=[REDACTED]"
    assert source["authorization"] == "Bearer abc.def"

    counters = snapshot["metrics"]["counters"]
    assert counters["observability.events_total"] == 3
    assert counters["observability.failures_total"] == 1
    assert counters["observability.retries_total"] == 1
    assert counters["observability.rate_limits_total"] == 1
    assert snapshot["metrics"]["gauges"] == {
        "observability.queue_depth": 3.0,
        "observability.memory_bytes": 1024.0,
    }


def test_structured_logger_redacts_messages_and_context() -> None:
    lines: list[str] = []
    logger = StructuredLogger(lines.append).bind(password="hidden", request_id="req-7")

    event = logger.error(
        "provider failed token=very-secret",
        authorization="Bearer abc.def",
        safe="visible",
    )

    assert event.message == "provider failed token=[REDACTED]"
    assert event.context["password"] == "[REDACTED]"
    assert event.context["authorization"] == "[REDACTED]"
    assert event.context["request_id"] == "req-7"
    assert "very-secret" not in lines[0]
    assert json.loads(lines[0])["context"]["safe"] == "visible"


def test_tracer_failure_never_persists_exception_message() -> None:
    tracer = Tracer("test-service")

    try:
        with tracer("tool.call", api_key="secret-value"):
            raise RuntimeError("password=leaked-value")
    except RuntimeError:
        pass

    span = tracer.exporter.query(limit=1)[0]
    rendered = span.to_dict()
    assert rendered["attributes"]["api_key"] == "[REDACTED]"
    assert rendered["attributes"]["error.type"] == "RuntimeError"
    assert rendered["attributes"]["error.message"] == "RuntimeError"
    assert "leaked-value" not in str(rendered)
    assert "secret-value" not in str(rendered)


def test_redaction_depth_is_bounded() -> None:
    value = {"a": {"b": {"c": "deep"}}}

    assert redact_payload(value, max_depth=2) == {"a": {"b": "[TRUNCATED]"}}
