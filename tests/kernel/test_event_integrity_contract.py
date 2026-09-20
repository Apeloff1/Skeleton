"""Regression contracts for kernel event integrity helpers."""

from __future__ import annotations

from skeleton.kernel.event_diagnostics import EventDiagnostics
from skeleton.kernel.event_integrity import EventIntegrityIndex, event_fingerprint
from skeleton.kernel.events import EventBus


def test_equivalent_events_have_stable_fingerprints() -> None:
    bus = EventBus()
    first = bus.emit("kernel.test", {"b": 2, "a": 1})
    second = bus.emit("kernel.test", {"a": 1, "b": 2})

    assert event_fingerprint(first) == event_fingerprint(second)


def test_integrity_index_detects_duplicate_logical_events() -> None:
    bus = EventBus()
    event = bus.emit("kernel.test", {"value": 1})
    duplicate = bus.emit("kernel.test", {"value": 1})

    index = EventIntegrityIndex()

    assert index.observe(event) is True
    assert index.observe(duplicate) is False
    assert index.size() == 1


def test_diagnostics_reports_duplicate_state() -> None:
    bus = EventBus()
    diagnostics = EventDiagnostics()

    first = bus.emit("kernel.test", {"value": 3})
    second = bus.emit("kernel.test", {"value": 3})

    assert diagnostics.inspect(first).duplicate is False
    assert diagnostics.inspect(second).duplicate is True
