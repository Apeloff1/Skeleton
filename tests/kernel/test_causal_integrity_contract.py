"""Cross-check causal lineage and event integrity contracts."""

from __future__ import annotations

from skeleton.kernel.event_diagnostics import EventDiagnostics
from skeleton.kernel.events import EventBus
from skeleton.kernel.causality import CausalGraph


def test_causal_chain_keeps_integrity_identity():
    bus = EventBus()
    root = bus.emit("pipeline.start", {"stage": 0})
    child = root.derive("pipeline.child", {"stage": 1})
    bus.publish(child)

    diagnostics = EventDiagnostics()
    first = diagnostics.inspect(root)
    second = diagnostics.inspect(child)

    assert first.duplicate is False
    assert second.duplicate is False
    assert first.fingerprint != second.fingerprint

    graph = CausalGraph.from_bus(bus)
    assert graph.stats()["events"] == 2
    assert graph.stats()["edges"] == 1


def test_repeated_inspection_detects_duplicate_logical_event():
    bus = EventBus()
    event = bus.emit("pipeline.once", {"value": 1})

    diagnostics = EventDiagnostics()
    assert diagnostics.inspect(event).duplicate is False
    assert diagnostics.inspect(event).duplicate is True
