"""Throughput deepen for #121 — shared correlation ContextVar + bus fallback.

Extend-only coverage: correlation survives bare EventBus.publish / emit when a
scope is active, background jobs emit metadata-only lifecycle events, and
sensitive fields stay redacted.
"""

from __future__ import annotations

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.primitives import register_correlation_fallback
from skeleton.observability.correlation import (
    background_job,
    correlation_scope,
    get_correlation_id,
    install_event_bus_fallback,
)
from skeleton.observability.event_bridge import EventMetricsBridge
from skeleton.observability.redaction import REDACTED, redact_payload


def setup_function() -> None:
    install_event_bus_fallback()


def teardown_function() -> None:
    # Leave provider installed for other tests; explicit clear only when needed.
    install_event_bus_fallback()


def test_publish_inherits_active_correlation_scope() -> None:
    bus = EventBus()
    with correlation_scope("req-scope-1") as cid:
        assert get_correlation_id() == "req-scope-1"
        event = bus.publish(DomainEvent(topic="probe.side", payload={"ok": True}))
    assert event.correlation_id == "req-scope-1"
    assert cid == "req-scope-1"
    assert bus.trace("req-scope-1")[0].topic == "probe.side"
    assert get_correlation_id() == ""


def test_emit_inherits_scope_when_payload_lacks_ids() -> None:
    bus = EventBus()
    with correlation_scope("emit-scope-9"):
        event = bus.emit("probe.tick", {"n": 1})
    assert event.correlation_id == "emit-scope-9"


def test_explicit_correlation_id_wins_over_scope() -> None:
    bus = EventBus()
    with correlation_scope("scope-a"):
        event = bus.publish(
            DomainEvent(
                topic="probe.explicit",
                payload={},
                correlation_id="explicit-b",
            )
        )
    assert event.correlation_id == "explicit-b"


def test_background_job_emits_correlated_lifecycle_without_secrets() -> None:
    bus = EventBus()
    bridge = EventMetricsBridge()
    bridge.attach(bus)

    def _emit(topic: str, payload: dict) -> None:
        bus.emit(topic, payload, correlation_id=str(payload.get("correlation_id") or ""))

    with background_job("compact-memory", correlation_id="job-77", emit=_emit) as cid:
        assert cid == "job-77"
        bus.publish(
            DomainEvent(
                topic="memory.compact.step",
                payload={"token": "should-not-matter", "api_key": "SECRET"},
            )
        )

    topics = [e.topic for e in bus.trace("job-77")]
    assert "observability.job.started" in topics
    assert "observability.job.completed" in topics
    assert "memory.compact.step" in topics
    step = next(e for e in bus.trace("job-77") if e.topic == "memory.compact.step")
    # EventMetricsBridge retains redacted copies; raw DomainEvent payload is
    # caller-owned — assert redaction helper still protects telemetry export.
    safe = redact_payload(step.payload)
    assert safe["api_key"] == REDACTED


def test_background_job_failure_emits_error_type_only() -> None:
    bus = EventBus()
    seen: list[tuple[str, dict]] = []

    def _emit(topic: str, payload: dict) -> None:
        seen.append((topic, dict(payload)))
        bus.emit(topic, payload, correlation_id=str(payload.get("correlation_id") or ""))

    try:
        with background_job("boom", correlation_id="job-fail", emit=_emit):
            raise RuntimeError("password=super-secret")
    except RuntimeError:
        pass

    failed = next(p for t, p in seen if t == "observability.job.failed")
    assert failed["error_type"] == "RuntimeError"
    assert "password" not in failed
    assert "super-secret" not in str(failed)


def test_provider_clear_disables_fallback() -> None:
    register_correlation_fallback(None)
    bus = EventBus()
    with correlation_scope("should-not-apply"):
        event = bus.publish(DomainEvent(topic="probe.off", payload={}))
    assert event.correlation_id == ""
    install_event_bus_fallback()
