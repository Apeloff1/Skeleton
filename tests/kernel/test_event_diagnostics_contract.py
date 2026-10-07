"""Regression tests for kernel event diagnostics contracts."""

from __future__ import annotations

from skeleton.kernel.event_diagnostics import EventDiagnostics
from skeleton.kernel.event_integrity import EventIntegrityIndex
from skeleton.kernel.events import EventBus


def test_diagnostics_reports_first_and_duplicate_events() -> None:
    bus = EventBus()
    event = bus.emit("kernel.sample", {"value": 1})
    diagnostics = EventDiagnostics(EventIntegrityIndex())

    first = diagnostics.inspect(event)
    second = diagnostics.inspect(event)

    assert first.duplicate is False
    assert second.duplicate is True
    assert first.fingerprint == second.fingerprint


def test_diagnostics_seen_count_tracks_unique_logical_events() -> None:
    bus = EventBus()
    diagnostics = EventDiagnostics()

    first = bus.emit("kernel.sample", {"value": 1})
    second = bus.emit("kernel.other", {"value": 2})

    diagnostics.inspect(first)
    diagnostics.inspect(second)

    assert diagnostics.seen_count() == 2
