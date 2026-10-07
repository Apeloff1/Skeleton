"""Regression contracts for kernel EventBus integrity behavior."""

from skeleton.kernel.primitives import DomainEvent, EventBus


def test_eventbus_trace_keeps_correlation_context():
    bus = EventBus()
    event = DomainEvent(
        topic="runtime.test",
        payload={"value": 1},
        correlation_id="corr-001",
    )

    bus.publish(event)

    assert bus.trace("corr-001") == [event]


def test_eventbus_replay_filters_topics():
    bus = EventBus()
    bus.publish(DomainEvent(topic="kernel.alpha"))
    bus.publish(DomainEvent(topic="runtime.beta"))

    assert [e.topic for e in bus.replay("kernel.*")] == ["kernel.alpha"]
