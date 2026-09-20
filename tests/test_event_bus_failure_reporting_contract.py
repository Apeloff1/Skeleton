"""Regression coverage for EventBus failure isolation contract.

These tests document the current safe-dispatch behaviour while preparing the
kernel for optional diagnostic reporting.
"""

from skeleton.kernel.primitives import DomainEvent, EventBus


def test_event_bus_keeps_publishing_after_subscriber_failure():
    bus = EventBus()
    received = []

    def failing_handler(_event):
        raise RuntimeError("subscriber failed")

    def healthy_handler(event):
        received.append(event.event_id)

    bus.subscribe("kernel.*", failing_handler)
    bus.subscribe("kernel.*", healthy_handler)

    event = bus.publish(DomainEvent(topic="kernel.test"))

    assert received == [event.event_id]
    assert bus.stats()["published"] == 1


def test_event_bus_trace_preserves_correlation_context():
    bus = EventBus()

    event = bus.emit(
        "kernel.test",
        {"request_id": "req-1"},
    )

    traced = bus.trace("req-1")

    assert traced == [event]
    assert event.correlation_id == "req-1"
