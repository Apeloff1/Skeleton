"""Regression coverage for deterministic event integrity helpers."""

from skeleton.kernel.event_integrity import EventIntegrityIndex, event_fingerprint
from skeleton.kernel.primitives import DomainEvent


def test_event_fingerprint_is_stable_for_equivalent_events():
    first = DomainEvent(topic="kernel.test", payload={"b": 2, "a": 1}, correlation_id="c1")
    second = DomainEvent(topic="kernel.test", payload={"a": 1, "b": 2}, correlation_id="c1")

    assert event_fingerprint(first) == event_fingerprint(second)


def test_integrity_index_detects_duplicate_logical_events():
    index = EventIntegrityIndex()
    event = DomainEvent(topic="kernel.test", payload={"x": 1})

    assert index.observe(event) is True
    assert index.observe(event) is False
    assert index.size() == 1
