"""Focused regressions for bounded event replay and causal reconstruction."""

from __future__ import annotations

import pytest

from skeleton.kernel.causality import CausalGraph, CausalGraphError
from skeleton.kernel.events import DomainEvent, EventBus


def _chain(bus: EventBus, length: int) -> list[DomainEvent]:
    root = bus.emit("run.started", {"run_id": "r-1"})
    events = [root]
    for index in range(1, length):
        child = events[-1].derive(f"run.stage.{index}", {"index": index})
        bus.publish(child)
        events.append(child)
    return events


def test_event_bus_replay_is_bounded_and_traceable() -> None:
    bus = EventBus(replay_capacity=3)
    first = bus.emit("run.0", {}, correlation_id="corr-a")
    for index in range(1, 4):
        bus.publish(first.derive(f"run.{index}", {"index": index}))

    retained = bus.replay("*")
    assert len(retained) == 3
    assert [event.topic for event in retained] == ["run.1", "run.2", "run.3"]
    assert len(bus.trace("corr-a")) == 3


def test_derive_preserves_correlation_and_sets_causation() -> None:
    parent = DomainEvent(topic="parent", correlation_id="corr-1")
    child = parent.derive("child", {"ok": True})

    assert child.correlation_id == "corr-1"
    assert child.causation_id == parent.event_id
    assert child.event_id != parent.event_id


def test_out_of_order_ingestion_grafts_late_parent() -> None:
    bus = EventBus()
    parent = bus.emit("parent", {}, correlation_id="corr")
    child = parent.derive("child", {})

    graph = CausalGraph()
    graph.add(child)
    assert graph.node(child.event_id).is_root
    assert graph.node(child.event_id).depth == 0

    graph.add(parent)
    resolved = graph.node(child.event_id)
    assert resolved.parent_id == parent.event_id
    assert resolved.depth == 1
    assert graph.fan_out(parent.event_id) == 1


def test_missing_parent_remains_safe_root() -> None:
    orphan = DomainEvent(
        topic="orphan",
        correlation_id="corr",
        causation_id="not-retained",
    )
    graph = CausalGraph()
    graph.add(orphan)

    node = graph.node(orphan.event_id)
    assert node.is_root
    assert node.depth == 0
    assert graph.lineage(orphan.event_id).event_ids == (orphan.event_id,)


def test_from_bus_lineage_and_walk_are_ordered() -> None:
    bus = EventBus()
    events = _chain(bus, 5)
    graph = CausalGraph.from_bus(bus, events[0].correlation_id)

    path = graph.lineage(events[-1].event_id)
    assert path.event_ids == tuple(event.event_id for event in events)
    assert path.topics[0] == "run.started"
    assert path.elapsed_seconds >= 0.0
    assert [node.event.event_id for node in graph.walk()] == [event.event_id for event in events]
    assert graph.stats()["max_depth"] == 4


def test_cycle_detection_and_lineage_fail_closed() -> None:
    a = DomainEvent(topic="a", event_id="a", causation_id="b", correlation_id="corr")
    b = DomainEvent(topic="b", event_id="b", causation_id="a", correlation_id="corr")
    graph = CausalGraph()
    graph.add_all([a, b])

    assert graph.cycles()
    with pytest.raises(CausalGraphError):
        graph.lineage("a")


def test_unknown_event_raises_typed_error() -> None:
    graph = CausalGraph()
    with pytest.raises(CausalGraphError):
        graph.node("missing")
