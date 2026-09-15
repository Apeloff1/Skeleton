"""Tests for skeleton.kernel.causality — the causal graph layer."""

from __future__ import annotations

import pytest

from skeleton.kernel.causality import CausalGraph, CausalGraphError
from skeleton.kernel.events import DomainEvent, EventBus


def make_chain(bus: EventBus, n: int, topic_prefix: str = "pipeline.npc") -> list[DomainEvent]:
    """Publish a linear causal chain of n events and return them in order."""
    events: list[DomainEvent] = []
    parent: DomainEvent | None = None
    for i in range(n):
        if parent is None:
            ev = bus.emit(f"{topic_prefix}.stage{i}", {"i": i})
        else:
            ev = parent.derive(f"{topic_prefix}.stage{i}", {"i": i})
            bus.publish(ev)
        events.append(ev)
        parent = ev
    return events


class TestIngestion:
    def test_add_is_idempotent(self):
        bus = EventBus()
        (ev,) = make_chain(bus, 1)
        g = CausalGraph()
        g.add(ev)
        g.add(ev)
        assert g.stats()["events"] == 1

    def test_out_of_order_ingestion_grafts_children(self):
        bus = EventBus()
        chain = make_chain(bus, 3)
        g = CausalGraph()
        for ev in reversed(chain):  # children first
            g.add(ev)
        assert g.stats()["edges"] == 2
        assert len(g.roots()) == 1

    def test_from_bus_scopes_by_correlation_id(self):
        bus = EventBus()
        chain_a = make_chain(bus, 2, "pipeline.npc")
        make_chain(bus, 4, "pipeline.animation")
        g = CausalGraph.from_bus(bus, chain_a[0].correlation_id)
        assert g.stats()["events"] == 2


class TestQueries:
    def test_lineage_orders_root_to_leaf(self):
        bus = EventBus()
        chain = make_chain(bus, 4)
        g = CausalGraph.from_bus(bus)
        path = g.lineage(chain[-1].event_id)
        assert path.event_ids == tuple(e.event_id for e in chain)
        assert len(path) == 4
        assert path.elapsed_seconds >= 0.0

    def test_fan_out_counts_direct_children(self):
        bus = EventBus()
        root = bus.emit("run.started", {})
        for i in range(3):
            bus.publish(root.derive(f"agent.{i}.spawned", {"i": i}))
        g = CausalGraph.from_bus(bus)
        assert g.fan_out(root.event_id) == 3
        assert len(g.leaves()) == 3

    def test_unknown_event_raises(self):
        g = CausalGraph()
        with pytest.raises(CausalGraphError):
            g.node("nope")

    def test_cycles_detects_loop(self):
        bus = EventBus()
        a = bus.emit("x.a", {})
        b = bus.publish(a.derive("x.b", {})) or a.derive("x.b", {})
        # hand-craft a cycle: a caused b, b "caused" a (re-ingested under new id)
        g = CausalGraph()
        g.add(a)
        g.add(b)
        c = DomainEvent(topic="x.c", payload={}, causation_id=b.event_id,
                        correlation_id=a.correlation_id)
        d = DomainEvent(topic="x.d", payload={}, causation_id=c.event_id,
                        correlation_id=a.correlation_id)
        e = DomainEvent(topic="x.e", payload={}, causation_id=d.event_id,
                        correlation_id=a.correlation_id)
        g.add_all([c, d, e])
        assert g.cycles() == []  # sane chain


class TestTraversal:
    def test_walk_visits_every_event_once(self):
        bus = EventBus()
        root = bus.emit("run.started", {})
        kids = [root.derive(f"agent.{i}.spawned", {}) for i in range(3)]
        for k in kids:
            bus.publish(k)
            bus.publish(k.derive(f"agent.done", {}))
        g = CausalGraph.from_bus(bus)
        visited = list(g.walk())
        assert len(visited) == 7
        assert visited[0].event.event_id == root.event_id

    def test_stats_shape(self):
        bus = EventBus()
        make_chain(bus, 5)
        g = CausalGraph.from_bus(bus)
        s = g.stats()
        assert s["events"] == 5
        assert s["edges"] == 4
        assert s["roots"] == 1
        assert s["leaves"] == 1
        assert s["max_depth"] == 4
        assert s["cycles"] == 0
